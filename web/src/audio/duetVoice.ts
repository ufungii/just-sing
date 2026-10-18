import { createMicGain } from './micGain';
import { roomLive, sendVoice, subscribeRoomLive, subscribeVoice, type VoiceSignal } from '../lib/rooms';
import type { TimedDuetSection } from '../lib/types';

export interface VoiceStatus {
  state: 'waiting' | 'connecting' | 'connected' | 'unavailable';
  rttMs?: number;
  bufferMs?: number;
}

/** Schedule privacy gates on the SAME audio clock as the instrumental, including practice ranges. */
export function scheduleVoiceGate(param: AudioParam, ctx: AudioContext, origin: number,
  sections: TimedDuetSection[], slot: number) {
  param.cancelScheduledValues(ctx.currentTime);
  param.setValueAtTime(0, ctx.currentTime);
  for (const section of sections) {
    if (section.slot !== slot || origin + section.end <= ctx.currentTime) continue;
    param.setValueAtTime(1, Math.max(ctx.currentTime, origin + section.start));
    param.setValueAtTime(0, origin + section.end);
  }
}

/** A small Opus packetization hint; browsers remain free to choose their actual packet size. */
export function voiceSdp(sdp: string): string {
  return sdp.split(/(?=m=)/).map((section) => section.startsWith('m=audio ')
    ? section.replace(/a=ptime:[^\r\n]*\r\n/g, '').trimEnd() + '\r\na=ptime:10\r\n'
    : section).join('');
}

/**
 * One peer across the online lobby and its duet. Only signaling traverses the room server. The source mic
 * remains untouched for scoring; an independent WebAudio stream sends silence outside our sections.
 * A second receive gate prevents remote audio playing during our own sections (even from a bad peer).
 */
export class DuetVoice {
  private pc: RTCPeerConnection | null = null;
  private peer: string | null = null;
  private session = crypto.randomUUID();
  private closed = false;
  private available = false;
  private queue: Promise<void> = Promise.resolve();
  private candidates: RTCIceCandidateInit[] = [];
  private remote: MediaStreamAudioSourceNode | null = null;
  private remotePlayback: HTMLAudioElement | null = null;
  private readonly micGain: ReturnType<typeof createMicGain>;
  private readonly source: MediaStreamAudioSourceNode;
  readonly sendGate: GainNode;
  readonly receiveGate: GainNode;
  private readonly muteGain: GainNode;
  private readonly volumeGain: GainNode;
  private readonly outgoing: MediaStreamAudioDestinationNode;
  private readonly unsubscribe: (() => void)[];
  private readonly timer: ReturnType<typeof setInterval>;
  private lastState: VoiceStatus['state'] = 'waiting';
  private failedAt = 0;
  private connectingAt = 0;
  private statsBusy = false;

  constructor(private readonly ctx: AudioContext, mic: MediaStream, output: AudioNode,
    private readonly roomId: string, private matchId: string | null, private readonly slot: number,
    private report: (status: VoiceStatus) => void, muted = false) {
    if (typeof RTCPeerConnection === 'undefined') throw new Error('WebRTC unavailable');
    this.source = ctx.createMediaStreamSource(mic);
    this.sendGate = ctx.createGain(); this.sendGate.gain.value = 0;
    this.muteGain = ctx.createGain(); this.muteGain.gain.value = muted ? 0 : 1;
    this.outgoing = ctx.createMediaStreamDestination();
    this.micGain = createMicGain(ctx);
    this.source.connect(this.micGain.node).connect(this.sendGate).connect(this.muteGain).connect(this.outgoing);
    for (const track of this.outgoing.stream.getAudioTracks()) track.contentHint = 'music';
    this.receiveGate = ctx.createGain(); this.receiveGate.gain.value = 0;
    this.volumeGain = ctx.createGain(); this.volumeGain.gain.value = 0.6;
    this.receiveGate.connect(this.volumeGain).connect(output);
    this.unsubscribe = [subscribeVoice((from, data) => {
      if (from === this.slot || data.match_id !== this.matchId || !this.available) return;
      // Serialize SDP and trickled candidates. A candidate may arrive before setRemoteDescription.
      const session = this.session;
      this.queue = this.queue.then(() => { if (this.session === session && data.match_id === this.matchId) return this.signal(data); })
        .catch(() => { if (this.session === session) this.fail(); });
    }), subscribeRoomLive(() => this.presence())];
    this.timer = setInterval(() => {
      if (!this.available) return;
      if (this.connectingAt && performance.now() - this.connectingAt > 15000 && !this.failedAt) this.fail();
      // Failed NAT traversal gets a fresh attempt, without restarting the song or scoring.
      if (this.failedAt && performance.now() - this.failedAt > 8000) this.reset();
      this.hello();
      void this.stats();
    }, 2000);
    this.presence();
  }

  setReporter(report: (status: VoiceStatus) => void) { this.report = report; this.status(this.lastState); }
  /** Reused by the instrumental so section gates share its exact audio clock. */
  get context() { return this.ctx; }
  setOutput(output: AudioNode) { this.volumeGain.disconnect(); this.volumeGain.connect(output); }

  private gate(open: boolean) {
    for (const node of [this.sendGate, this.receiveGate]) {
      node.gain.cancelScheduledValues(this.ctx.currentTime);
      node.gain.setValueAtTime(open ? 1 : 0, this.ctx.currentTime);
    }
  }

  setMuted(muted: boolean) { this.muteGain.gain.setValueAtTime(muted ? 0 : 1, this.ctx.currentTime); }
  setVolume(volume: number) { this.volumeGain.gain.setTargetAtTime(Math.max(0, Math.min(1, volume)), this.ctx.currentTime, 0.02); }

  schedule(origin: number, sections: TimedDuetSection[]) {
    scheduleVoiceGate(this.sendGate.gain, this.ctx, origin, sections, this.slot);
    scheduleVoiceGate(this.receiveGate.gain, this.ctx, origin, sections, 1 - this.slot);
  }

  private status(state: VoiceStatus['state']) {
    this.lastState = state;
    if (!this.closed) this.report({ state });
  }
  private presence() {
    if (this.closed) return;
    const live = roomLive();
    const snap = live.snapshot;
    const lobby = snap?.state === 'lobby';
    const song = snap?.state === 'playing' && !!snap.match?.duet &&
      ['preparing', 'active'].includes(snap.match.state);
    const context = lobby ? null : snap?.match?.id ?? null;
    // Close the open lobby gates on the snapshot itself, before React mounts song preparation.
    // A connected peer survives the context change; stale lobby SDP/ICE cannot cross that boundary.
    const contextChanged = context !== this.matchId;
    if (contextChanged || !lobby && !song) this.gate(false);
    this.matchId = context;
    const available = live.conn === 'open' && snap?.id === this.roomId && !!(lobby || song) &&
      snap.members.length === 2 && snap.members.every((m) => m.connected);
    if (lobby) this.gate(available);
    if (available === this.available) {
      if (available && contextChanged) {
        // A lobby negotiation still in flight may have sent old-context SDP. Start it afresh;
        // established audio keeps the same peer and only its privacy schedule changes.
        if (this.pc?.connectionState !== 'connected') this.reset();
        this.hello();
      }
      return;
    }
    this.available = available;
    this.reset();
    if (available) this.hello();
  }
  private hello() {
    sendVoice({ kind: 'ready', match_id: this.matchId, session: this.session });
  }
  private send(data: { kind: 'offer' | 'answer'; sdp: string } | { kind: 'ice'; candidate: RTCIceCandidateInit }) {
    if (!this.closed && this.available && this.peer) sendVoice({ ...data, match_id: this.matchId, session: this.session, peer: this.peer });
  }
  private reset() {
    this.pc?.close(); this.pc = null;
    this.detachRemote();
    this.peer = null; this.candidates = []; this.failedAt = 0;
    this.connectingAt = 0;
    this.session = crypto.randomUUID();
    this.status(this.available ? 'connecting' : 'waiting');
  }
  private fail() {
    if (this.closed || !this.available) return;
    this.pc?.close(); this.pc = null;
    this.detachRemote();
    this.failedAt = performance.now();
    this.status('unavailable');
  }
  private connection(peer: string) {
    this.pc?.close(); this.detachRemote();
    this.peer = peer; this.candidates = []; this.failedAt = 0;
    this.connectingAt = performance.now();
    const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }], bundlePolicy: 'max-bundle' });
    this.pc = pc;
    pc.addTrack(this.outgoing.stream.getAudioTracks()[0], this.outgoing.stream);
    pc.onicecandidate = ({ candidate }) => { if (this.pc === pc && candidate) this.send({ kind: 'ice', candidate: candidate.toJSON() }); };
    pc.ontrack = ({ track, receiver }) => {
      if (this.pc !== pc || this.closed) return;
      // Feature-detected low-latency hints, never promises about end-to-end delay.
      const lowDelay = receiver as RTCRtpReceiver & { jitterBufferTarget?: number; playoutDelayHint?: number };
      try { if ('jitterBufferTarget' in lowDelay) lowDelay.jitterBufferTarget = 0;
        if ('playoutDelayHint' in lowDelay) lowDelay.playoutDelayHint = 0; } catch { /* unsupported hint */ }
      this.detachRemote();
      const stream = new MediaStream([track]);
      // Chromium needs a playing media element to pull/decode remote WebRTC audio. Keep it
      // muted: audible output must ONLY pass through the section gate and volume graph.
      this.remotePlayback = new Audio();
      this.remotePlayback.muted = true;
      this.remotePlayback.srcObject = stream;
      void this.remotePlayback.play().catch(() => { /* WebAudio resumes on READY TO SING */ });
      this.remote = this.ctx.createMediaStreamSource(stream);
      this.remote.connect(this.receiveGate);
    };
    pc.onconnectionstatechange = () => {
      if (this.pc !== pc || this.closed) return;
      if (pc.connectionState === 'connected') { this.failedAt = 0; this.connectingAt = 0; this.status('connected'); }
      else if (pc.connectionState === 'failed') this.fail();
      else if (pc.connectionState === 'disconnected') {
        this.failedAt ||= performance.now(); this.status('connecting');
      }
    };
    this.status('connecting');
    return pc;
  }
  private async signal(data: VoiceSignal) {
    if (this.closed || !this.available) return;
    if (data.kind === 'ready') {
      if (this.peer === data.session) return;
      const pc = this.connection(data.session);
      this.hello(); // lets a newly joined/reconnected peer discover our generation
      if (this.slot === 0) {
        const offer = await pc.createOffer();
        if (this.pc !== pc) return;
        await pc.setLocalDescription({ type: 'offer', sdp: voiceSdp(offer.sdp!) });
        if (this.pc === pc) this.send({ kind: 'offer', sdp: pc.localDescription!.sdp });
      }
      return;
    }
    if (data.peer !== this.session || data.session !== this.peer || !this.pc) return;
    const pc = this.pc;
    if (data.kind === 'ice') {
      if (pc.remoteDescription) await pc.addIceCandidate(data.candidate);
      else if (this.candidates.length < 64) this.candidates.push(data.candidate);
      return;
    }
    if (data.kind === 'offer' && this.slot !== 1 || data.kind === 'answer' && this.slot !== 0) return;
    await pc.setRemoteDescription({ type: data.kind, sdp: data.sdp });
    if (this.pc !== pc) return;
    for (const candidate of this.candidates.splice(0)) await pc.addIceCandidate(candidate);
    if (data.kind === 'offer') {
      const answer = await pc.createAnswer();
      if (this.pc !== pc) return;
      await pc.setLocalDescription({ type: 'answer', sdp: voiceSdp(answer.sdp!) });
      if (this.pc === pc) this.send({ kind: 'answer', sdp: pc.localDescription!.sdp });
    }
  }
  private async stats() {
    const pc = this.pc;
    if (!pc || pc.connectionState !== 'connected' || this.statsBusy) return;
    this.statsBusy = true;
    try {
      const stats = await pc.getStats();
      if (this.closed || this.pc !== pc) return;
      let rttMs: number | undefined, bufferMs: number | undefined;
      stats.forEach((s) => {
        if (s.type === 'candidate-pair' && s.state === 'succeeded' && s.nominated && typeof s.currentRoundTripTime === 'number') rttMs = s.currentRoundTripTime * 1000;
        if (s.type === 'inbound-rtp' && s.kind === 'audio' && s.jitterBufferEmittedCount > 0) bufferMs = s.jitterBufferDelay / s.jitterBufferEmittedCount * 1000;
      });
      this.report({ state: this.lastState, rttMs, bufferMs });
    } catch { /* stats are optional; voice and scoring continue */ }
    finally { this.statsBusy = false; }
  }
  private detachRemote() {
    this.remote?.disconnect(); this.remote = null;
    if (this.remotePlayback) {
      this.remotePlayback.pause(); this.remotePlayback.srcObject = null; this.remotePlayback = null;
    }
  }
  close() {
    if (this.closed) return;
    this.gate(false);
    this.closed = true; this.available = false;
    clearInterval(this.timer); this.unsubscribe.forEach((unsubscribe) => unsubscribe());
    this.pc?.close(); this.detachRemote();
    this.micGain.close();
    for (const node of [this.source, this.sendGate, this.muteGain, this.receiveGate, this.volumeGain, this.outgoing]) node.disconnect();
    this.outgoing.stream.getTracks().forEach((track) => track.stop());
  }
}

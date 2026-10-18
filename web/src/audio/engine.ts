/**
 * One singing turn's audio graph. AudioContext.currentTime is the single master clock: the backing
 * track is scheduled at a known context time t0, so clip time = currentTime - t0 drives the notes,
 * lyrics and scoring, and captured mic samples are timestamped on the same clock by the worklet.
 *
 *   instrumental/click  -> destination
 *   guide vocals (optional) -> guide gain -> destination
 *   mic -> capture worklet -> (silent) destination      batches -> PitchTracker (Pitchy, hop grid)
 *                                                               -> TakeRecorder (16 kHz copy for the lyric check)
 */
import type { TimeRange } from '../lib/types';
import { SCORING_CONFIG } from '../scoring/config';
import { CAPTURE_PROCESSOR, loadCaptureWorklet, type CaptureBatch } from './captureWorklet';
import { PitchTracker } from './pitchTracker';
import { TakeRecorder } from './takeRecorder';
import { loadBacking, loadVocals, scheduleCountIn, stopStream, type Backing } from './sources';

/** Seconds of 3-2-1 count-in before the selected playback start. */
export const COUNT_IN = 3;

export class SingEngine {
  readonly tracker: PitchTracker;
  /** The singer's voice on the clip clock, kept for the lyric check after the song. */
  readonly recorder: TakeRecorder;
  private mic: MediaStream | null = null;
  private micNode: MediaStreamAudioSourceNode | null = null;
  private capture: AudioWorkletNode | null = null;
  private source: AudioBufferSourceNode | null = null;
  private guideSource: AudioBufferSourceNode | null = null;
  private readonly guideGain: GainNode;
  private t0 = Infinity;
  private closed = false;
  private voiceMix: DynamicsCompressorNode | null = null;

  private constructor(
    readonly ctx: AudioContext,
    readonly backing: Backing,
    readonly duration: number,
    offset: number,
    /** Decoded guide vocals, or null when the clip has none. */
    readonly vocals: AudioBuffer | null,
    readonly range: TimeRange | null,
    private readonly ownsContext: boolean,
  ) {
    this.guideGain = ctx.createGain();
    this.guideGain.gain.value = 0;
    this.guideGain.connect(ctx.destination);
    this.tracker = new PitchTracker(ctx.sampleRate, offset, Math.ceil(duration / SCORING_CONFIG.hopSeconds));
    // A little margin around the sung range, so a line sung slightly early or late is still in the take.
    this.recorder = new TakeRecorder(ctx.sampleRate, offset, Math.max(0, (range?.start ?? 0) - 0.5), (range?.end ?? duration) + 1);
  }

  /** Load capture/backing; a supplied room context stays owned by that room, including on failure. */
  static async create(clipId: string, duration: number, offset: number | null, range: TimeRange | null = null, sharedContext?: AudioContext): Promise<SingEngine> {
    const ctx = sharedContext ?? new AudioContext({ latencyHint: 'interactive' });
    try {
      await loadCaptureWorklet(ctx);
      const backing = await loadBacking(ctx, clipId, duration);
      const vocals = await loadVocals(ctx, clipId);
      return new SingEngine(ctx, backing, duration, offset ?? 0, vocals, range, !sharedContext);
    } catch (e) {
      if (!sharedContext) void ctx.close();
      throw e;
    }
  }

  /** Route an open mic stream into the capture worklet (replaces any previous mic). */
  attachMic(stream: MediaStream, recordTake = true) {
    this.detachMic();
    this.mic = stream;
    this.micNode = this.ctx.createMediaStreamSource(stream);
    this.capture = new AudioWorkletNode(this.ctx, CAPTURE_PROCESSOR, { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1, channelCountMode: 'explicit' });
    this.capture.port.onmessage = (e: MessageEvent<CaptureBatch>) => {
      this.tracker.push(e.data);
      if (recordTake) this.recorder.push(e.data);
    };
    // The worklet outputs silence; connecting it keeps the browser pulling it every render quantum.
    this.micNode.connect(this.capture).connect(this.ctx.destination);
  }

  /** True while the mic track is still delivering audio (it ends if unplugged or revoked). */
  get micLive() {
    return this.mic?.getAudioTracks().some((t) => t.readyState === 'live') ?? false;
  }

  /** Read-only source for a separate voice-sharing graph; never mute/stop these scoring tracks. */
  get micStream() { return this.mic; }

  /** Online-only mix bus: headroom and a limiter shared by backing, guide and remote voice. */
  enableVoiceMix(): AudioNode {
    if (!this.voiceMix) {
      const mix = this.ctx.createDynamicsCompressor();
      mix.threshold.value = -6; mix.knee.value = 0; mix.ratio.value = 20;
      mix.attack.value = 0.003; mix.release.value = 0.1;
      mix.connect(this.ctx.destination);
      this.guideGain.disconnect(); this.guideGain.connect(mix);
      this.voiceMix = mix;
    }
    return this.voiceMix;
  }

  /**
   * Start the turn (call from a user gesture so the context may resume). Schedules the count-in beeps
   * and the backing track on the master clock and returns t0, the context time of clip time 0.
   */
  start(at?: number): Promise<number> {
    if (this.started) return this.started; // a double click must not schedule the sources twice
    this.started = this.startOnce(at);
    return this.started;
  }
  private started: Promise<number> | null = null;

  private async startOnce(scheduledAt?: number): Promise<number> {
    await this.ctx.resume();
    const start = this.range?.start ?? 0;
    const end = this.range?.end ?? this.duration;
    const at = scheduledAt ?? this.ctx.currentTime + COUNT_IN + 0.15;
    if (at < this.ctx.currentTime + 0.1) throw new Error('The shared start was missed. Restart the duet together.');
    // Keep t0 as the origin of the full clip, including when it lies before context time 0.
    this.t0 = at - start;
    scheduleCountIn(this.ctx, [3, 2, 1].map((n) => at - n));
    this.source = this.ctx.createBufferSource();
    this.source.buffer = this.backing.buffer;
    this.source.connect(this.voiceMix ?? this.ctx.destination);
    this.source.start(at, start, end - start);
    if (this.vocals) {
      // Always scheduled (silent while the gain is 0) so the guide can be switched on mid-song, in sync.
      this.guideSource = this.ctx.createBufferSource();
      this.guideSource.buffer = this.vocals;
      this.guideSource.connect(this.guideGain);
      this.guideSource.start(at, start, end - start);
    }
    this.tracker.start(this.t0);
    this.recorder.start(this.t0);
    return this.t0;
  }

  /** Guide vocal loudness, 0 (off) to 1; takes effect immediately. */
  setGuideVolume(v: number) {
    this.guideGain.gain.setTargetAtTime(Math.max(0, Math.min(1, v)), this.ctx.currentTime, 0.02);
  }

  /** Clip time on the master clock (before the selected start during count-in; -Infinity before start). */
  clipTime(): number {
    return this.ctx.currentTime - this.t0;
  }

  private detachMic() {
    this.capture?.port.close();
    this.capture?.disconnect();
    this.micNode?.disconnect();
    stopStream(this.mic);
    this.mic = this.micNode = this.capture = null;
  }

  /** Stop audio, release the mic tracks and close the context. Safe to call more than once. */
  close() {
    if (this.closed) return;
    this.closed = true;
    for (const src of [this.source, this.guideSource]) {
      try {
        src?.stop();
      } catch {
        // never started
      }
      src?.disconnect();
    }
    this.detachMic();
    this.guideGain.disconnect();
    this.voiceMix?.disconnect();
    if (this.ownsContext) void this.ctx.close();
  }
}

/**
 * One singing turn's audio graph. AudioContext.currentTime is the single master clock: the backing
 * track is scheduled at a known context time t0, so clip time = currentTime - t0 drives the notes,
 * lyrics and scoring, and captured mic samples are timestamped on the same clock by the worklet.
 *
 *   instrumental/click  -> destination
 *   guide vocals (optional) -> guide gain -> destination
 *   mic -> capture worklet -> (silent) destination      batches -> PitchTracker (Pitchy, hop grid)
 */
import { SCORING_CONFIG } from '../scoring/config';
import { CAPTURE_PROCESSOR, loadCaptureWorklet, type CaptureBatch } from './captureWorklet';
import { PitchTracker } from './pitchTracker';
import { loadBacking, loadVocals, scheduleCountIn, stopStream, type Backing } from './sources';

/** Seconds of 3-2-1 count-in before clip time 0. */
export const COUNT_IN = 3;

export class SingEngine {
  readonly tracker: PitchTracker;
  private mic: MediaStream | null = null;
  private micNode: MediaStreamAudioSourceNode | null = null;
  private capture: AudioWorkletNode | null = null;
  private source: AudioBufferSourceNode | null = null;
  private guideSource: AudioBufferSourceNode | null = null;
  private readonly guideGain: GainNode;
  private t0 = Infinity;
  private closed = false;

  private constructor(
    readonly ctx: AudioContext,
    readonly backing: Backing,
    readonly duration: number,
    offset: number,
    /** Decoded guide vocals, or null when the clip has none. */
    readonly vocals: AudioBuffer | null,
  ) {
    this.guideGain = ctx.createGain();
    this.guideGain.gain.value = 0;
    this.guideGain.connect(ctx.destination);
    this.tracker = new PitchTracker(ctx.sampleRate, offset, Math.ceil(duration / SCORING_CONFIG.hopSeconds));
  }

  /** Build the context, load the capture worklet and the backing track. Throws on load failure. */
  static async create(clipId: string, duration: number, offset: number | null): Promise<SingEngine> {
    const ctx = new AudioContext({ latencyHint: 'interactive' });
    try {
      await loadCaptureWorklet(ctx);
      const backing = await loadBacking(ctx, clipId, duration);
      const vocals = await loadVocals(ctx, clipId);
      return new SingEngine(ctx, backing, duration, offset ?? 0, vocals);
    } catch (e) {
      void ctx.close();
      throw e;
    }
  }

  /** Route an open mic stream into the capture worklet (replaces any previous mic). */
  attachMic(stream: MediaStream) {
    this.detachMic();
    this.mic = stream;
    this.micNode = this.ctx.createMediaStreamSource(stream);
    this.capture = new AudioWorkletNode(this.ctx, CAPTURE_PROCESSOR, { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1, channelCountMode: 'explicit' });
    this.capture.port.onmessage = (e: MessageEvent<CaptureBatch>) => this.tracker.push(e.data);
    // The worklet outputs silence; connecting it keeps the browser pulling it every render quantum.
    this.micNode.connect(this.capture).connect(this.ctx.destination);
  }

  /** True while the mic track is still delivering audio (it ends if unplugged or revoked). */
  get micLive() {
    return this.mic?.getAudioTracks().some((t) => t.readyState === 'live') ?? false;
  }

  /**
   * Start the turn (call from a user gesture so the context may resume). Schedules the count-in beeps
   * and the backing track on the master clock and returns t0, the context time of clip time 0.
   */
  async start(): Promise<number> {
    await this.ctx.resume();
    this.t0 = this.ctx.currentTime + COUNT_IN + 0.15;
    scheduleCountIn(this.ctx, [3, 2, 1].map((n) => this.t0 - n));
    this.source = this.ctx.createBufferSource();
    this.source.buffer = this.backing.buffer;
    this.source.connect(this.ctx.destination);
    this.source.start(this.t0);
    if (this.vocals) {
      // Always scheduled (silent while the gain is 0) so the guide can be switched on mid-song, in sync.
      this.guideSource = this.ctx.createBufferSource();
      this.guideSource.buffer = this.vocals;
      this.guideSource.connect(this.guideGain);
      this.guideSource.start(this.t0);
    }
    this.tracker.start(this.t0);
    return this.t0;
  }

  /** Guide vocal loudness, 0 (off) to 1; takes effect immediately. */
  setGuideVolume(v: number) {
    this.guideGain.gain.setTargetAtTime(Math.max(0, Math.min(1, v)), this.ctx.currentTime, 0.02);
  }

  /** Clip time in seconds on the master clock (negative during the count-in, -Infinity before start). */
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
    void this.ctx.close();
  }
}

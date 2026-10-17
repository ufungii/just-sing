/**
 * Live user pitch on the clip's hop grid. Captured batches carry master-clock frame numbers; once the
 * clip is scheduled to start at context time t0, user frame k (clip time k * hop) is the Pitchy pitch of
 * the window centred on context time t0 + k * hop + offset, where offset is the one device latency from
 * the setup step. Nothing here estimates a per-take offset.
 *
 * A frame is voiced only if Pitchy's clarity, the window RMS and the frequency range all pass the config
 * gates, so mic noise does not become pitch just because the tracker returned a number.
 */
import { PitchDetector } from 'pitchy';
import { SCORING_CONFIG } from '../scoring/config';
import type { CaptureBatch } from './captureWorklet';

/** Keep about this many seconds of raw samples (only the latest window is ever needed). */
const KEEP_SECONDS = 2;

export class PitchTracker {
  /** User Hz per clip frame (null = unvoiced). Read by the pitch lane and the scorer. */
  readonly hz: (number | null)[] = [];
  /** RMS of the latest analysed window, for the mic level meter. */
  level = 0;

  private chunks: CaptureBatch[] = [];
  private readonly detector: PitchDetector<Float32Array>;
  private readonly window: Float32Array;
  private readonly hop = SCORING_CONFIG.hopSeconds;
  private t0 = Infinity;
  private next = 0; // next clip frame to analyse

  constructor(
    private readonly sampleRate: number,
    /** Device latency in seconds (null from setup = 0). Applied once for the whole turn. */
    private readonly offset: number,
    private readonly frames: number,
  ) {
    this.window = new Float32Array(SCORING_CONFIG.windowSamples);
    this.detector = PitchDetector.forFloat32Array(SCORING_CONFIG.windowSamples);
    this.detector.minVolumeAbsolute = SCORING_CONFIG.minRms;
  }

  /** Clip time 0 plays at this context time. */
  start(t0: number) {
    this.t0 = t0;
  }

  /** Clip frames analysed so far; frames below this index are final. */
  get analysed() {
    return this.next;
  }

  push(batch: CaptureBatch) {
    this.chunks.push(batch);
    const keepFrom = batch.startFrame + batch.samples.length - KEEP_SECONDS * this.sampleRate;
    while (this.chunks.length > 1 && this.chunks[0].startFrame + this.chunks[0].samples.length < keepFrom) this.chunks.shift();
    this.analyse(batch.startFrame + batch.samples.length);
  }

  /** Analyse every clip frame whose whole window has been captured (samples before `endFrame`). */
  private analyse(endFrame: number) {
    if (!Number.isFinite(this.t0)) return;
    const half = this.window.length / 2;
    while (this.next < this.frames) {
      const centre = Math.round((this.t0 + this.next * this.hop + this.offset) * this.sampleRate);
      if (centre + half > endFrame) break;
      this.hz[this.next] = this.copyWindow(centre - half) ? this.pitchOfWindow() : null;
      this.next++;
    }
  }

  /** Copy samples [from, from + window) into the window buffer; false if any of them were never captured. */
  private copyWindow(from: number): boolean {
    let filled = 0;
    for (const c of this.chunks) {
      const a = Math.max(from, c.startFrame);
      const b = Math.min(from + this.window.length, c.startFrame + c.samples.length);
      if (b <= a) continue;
      this.window.set(c.samples.subarray(a - c.startFrame, b - c.startFrame), a - from);
      filled += b - a;
    }
    return filled === this.window.length;
  }

  private pitchOfWindow(): number | null {
    let sq = 0;
    for (let i = 0; i < this.window.length; i++) sq += this.window[i] * this.window[i];
    this.level = Math.sqrt(sq / this.window.length);
    if (this.level < SCORING_CONFIG.minRms) return null;
    const [hz, clarity] = this.detector.findPitch(this.window, this.sampleRate);
    if (clarity < SCORING_CONFIG.minClarity || hz < SCORING_CONFIG.fminHz || hz > SCORING_CONFIG.fmaxHz) return null;
    return hz;
  }
}

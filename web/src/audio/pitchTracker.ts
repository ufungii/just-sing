/**
 * Live user pitch on the clip's hop grid. Captured batches carry master-clock frame numbers; once the
 * clip is scheduled to start at context time t0, user frame k (clip time k * hop) is the Pitchy pitch of
 * the window centred on context time t0 + k * hop + offset, where offset is the one device latency from
 * the setup step. Nothing here estimates a per-take offset.
 *
 * A frame is voiced only if Pitchy's clarity, the window RMS and the frequency range all pass the config
 * gates, so mic noise does not become pitch just because the tracker returned a number.
 *
 * Raw Pitchy output is smoothed (see smoothFrame) before anyone reads it. The filter is centred, so it
 * shifts nothing in time (frame k is still clip time k * hop); the price is that frame k is only final
 * once frame k + SMOOTH_HALF has been analysed, i.e. 40 ms of extra display/rating latency. `analysed`
 * reports the smoothed frames, so phrase rating waits for them.
 */
import { PitchDetector } from 'pitchy';
import { SCORING_CONFIG } from '../scoring/config';
import type { CaptureBatch } from './captureWorklet';

/** Median window is 2 * SMOOTH_HALF + 1 = 5 frames (0.1 s). */
export const SMOOTH_HALF = 2;
/** A frame this far (+-OCTAVE_TOL cents) from +-1200 cents off two agreeing neighbours is an octave glitch. */
const OCTAVE_TOL_CENTS = 150;
const AGREE_CENTS = 100;

const cents = (a: number, b: number) => 1200 * Math.log2(a / b);

/**
 * Smoothed value for frame i of the raw track. Unvoiced stays unvoiced (voiced pitch is never smeared into
 * a gap); a voiced frame becomes the median of the voiced frames within SMOOTH_HALF of it, after a
 * single-frame octave jump (both neighbours voiced, agreeing, and an octave away) is replaced by them.
 * Frames past the end of `raw` are simply absent, so the last frames use a shorter window.
 */
export function smoothFrame(raw: readonly (number | null)[], i: number): number | null {
  if (raw[i] == null) return null;
  const at = (j: number) => {
    const v = raw[j] ?? null;
    const a = raw[j - 1] ?? null, b = raw[j + 1] ?? null;
    if (v != null && a != null && b != null && Math.abs(cents(a, b)) < AGREE_CENTS
      && [a, b].every((n) => Math.abs(Math.abs(cents(v, n)) - 1200) < OCTAVE_TOL_CENTS)) return Math.sqrt(a * b);
    return v;
  };
  const vals: number[] = [];
  for (let j = i - SMOOTH_HALF; j <= i + SMOOTH_HALF; j++) { const v = at(j); if (v != null) vals.push(v); }
  vals.sort((x, y) => x - y);
  const m = vals.length >> 1;
  return vals.length % 2 ? vals[m] : Math.sqrt(vals[m - 1] * vals[m]);
}

/** Keep about this many seconds of raw samples (only the latest window is ever needed). */
const KEEP_SECONDS = 2;

export class PitchTracker {
  /** Smoothed user Hz per clip frame (null = unvoiced). Read by the pitch lane and the scorer. */
  readonly hz: (number | null)[] = [];
  private readonly raw: (number | null)[] = [];
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

  /** Clip frames final so far (analysed and smoothed); frames below this index are final. */
  get analysed() {
    return this.hz.length;
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
      this.raw[this.next] = this.copyWindow(centre - half) ? this.pitchOfWindow() : null;
      this.next++;
      // Frame k is final once k + SMOOTH_HALF is in, or when the clip has no more frames.
      const final = this.next >= this.frames ? this.next : this.next - SMOOTH_HALF;
      while (this.hz.length < final) this.hz.push(smoothFrame(this.raw, this.hz.length));
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

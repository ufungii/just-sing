/**
 * Keeps a 16 kHz copy of the singer's voice for the lyric check after the song, placed on the clip
 * clock exactly like the pitch tracker places its frames: an input sample captured at context time c
 * belongs to clip time c - t0 - offset, where offset is the one device latency from setup.
 *
 * Output sample i covers clip time `from + i / 16000`. Each output sample is the mean of the input
 * samples that fall in it (a box filter: crude, but enough for a speech model). Samples that were never
 * captured stay silent. The recording only lives in memory for this turn and is uploaded once.
 */
import type { CaptureBatch } from './captureWorklet';

export const TAKE_RATE = 16_000;

export class TakeRecorder {
  private readonly sum: Float32Array;
  private readonly count: Uint8Array;
  private t0 = Infinity;

  constructor(
    private readonly sampleRate: number,
    /** Device latency in seconds (the same value the pitch tracker uses). */
    private readonly offset: number,
    /** Clip time of the first output sample. */
    readonly from: number,
    /** Clip time just after the last output sample. */
    readonly to: number,
  ) {
    const n = Math.max(0, Math.ceil((to - from) * TAKE_RATE));
    this.sum = new Float32Array(n);
    this.count = new Uint8Array(n);
  }

  /** Clip time 0 plays at this context time. */
  start(t0: number) {
    this.t0 = t0;
  }

  push(batch: CaptureBatch) {
    if (!Number.isFinite(this.t0)) return;
    // Output index of input sample k: floor((startFrame + k) / sampleRate - t0 - offset - from) * TAKE_RATE)
    const base = (batch.startFrame / this.sampleRate - this.t0 - this.offset - this.from) * TAKE_RATE;
    const step = TAKE_RATE / this.sampleRate;
    const n = this.sum.length;
    for (let k = 0; k < batch.samples.length; k++) {
      const i = Math.floor(base + k * step);
      if (i < 0 || i >= n || this.count[i] === 255) continue;
      this.sum[i] += batch.samples[k];
      this.count[i]++;
    }
  }

  /** The take as samples at 16 kHz (mean per output sample). */
  samples(): Float32Array {
    const out = new Float32Array(this.sum.length);
    for (let i = 0; i < out.length; i++) out[i] = this.count[i] ? this.sum[i] / this.count[i] : 0;
    return out;
  }

  /**
   * A 16-bit mono WAV of the take, plus `offsetS`: the time in the recording at which clip time 0 falls
   * (what the server's lyric check needs). Latency is already removed, so offsetS is just -from.
   */
  toWav(): { wav: Blob; offsetS: number } {
    return { wav: encodeWav(this.samples()), offsetS: -this.from };
  }

  /**
   * A WAV of clip times [a, b) only (clamped to what this recorder keeps), for checking one lyric line
   * while the song is still playing. offsetS is the time in that WAV of clip time 0.
   */
  slice(a: number, b: number): { wav: Blob; offsetS: number } {
    const i = Math.max(0, Math.floor((a - this.from) * TAKE_RATE));
    const j = Math.min(this.sum.length, Math.ceil((b - this.from) * TAKE_RATE));
    const pcm = new Float32Array(Math.max(0, j - i));
    for (let k = 0; k < pcm.length; k++) pcm[k] = this.count[i + k] ? this.sum[i + k] / this.count[i + k] : 0;
    return { wav: encodeWav(pcm), offsetS: -(this.from + i / TAKE_RATE) };
  }
}

/** 16-bit mono WAV at TAKE_RATE. */
function encodeWav(pcm: Float32Array): Blob {
  const view = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const text = (at: number, s: string) => [...s].forEach((ch, j) => view.setUint8(at + j, ch.charCodeAt(0)));
  text(0, 'RIFF');
  view.setUint32(4, 36 + pcm.length * 2, true);
  text(8, 'WAVE');
  text(12, 'fmt ');
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, TAKE_RATE, true);
  view.setUint32(28, TAKE_RATE * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per frame
  view.setUint16(34, 16, true); // bits per sample
  text(36, 'data');
  view.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) view.setInt16(44 + i * 2, Math.round(Math.max(-1, Math.min(1, pcm[i])) * 32767), true);
  return new Blob([view.buffer], { type: 'audio/wav' });
}

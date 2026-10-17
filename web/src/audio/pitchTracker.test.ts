import { existsSync, readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { PitchTracker, smoothFrame } from './pitchTracker';

const smooth = (raw: (number | null)[]) => raw.map((_, i) => smoothFrame(raw, i));
const cents = (a: number, b: number) => 1200 * Math.log2(a / b);

it('keeps unvoiced frames unvoiced and does not smear pitch across a gap', () => {
  const out = smooth([220, 220, null, null, 220, 220]);
  expect(out.map((v) => v == null)).toEqual([false, false, true, true, false, false]);
});

it('removes a single-frame octave jump but keeps a real octave step', () => {
  expect(smooth([220, 220, 440, 220, 220])[2]).toBeCloseTo(220);
  const step = smooth([220, 220, 220, 440, 440, 440]);
  expect(step[2]).toBeCloseTo(220);
  expect(step[3]).toBeCloseTo(440);
});

it('median-filters spikes and leaves a clean track alone', () => {
  expect(smooth([220, 220, 260, 220, 220])[2]).toBeCloseTo(220);
  const clean = [220, 221, 222, 223, 224, 225];
  expect(smooth(clean)[2]).toBeCloseTo(222);
});

it('uses a shorter window at the clip edges instead of inventing frames', () => {
  expect(smooth([220, 330])[0]).toBeCloseTo(Math.sqrt(220 * 330));
});

/** Median / p95 / mean absolute frame-to-frame jump (cents) between consecutive voiced frames. */
function jumps(track: readonly (number | null)[]) {
  const d: number[] = [];
  for (let i = 1; i < track.length; i++) { const a = track[i - 1], b = track[i]; if (a != null && b != null) d.push(Math.abs(cents(a, b))); }
  d.sort((x, y) => x - y);
  return { n: d.length, median: d[d.length >> 1] ?? 0, p95: d[Math.floor(d.length * 0.95)] ?? 0, mean: d.reduce((s, v) => s + v, 0) / (d.length || 1) };
}

function wav(path: string) {
  const b = readFileSync(path);
  const pcm = new Int16Array(b.buffer.slice(b.byteOffset + 44, b.byteOffset + b.length - ((b.length - 44) % 2)));
  return Float32Array.from(pcm, (v) => v / 32768);
}

// Measurement on the recorded takes: `npx vitest run src/audio/pitchTracker.test.ts` prints before/after.
const TAKES = ['../e2e/takes/synthetic-demo/good.wav', '../e2e/takes/synthetic-demo/wrong.wav', '../e2e/takes/russian-roulette/good.wav', '../e2e/takes/russian-roulette/wrong.wav'];
it.each(TAKES.filter(existsSync))('smoothing does not increase frame-to-frame jumps on %s', (path) => {
  const sr = 48000, samples = wav(path), frames = Math.floor(samples.length / sr / 0.02) - 4;
  const tracker = new PitchTracker(sr, 0, frames);
  tracker.start(0);
  for (let s = 0; s < samples.length; s += 4096) tracker.push({ startFrame: s, samples: samples.subarray(s, s + 4096) });
  const raw = (tracker as unknown as { raw: (number | null)[] }).raw;
  expect(tracker.analysed).toBe(frames);
  const before = jumps(raw), after = jumps(tracker.hz);
  console.log(`JITTER ${path.split('e2e/takes/')[1]} voiced pairs ${before.n}->${after.n}; jump cents median ${before.median.toFixed(1)}->${after.median.toFixed(1)}, p95 ${before.p95.toFixed(0)}->${after.p95.toFixed(0)}, mean ${before.mean.toFixed(1)}->${after.mean.toFixed(1)}`);
  expect(after.mean).toBeLessThanOrEqual(before.mean);
});

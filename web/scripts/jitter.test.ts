import { existsSync, readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { PitchTracker } from '../src/audio/pitchTracker';

const cents = (a: number, b: number) => 1200 * Math.log2(a / b);

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

// Live-pitch jitter on the recorded takes, run from web/ (scripts/ is not type-checked by `tsc -b`, which only covers src/).
// Print the numbers with: npx vitest run scripts/jitter.test.ts --disableConsoleIntercept
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

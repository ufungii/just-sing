import { expect, it } from 'vitest';
import { TAKE_RATE, TakeRecorder } from './takeRecorder';

const SR = 48_000;

/** Batches of a constant value covering context time [a, b). */
function batches(rec: TakeRecorder, a: number, b: number, value: number) {
  for (let f = Math.round(a * SR); f < Math.round(b * SR); f += 512) {
    rec.push({ startFrame: f, samples: new Float32Array(Math.min(512, Math.round(b * SR) - f)).fill(value) });
  }
}

it('places captured audio on the clip clock, after removing the device latency', () => {
  // Clip time 0 plays at context time 10; the device delays the voice by 0.1 s.
  const rec = new TakeRecorder(SR, 0.1, 2, 4);
  rec.start(10);
  // The singer is heard at clip times 3.0-3.5, so it reaches the capture at context 13.1-13.6.
  batches(rec, 13.1, 13.6, 0.5);
  const pcm = rec.samples();
  expect(pcm.length).toBe(2 * TAKE_RATE);
  const at = (clipT: number) => pcm[Math.floor((clipT - 2) * TAKE_RATE)];
  expect(at(2.9)).toBe(0);
  expect(at(3.01)).toBeCloseTo(0.5);
  expect(at(3.49)).toBeCloseTo(0.5);
  expect(at(3.6)).toBe(0);
});

it('ignores audio before the clip starts and outside the kept range', () => {
  const rec = new TakeRecorder(SR, 0, 0, 1);
  batches(rec, 0, 1, 0.3); // before start(): t0 unknown
  rec.start(5);
  batches(rec, 3, 5, 0.3); // count-in, before clip time 0
  batches(rec, 6.2, 7, 0.3); // after clip time 1
  expect(rec.samples().every((v) => v === 0)).toBe(true);
});

it('writes a 16 kHz mono WAV and the offset the server needs', async () => {
  const rec = new TakeRecorder(SR, 0, 14.5, 16);
  rec.start(0);
  batches(rec, 15, 15.5, 1);
  const { wav, offsetS } = rec.toWav();
  expect(offsetS).toBe(-14.5); // clip time 0 lies 14.5 s before the recording starts
  const view = new DataView(await wav.arrayBuffer());
  expect(view.getUint32(24, true)).toBe(TAKE_RATE);
  expect(view.getUint16(22, true)).toBe(1);
  expect(view.getUint32(40, true)).toBe(1.5 * TAKE_RATE * 2);
  expect(view.getInt16(44 + Math.floor(0.7 * TAKE_RATE) * 2, true)).toBe(32767);
});

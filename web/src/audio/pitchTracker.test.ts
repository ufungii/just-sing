import { expect, it } from 'vitest';
import { smoothFrame } from './pitchTracker';

const smooth = (raw: (number | null)[]) => raw.map((_, i) => smoothFrame(raw, i));

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

import { expect, it } from 'vitest';
import { applyRemotePitch, duetDisplayTarget, duetFrameOwners, duetRegisters, validDuetProgress } from './duetLive';
import type { TargetTrack } from '../scoring';

const sections = [
  { id: 'a', slot: 0 as const, start: 0, end: 0.04, phrase_ids: ['a'] },
  { id: 'b', slot: 1 as const, start: 0.06, end: 0.1, phrase_ids: ['b'] },
];
const owners = duetFrameOwners(sections, 6, 0.02);
const progress = { match_id: 'match', t: 0.1, running: 72, pitch: { start: 0, hz: [110, 110, 110, 220, null, 110] } };

it('draws the remote capture at its original clip frames, only during its assigned sections', () => {
  const lane = [110, 110, null, null, 220, null];
  applyRemotePitch(lane, owners, 1, progress);
  expect(owners).toEqual([0, 0, null, 1, 1, null]);
  expect(lane).toEqual([110, 110, null, 220, null, null]);
  applyRemotePitch(lane, owners, 1, { ...progress, pitch: { start: 99999, hz: [440] } });
  expect(lane).toHaveLength(6);
});

it('shows the same targets to both players when they choose different octaves', () => {
  const attempts = [{ slot: 0, register: -12 as const }, { slot: 1, register: 12 as const }];
  expect(duetRegisters([-12, -12], attempts, 0)).toEqual([-12, 12]);
  expect(duetRegisters([12, 12], attempts, 1)).toEqual([-12, 12]);
  expect(duetRegisters([-12, 0], attempts)).toEqual([-12, 0]);
  const track = (hz: number): TargetTrack => ({ hop: 0.02, hz: Array(6).fill(hz), excluded: Array(6).fill(false), source: 'hz', onsets: [] });
  const targets = [track(110), track(440)];
  expect(duetDisplayTarget(targets, owners).hz).toEqual([110, 110, 110, 440, 440, 110]);
  expect(targets[0].hz).toEqual(Array(6).fill(110)); // display does not mutate scoring targets
});

it('accepts zero scores and unvoiced pitch, rejects malformed or oversized peer messages', () => {
  expect(validDuetProgress(progress)).toBe(true);
  expect(validDuetProgress({ ...progress, running: 0 })).toBe(true);
  expect(validDuetProgress({ ...progress, running: null })).toBe(true);
  for (const data of [null, {}, { ...progress, running: 101 }, { ...progress, t: NaN },
    { ...progress, pitch: { start: -1, hz: [220] } }, { ...progress, pitch: { start: 0, hz: [Infinity] } },
    { ...progress, pitch: { start: 0, hz: Array(26).fill(220) } }]) expect(validDuetProgress(data)).toBe(false);
});

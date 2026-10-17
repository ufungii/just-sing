import { expect, it } from 'vitest';
import { assignedIds, bestClock, sectionAt, serverNow } from './timeline';
const sections = [
  { id: 'a', slot: 1 as const, start: 1, end: 4, phrase_ids: ['p1'] },
  { id: 'b', slot: 1 as const, start: 5, end: 8, phrase_ids: ['p2'] },
  { id: 'c', slot: 0 as const, start: 9, end: 12, phrase_ids: ['p3'] },
];
it('keeps explicit repeated slots and changes ownership automatically on the clip clock', () => {
  expect([...assignedIds(sections, 1)]).toEqual(['p1', 'p2']);
  expect(sectionAt(sections, -3)).toBe(0);
  expect(sectionAt(sections, 4.5)).toBe(0);
  expect(sectionAt(sections, 5)).toBe(1);
  expect(sections[sectionAt(sections, 9)].slot).toBe(0);
});
it('estimates server time from the fastest round trip independent of client wall clock', () => {
  const slow = { sent: 100, received: 500, serverTime: 5000 };
  const fast = { sent: 1000, received: 1020, serverTime: 5001 };
  const chosen = bestClock([slow, fast]);
  expect(chosen).toBe(fast);
  expect(serverNow(chosen, 3010)).toBe(5003);
  const otherBrowser = { sent: 100_000, received: 100_020, serverTime: 5001 };
  expect(serverNow(otherBrowser, 102_010)).toBe(5003);
});

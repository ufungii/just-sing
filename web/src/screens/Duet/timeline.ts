import type { TimedDuetSection } from '../../lib/types';

export interface ClockSample { sent: number; received: number; serverTime: number }
/** Use the shortest round trip; monotonic client time is unaffected by an incorrect wall clock. */
export const bestClock = (samples: ClockSample[]) => samples.reduce((a, b) => b.received - b.sent < a.received - a.sent ? b : a);
export const serverNow = (sample: ClockSample, monotonicNow: number) => sample.serverTime + (monotonicNow - (sample.sent + sample.received) / 2) / 1000;
export function sectionAt(sections: TimedDuetSection[], time: number): number {
  let index = 0;
  for (let i = 0; i < sections.length; i++) if (sections[i].start <= time) index = i;
  return index;
}
export const assignedIds = (sections: TimedDuetSection[], slot: number) => new Set(sections.filter((s) => s.slot === slot).flatMap((s) => s.phrase_ids));

/** Seconds until a switch for display: whole seconds (rounded up), then tenths once under 3 s. */
export const countdownLabel = (seconds: number) => (seconds <= 0 ? '0' : seconds < 3 ? seconds.toFixed(1) : String(Math.ceil(seconds)));

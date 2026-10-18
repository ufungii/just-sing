import type { Register, TimedDuetSection } from './types';
import type { TargetTrack } from '../scoring';

/** Provisional display data only; scoring always uses the singer's own captured frames. */
export interface DuetProgress {
  match_id: string;
  t: number;
  running: number | null;
  pitch: { start: number; hz: (number | null)[] };
}
export const MAX_PITCH_BATCH = 25;

export function validDuetProgress(data: unknown): data is DuetProgress {
  if (!data || typeof data !== 'object') return false;
  const d = data as DuetProgress;
  return typeof d.match_id === 'string' && typeof d.t === 'number' && Number.isFinite(d.t) && d.t >= 0 &&
    (d.running === null || typeof d.running === 'number' && Number.isFinite(d.running) && d.running >= 0 && d.running <= 100) &&
    !!d.pitch && Number.isSafeInteger(d.pitch.start) && d.pitch.start >= 0 &&
    Array.isArray(d.pitch.hz) && d.pitch.hz.length <= MAX_PITCH_BATCH &&
    d.pitch.hz.every((h) => h === null || typeof h === 'number' && Number.isFinite(h) && h > 0 && h <= 20000);
}

/** Per-frame owner, including silent gaps. Unassigned frames never draw either microphone. */
export function duetFrameOwners(sections: TimedDuetSection[], frames: number, hop: number): (number | null)[] {
  return Array.from({ length: frames }, (_, k) => sections.find((s) => k * hop >= s.start && k * hop < s.end)?.slot ?? null);
}

/** Each singer's own register is used on both screens, including when their ranges differ. */
export function duetDisplayTarget(targets: TargetTrack[], owners: (number | null)[]): TargetTrack {
  return { ...targets[0], hz: targets[0].hz.map((_, k) => targets[owners[k] ?? 0].hz[k]) };
}

export function duetRegisters(local: Register[], attempts: { slot: number; register: Register }[], mySlot?: number): Register[] {
  return local.map((r, slot) => slot === mySlot || mySlot === undefined ? r : attempts.find((a) => a.slot === slot)?.register ?? r);
}

/** Bound writes to the clip and assigned sections; never replace the local singer's trace. */
export function applyRemotePitch(track: (number | null)[], owners: (number | null)[], slot: number, data: DuetProgress) {
  data.pitch.hz.forEach((hz, i) => {
    const k = data.pitch.start + i;
    if (k < track.length && owners[k] === slot) track[k] = hz;
  });
}

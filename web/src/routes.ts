/**
 * Every screen the app can show, with the data it needs. App renders the current route;
 * screens move with `useNav().go(route)`. No URL router yet: the desktop shell loads one page.
 */
import { createContext, useContext } from 'react';
import type { PhraseScore, Register, Score, TimeRange } from './lib/types';

/** Chosen on the solo setup screen and handed to the singing screen. */
export interface SingSetup {
  /** Unique per singing run (crypto.randomUUID()), so a rematch always starts a fresh screen. */
  runId: string;
  clipId: string;
  range?: TimeRange | null;
  register: Register;
  /** Device latency in seconds from the tap-along check, or null if skipped. One value per device, never per take. */
  calibrationOffset: number | null;
  playerName: string;
  /** Server match for saving results; null when the server or database is unavailable (play still works, unsaved). */
  match: { matchId: string; attemptId: string } | null;
  /** Set for a local battle turn; solo leaves it undefined. */
  battle?: BattleCtx;
  /** Set for an online room turn; the results go back to the room screen instead of a results screen. */
  online?: { roomId: string; slot: number };
}

/** Which room this browser is in, and which seat it holds. `prefs` survives a trip to the singing screen. */
export interface RoomRef {
  id: string;
  slot: number;
  prefs?: { register: Register; offset: number | null };
}

/** Local 1P vs 2P: one clip, two singers on one laptop, each with their own register. */
export interface BattleCtx {
  turn: 0 | 1;
  names: [string, string];
  registers: [Register, Register];
  calibrationOffset: number | null;
}

/** Handed from the singing screen to the results screen. */
export interface SingResult {
  setup: SingSetup;
  /** Phrase scores rated locally during the turn. */
  phrases: PhraseScore[];
  /** Totals computed locally from the same phrase scores (shown when saving failed). */
  local: { total: number; pitch: number; timing: number };
  /** The accepted server result, or null if not saved. */
  saved: Score | null;
  /** Why saving failed, for a friendly notice. */
  saveError: string | null;
}

export type Route =
  | { name: 'home' }
  | { name: 'solo' }
  | { name: 'sing'; setup: SingSetup }
  | { name: 'results'; result: SingResult }
  | { name: 'practice' }
  | { name: 'history' }
  | { name: 'battle' }
  /** Online lobby: no `room` means the create/join form. `notice` carries a save failure back from singing. */
  | { name: 'online'; room?: RoomRef; notice?: string }
  /** After a battle turn: hand-off after player 1, final results after player 2. */
  | { name: 'battleturn'; result: SingResult };

export interface Nav {
  route: Route;
  go: (route: Route) => void;
  home: () => void;
}

export const NavContext = createContext<Nav | null>(null);

export function useNav(): Nav {
  const nav = useContext(NavContext);
  if (!nav) throw new Error('useNav must be used inside App');
  return nav;
}

/**
 * Every screen the app can show, with the data it needs. App renders the current route;
 * screens move with `useNav().go(route)`. No URL router yet: the desktop shell loads one page.
 */
import { createContext, useContext } from 'react';
import type { PhraseScore, Register, Score } from './lib/types';

/** Chosen on the solo setup screen and handed to the singing screen. */
export interface SingSetup {
  /** Unique per singing run (crypto.randomUUID()), so a rematch always starts a fresh screen. */
  runId: string;
  clipId: string;
  register: Register;
  /** Device latency in seconds from the tap-along check, or null if skipped. One value per device, never per take. */
  calibrationOffset: number | null;
  playerName: string;
  /** Server match for saving results; null when the server or database is unavailable (play still works, unsaved). */
  match: { matchId: string; attemptId: string } | null;
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
  | { name: 'battle' };

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

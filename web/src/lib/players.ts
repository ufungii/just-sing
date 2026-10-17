/**
 * Local player profiles: the names (and pixel avatars) people sing under on this device.
 * Kept in localStorage, so they are per device and never sent anywhere except as the display name
 * of a guest session or match. Solo, battle and online setup pick from this list.
 */
import { useSyncExternalStore } from 'react';
import { savedName } from './api';
import { blockedPlayerNameReason } from './playerNamePolicy';

export type AvatarId = 'bunny' | 'kitty' | 'froggy' | 'strawberry' | 'mochi' | 'chick';
export const AVATAR_IDS: AvatarId[] = ['bunny', 'kitty', 'froggy', 'strawberry', 'mochi', 'chick'];

export interface Player {
  id: string;
  name: string;
  avatar: AvatarId;
}

interface PlayerState {
  players: Player[];
  /** The player picked last time, so setup screens open on them. */
  lastId: string | null;
}

/** The server's display-name limit. */
export const PLAYER_NAME_MAX = 40;

const KEY = 'just-sing.players';
const listeners = new Set<() => void>();
let state: PlayerState = load();

function load(): PlayerState {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as PlayerState;
      if (Array.isArray(parsed.players)) return parsed;
    }
  } catch {
    // unreadable or blocked storage: start fresh
  }
  // First run: carry over the name typed on the old setup screen, if any.
  const name = savedName().trim();
  const players = name ? [{ id: crypto.randomUUID(), name, avatar: 'bunny' as AvatarId }] : [];
  return { players, lastId: players[0]?.id ?? null };
}

function save(next: PlayerState) {
  state = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // storage blocked: changes last for this session only
  }
  listeners.forEach((l) => l());
}

export function usePlayers(): PlayerState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
  );
}

export function getPlayer(id: string | null): Player | null {
  return state.players.find((p) => p.id === id) ?? null;
}

/** Names must be non-empty and unique (case-insensitive), so matches and history read clearly. */
export function nameProblem(name: string, exceptId?: string): string | null {
  const n = name.trim();
  if (!n) return 'Give them a name first.';
  if (blockedPlayerNameReason(n)) return 'Choose a different player name.';
  if (n.length > PLAYER_NAME_MAX) return `Keep it under ${PLAYER_NAME_MAX} characters.`;
  if (state.players.some((p) => p.id !== exceptId && p.name.toLowerCase() === n.toLowerCase())) return 'That name is taken.';
  return null;
}

export function addPlayer(name: string, avatar: AvatarId): Player {
  const problem = nameProblem(name);
  if (problem) throw new Error(problem);
  const player = { id: crypto.randomUUID(), name: name.trim(), avatar };
  save({ players: [...state.players, player], lastId: player.id });
  return player;
}

export function updatePlayer(id: string, change: Partial<Pick<Player, 'name' | 'avatar'>>) {
  if (change.name !== undefined) {
    const problem = nameProblem(change.name, id);
    if (problem) throw new Error(problem);
  }
  save({
    ...state,
    players: state.players.map((p) => (p.id === id ? { ...p, ...change, name: (change.name ?? p.name).trim() } : p)),
  });
}

export function removePlayer(id: string) {
  const players = state.players.filter((p) => p.id !== id);
  save({ players, lastId: state.lastId === id ? (players[0]?.id ?? null) : state.lastId });
}

export function rememberPlayer(id: string) {
  if (state.lastId !== id) save({ ...state, lastId: id });
}

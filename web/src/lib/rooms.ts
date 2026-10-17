/**
 * Online rooms: the HTTP calls (durable actions) and one shared WebSocket (presence, snapshots, provisional
 * progress). The socket lives at module level so it survives the Sing screen replacing the lobby screen;
 * the singer pushes live progress through `sendLive`. Progress and badges are provisional, only a saved
 * result counts: after any reconnect the fresh snapshot is the truth.
 */
import { useSyncExternalStore } from 'react';
import { bearerToken, request } from './api';
import type { MatchView, NewMatch, Rating } from './types';

export interface RoomSnapshot {
  id: string;
  code: string;
  state: 'lobby' | 'playing' | 'finished' | 'aborted';
  state_version: number;
  clip_id: string;
  members: { slot: number; display_name: string; ready: boolean; connected: boolean }[];
  match: MatchView | null;
  /** The caller's own seat; only on HTTP responses, not on shared snapshots. */
  you?: number;
}

const call = <T>(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST') =>
  request<T>(path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });

export const createRoom = (clipId: string) => call<RoomSnapshot>('/api/rooms', { clip_id: clipId });
export const joinRoom = (code: string) => call<RoomSnapshot>('/api/rooms/join', { code });
export const getRoom = (id: string) => call<RoomSnapshot>(`/api/rooms/${id}`);
export const setReady = (id: string, ready: boolean) => call<RoomSnapshot>(`/api/rooms/${id}/ready`, { ready });
export const setRoomClip = (id: string, clipId: string) => call<RoomSnapshot>(`/api/rooms/${id}/clip`, { clip_id: clipId });
export const startRoom = (id: string) => call<NewMatch>(`/api/rooms/${id}/start`, {});
export const rematchRoom = (id: string) => call<NewMatch>(`/api/rooms/${id}/rematch`, {});
export const abortRoom = (id: string) => call<RoomSnapshot>(`/api/rooms/${id}/abort`, {}, 'POST');

// ---------- live socket ----------

export interface LiveBadge {
  phrase_id: string;
  rating: Rating;
  score: number;
}
export interface RoomLive {
  conn: 'idle' | 'connecting' | 'open' | 'reconnecting' | 'refused';
  snapshot: RoomSnapshot | null;
  /** Provisional, from the singer's browser: clip time and running score. */
  progress: { slot: number; t: number; running: number } | null;
  badges: LiveBadge[];
}

const IDLE: RoomLive = { conn: 'idle', snapshot: null, progress: null, badges: [] };
let state: RoomLive = IDLE;
let roomId: string | null = null;
let ws: WebSocket | null = null;
let timers: number[] = [];
let retry = 0;
const listeners = new Set<() => void>();

function set(patch: Partial<RoomLive>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

async function open() {
  if (!roomId) return;
  const id = roomId;
  // Logged-in players authenticate with the Auth0 token as a subprotocol (a query string would reach server logs).
  const token = await bearerToken();
  if (roomId !== id) return; // left while the token was being fetched
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/rooms/${id}`;
  const sock = token ? new WebSocket(url, ['bearer', token]) : new WebSocket(url);
  ws = sock;
  let opened = false;
  sock.onopen = () => {
    opened = true;
    retry = 0;
    set({ conn: 'open' });
    timers.push(window.setInterval(() => sock.readyState === 1 && sock.send('{"type":"heartbeat"}'), 15_000));
  };
  sock.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === 'room_snapshot') {
      const { type: _t, id: _i, ...snap } = ev;
      if (state.snapshot && snap.state_version < state.snapshot.state_version) return; // stale
      const turnChanged = state.snapshot?.match?.active_slot !== snap.match?.active_slot || state.snapshot?.match?.id !== snap.match?.id;
      set({ snapshot: snap, ...(turnChanged ? { progress: null, badges: [] } : {}) });
    } else if (ev.type === 'turn_progress' && ev.data) set({ progress: { slot: ev.slot, t: ev.data.t, running: ev.data.running } });
    else if (ev.type === 'phrase_rating' && ev.data) set({ badges: [...state.badges, ev.data] });
  };
  sock.onclose = () => {
    timers.forEach((t) => clearInterval(t));
    timers = [];
    if (roomId !== id || ws !== sock) return; // left on purpose
    // The server closes with 4403 when we are not in the room (any pre-accept failure): do not loop.
    if (!opened && retry >= 3) return set({ conn: 'refused' });
    set({ conn: 'reconnecting' });
    timers.push(window.setTimeout(() => void open(), Math.min(5000, 500 * 2 ** retry++)));
  };
}

/** Start (or keep) the live connection for a room. The first snapshot comes from `initial` or the socket. */
export function connectRoom(id: string, initial?: RoomSnapshot) {
  if (roomId === id) return;
  leaveRoom();
  roomId = id;
  state = { ...IDLE, conn: 'connecting', snapshot: initial ?? null };
  listeners.forEach((l) => l());
  void open();
}

export function leaveRoom() {
  roomId = null;
  const old = ws;
  ws = null;
  timers.forEach((t) => clearTimeout(t));
  timers = [];
  old?.close();
  set(IDLE);
}

/** The singer's provisional updates; silently dropped while disconnected. */
export function sendLive(type: 'progress' | 'phrase_rating', data: object) {
  if (ws?.readyState === 1) ws.send(JSON.stringify({ type, data }));
}

/** Merge a fresher HTTP snapshot (same ordering rule as the socket). */
export function pushSnapshot(snap: RoomSnapshot) {
  if (!state.snapshot || snap.state_version >= state.snapshot.state_version) set({ snapshot: { ...state.snapshot, ...snap } });
}

export function useRoomLive(): RoomLive {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
  );
}

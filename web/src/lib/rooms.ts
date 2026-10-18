/**
 * Online rooms: the HTTP calls (durable actions) and one shared WebSocket (presence, snapshots, provisional
 * progress). The socket lives at module level so it survives the Sing screen replacing the lobby screen;
 * the singer pushes live progress through `sendLive`. Progress and badges are provisional, only a saved
 * result counts: after any reconnect the fresh snapshot is the truth.
 */
import { useSyncExternalStore } from 'react';
import { bearerToken, request } from './api';
import type { MatchView, NewMatch, Rating, TimeRange } from './types';

export interface RoomSnapshot {
  id: string;
  code: string;
  state: 'lobby' | 'playing' | 'finished' | 'aborted';
  state_version: number;
  visibility: Visibility;
  clip_id: string;
  range: TimeRange | null;
  members: { slot: number; display_name: string; ready: boolean; connected: boolean }[];
  match: MatchView | null;
  /** The caller's own seat; only on HTTP responses, not on shared snapshots. */
  you?: number;
}

export type Visibility = 'public' | 'private';

/** One row of the room list: no code, no password data. */
export interface RoomListItem {
  id: string;
  visibility: Visibility;
  host_name: string;
  clip_id: string;
  players: number;
  created_at: string;
  /** You already sit in this room (rejoin without a password). */
  mine?: boolean;
}

export const PASSWORD_MIN = 3;
export const PASSWORD_MAX = 16;

/** Why a private-room password is not acceptable, or null when it is fine (the server checks the same rule). */
export const passwordProblem = (pw: string): string | null =>
  pw.length < PASSWORD_MIN || pw.length > PASSWORD_MAX ? `Use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters.` : null;

export type RoomTab = 'all' | Visibility;

/** The list as the join screen shows it: the tab, then a case-insensitive match on the host's name. */
export function filterRooms(rooms: RoomListItem[], tab: RoomTab, query: string): RoomListItem[] {
  const q = query.trim().toLowerCase();
  return rooms.filter((r) => (tab === 'all' || r.visibility === tab) && (!q || r.host_name.toLowerCase().includes(q)));
}

const call = <T>(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST') =>
  request<T>(path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });

/** The song is picked inside the room, so a new room starts on the server's default clip. */
export const createRoom = (visibility: Visibility = 'public', password?: string) =>
  call<RoomSnapshot>('/api/rooms', { duet: true, visibility, ...(visibility === 'private' ? { password } : {}) });
export const listRooms = () => call<RoomListItem[]>('/api/rooms');
export const joinRoom = (code: string, password?: string) => call<RoomSnapshot>('/api/rooms/join', { code, password });
export const joinRoomById = (id: string, password?: string) => call<RoomSnapshot>(`/api/rooms/${id}/join`, { password });
export const getRoom = (id: string) => call<RoomSnapshot>(`/api/rooms/${id}`);
export const setReady = (id: string, ready: boolean) => call<RoomSnapshot>(`/api/rooms/${id}/ready`, { ready });
export const setRoomClip = (id: string, clipId: string) => call<RoomSnapshot>(`/api/rooms/${id}/clip`, { clip_id: clipId });
export const setRoomRange = (id: string, range: TimeRange | null) => call<RoomSnapshot>(`/api/rooms/${id}/range`, { range });
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
let generation = 0;
const listeners = new Set<() => void>();
const voiceListeners = new Set<(slot: number, data: VoiceSignal) => void>();

/** Ephemeral signaling only. SDP/ICE must never be persisted with match results. */
export type VoiceSignal = { match_id: string | null; session: string; peer?: string } & (
  { kind: 'ready' } | { kind: 'offer' | 'answer'; sdp: string } |
  { kind: 'ice'; candidate: RTCIceCandidateInit }
);
export const roomLive = () => state;
export function subscribeRoomLive(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function subscribeVoice(listener: (slot: number, data: VoiceSignal) => void) {
  voiceListeners.add(listener);
  return () => { voiceListeners.delete(listener); };
}
export function sendVoice(data: VoiceSignal) {
  if (ws?.readyState === 1) ws.send(JSON.stringify({ type: 'voice_signal', data }));
}

function set(patch: Partial<RoomLive>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

async function open() {
  if (!roomId) return;
  const id = roomId;
  const openedGeneration = generation;
  // Logged-in players authenticate with the Auth0 token as a subprotocol (a query string would reach server logs).
  const token = await bearerToken();
  if (roomId !== id || generation !== openedGeneration) return; // left, including a rejoin to the same ID
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/rooms/${id}`;
  const sock = token ? new WebSocket(url, ['bearer', token]) : new WebSocket(url);
  ws = sock;
  let opened = false;
  sock.onopen = () => {
    if (roomId !== id || ws !== sock) return;
    opened = true;
    retry = 0;
    set({ conn: 'open' });
    timers.push(window.setInterval(() => sock.readyState === 1 && sock.send('{"type":"heartbeat"}'), 15_000));
  };
  sock.onmessage = (m) => {
    if (roomId !== id || ws !== sock) return;
    const ev = JSON.parse(m.data);
    if (ev.type === 'room_snapshot') {
      // On snapshots `id` is the room ID (the server's fields override its event ID).
      const { type: _t, ...snap } = ev;
      if (snap.id !== id) return;
      if (state.snapshot && snap.state_version < state.snapshot.state_version) return; // stale
      const turnChanged = state.snapshot?.match?.active_slot !== snap.match?.active_slot || state.snapshot?.match?.id !== snap.match?.id;
      set({ snapshot: snap, ...(turnChanged ? { progress: null, badges: [] } : {}) });
    } else if (ev.type === 'turn_progress' && ev.data) set({ progress: { slot: ev.slot, t: ev.data.t, running: ev.data.running } });
    else if (ev.type === 'phrase_rating' && ev.data) set({ badges: [...state.badges, ev.data] });
    else if (ev.type === 'voice_signal' && ev.data) voiceListeners.forEach((l) => l(ev.slot, ev.data));
  };
  sock.onclose = () => {
    if (roomId !== id || ws !== sock) return; // an old close must not cancel the replacement's heartbeat
    timers.forEach((t) => clearInterval(t));
    timers = [];
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
  generation++;
  retry = 0;
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
  if (snap.id !== roomId) return; // a late HTTP response from a room we left
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

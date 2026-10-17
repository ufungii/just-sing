/**
 * Typed client for the FastAPI routes documented in api/README.md.
 * Every call goes to the same origin (/api), which the Vite dev server proxies to FastAPI and
 * which FastAPI serves itself in production, so the httpOnly guest cookie just works.
 */
import type { ClipSummary, HistoryItem, MatchView, NewMatch, PhraseScore, Practice, Register, Score, Song } from './types';

/** The API's error envelope, or a network failure (code "network"). Branch on `code`, show `message`. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable: boolean,
  ) {
    super(message);
  }
}

/** Set by the Auth0 bridge (lib/auth.tsx) when someone is logged in; guests leave it null. */
let accessToken: (() => Promise<string | undefined>) | null = null;
export const setAccessTokenProvider = (fn: typeof accessToken) => {
  accessToken = fn;
};

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  try {
    const token = await accessToken?.();
    if (token) headers.set('Authorization', `Bearer ${token}`);
  } catch {
    // token refresh failed: carry on as a guest rather than blocking play
  }
  let res: Response;
  try {
    res = await fetch(path, { credentials: 'same-origin', ...init, headers });
  } catch {
    throw new ApiError(0, 'network', 'Could not reach the server.', true);
  }
  if (res.ok) return (await res.json()) as T;
  let body: { error?: { code: string; message: string; retryable: boolean } } = {};
  try {
    body = await res.json();
  } catch {
    // non-JSON error (e.g. proxy with the API down)
  }
  const e = body.error;
  throw new ApiError(res.status, e?.code ?? 'http_' + res.status, e?.message ?? `Server answered ${res.status}.`, e?.retryable ?? res.status >= 500);
}

/** The Auth0 access token for the current login, or undefined for guests (used by the room WebSocket). */
export async function bearerToken(): Promise<string | undefined> {
  try {
    return await accessToken?.();
  } catch {
    return undefined;
  }
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

// ---------- guest identity ----------

const NAME_KEY = 'just-sing.displayName';

/** The display name this browser last used (the guest cookie itself is httpOnly and unreadable). */
export function savedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? '';
  } catch {
    return '';
  }
}

export async function createGuest(displayName: string): Promise<{ id: string; display_name: string }> {
  const guest = await request<{ id: string; display_name: string }>('/api/guests', json({ display_name: displayName }));
  try {
    localStorage.setItem(NAME_KEY, guest.display_name);
  } catch {
    // storage blocked: the cookie still identifies the guest
  }
  return guest;
}

/** Runs `call`; if the server has no guest session yet, creates one with `displayName` and retries once. */
export async function asGuest<T>(displayName: string, call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (e) {
    if (e instanceof ApiError && e.code === 'not_authenticated') {
      await createGuest(displayName || 'Player');
      return call();
    }
    throw e;
  }
}

// ---------- catalog ----------

export const getReady = () => request<{ catalog: boolean; database: string; pronunciation: string }>('/api/ready');
export const getClips = () => request<ClipSummary[]>('/api/clips');
export const getManifest = (clipId: string) => request<Song>(`/api/clips/${encodeURIComponent(clipId)}/manifest`);
/** Instrumental only; 404 audio_missing when the clip has no installed audio (e.g. the synthetic demo). */
export const audioUrl = (clipId: string) => `/api/clips/${encodeURIComponent(clipId)}/audio`;
export const vocalsUrl = (clipId: string) => `/api/clips/${encodeURIComponent(clipId)}/vocals`;

// ---------- solo play ----------

/** Solo by default; two player names make a local battle (player 1's attempt comes back, player 2's appears after). */
export const createMatch = (clipId: string, players?: [string, string]) =>
  request<NewMatch>('/api/matches', json(players ? { clip_id: clipId, players } : { clip_id: clipId }));
export const beginTurn = (attemptId: string, register: Register, calibrationOffset: number | null) =>
  request<{ attempt_id: string; state: string }>(
    `/api/turns/${attemptId}/begin`,
    json({ register, calibration_offset: calibrationOffset }),
  );
/** Submit the finished phrase results once. Reuse the same key on retry so nothing is counted twice. */
export const submitResult = (attemptId: string, phrases: PhraseScore[], idempotencyKey: string, guideUsed = false) =>
  request<Score>(`/api/turns/${attemptId}/result`, {
    ...json({ phrases, guide_used: guideUsed }),
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
  });
export const getCoach = (attemptId: string) =>
  request<{ status: 'ok' | 'unavailable'; coach_blurb: string | null }>(`/api/turns/${attemptId}/coach`, { method: 'POST' });
export const rematch = (matchId: string) => request<NewMatch>(`/api/matches/${matchId}/rematch`, { method: 'POST' });
export const getMatch = (matchId: string) => request<MatchView>(`/api/matches/${matchId}`);
export const retryTurn = (matchId: string) => request<{ attempt_id: string }>(`/api/matches/${matchId}/retry`, { method: 'POST' });
/** After login: attach this browser's guest history to the account (needs the bearer token and the guest cookie). */
export const claimGuest = () => request<{ id: string; claimed_guest_history: boolean }>('/api/auth/claim', { method: 'POST' });
export const getHistory = () => request<HistoryItem[]>('/api/history');

// ---------- spoken practice ----------

export function submitPractice(clipId: string, phraseId: string, audio: Blob): Promise<Practice> {
  const form = new FormData();
  form.set('clip_id', clipId);
  form.set('phrase_id', phraseId);
  form.set('audio', audio, 'speech.webm');
  return request<Practice>('/api/practice', { method: 'POST', body: form });
}

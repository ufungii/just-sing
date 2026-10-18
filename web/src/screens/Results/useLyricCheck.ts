/**
 * Runs the lyric check for a solo take once and reports its state. The server compares each sung line
 * with the original singer's line; it takes a few seconds and never changes the score.
 */
import { useEffect, useState } from 'react';
import { ApiError, checkLyrics } from '../../lib/api';
import type { LyricStatus } from '../../lib/types';

export type LyricState =
  | { state: 'none' } // no take (battle, online, or an old route)
  | { state: 'loading' }
  | { state: 'ok'; lines: Map<number, LyricStatus> }
  | { state: 'offline'; reason: 'unavailable' | 'busy' | 'network' | 'failed' };

type LyricOutcome = Extract<LyricState, { state: 'ok' | 'offline' }>;

// One upload per take, even if React runs the effect twice or the screen re-mounts.
const pending = new WeakMap<Blob, Promise<LyricOutcome>>();

function run(clipId: string, wav: Blob, offsetS: number) {
  let p = pending.get(wav);
  if (!p) {
    const attempt = () => checkLyrics(clipId, wav, offsetS);
    const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
    p = attempt()
      .catch(async (e) => {
        // The speech model is shared with practice; one retry after a short wait covers a busy moment.
        if (!(e instanceof ApiError && e.code === 'pronunciation_busy')) throw e;
        await wait(4000);
        return attempt();
      })
      .then((r): LyricOutcome => r.status === 'ok'
        ? { state: 'ok', lines: new Map(r.lines.map((l) => [l.line_index, l.status])) }
        : { state: 'offline', reason: r.status === 'unavailable' ? 'unavailable' : 'failed' })
      .catch((e): LyricOutcome => ({ state: 'offline', reason:
        e instanceof ApiError && e.code === 'pronunciation_busy' ? 'busy'
          : e instanceof ApiError && e.code === 'network' ? 'network' : 'failed' }));
    pending.set(wav, p);
  }
  return p;
}

/** Keep real failure reasons instead of describing every failed check as offline. */
export async function resolveLyricCheck(
  clipId: string,
  take: { wav: Blob; offsetS: number } | null | undefined,
  live?: Promise<Map<number, LyricStatus> | null> | null,
): Promise<LyricOutcome> {
  const lines = live ? await live.catch(() => null) : null;
  if (lines) return { state: 'ok', lines };
  return take ? run(clipId, take.wav, take.offsetS) : { state: 'offline', reason: 'failed' };
}

/**
 * `live` holds the lines already checked during the song; when it is missing or incomplete, the whole
 * take is uploaded instead (the slower path).
 */
export function useLyricCheck(
  clipId: string,
  take: { wav: Blob; offsetS: number } | null | undefined,
  live?: Promise<Map<number, LyricStatus> | null> | null,
): LyricState {
  const [st, setSt] = useState<LyricState>(take || live ? { state: 'loading' } : { state: 'none' });
  useEffect(() => {
    if (!take && !live) return;
    let alive = true;
    (async () => {
      const result = await resolveLyricCheck(clipId, take, live);
      if (alive) setSt(result);
    })();
    return () => {
      alive = false;
    };
  }, [clipId, take, live]);
  return st;
}

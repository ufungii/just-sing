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
  | { state: 'offline' }; // checker or fingerprints missing, busy, or failed: no result, not a bad one

// One upload per take, even if React runs the effect twice or the screen re-mounts.
const pending = new WeakMap<Blob, Promise<Map<number, LyricStatus> | null>>();

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
      .then((r) => (r.status === 'ok' ? new Map(r.lines.map((l) => [l.line_index, l.status])) : null))
      .catch(() => null);
    pending.set(wav, p);
  }
  return p;
}

export function useLyricCheck(clipId: string, take: { wav: Blob; offsetS: number } | null | undefined): LyricState {
  const [st, setSt] = useState<LyricState>(take ? { state: 'loading' } : { state: 'none' });
  useEffect(() => {
    if (!take) return;
    let live = true;
    run(clipId, take.wav, take.offsetS).then((lines) => live && setSt(lines ? { state: 'ok', lines } : { state: 'offline' }));
    return () => {
      live = false;
    };
  }, [clipId, take]);
  return st;
}

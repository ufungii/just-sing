/**
 * Saved solo results for this browser's guest (or logged-in) identity, newest first. Clicking a
 * row loads that match and shows the accepted attempt's breakdown with the same phrase rows as
 * the results screen. No guest cookie yet is a normal "nothing saved here" state, not an error.
 */
import { useCallback, useEffect, useState } from 'react';
import { ApiError, getClips, getHistory, getMatch } from '../../lib/api';
import type { ClipSummary, HistoryItem, Score } from '../../lib/types';
import { useNav } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell } from '../../ui';
import { PhraseChips, ScoreSummary } from '../Results/PhraseChips';
import { useManifest } from '../Results/useManifest';
import './History.css';

type List =
  | { state: 'loading' }
  | { state: 'ok'; items: HistoryItem[]; clips: Map<string, ClipSummary> }
  | { state: 'no-identity' } // no guest cookie in this browser yet
  | { state: 'error'; message: string };

type Detail =
  | { state: 'closed' }
  | { state: 'loading'; matchId: string }
  | { state: 'ok'; matchId: string; score: Score }
  | { state: 'error'; matchId: string; message: string };

const dateFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

export function History() {
  const nav = useNav();
  const [list, setList] = useState<List>({ state: 'loading' });
  const [detail, setDetail] = useState<Detail>({ state: 'closed' });

  const load = useCallback(async () => {
    setList({ state: 'loading' });
    try {
      // Titles are nice to have: a catalog failure should not hide the saved scores.
      const [items, clips] = await Promise.all([getHistory(), getClips().catch(() => [] as ClipSummary[])]);
      setList({ state: 'ok', items, clips: new Map(clips.map((c) => [c.id, c])) });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'not_authenticated') setList({ state: 'no-identity' });
      else setList({ state: 'error', message: e instanceof ApiError ? e.message : 'Something went wrong.' });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function toggle(matchId: string) {
    if (detail.state !== 'closed' && detail.matchId === matchId) setDetail({ state: 'closed' }); // fold back up
    else void open(matchId);
  }

  async function open(matchId: string) {
    setDetail({ state: 'loading', matchId });
    try {
      const match = await getMatch(matchId);
      const score = match.attempts.find((a) => a.state === 'accepted' && a.score)?.score;
      setDetail(
        score
          ? { state: 'ok', matchId, score }
          : { state: 'error', matchId, message: 'This match has no accepted score.' },
      );
    } catch (e) {
      setDetail({ state: 'error', matchId, message: e instanceof ApiError ? e.message : 'Could not load this match.' });
    }
  }

  const soloButton = (
    <PixelButton tone="hot" size="lg" onClick={() => nav.go({ name: 'solo' })}>
      ▶ SOLO SING
    </PixelButton>
  );

  return (
    <ScreenShell title="HISTORY" kao="★(＾▽＾)★">
      {list.state === 'loading' && <Notice>loading your saved songs…</Notice>}

      {list.state === 'error' && (
        <Notice
          tone="error"
          action={
            <PixelButton tone="paper" size="sm" onClick={() => void load()}>
              RETRY
            </PixelButton>
          }
        >
          Couldn't load your history. {list.message}
        </Notice>
      )}

      {(list.state === 'no-identity' || (list.state === 'ok' && list.items.length === 0)) && (
        <Panel className="history-empty">
          <span className="history-empty__kao" aria-hidden="true">
            (｡&gt;﹏&lt;｡)
          </span>
          <p>
            {list.state === 'no-identity'
              ? 'No saved history in this browser yet.'
              : 'Nothing saved yet. Sing a song and it shows up here!'}
          </p>
          {soloButton}
        </Panel>
      )}

      {list.state === 'ok' && list.items.length > 0 && (
        <ul className="history-list">
          {list.items.map((item) => {
            const clip = list.clips.get(item.clip_id);
            const isOpen = detail.state !== 'closed' && detail.matchId === item.match_id;
            return (
              <li key={item.match_id}>
                <button
                  type="button"
                  className={isOpen ? 'history-row is-open' : 'history-row'}
                  aria-expanded={isOpen}
                  onClick={() => toggle(item.match_id)}
                >
                  <span className="history-row__clip">
                    <span className="history-row__title">{clip?.title ?? item.clip_id}</span>
                    {clip && <span className="history-row__artist">{clip.artist}</span>}
                  </span>
                  <span className="history-row__date">{dateFmt.format(new Date(item.created_at))}</span>
                  <span className="history-row__total">{Math.round(item.total)}</span>
                  <span className="history-row__caret" aria-hidden="true">
                    {isOpen ? '▼' : '▶'}
                  </span>
                </button>
                {isOpen && <MatchDetail detail={detail} clipId={item.clip_id} onRetry={() => void open(item.match_id)} />}
              </li>
            );
          })}
        </ul>
      )}
    </ScreenShell>
  );
}

function MatchDetail({ detail, clipId, onRetry }: { detail: Detail; clipId: string; onRetry: () => void }) {
  const song = useManifest(clipId);
  return (
    <div className="history-detail">
      {detail.state === 'loading' && <Notice>loading this match…</Notice>}
      {detail.state === 'error' && (
        <Notice
          tone="error"
          action={
            <PixelButton tone="paper" size="sm" onClick={onRetry}>
              RETRY
            </PixelButton>
          }
        >
          {detail.message}
        </Notice>
      )}
      {detail.state === 'ok' && (
        <>
          <ScoreSummary total={detail.score.total} pitch={detail.score.pitch} timing={detail.score.timing} guided={detail.score.guided} />
          <PhraseChips phrases={detail.score.phrases} song={song} />
        </>
      )}
    </div>
  );
}

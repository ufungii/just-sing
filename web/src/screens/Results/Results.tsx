/**
 * Results after a solo turn: total, pitch and timing, a row per phrase, the save status, and
 * Mic-chan's coaching blurb. Totals come from the server when the turn was saved (it recomputes
 * them with the same config) and from the local phrase scores otherwise. The coach only ever
 * writes words about the measured numbers; it never produces a score.
 */
import { useState } from 'react';
import { asGuest, rematch } from '../../lib/api';
import { useNav, type SingResult } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell } from '../../ui';
import { CoachPanel } from './CoachPanel';
import { PhraseChips, ScoreSummary, type LyricTally } from './PhraseChips';
import { useLyricCheck, type LyricState } from './useLyricCheck';
import { useManifest } from './useManifest';
import './Results.css';

export function Results({ result }: { result: SingResult }) {
  const nav = useNav();
  const { setup, saved } = result;
  const totals = saved ?? result.local;
  const phrases = saved?.phrases ?? result.phrases;

  const song = useManifest(setup.clipId);
  const lyrics = useLyricCheck(setup.clipId, result.take);
  const [starting, setStarting] = useState(false);

  /** Rematch on the server when we can, so the next take saves too; otherwise sing unsaved. */
  async function singAgain() {
    setStarting(true);
    let match = null;
    if (setup.match) {
      const matchId = setup.match.matchId;
      try {
        const next = await asGuest(setup.playerName, () => rematch(matchId));
        match = { matchId: next.match_id, attemptId: next.attempt_id };
      } catch {
        match = null; // server or database down: still let them sing
      }
    }
    nav.go({ name: 'sing', setup: { ...setup, runId: crypto.randomUUID(), match } });
  }

  return (
    <ScreenShell title="RESULTS" kao="ヾ(＾∇＾)">
      <div className="results-top">
        <Panel label={song ? `${song.title} / ${song.artist}` : 'YOUR SCORE'} className="results-score">
          <ScoreSummary total={totals.total} pitch={totals.pitch} timing={totals.timing} guided={saved?.guided} range={saved ? saved.range : setup.range} lyrics={lyricTally(lyrics)} />
          {saved ? (
            <Notice tone="ok">saved to your history ♡</Notice>
          ) : (
            <Notice tone="warn">
              Not saved: {result.saveError ?? 'the server did not accept this turn.'} Your score above is from this
              device.
            </Notice>
          )}
        </Panel>

        <CoachPanel attemptId={saved ? setup.match?.attemptId ?? null : null} />
      </div>

      <Panel label="PHRASES">
        <LyricSummary lyrics={lyrics} />
        <PhraseChips
          phrases={phrases}
          song={song}
          lyrics={lyrics.state === 'ok' ? lyrics.lines : undefined}
          onPractice={(phraseId) => nav.go({ name: 'practice', start: { clipId: setup.clipId, phraseId } })}
        />
      </Panel>

      <div className="results-actions">
        <PixelButton tone="hot" size="lg" onClick={singAgain} disabled={starting}>
          {starting ? 'STARTING…' : '▶ SING AGAIN'}
        </PixelButton>
        <PixelButton tone="sky" size="lg" onClick={() => nav.go({ name: 'solo' })}>
          ♪ NEW SONG
        </PixelButton>
        <PixelButton tone="mint" size="lg" onClick={() => nav.go({ name: 'history' })}>
          ★ HISTORY
        </PixelButton>
      </div>

      <p className="results-fine">
        Rating cutoffs come from real takes measured against the original singer (one singer so far), so they may still change.
      </p>
    </ScreenShell>
  );
}

/** Matched / graded lines for the LYRICS bar; 'unavailable' when the check could not run; null while waiting or not run. */
function lyricTally(lyrics: LyricState): LyricTally | 'unavailable' | null {
  if (lyrics.state === 'offline') return 'unavailable';
  if (lyrics.state !== 'ok') return null;
  const graded = [...lyrics.lines.values()].filter((s) => s === 'match' || s === 'unclear');
  return { matched: graded.filter((s) => s === 'match').length, graded: graded.length };
}

/** One line above the phrase rows: the lyric check's state, plus what it is and isn't. */
function LyricSummary({ lyrics }: { lyrics: LyricState }) {
  if (lyrics.state === 'none') return null;
  if (lyrics.state === 'loading') return <p className="results-lyrics" aria-live="polite">checking your lyrics against the original singer… (・_・;)</p>;
  if (lyrics.state === 'offline') return <p className="results-lyrics">lyric check is offline right now ♪ your scores are all here, though!</p>;
  const graded = [...lyrics.lines.values()].filter((s) => s === 'match' || s === 'unclear');
  const matched = graded.filter((s) => s === 'match').length;
  return (
    <p className="results-lyrics" aria-live="polite">
      {graded.length ? <><strong>{matched} of {graded.length}</strong> sung lines sounded like the original lyrics ♡ </> : <>no lines long enough to check this time. </>}
      <span className="results-lyrics__fine">Compared with the original singer by a speech model. Automated, not checked by a fluent speaker, and not part of your score.</span>
    </p>
  );
}

/** Asks the server for the coaching blurb of a saved attempt. */

/**
 * Results after a solo turn: total, pitch and timing, a row per phrase, the save status, and
 * Mic-chan's coaching blurb. Totals come from the server when the turn was saved (it recomputes
 * them with the same config) and from the local phrase scores otherwise. The coach only ever
 * writes words about the measured numbers; it never produces a score.
 */
import { useEffect, useState } from 'react';
import { MicChan } from '../../components/pixel';
import { asGuest, getCoach, rematch } from '../../lib/api';
import { useNav, type SingResult } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell } from '../../ui';
import { PhraseChips, ScoreSummary } from './PhraseChips';
import { useLyricCheck, type LyricState } from './useLyricCheck';
import { useManifest } from './useManifest';
import './Results.css';

type Coach =
  | { state: 'none' } // turn not saved, so there is nothing to coach on the server
  | { state: 'loading' }
  | { state: 'ok'; text: string }
  | { state: 'offline' }; // Gemini unavailable or the call failed: not an error, just no blurb

export function Results({ result }: { result: SingResult }) {
  const nav = useNav();
  const { setup, saved } = result;
  const totals = saved ?? result.local;
  const phrases = saved?.phrases ?? result.phrases;

  const song = useManifest(setup.clipId);
  const coach = useCoach(saved ? setup.match?.attemptId ?? null : null);
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
          <ScoreSummary total={totals.total} pitch={totals.pitch} timing={totals.timing} guided={saved?.guided} range={saved ? saved.range : setup.range} />
          {saved ? (
            <Notice tone="ok">saved to your history ♡</Notice>
          ) : (
            <Notice tone="warn">
              Not saved: {result.saveError ?? 'the server did not accept this turn.'} Your score above is from this
              device.
            </Notice>
          )}
        </Panel>

        <Panel tone="lav" label="COACH" className="results-coach">
          <div className="results-coach__row">
            <MicChan className="results-coach__mascot" />
            <p className="results-bubble" aria-live="polite">
              {coach.state === 'ok' && coach.text}
              {coach.state === 'loading' && <span className="results-bubble__wait">thinking (・_・;) …</span>}
              {coach.state === 'offline' && <>coach is offline right now ♪ your scores are all here, though!</>}
              {coach.state === 'none' && <>save a turn and I'll leave you a tip ♡</>}
            </p>
          </div>
          {coach.state === 'ok' && <p className="results-fine">Written by Gemini from your measured scores only.</p>}
        </Panel>
      </div>

      <Panel label="PHRASES">
        <LyricSummary lyrics={lyrics} />
        <PhraseChips phrases={phrases} song={song} lyrics={lyrics.state === 'ok' ? lyrics.lines : undefined} />
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
        Ratings are provisional: the thresholds will be recalibrated once the reference scoring engine and its evals land.
      </p>
    </ScreenShell>
  );
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
function useCoach(attemptId: string | null): Coach {
  const [coach, setCoach] = useState<Coach>(attemptId ? { state: 'loading' } : { state: 'none' });
  useEffect(() => {
    if (!attemptId) return;
    let live = true;
    getCoach(attemptId).then(
      (r) => live && setCoach(r.status === 'ok' && r.coach_blurb ? { state: 'ok', text: r.coach_blurb } : { state: 'offline' }),
      () => live && setCoach({ state: 'offline' }),
    );
    return () => {
      live = false;
    };
  }, [attemptId]);
  return coach;
}

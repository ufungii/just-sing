/**
 * Results after a solo turn: total, pitch and timing, a row per phrase, the save status, and
 * Mic-chan's coaching blurb. Totals come from the server when the turn was saved (it recomputes
 * them with the same config) and from the local phrase scores otherwise. The coach only ever
 * writes words about the measured numbers; it never produces a score.
 */
import { useMemo, useState } from 'react';
import { asGuest, rematch } from '../../lib/api';
import { includedPhrases } from '../../components/timeline/range';
import { useNav, type SingResult } from '../../routes';
import { buildTargetTrack, phraseWeights, pronunciationScore } from '../../scoring';
import type { Song } from '../../lib/types';
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
  const lyrics = useLyricCheck(setup.clipId, result.take, result.lyricsLive);
  const lyricSummary = useMemo(() => summariseLyrics(lyrics, song, setup.register, setup.range), [lyrics, song, setup.register, setup.range]);
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
          <ScoreSummary total={totals.total} pitch={totals.pitch} timing={totals.timing} guided={saved?.guided} range={saved ? saved.range : setup.range} lyrics={lyricSummary} />
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

/**
 * The LYRICS bar's numbers: matched / graded lines plus the 0-100 pronunciation score, weighted by each
 * line's scoreable frames exactly as the 0.4.0 total does (scoring/score.ts pronunciationScore).
 * 'unavailable' when the check could not run; null while it is still running or was not run.
 */
function summariseLyrics(lyrics: LyricState, song: Song | null, register: SingResult['setup']['register'], range: SingResult['setup']['range']): LyricTally | 'unavailable' | null {
  if (lyrics.state === 'offline') return 'unavailable';
  if (lyrics.state !== 'ok') return null;
  const graded = [...lyrics.lines.values()].filter((s) => s === 'match' || s === 'unclear');
  let score: number | null = null;
  if (song) {
    const byPhrase = phraseWeights(includedPhrases(song.phrases, range), buildTargetTrack(song, register));
    const byLine = new Map<number, number>();
    for (const p of song.phrases) byLine.set(p.line_index, (byLine.get(p.line_index) ?? 0) + (byPhrase.get(p.id) ?? 0));
    score = pronunciationScore(lyrics.lines, byLine);
  }
  return { matched: graded.filter((s) => s === 'match').length, graded: graded.length, score };
}

/** One line above the phrase rows: the lyric check's state, plus what it is and isn't. */
function LyricSummary({ lyrics }: { lyrics: LyricState }) {
  if (lyrics.state === 'none') return null;
  if (lyrics.state === 'loading') return <p className="results-lyrics" aria-live="polite">checking your lyrics against the original singer… (・_・;)</p>;
  if (lyrics.state === 'offline') {
    const message = {
      unavailable: 'Lyric checking is unavailable for this song right now.',
      busy: 'The lyric checker is busy. This take could not be checked.',
      network: 'Could not reach the lyric checker. This take could not be checked.',
      failed: 'The lyric check failed. This take could not be checked.',
    }[lyrics.reason];
    return <p className="results-lyrics">{message} Your pitch and timing scores are ready.</p>;
  }
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

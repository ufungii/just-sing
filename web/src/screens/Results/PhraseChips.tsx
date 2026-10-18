/**
 * Score pieces shared by Results and History: the big layered total, the PITCH / TIMING bars,
 * and one row per phrase with its lyric and rating. Display only: every number shown here was
 * computed by the scoring engine (locally or on the server), never by an LLM.
 */
import type { LyricStatus, PhraseScore, Rating, Song, TimeRange } from '../../lib/types';
import { rangeLabel } from '../../components/timeline/range';
import { practicePhrases } from '../../lib/practicePhrases';
import './PhraseChips.css';

export const RATING_LABEL: Record<Rating, string> = {
  perfect: 'PERFECT!',
  great: 'GREAT',
  okay: 'OKAY',
  bad: 'BAD',
  miss: 'MISS',
};

/** Scores arrive as 0-100 floats; the screen shows whole numbers. */
const whole = (n: number) => Math.round(Math.min(100, Math.max(0, n)));

/** The big 3D pixel total, layered like the screen titles. */
export function BigScore({ total }: { total: number }) {
  const text = String(whole(total));
  return (
    <div className="results-big" role="img" aria-label={`Total score ${text} out of 100`}>
      <span className="results-big__label" aria-hidden="true">TOTAL</span>
      <span className="results-big__num" aria-hidden="true">
        {text}
        <span className="l3">{text}</span>
        <span className="l2">{text}</span>
        <span className="l1">{text}</span>
        <span className="l0">{text}</span>
      </span>
    </div>
  );
}

/** A chunky segmented bar: 20 pixel blocks, each worth 5 points. `shown` replaces the number at the end. */
export function ScoreBar({ label, value, tone, shown }: { label: string; value: number; tone: 'sky' | 'mint' | 'lav'; shown?: string }) {
  const v = whole(value);
  const lit = Math.round(v / 5);
  return (
    <div className={`results-bar results-bar--${tone}`}>
      <span className="results-bar__label">{label}</span>
      <span className="results-bar__track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={v}>
        {Array.from({ length: 20 }, (_, i) => (
          <span key={i} className={i < lit ? 'results-bar__px is-lit' : 'results-bar__px'} />
        ))}
      </span>
      <span className="results-bar__num">{shown ?? v}</span>
    </div>
  );
}

/**
 * Lines whose words matched the original singer, out of the lines the lyric check could grade, and the
 * 0-100 pronunciation score over them (the same calculation as the 0.4.0 turn total: each line counts by
 * its length, "match" earns 100 and everything else 0). `score` is null when it could not be computed.
 */
export interface LyricTally {
  matched: number;
  graded: number;
  score: number | null;
}

/**
 * A plain-words verdict for the pronunciation score. Display-only defaults picked to fit what we measured
 * (real singing matched 83-89% of lines, a real hum 0-17%); one or two singers, so not validated.
 */
export function pronunciationVerdict(score: number): 'CLEAR' | 'MIXED' | 'UNCLEAR' {
  return score >= 80 ? 'CLEAR' : score >= 50 ? 'MIXED' : 'UNCLEAR';
}

/**
 * Total plus pitch and timing bars, as one block. `lyrics` adds a LYRICS bar (the pronunciation score from
 * the lyric check) with a plain-words verdict and the matched line count, or "—" when the check could not
 * run. The total shown is whatever the caller passes in; it is never derived here.
 */
export function ScoreSummary({ total, pitch, timing, guided, range, lyrics }: { total: number; pitch: number; timing: number; guided?: boolean; range?: TimeRange | null; lyrics?: LyricTally | 'unavailable' | null }) {
  return (
    <div className="results-summary">
      {range && <p className="solo-hint">Practice section · {rangeLabel(range)} · kept off the leaderboard.</p>}
      {guided && <p className="solo-hint">Guide vocals on: this run is kept off the leaderboard.</p>}
      <BigScore total={total} />
      <div className="results-summary__bars">
        <ScoreBar label="PITCH" value={pitch} tone="sky" />
        <ScoreBar label="TIMING" value={timing} tone="mint" />
        {lyrics === 'unavailable' && (
          <>
            <ScoreBar label="LYRICS" value={0} tone="lav" shown="—" />
            <p className="results-bar__note">Lyrics not checked this time.</p>
          </>
        )}
        {lyrics && lyrics !== 'unavailable' && lyrics.graded > 0 && (
          <>
            <ScoreBar label="LYRICS" value={lyrics.score ?? (100 * lyrics.matched) / lyrics.graded} tone="lav" shown={String(whole(lyrics.score ?? (100 * lyrics.matched) / lyrics.graded))} />
            <p className="results-bar__note">
              <strong>Pronunciation: {pronunciationVerdict(lyrics.score ?? (100 * lyrics.matched) / lyrics.graded)}</strong>
              {' · '}{lyrics.matched} of {lyrics.graded} sung lines sounded like the original. Automated, not validated by a fluent speaker.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

/** Lyric-check tags. "unclear" is a soft hint, never "wrong": the check is automated and line level. */
const LYRIC_TAG: Partial<Record<LyricStatus, { label: string; title: string }>> = {
  match: { label: 'LYRICS ♪', title: 'Sounded like the original singer’s words for this line' },
  unclear: { label: 'words?', title: 'The words on this line were hard to make out' },
  not_sung: { label: 'not sung', title: 'We didn’t hear singing on this line' },
};

/**
 * One row per phrase. `song` supplies the lyric for each phrase id; while it is loading (or if it
 * failed) rows fall back to the phrase number so the scores are still readable. `lyrics` (optional)
 * is the lyric check by manifest line index; it only decorates the lyric and never touches the score.
 */
export function PhraseChips({ phrases, song, lyrics, onPractice }: {
  phrases: PhraseScore[];
  song: Song | null;
  lyrics?: Map<number, LyricStatus>;
  /** When set, lines whose words were unclear get a button to practise them out loud. */
  onPractice?: (phraseId: string) => void;
}) {
  const speakable = new Set(song ? practicePhrases(song).map((p) => p.id) : []);
  if (phrases.length === 0) return <p className="results-empty">No phrases were rated in this turn.</p>;
  return (
    <ol className="results-phrases">
      {phrases.map((p, i) => {
        const phrase = song?.phrases.find((ph) => ph.id === p.phrase_id);
        const line = phrase ? song?.lines[phrase.line_index] : undefined;
        const lyric = phrase ? lyrics?.get(phrase.line_index) : undefined;
        const tag = lyric ? LYRIC_TAG[lyric] : undefined;
        return (
          <li key={p.phrase_id} className={`results-phrase results-phrase--${p.rating}`}>
            <span className="results-phrase__n">{String(i + 1).padStart(2, '0')}</span>
            <span className="results-phrase__lyric">
              {line ? (
                <>
                  <span className="results-phrase__ko-row">
                    <span className={lyric ? `results-phrase__ko results-lyric--${lyric}` : 'results-phrase__ko'} lang="ko">{line.text}</span>
                    {tag && <span className={`results-lyric-tag results-lyric-tag--${lyric}`} title={tag.title}>{tag.label}</span>}
                    {lyric === 'unclear' && onPractice && speakable.has(p.phrase_id) && (
                      <button type="button" className="results-say" onClick={() => onPractice(p.phrase_id)} title="Practise saying this line out loud in SAY IT RIGHT">
                        SAY IT ▶
                      </button>
                    )}
                  </span>
                  <span className="results-phrase__rom">{line.romanized}</span>
                </>
              ) : (
                <span className="results-phrase__rom">phrase {p.phrase_id}</span>
              )}
            </span>
            <span className="results-phrase__stats">
              <span title="pitch">P {whole(p.pitch)}</span>
              <span title="timing">T {p.timing === null ? '–' : whole(p.timing)}</span>
              <span title="sung coverage">C {whole(p.coverage * 100)}%</span>
            </span>
            <span className={`results-rating results-rating--${p.rating}`}>{RATING_LABEL[p.rating]}</span>
          </li>
        );
      })}
    </ol>
  );
}

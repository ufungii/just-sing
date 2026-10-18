/**
 * Lyrics under the lane: the current line with karaoke word highlighting from the manifest's word
 * times, optional romanization and translation, and the next line dimmed. Above them, the line just
 * sung shows its live lyric check as it arrives (about 2 s after the line ends): mint when the words
 * sounded like the original singer, a wavy underline when they were unclear.
 */
import type { CSSProperties } from 'react';
import type { Line, LyricStatus, Word } from '../../lib/types';

/** Line verdicts from the live lyric check, keyed by the Line object; 'checking' while the server works on it. */
export type LineVerdicts = Map<Line, LyricStatus | 'checking'>;

const VERDICT_TAG: Partial<Record<LyricStatus | 'checking', string>> = {
  match: 'LYRICS ✓',
  unclear: 'words?',
  not_sung: 'not sung',
  checking: 'checking…',
};

/** The most recent line that has finished by time t, or -1. */
export function lastSungLine(lines: Line[], t: number): number {
  let idx = -1;
  for (let i = 0; i < lines.length; i++) if (t >= lines[i].end) idx = i;
  return idx;
}

/** Latest line entrance at playback time t. Read-ahead belongs in NEXT, including during rests. */
export function currentLine(lines: Line[], t: number): number {
  let idx = -1;
  for (let i = 0; i < lines.length; i++) if (t >= lines[i].start) idx = i;
  return idx;
}

const progress = (w: Word, t: number) => Math.max(0, Math.min(1, (t - w.start) / Math.max(0.01, w.end - w.start)));

function Words({ words, t, className }: { words: { text: string; start: number; end: number }[]; t: number; className: string }) {
  return (
    <p className={className}>
      {words.map((w, i) => (
        <span key={i} className="sing-word" style={{ '--p': progress(w, t) } as CSSProperties}>
          {w.text}
        </span>
      ))}
    </p>
  );
}

export function Lyrics({ lines, t, showRoman, showTrans, verdicts }: { lines: Line[]; t: number; showRoman: boolean; showTrans: boolean; verdicts?: LineVerdicts }) {
  const idx = currentLine(lines, t);
  const sung = lastSungLine(lines, t);
  const last = sung >= 0 ? lines[sung] : null;
  const verdict = last ? verdicts?.get(last) : undefined;
  const line = idx >= 0 ? lines[idx] : null;
  const next = lines[idx + 1];
  // Highlight romanization word by word when it splits into as many words as the Hangul line.
  const roman = line?.romanized.split(/\s+/).filter(Boolean) ?? [];
  const romanWords = line && roman.length === line.words.length ? line.words.map((w, i) => ({ ...w, text: roman[i] })) : null;
  const done = line && t >= line.end;

  return (
    <div className="sing-lyrics" aria-live="off">
      {last && verdict && verdict !== 'not_covered' && (
        <p className={`sing-lyrics__last is-${verdict}`} title="Lyric check for the line you just sang">
          <span className="sing-lyrics__last-text" lang="ko">{last.text}</span>
          <span className="sing-lyrics__last-tag">{VERDICT_TAG[verdict]}</span>
        </p>
      )}
      {line && !done ? (
        <>
          <Words className="sing-lyrics__ko" words={line.words.length ? line.words : [{ text: line.text, start: line.start, end: line.end }]} t={t} />
          {showRoman &&
            (romanWords ? <Words className="sing-lyrics__roman" words={romanWords} t={t} /> : <p className="sing-lyrics__roman">{line.romanized}</p>)}
          {showTrans && <p className="sing-lyrics__trans">{line.translation}</p>}
        </>
      ) : (
        <p className="sing-lyrics__rest ui-kao" aria-label="instrumental">
          ♫⋆｡♪ ₊˚♬ﾟ.
        </p>
      )}
      {next && (
        <p className="sing-lyrics__next">
          <span className="sing-lyrics__next-tag">NEXT</span> {next.text}
          {showRoman && <span className="sing-lyrics__next-roman"> {next.romanized}</span>}
        </p>
      )}
    </div>
  );
}

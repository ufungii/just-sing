/**
 * Lyrics under the lane: the current line with karaoke word highlighting from the manifest's word
 * times, optional romanization and translation, and the next line dimmed.
 */
import type { CSSProperties } from 'react';
import type { Line, Word } from '../../lib/types';

/** Show a line this many seconds before it starts, so the singer can read ahead. */
const LEAD = 0.6;

/** Index of the line to show at clip time t (the last line whose lead-in has begun), or -1 before the first. */
export function currentLine(lines: Line[], t: number): number {
  let idx = -1;
  for (let i = 0; i < lines.length; i++) if (t >= lines[i].start - LEAD) idx = i;
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

export function Lyrics({ lines, t, showRoman, showTrans }: { lines: Line[]; t: number; showRoman: boolean; showTrans: boolean }) {
  const idx = currentLine(lines, t);
  const line = idx >= 0 ? lines[idx] : null;
  const next = lines[idx + 1];
  // Highlight romanization word by word when it splits into as many words as the Hangul line.
  const roman = line?.romanized.split(/\s+/).filter(Boolean) ?? [];
  const romanWords = line && roman.length === line.words.length ? line.words.map((w, i) => ({ ...w, text: roman[i] })) : null;
  const done = line && t > line.end + 0.3;

  return (
    <div className="sing-lyrics" aria-live="off">
      {line && !done ? (
        <>
          <Words className="sing-lyrics__ko" words={line.words.length ? line.words : [{ text: line.text, start: line.start, end: line.end }]} t={t} />
          {showRoman &&
            (romanWords ? <Words className="sing-lyrics__roman" words={romanWords} t={t} /> : <p className="sing-lyrics__roman">{line.romanized}</p>)}
          {showTrans && <p className="sing-lyrics__trans">{line.translation}</p>}
        </>
      ) : (
        <p className="sing-lyrics__rest ui-kao" aria-label="instrumental">
          ♪ ・ ♪ ・ ♪
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

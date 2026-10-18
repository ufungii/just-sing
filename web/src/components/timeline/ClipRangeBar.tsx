import { useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';
import type { Phrase, TimeRange } from '../../lib/types';
import { boundaries, includedPhrases, snapBoundary } from './range';
import './ClipRangeBar.css';

type Drag = { mode: 'start' | 'end' | 'move'; grabOffset: number };

/** m:ss for a time in seconds. */
export const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

/**
 * The player-facing section picker: one bar for the whole song, always the width of its panel
 * (no sideways scrolling). The highlighted part is what gets sung. Drag either handle, drag the
 * highlight to slide it, or click the bar to move the nearest handle there. Handles snap to whole
 * phrases while dragging, so what you see is exactly what will be scored. Sung parts of the song
 * show as soft blocks on the bar; the lyric the section starts on is shown underneath.
 */
export function ClipRangeBar({
  duration,
  phrases,
  lines,
  range,
  onChange,
  onCommit,
  disabled = false,
  playhead = null,
}: {
  duration: number;
  phrases: Pick<Phrase, 'start' | 'end'>[];
  lines: { start: number; end: number; text: string }[];
  range: TimeRange | null;
  /** Live updates while dragging (already snapped). Omit for a read-only bar. */
  onChange?: (range: TimeRange) => void;
  /** A finished drag, click or key press. */
  onCommit?: (range: TimeRange) => void;
  disabled?: boolean;
  playhead?: number | null;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const editable = !!onChange && !disabled;
  const sorted = [...phrases].sort((a, b) => a.start - b.start);
  // No section means the whole song.
  const start = range?.start ?? 0;
  const end = range?.end ?? duration;
  const pct = (t: number) => `${(Math.min(Math.max(t / duration, 0), 1) * 100).toFixed(3)}%`;

  /** Song time under a pointer x position. */
  const timeAt = (clientX: number) => {
    const box = track.current!.getBoundingClientRect();
    return Math.min(Math.max((clientX - box.left) / box.width, 0), 1) * duration;
  };

  /** Snap a candidate section to whole phrases, keeping at least one phrase inside. */
  const snap = (mode: Drag['mode'], t: number, len = end - start): TimeRange => {
    if (!sorted.length) return { start, end };
    if (mode === 'start') return { start: snapBoundary(boundaries(sorted, { start, end }, 'start'), t), end };
    if (mode === 'end') return { start, end: snapBoundary(boundaries(sorted, { start, end }, 'end'), t) };
    // Slide: snap the new start to any phrase start, then the end to the phrase end nearest the old length.
    const s = snapBoundary(sorted.map((p) => p.start), Math.min(Math.max(t, 0), duration - len));
    const ends = sorted.filter((p) => p.start >= s).map((p) => p.end);
    return { start: s, end: snapBoundary(ends, s + len) };
  };

  const begin = (mode: Drag['mode']) => (e: PointerEvent<HTMLElement>) => {
    if (!editable) return;
    e.preventDefault();
    e.stopPropagation();
    track.current!.setPointerCapture(e.pointerId);
    setDrag({ mode, grabOffset: mode === 'move' ? timeAt(e.clientX) - start : 0 });
  };

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    onChange?.(snap(drag.mode, timeAt(e.clientX) - drag.grabOffset));
  };

  const finish = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const next = snap(drag.mode, timeAt(e.clientX) - drag.grabOffset);
    setDrag(null);
    onCommit?.(next);
  };

  // Clicking the bar itself (not a handle or the highlight) moves the nearer handle to that spot.
  const onTrackDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!editable || e.target !== e.currentTarget) return;
    const t = timeAt(e.clientX);
    const mode = Math.abs(t - start) <= Math.abs(t - end) ? 'start' : 'end';
    track.current!.setPointerCapture(e.pointerId);
    setDrag({ mode, grabOffset: 0 });
    onChange?.(snap(mode, t));
  };

  // Arrow keys step a handle to the previous or next phrase edge; Home/End go to the extremes.
  const onKey = (edge: 'start' | 'end') => (e: KeyboardEvent<HTMLDivElement>) => {
    if (!editable || !sorted.length) return;
    const options = boundaries(sorted, { start, end }, edge);
    const at = options.indexOf(snapBoundary(options, edge === 'start' ? start : end));
    const to = { ArrowLeft: at - 1, ArrowDown: at - 1, ArrowRight: at + 1, ArrowUp: at + 1, Home: 0, End: options.length - 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    const t = options[Math.min(Math.max(to, 0), options.length - 1)];
    const next = edge === 'start' ? { start: t, end } : { start, end: t };
    onChange?.(next);
    onCommit?.(next);
  };

  const count = includedPhrases(sorted, { start, end }).length;
  const opening = lines.find((l) => l.end > start + 0.05 && l.start < end)?.text;

  return (
    <div className={`clip-bar${editable ? '' : ' clip-bar--readonly'}${drag ? ' is-dragging' : ''}`}>
      {/* Time tags ride above the grips: the start tag sits left of its grip and the end tag right,
          except near the bar's ends, where they flip inward so they never stick out of the panel. */}
      <div className="clip-bar__labels" aria-hidden="true">
        <span className={`clip-bar__label${start / duration < 0.06 ? ' clip-bar__label--in' : ''}`} style={{ left: pct(start) }}>
          {clock(start)}
        </span>
        <span className={`clip-bar__label clip-bar__label--end${end / duration > 0.94 ? ' clip-bar__label--in' : ''}`} style={{ left: pct(end) }}>
          {clock(end)}
        </span>
      </div>

      <div
        ref={track}
        className="clip-bar__track"
        onPointerDown={onTrackDown}
        onPointerMove={onMove}
        onPointerUp={finish}
        onPointerCancel={() => setDrag(null)}
      >
        <div
          className="clip-bar__sel"
          style={{ left: pct(start), width: `calc(${pct(end)} - ${pct(start)})` }}
          onPointerDown={begin('move')}
          title={editable ? 'Drag to slide the section' : undefined}
        />
        {/* Sung phrases on top of the highlight; the ones outside the section are faded. */}
        {sorted.map((p, i) => (
          <span
            key={i}
            className={`clip-bar__phrase${p.start >= start - 0.05 && p.end <= end + 0.05 ? ' is-in' : ''}`}
            style={{ left: pct(p.start), width: `calc(${pct(p.end)} - ${pct(p.start)})` }}
          />
        ))}
        {playhead !== null && <span className="clip-bar__playhead" style={{ left: pct(playhead) }} />}
        {(['start', 'end'] as const).map((edge) => (
          <div
            key={edge}
            className={`clip-bar__handle clip-bar__handle--${edge}`}
            style={{ left: pct(edge === 'start' ? start : end) }}
            role="slider"
            aria-label={edge === 'start' ? 'Start of practice section' : 'End of practice section'}
            aria-valuemin={0}
            aria-valuemax={duration}
            aria-valuenow={edge === 'start' ? start : end}
            aria-valuetext={clock(edge === 'start' ? start : end)}
            aria-disabled={!editable}
            tabIndex={editable ? 0 : -1}
            onPointerDown={begin(edge)}
            onKeyDown={onKey(edge)}
          />
        ))}
      </div>

      <p className="clip-bar__summary" aria-live="polite">
        <strong>
          {clock(start)} – {clock(end)}
        </strong>{' '}
        of {clock(duration)} · {Math.round(end - start)} s · {count} {count === 1 ? 'phrase' : 'phrases'}
        {opening && (
          <>
            {' '}· starts at <span className="clip-bar__lyric">“{opening}”</span>
          </>
        )}
      </p>
    </div>
  );
}

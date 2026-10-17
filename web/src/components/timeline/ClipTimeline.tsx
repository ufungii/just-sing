import { useRef, type KeyboardEvent, type PointerEvent } from 'react';
import type { TimeRange } from '../../lib/types';
import { boundaries, includedPhrases, snapBoundary } from './range';
import './ClipTimeline.css';

export interface TimelinePhrase { id: string; start: number; end: number }
export interface TimelineLine { start: number; end: number; text: string }

/** Controlled, audio-independent timeline. All times stay relative to the original clip. */
export function ClipTimeline({ duration, phrases, lines, range, onChange, onCommit, playhead, onSeek, disabled = false }: {
  duration: number;
  phrases: TimelinePhrase[];
  lines: TimelineLine[];
  range: TimeRange | null;
  onChange?: (range: TimeRange) => void;
  /** Called on pointer release or a keyboard step; useful for persisting a completed edit. */
  onCommit?: (range: TimeRange) => void;
  playhead?: number | null;
  onSeek?: (time: number) => void;
  disabled?: boolean;
}) {
  const track = useRef<HTMLDivElement>(null);
  const selection = range ?? { start: 0, end: duration };
  const selected = new Set(includedPhrases(phrases, range).map((p) => p.id));
  const pct = (t: number) => `${100 * t / duration}%`;
  const editable = !!onChange && !disabled && phrases.length > 0;
  const change = (edge: 'start' | 'end', time: number, commit = false) => {
    const values = boundaries(phrases, selection, edge);
    if (values.length) {
      const next = { ...selection, [edge]: snapBoundary(values, time) };
      onChange?.(next);
      if (commit) onCommit?.(next);
    }
  };
  function drag(e: PointerEvent<HTMLButtonElement>, edge: 'start' | 'end', commit = false) {
    if (!editable) return;
    const rect = track.current!.getBoundingClientRect();
    change(edge, Math.max(0, Math.min(duration, (e.clientX - rect.left) / rect.width * duration)), commit);
  }
  function key(e: KeyboardEvent<HTMLButtonElement>, edge: 'start' | 'end') {
    const values = boundaries(phrases, selection, edge);
    const i = values.indexOf(snapBoundary(values, selection[edge]));
    const n = e.key === 'Home' ? 0 : e.key === 'End' ? values.length - 1
      : ['ArrowRight', 'ArrowUp'].includes(e.key) ? Math.min(values.length - 1, i + 1)
      : ['ArrowLeft', 'ArrowDown'].includes(e.key) ? Math.max(0, i - 1) : -1;
    if (n < 0) return;
    e.preventDefault();
    change(edge, values[n], true);
    const handle = e.currentTarget;
    requestAnimationFrame(() => handle.scrollIntoView({ block: 'nearest', inline: 'center' }));
  }
  // Pack overlapping lyric lines into rows without changing their horizontal time positions.
  const ends: number[] = [];
  const rows = lines.map((line) => {
    let row = ends.findIndex((end) => end <= line.start);
    if (row < 0) row = ends.length;
    ends[row] = line.end;
    return row;
  });
  return (
    <div className="clip-timeline" aria-label="Clip timeline">
      <div className="clip-timeline__scroll">
        <div className="clip-timeline__canvas" style={{ minWidth: Math.max(640, duration * 28) }}>
          <div className="clip-timeline__lyrics" style={{ height: Math.max(1, ends.length) * 52 }}>
            {lines.map((line, i) => (
              <button key={i} type="button" className="clip-timeline__line" title={line.text}
                style={{ left: pct(line.start), width: pct(line.end - line.start), top: rows[i] * 52 }}
                onClick={() => onSeek?.(line.start)} disabled={!onSeek}>
                <small>{line.start.toFixed(1)} s</small><span>{line.text}</span>
              </button>
            ))}
          </div>
          <div ref={track} className="clip-timeline__track">
            <div className="clip-timeline__selection" style={{ left: pct(selection.start), width: pct(selection.end - selection.start) }} />
            {phrases.map((p, i) => <div key={p.id} className={`clip-timeline__phrase${selected.has(p.id) ? ' is-selected' : ''}`}
              style={{ left: pct(p.start), width: pct(p.end - p.start) }} title={`Phrase ${i + 1}: ${p.start.toFixed(1)}–${p.end.toFixed(1)} s`}>{i + 1}</div>)}
            {(['start', 'end'] as const).map((edge) => (
              <button key={edge} type="button" role="slider" aria-label={`${edge === 'start' ? 'Start' : 'End'} of practice section`}
                aria-valuemin={Math.min(selection[edge], boundaries(phrases, selection, edge)[0] ?? 0)}
                aria-valuemax={Math.max(selection[edge], boundaries(phrases, selection, edge).at(-1) ?? duration)}
                aria-valuenow={selection[edge]} aria-valuetext={`${selection[edge].toFixed(2)} seconds`}
                disabled={!editable} className={`clip-timeline__handle clip-timeline__handle--${edge}`}
                style={{ left: pct(selection[edge]) }} onKeyDown={(e) => key(e, edge)}
                onPointerDown={(e) => { if (editable) e.currentTarget.setPointerCapture(e.pointerId); }}
                onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) drag(e, edge); }}
                onPointerUp={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) { drag(e, edge, true); e.currentTarget.releasePointerCapture(e.pointerId); } }}
                onPointerCancel={() => onCommit?.(selection)}>
                {edge === 'start' ? '⟦' : '⟧'}
              </button>
            ))}
          </div>
          {playhead != null && <div className="clip-timeline__playhead" style={{ left: pct(Math.max(0, Math.min(duration, playhead))) }} />}
          <div className="clip-timeline__ruler"><span>0 s</span><span>{duration.toFixed(1)} s</span></div>
        </div>
      </div>
      <p className="solo-hint">{editable ? 'Drag the ends, or focus an end and use the arrow keys. Ends snap to whole phrases. Scroll sideways to see more.' : 'The host chooses the section for both singers.'}</p>
    </div>
  );
}

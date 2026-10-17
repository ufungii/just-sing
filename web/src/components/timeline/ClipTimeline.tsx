import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import type { TimeRange } from '../../lib/types';
import { boundaries, includedPhrases, snapBoundary } from './range';
import './ClipTimeline.css';

export interface TimelinePhrase { id: string; start: number; end: number }
export interface TimelineLine { start: number; end: number; text: string; romanized?: string }
export interface LineMovePreview { start: number; end: number; valid: boolean }

/** Controlled, audio-independent timeline. All times stay relative to the original clip. */
export function ClipTimeline({ duration, phrases, lines, range, onChange, onCommit, playhead, onSeek, disabled = false,
  overlay, onLineSelect, onLineMove, onLineMovePreview, selectedLines, lineLabels,
  pixelsPerSecond = 28, followPlayhead = false, scrollToTime, freeBoundaries = false, onViewportChange }: {
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
  /** Author-only extensions. Existing player callers keep their behavior. */
  overlay?: ReactNode;
  onLineSelect?: (index: number, additive: boolean) => void;
  onLineMove?: (index: number, start: number) => void;
  onLineMovePreview?: (index: number, start: number) => LineMovePreview;
  selectedLines?: number[];
  lineLabels?: string[];
  pixelsPerSecond?: number;
  followPlayhead?: boolean;
  scrollToTime?: {time:number; token:number};
  freeBoundaries?: boolean;
  onViewportChange?: (range: TimeRange) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const lineDrag = useRef<{ x: number; clientX: number; index: number; grabOffset: number; raf: number } | null>(null);
  const [linePreview, setLinePreview] = useState<(LineMovePreview & { index: number }) | null>(null);
  const moved = useRef(false);
  const selection = range ?? { start: 0, end: duration };
  const selected = new Set(includedPhrases(phrases, range).map((p) => p.id));
  const pct = (t: number) => `${100 * t / duration}%`;
  const editable = !!onChange && !disabled && phrases.length > 0;
  const moveValues = (edge: 'start' | 'end') => freeBoundaries
    ? edge === 'start' ? [0, selection.end - 0.01] : [selection.start + 0.01, duration]
    : boundaries(phrases, selection, edge);
  const change = (edge: 'start' | 'end', time: number, commit = false) => {
    const values = moveValues(edge);
    if (values.length) {
      const value = freeBoundaries ? Math.max(values[0], Math.min(values.at(-1)!, Math.round(time * 100) / 100)) : snapBoundary(values, time);
      const next = { ...selection, [edge]: value };
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
    if (freeBoundaries && ['Home', 'End', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'ArrowDown'].includes(e.key)) {
      e.preventDefault();
      const values = moveValues(edge);
      const time = e.key === 'Home' ? values[0] : e.key === 'End' ? values.at(-1)!
        : selection[edge] + (['ArrowRight','ArrowUp'].includes(e.key) ? 1 : -1) * (e.shiftKey ? 1 : 0.01);
      change(edge, time, true); return;
    }
    const values = moveValues(edge);
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
  function endLineDrag() {
    if (lineDrag.current) cancelAnimationFrame(lineDrag.current.raf);
    lineDrag.current = null; setLinePreview(null);
  }
  function previewLine(clientX: number, index: number) {
    const active = lineDrag.current;
    if (!active || !track.current) return null;
    const rect = track.current.getBoundingClientRect();
    const start = (clientX - rect.left) / rect.width * duration - active.grabOffset;
    const line = lines[index];
    const preview = onLineMovePreview?.(index, start) ?? {
      start, end: start + line.end - line.start,
      valid: start >= 0 && start + line.end - line.start <= duration,
    };
    setLinePreview((current) => current?.index === index && current.start === preview.start && current.end === preview.end && current.valid === preview.valid
      ? current : { ...preview, index });
    return preview;
  }
  function lineFrame() {
    const active = lineDrag.current, scroll = scroller.current;
    if (!active || !scroll) return;
    if (Math.abs(active.clientX - active.x) > 3) {
      if (!moved.current) onLineSelect?.(active.index, false);
      moved.current = true;
      const rect = scroll.getBoundingClientRect();
      if (active.clientX < rect.left + 40) scroll.scrollLeft -= 14;
      else if (active.clientX > rect.right - 40) scroll.scrollLeft += 14;
      previewLine(active.clientX, active.index);
    }
    active.raf = requestAnimationFrame(lineFrame);
  }
  useEffect(() => () => { if (lineDrag.current) cancelAnimationFrame(lineDrag.current.raf); }, []);
  const reportViewport = useCallback(() => {
    const scroll = scroller.current, width = track.current?.getBoundingClientRect().width;
    if (scroll && width) onViewportChange?.({
      start: scroll.scrollLeft / width * duration,
      end: Math.min(duration, (scroll.scrollLeft + scroll.clientWidth - 40) / width * duration),
    });
  }, [duration, onViewportChange]);
  useEffect(() => {
    reportViewport();
    const observer = new ResizeObserver(reportViewport);
    if (scroller.current) observer.observe(scroller.current);
    if (track.current) observer.observe(track.current);
    return () => observer.disconnect();
  }, [reportViewport, pixelsPerSecond]);
  useEffect(() => {
    if (scrollToTime === undefined || !scroller.current || !track.current) return;
    const width = track.current.getBoundingClientRect().width;
    scroller.current.scrollLeft = scrollToTime.time / duration * width - scroller.current.clientWidth / 2;
  }, [scrollToTime, pixelsPerSecond, duration]);
  useEffect(() => {
    const scroll = scroller.current;
    if (!followPlayhead || playhead == null || !scroll || !track.current || lineDrag.current) return;
    const x = playhead / duration * track.current.getBoundingClientRect().width;
    if (x < scroll.scrollLeft + 25 || x > scroll.scrollLeft + scroll.clientWidth - 40) scroll.scrollLeft = x - scroll.clientWidth / 3;
  }, [playhead, followPlayhead, duration]);
  const tickStep = [1,2,5,10,15,30,60,120,300].find((step) => step * pixelsPerSecond >= 80) ?? 300;
  const ticks = Array.from({ length: Math.floor(duration / tickStep) + 1 }, (_, i) => i * tickStep);
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
      <div ref={scroller} className="clip-timeline__scroll" onScroll={reportViewport}>
        <div className="clip-timeline__canvas" style={{ minWidth: Math.max(640, duration * pixelsPerSecond) }}
          onClick={(e) => {
            if ((e.target as HTMLElement).closest('button')) return;
            const rect = track.current!.getBoundingClientRect();
            onSeek?.(Math.max(0, Math.min(duration, (e.clientX - rect.left) / rect.width * duration)));
          }}>
          {overlay}
          <div className="clip-timeline__lyrics" style={{ height: Math.max(1, ends.length) * (onLineSelect ? 82 : 52) }}>
            {linePreview && <div className="clip-timeline__drag-origin" style={{left:pct(lines[linePreview.index].start),width:pct(lines[linePreview.index].end-lines[linePreview.index].start),top:rows[linePreview.index]*(onLineSelect?82:52)}}/>}
            {lines.map((line, i) => (
              <button key={i} type="button" className="clip-timeline__line" title={line.text}
                aria-pressed={onLineSelect ? selectedLines?.includes(i) : undefined}
                data-owner={onLineSelect ? lineLabels?.[i]?.startsWith('Player 2') ? '2' : lineLabels?.[i]?.startsWith('Player 1') ? '1' : undefined : undefined}
                data-dragging={linePreview?.index === i ? linePreview.valid ? 'valid' : 'invalid' : undefined}
                style={{ left: pct(linePreview?.index === i ? linePreview.start : line.start), width: pct(linePreview?.index === i ? linePreview.end - linePreview.start : line.end - line.start), top: rows[i] * (onLineSelect ? 82 : 52),
                  height: onLineSelect ? 78 : undefined, touchAction: onLineMove ? 'none' : undefined }}
                onPointerDown={(e) => { if (onLineMove) {
                  endLineDrag(); moved.current = false;
                  const rect = track.current!.getBoundingClientRect();
                  lineDrag.current = { x:e.clientX, clientX:e.clientX, index:i,
                    grabOffset:(e.clientX-rect.left)/rect.width*duration-line.start, raf:0 };
                  lineDrag.current.raf = requestAnimationFrame(lineFrame);
                  e.currentTarget.setPointerCapture(e.pointerId);
                } }}
                onPointerMove={(e) => {
                  if (!lineDrag.current) return;
                  lineDrag.current.clientX = e.clientX;
                  if (Math.abs(e.clientX-lineDrag.current.x)>3) {
                    if (!moved.current) onLineSelect?.(i,false);
                    moved.current=true; previewLine(e.clientX,i);
                  }
                }}
                onPointerUp={(e) => {
                  const drag = lineDrag.current;
                  if (drag && moved.current) {
                    moved.current = true;
                    const preview=previewLine(e.clientX,i);
                    if (preview?.valid) onLineMove?.(i, preview.start);
                  }
                  endLineDrag();
                  if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
                }}
                onPointerCancel={endLineDrag}
                onKeyDown={(e) => { if (e.key==='Escape' && lineDrag.current) { e.preventDefault();e.stopPropagation();moved.current=true;endLineDrag(); } }}
                onClick={(e) => { if (moved.current) { moved.current = false; return; }
                  onLineSelect?.(i, e.ctrlKey || e.metaKey || e.shiftKey); onSeek?.(line.start);
                }} disabled={!onSeek && !onLineSelect}>
                <small>{line.start.toFixed(1)} s {lineLabels?.[i]}</small><span>{line.text}</span>
                {onLineSelect && <span>{line.romanized}</span>}
              </button>
            ))}
          </div>
          <div ref={track} className="clip-timeline__track">
            <div className="clip-timeline__selection" style={{ left: pct(selection.start), width: pct(selection.end - selection.start) }} />
            {phrases.map((p, i) => <div key={p.id} className={`clip-timeline__phrase${selected.has(p.id) ? ' is-selected' : ''}`}
              style={{ left: pct(p.start), width: pct(p.end - p.start) }} title={`Phrase ${i + 1}: ${p.start.toFixed(1)}–${p.end.toFixed(1)} s`}>{i + 1}</div>)}
            {(['start', 'end'] as const).map((edge) => (
              <button key={edge} type="button" role="slider" aria-label={`${edge === 'start' ? 'Start' : 'End'} of practice section`}
                aria-valuemin={Math.min(selection[edge], moveValues(edge)[0] ?? 0)}
                aria-valuemax={Math.max(selection[edge], moveValues(edge).at(-1) ?? duration)}
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
          <div className="clip-timeline__ruler">{ticks.map((time)=><span key={time} style={{left:pct(time)}}>{Math.floor(time/60)}:{String(Math.floor(time%60)).padStart(2,'0')}</span>)}<span className="clip-timeline__ruler-end">{duration.toFixed(1)} s</span></div>
        </div>
      </div>
      {linePreview && <p className={`clip-timeline__drag-readout${linePreview.valid?'':' is-invalid'}`} role="status">
        Line {linePreview.index+1}: {linePreview.start.toFixed(2)}–{linePreview.end.toFixed(2)} s · {linePreview.valid?'Release to place · Esc to cancel':'Overlaps another line or exceeds the song · Esc to cancel'}
      </p>}
      <p className="solo-hint">{onLineMove ? 'Drag a lyric block to move the line. Scroll sideways to see more.' : editable ? 'Drag the ends, or focus an end and use the arrow keys. Ends snap to whole phrases. Scroll sideways to see more.' : 'The host chooses the section for both singers.'}</p>
    </div>
  );
}

import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react';
import type { Song, TimeRange } from '../../lib/types';
import { boundaries, includedPhrases, snapBoundary } from './range';

const timestamp = (time: number) => `${Math.floor(time / 60)}:${String(Math.floor(time % 60)).padStart(2, '0')}`;

/** A lyric-first practice picker. The playhead and the selected section are separate. */
export function PracticeSectionView({ song, selection, position, disabled, onSeek, onEdge, onLineEdge, waveform, children }: {
  song: Song;
  selection: TimeRange;
  position: number;
  disabled: boolean;
  onSeek: (time: number) => void;
  onEdge: (edge: 'start' | 'end', time: number) => void;
  onLineEdge: (index: number, edge: 'start' | 'end') => void;
  waveform: ReactNode;
  children: ReactNode;
}) {
  const [query, setQuery] = useState('');
  const [view, setView] = useState<TimeRange>({ start: 0, end: song.duration });
  const lyrics = useRef<HTMLDivElement>(null), track = useRef<HTMLDivElement>(null);
  let activeLine = 0;
  song.lines.forEach((line,index) => { if (line.start <= position) activeLine = index; });
  const selected = new Set(includedPhrases(song.phrases, selection).map(phrase => phrase.line_index));
  const ordered = [...selected].sort((a, b) => song.lines[a].start - song.lines[b].start);
  const first = ordered[0], last = ordered.at(-1);
  const span = view.end - view.start;
  const percent = (time: number) => Math.max(0, Math.min(100, (time - view.start) / span * 100));

  useEffect(() => {
    const node = lyrics.current;
    const line = node?.querySelector<HTMLElement>(`[data-line-index="${activeLine}"]`);
    if (!node || !line) return;
    const center = () => {
      const top = line.getBoundingClientRect().top - node.getBoundingClientRect().top + node.scrollTop;
      node.scrollTo({ top: top - node.clientHeight * .32, behavior: 'instant' });
    };
    center();
    const observer = new ResizeObserver(center);
    observer.observe(node);
    return () => observer.disconnect();
  }, [activeLine, query]);

  useEffect(() => {
    setView(current => {
      if (position >= current.start && position <= current.end) return current;
      const length = current.end - current.start;
      const start = Math.max(0, Math.min(song.duration - length, position - length / 2));
      return { start, end: start + length };
    });
  }, [position, song.duration]);

  function zoom(length: number, center = position) {
    length = Math.max(Math.min(2, song.duration), Math.min(song.duration, length));
    const start = Math.max(0, Math.min(song.duration - length, center - length / 2));
    setView({ start, end: start + length });
  }
  function drag(event: PointerEvent<HTMLButtonElement>, edge: 'start' | 'end') {
    const rect = track.current!.getBoundingClientRect();
    const time = view.start + (event.clientX - rect.left) / rect.width * span;
    onEdge(edge, Math.max(0, Math.min(song.duration, time)));
  }
  const visibleLines = song.lines.map((line, index) => ({ line, index })).filter(({ line }) =>
    `${line.text} ${line.romanized ?? ''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));

  return <div className="practice-section-view">
    <div className="practice-lyrics-heading">
      <div><p>YOUR PRACTICE SECTION</p><span>Choose a lyric, then set your start or end.</span></div>
      <label className="practice-search"><span>Find lyrics</span><input type="search" aria-label="Find lyrics" value={query}
        onChange={event => setQuery(event.target.value)} placeholder="Search original or romanized lyrics" /></label>
    </div>
    <div ref={lyrics} className="practice-lyrics" role="region" aria-label="Song lyrics" tabIndex={0}>
      {visibleLines.map(({ line, index }) => <div key={index} data-line-index={index}
        data-in-selection={selected.has(index)} data-current={index === activeLine}
        className="practice-lyric-row">
        <div className="practice-lyric-marker">
          {index === first && <span className="practice-boundary-label" data-boundary="start">START · {timestamp(selection.start)}</span>}
        </div>
        <div className="practice-lyric-content">
          <button className="practice-lyric-text" onClick={() => onSeek(line.start)} aria-current={index === activeLine ? 'true' : undefined}>
            <span>{line.text}</span>
            {line.romanized && line.romanized !== line.text && <small>{line.romanized}</small>}
          </button>
          {!disabled && <div className="practice-lyric-actions">
            <button onClick={() => onLineEdge(index, 'start')} aria-label={`Start at line ${index + 1}`}>Start here</button>
            <button onClick={() => onLineEdge(index, 'end')} aria-label={`End at line ${index + 1}`}>End here</button>
          </div>}
        </div>
        {index === last && <div className="practice-lyric-marker is-end"><span className="practice-boundary-label" data-boundary="end">END · {timestamp(selection.end)}</span></div>}
      </div>)}
      {!visibleLines.length && <p className="practice-no-lyrics">No matching lyrics. Try another word.</p>}
    </div>
    <div className="practice-transport">
      <div className="practice-transport-heading">
        <span><strong>{timestamp(position)}</strong> <span>/ {timestamp(song.duration)}</span></span>
        <span className="practice-selection-summary">{timestamp(selection.start)} – {timestamp(selection.end)} · {Math.round(selection.end - selection.start)} sec selected</span>
        <div className="practice-zoom">
          <button onClick={() => zoom(span * 1.6)} disabled={span >= song.duration}>Zoom out</button>
          <button onClick={() => zoom(span / 1.6)} disabled={span <= Math.min(2, song.duration)}>Zoom in</button>
          <button onClick={() => setView({ start: 0, end: song.duration })}>Fit song</button>
          <button onClick={() => zoom((selection.end - selection.start) * 1.2, (selection.start + selection.end) / 2)}>Fit selection</button>
        </div>
      </div>
      <div ref={track} className="practice-song-bar">
        <div className="practice-song-bar__wave-clip"><div className="practice-song-bar__wave" style={{
          left: `${-view.start / span * 100}%`, width: `${song.duration / span * 100}%`,
        }}>{waveform}</div></div>
        <div className="practice-song-bar__selected" style={{ left: `${percent(selection.start)}%`, width: `${percent(selection.end) - percent(selection.start)}%` }} />
        <input className="practice-song-bar__seek" type="range" aria-label="Song position" min={view.start} max={view.end}
          step="0.01" value={Math.max(view.start, Math.min(view.end, position))} aria-valuetext={`${timestamp(position)} of ${timestamp(song.duration)}`}
          onChange={event => onSeek(Number(event.target.value))} />
        <div className="practice-song-bar__playhead" style={{ left: `${percent(position)}%` }} />
        {(['start', 'end'] as const).map(edge => {
          const values = boundaries(song.phrases, selection, edge);
          return <button key={edge} type="button" role="slider" className={`practice-song-bar__handle is-${edge}`}
            aria-label={`${edge === 'start' ? 'Start' : 'End'} of practice section`} aria-valuenow={selection[edge]}
            aria-valuemin={Math.min(selection[edge],values[0] ?? 0)} aria-valuemax={Math.max(selection[edge],values.at(-1) ?? song.duration)} aria-valuetext={`${selection[edge].toFixed(2)} seconds`}
            disabled={disabled || !values.length} hidden={selection[edge] < view.start || selection[edge] > view.end}
            style={{ left: `${percent(selection[edge])}%` }}
            onPointerDown={event => event.currentTarget.setPointerCapture(event.pointerId)}
            onPointerMove={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) drag(event, edge); }}
            onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) { drag(event, edge); event.currentTarget.releasePointerCapture(event.pointerId); } }}
            onKeyDown={event => {
              const index = values.indexOf(snapBoundary(values, selection[edge]));
              const next = event.key === 'Home' ? 0 : event.key === 'End' ? values.length - 1
                : ['ArrowLeft', 'ArrowDown'].includes(event.key) ? Math.max(0, index - 1)
                : ['ArrowRight', 'ArrowUp'].includes(event.key) ? Math.min(values.length - 1, index + 1) : -1;
              if (next >= 0) { event.preventDefault(); onEdge(edge, values[next]); }
            }}><span>{edge === 'start' ? 'Start' : 'End'}</span><i aria-hidden="true" /></button>;
        })}
      </div>
      <div className="practice-bar-times"><span>{timestamp(view.start)}</span><span>Drag the pink handles to choose your section</span><span>{timestamp(view.end)}</span></div>
      {children}
    </div>
  </div>;
}

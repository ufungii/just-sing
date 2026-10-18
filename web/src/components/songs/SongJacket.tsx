import { useState } from 'react';
import type { ReactNode } from 'react';
import { coverUrl, formatDuration } from './setlist';
import type { SongEntry } from './setlist';
import './songs.css';

/** 14x12 pixel heart: X = filled. The outline is every filled cell touching an empty one. */
const HEART_ROWS = [
  '..XXX....XXX..',
  '.XXXXX..XXXXX.',
  'XXXXXXXXXXXXXX',
  'XXXXXXXXXXXXXX',
  'XXXXXXXXXXXXXX',
  'XXXXXXXXXXXXXX',
  '.XXXXXXXXXXXX.',
  '..XXXXXXXXXX..',
  '...XXXXXXXX...',
  '....XXXXXX....',
  '.....XXXX.....',
  '......XX......',
];
const filled = (x: number, y: number) => HEART_ROWS[y]?.[x] === 'X';
const HEART_CELLS = HEART_ROWS.flatMap((row, y) =>
  [...row].flatMap((c, x) =>
    c === 'X' ? [{ x, y, edge: !(filled(x - 1, y) && filled(x + 1, y) && filled(x, y - 1) && filled(x, y + 1)) }] : [],
  ),
);
const FACE = [
  { x: 4, y: 4, fill: 'var(--ink)' }, { x: 4, y: 5, fill: 'var(--ink)' },
  { x: 9, y: 4, fill: 'var(--ink)' }, { x: 9, y: 5, fill: 'var(--ink)' },
  { x: 6, y: 7, fill: 'var(--ink)' }, { x: 7, y: 7, fill: 'var(--ink)' },
  { x: 3, y: 6, fill: 'var(--pink)' }, { x: 10, y: 6, fill: 'var(--pink)' },
  { x: 2, y: 2, fill: '#ffffff' }, { x: 3, y: 2, fill: '#ffffff' },
];

/** Pixel heart with a smiley face, used as the jacket art and the banner thumbnails. */
export function PixelHeartFace({ size }: { size: number }) {
  return (
    <svg viewBox="0 0 14 12" width={size} height={(size * 12) / 14} className="song-heart" aria-hidden="true">
      {HEART_CELLS.map((c) => (
        <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width="1" height="1" fill={c.edge ? 'var(--ink)' : '#fff6fb'} />
      ))}
      {FACE.map((c) => (
        <rect key={`f${c.x}-${c.y}`} x={c.x} y={c.y} width="1" height="1" fill={c.fill} />
      ))}
    </svg>
  );
}

/**
 * Album cover for a prepared song, or `fallback` when there is none. Covers are local-only files
 * (web/public/covers/<clip id>.png, gitignored), so a fresh clone shows the drawn pixel art instead.
 */
export function SongCover({ clipId, className, fallback }: { clipId: string | null; className: string; fallback: ReactNode }) {
  const [missing, setMissing] = useState<string | null>(null);
  if (!clipId || missing === clipId) return <>{fallback}</>;
  return <img className={className} src={coverUrl(clipId)} alt="" draggable={false} onError={() => setMissing(clipId)} />;
}

/**
 * The big "album jacket" for the chosen song: its cover (or drawn pixel art when there is none),
 * a disc peeking out behind it, a slow sunburst, and the title in the layered pixel display font.
 */
export function SongJacket({ entry }: { entry: SongEntry | null }) {
  const tone = entry && entry.kind !== 'soon' ? entry.tone : 'pink';
  return (
    <section className={`song-jacket song-jacket--${tone}`} aria-label="Selected song">
      <div className="song-jacket__art-wrap" aria-hidden="true">
        <div className="song-jacket__rays" />
        <div className="song-jacket__disc" />
        <div className="song-jacket__art">
          <SongCover
            clipId={entry?.clip?.id ?? null}
            className="song-jacket__cover"
            fallback={<PixelHeartFace size={132} />}
          />
          <span className="song-jacket__art-label">{entry ? 'NOW PLAYING ♪' : 'PICK A SONG'}</span>
        </div>
      </div>

      <div className="song-jacket__info">
        <span className="song-jacket__chip song-jacket__chip--now">{entry ? 'NOW SELECTED' : 'NOTHING PICKED'}</span>
        <h2 className="song-jacket__title" data-text={entry?.title ?? 'Pick a song'}>
          {entry?.title ?? 'Pick a song'}
        </h2>
        <p className="song-jacket__artist">{entry?.artist ?? 'from the wheel'}</p>
        {entry?.clip && (
          <div className="song-jacket__chips">
            <span className="song-jacket__chip">CLIP {formatDuration(entry.clip.duration)}</span>
            {entry.kind === 'test' && <span className="song-jacket__chip">TEST CLIP</span>}
          </div>
        )}
      </div>
    </section>
  );
}

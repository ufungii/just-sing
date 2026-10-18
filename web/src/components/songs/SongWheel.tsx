import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { ClipSummary } from '../../lib/types';
import { Notice, PixelButton } from '../../ui';
import { buildEntries, formatDuration } from './setlist';
import type { SongEntry } from './setlist';
import { PixelHeartFace, SongCover } from './SongJacket';
import { useSongPreview } from './useSongPreview';
import './songs.css';

export type Clips = { kind: 'loading' } | { kind: 'error'; detail: string | null } | { kind: 'ok'; clips: ClipSummary[] };

/** The song entries for a loaded catalog (setlist merged with prepared clips). */
export function useSongEntries(clips: Clips): SongEntry[] {
  return useMemo(() => (clips.kind === 'ok' ? buildEntries(clips.clips) : []), [clips]);
}

/**
 * Arcade-style song wheel: slanted neutral keycap banners, the chosen one pink and popped out with
 * a bouncing pointer, held in the middle of the wheel while the rest fade out above and below. Songs that aren't prepared yet stay on the wheel as "coming soon" and can't be picked.
 * Up/Down arrows move between playable songs, and the chosen one plays a short preview.
 */
export function SongWheel({
  clips,
  selected,
  onSelect,
  onRetry,
}: {
  clips: Clips;
  selected: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
}) {
  const entries = useSongEntries(clips);
  const playable = entries.filter((e) => e.clip);
  const selIndex = entries.findIndex((e) => e.clip?.id === selected);
  const listRef = useRef<HTMLUListElement>(null);
  // The chosen song plays a short loop while it stays selected.
  const chosenClip = selIndex < 0 ? null : entries[selIndex].clip;
  useSongPreview(chosenClip?.id ?? null, chosenClip?.duration ?? null);

  // Which ends of the list have more songs past them, so only those edges fade.
  const [more, setMore] = useState({ above: false, below: false });
  const measure = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    const above = list.scrollTop > 2;
    const below = list.scrollTop + list.clientHeight < list.scrollHeight - 2;
    setMore((m) => (m.above === above && m.below === below ? m : { above, below }));
  }, []);

  // Keep the chosen banner in the middle of the wheel where the list allows it (the first and last
  // songs stop at the ends: there is no scrolling past them). Scrolls only the list, never the page.
  useEffect(() => {
    const list = listRef.current;
    const item = list?.querySelector<HTMLElement>('.is-selected')?.closest('li');
    if (list && item) list.scrollTo({ top: item.offsetTop - (list.clientHeight - item.offsetHeight) / 2, behavior: 'smooth' });
    measure();
  }, [selected, clips.kind, measure]);

  if (clips.kind === 'loading') return <Notice>Loading songs…</Notice>;
  if (clips.kind === 'error')
    return (
      <Notice
        tone="error"
        action={
          <PixelButton tone="paper" size="sm" onClick={onRetry}>
            RETRY
          </PixelButton>
        }
      >
        Can’t reach the server, so no songs yet. {clips.detail}
      </Notice>
    );

  const step = (e: KeyboardEvent, dir: 1 | -1) => {
    e.preventDefault();
    if (!playable.length) return;
    const at = playable.findIndex((p) => p.clip!.id === selected);
    const next = playable[(at + dir + playable.length) % playable.length];
    onSelect(next.clip!.id);
    listRef.current?.querySelector<HTMLButtonElement>(`[data-clip="${next.clip!.id}"]`)?.focus();
  };

  return (
    <div className="song-wheel">
      <p className="song-wheel__count">TRACKLIST · {entries.length} {entries.length === 1 ? 'SONG' : 'SONGS'}</p>
      <ul
        className={`song-wheel__list${more.above ? ' has-more-above' : ''}${more.below ? ' has-more-below' : ''}`}
        ref={listRef}
        role="list"
        onScroll={measure}
      >
        {entries.map((e, i) => {
          const on = e.clip !== null && e.clip.id === selected;
          // Banners further from the chosen one sit further right, so the list reads as a wheel.
          const indent = selIndex < 0 ? 0 : Math.min(54, Math.abs(i - selIndex) * 14);
          return (
            <li key={e.key} className="song-wheel__item" style={{ paddingLeft: on ? 0 : 34 + indent }}>
              {on && <WheelPointer />}
              <button
                type="button"
                data-clip={e.clip?.id}
                className={`song-banner song-banner--${e.kind === 'soon' ? 'soon' : on ? 'pink' : 'neutral'}${on ? ' is-selected' : ''}`}
                disabled={!e.clip}
                aria-pressed={e.clip ? on : undefined}
                aria-label={e.clip ? undefined : `${e.title} by ${e.artist}, coming soon`}
                tabIndex={e.clip ? (on || (selIndex < 0 && e === playable[0]) ? 0 : -1) : -1}
                onClick={() => e.clip && onSelect(e.clip.id)}
                onKeyDown={(ev) => {
                  if (ev.key === 'ArrowDown') step(ev, 1);
                  if (ev.key === 'ArrowUp') step(ev, -1);
                }}
              >
                <span className="song-banner__thumb" aria-hidden="true">
                  {e.kind === 'soon' ? '?' : <SongCover clipId={e.clip!.id} className="song-banner__cover" fallback={<PixelHeartFace size={30} />} />}
                </span>
                <span className="song-banner__text">
                  <span className="song-banner__title">{e.title}</span>
                  <span className="song-banner__artist">{e.artist}</span>
                </span>
                <span className="song-banner__tag">
                  {e.kind === 'soon' ? 'SOON' : e.kind === 'test' ? 'TEST' : formatDuration(e.clip!.duration)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Little pixel arrow that bobs next to the chosen banner. */
function WheelPointer() {
  return (
    <svg className="song-pointer" viewBox="0 0 32 32" width="32" height="32" aria-hidden="true">
      <path transform="scale(4)" d="M0 1h3v1h1v1h1v1h1v1h-1v1h-1v1h-1v1h-3z" fill="var(--ink)" />
      <path transform="scale(4)" d="M1 2h2v1h1v1h1v1h-1v1h-1v1h-2z" fill="var(--butter)" />
    </svg>
  );
}

/**
 * The songs the team plans to offer, in song-select order. Titles only: audio, lyrics and notes
 * come from the prepared catalog (/api/clips), which the ML pipeline fills per machine.
 *
 * A planned song becomes playable as soon as a prepared clip with the same title shows up in the
 * catalog; until then the song wheel shows it as "coming soon". Album covers are local-only files
 * (see coverUrl), so nothing copyrighted lands in this public repo.
 */
import type { ClipSummary } from '../../lib/types';

export type SongTone = 'pink' | 'sky' | 'mint' | 'lav' | 'butter';

export interface PlannedSong {
  title: string;
  artist: string;
}

export const SETLIST: PlannedSong[] = [
  { title: 'Blood Sweat & Tears', artist: 'BTS' },
  { title: 'How Sweet', artist: 'NewJeans' },
  { title: 'Last Christmas', artist: 'Wham!' },
  { title: 'Love', artist: 'Keyshia Cole' },
  { title: 'Love Language', artist: 'TOMORROW X TOGETHER' },
  { title: 'Love Scenario', artist: 'iKON' },
  { title: 'Party in the USA', artist: 'Miley Cyrus' },
  { title: 'Russian Roulette', artist: 'Red Velvet' },
  { title: 'Soda Pop', artist: 'Saja Boys' },
];

/**
 * Album cover for a prepared clip: web/public/covers/<clip id>.png. That folder is gitignored (covers
 * are copyrighted and the repo is public); when a cover is missing the jacket shows pixel art.
 */
export const coverUrl = (clipId: string) => `/covers/${encodeURIComponent(clipId)}.png`;

const TONES: SongTone[] = ['pink', 'sky', 'mint', 'lav', 'butter'];

export function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  return s < 60 ? `~${s} s` : `~${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export interface SongEntry {
  key: string;
  title: string;
  artist: string;
  tone: SongTone;
  /** The prepared clip to play, or null while the song is not prepared yet. */
  clip: ClipSummary | null;
  kind: 'song' | 'test' | 'soon';
}

/** Case, spacing and punctuation don't matter when matching a planned title to a catalog clip. */
const norm = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');

/**
 * Merge the setlist with the catalog: prepared setlist songs first, then any other catalog clips
 * (test fixtures, songs not on the setlist), then the setlist songs still coming soon.
 */
export function buildEntries(clips: ClipSummary[]): SongEntry[] {
  const byTitle = new Map(clips.map((c) => [norm(c.title), c]));
  const used = new Set<string>();
  const planned = SETLIST.map((s, i): SongEntry => {
    const clip = byTitle.get(norm(s.title)) ?? null;
    if (clip) used.add(clip.id);
    return { key: clip?.id ?? `planned-${i}`, ...s, tone: TONES[i % TONES.length], clip, kind: clip ? 'song' : 'soon' };
  });
  const extras = clips
    .filter((c) => !used.has(c.id))
    .map((c, i): SongEntry => ({
      key: c.id,
      title: c.title,
      artist: c.artist,
      tone: TONES[(planned.length + i) % TONES.length],
      clip: c,
      kind: c.synthetic ? 'test' : 'song',
    }));
  return [...planned.filter((e) => e.clip), ...extras.filter((e) => e.kind === 'song'), ...extras.filter((e) => e.kind === 'test'), ...planned.filter((e) => !e.clip)];
}

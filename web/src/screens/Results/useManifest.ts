import { useEffect, useState } from 'react';
import { getManifest } from '../../lib/api';
import type { Song } from '../../lib/types';

/** Loads a clip manifest for its title and lyrics; null while loading or if it failed (phrase rows fall back). */
export function useManifest(clipId: string): Song | null {
  const [song, setSong] = useState<Song | null>(null);
  useEffect(() => {
    let live = true;
    getManifest(clipId).then(
      (s) => live && setSong(s),
      () => live && setSong(null),
    );
    return () => {
      live = false;
    };
  }, [clipId]);
  return song;
}

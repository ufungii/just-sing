import { describe, expect, it } from 'vitest';
import type { ClipSummary } from '../../lib/types';
import { buildEntries } from './setlist';

const clip = (id: string, title: string, synthetic = false) => ({ id, title, artist: 'A', synthetic }) as unknown as ClipSummary;

describe('song order', () => {
  it('lists playable songs A-Z (setlist or not), then songs coming soon A-Z', () => {
    const titles = buildEntries([clip('z', 'Zombie'), clip('x', 'An Extra Song'), clip('c', 'Crazy'), clip('l', 'love')]).map((e) => `${e.kind}:${e.title}`);
    const playable = titles.filter((t) => t.startsWith('song:'));
    expect(playable).toEqual(['song:An Extra Song', 'song:Crazy', 'song:Love', 'song:Zombie']);
    const soon = titles.filter((t) => t.startsWith('soon:'));
    expect(soon).toEqual([...soon].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base', ignorePunctuation: true })));
    expect(titles.indexOf(soon[0])).toBeGreaterThan(titles.indexOf('song:Zombie'));
  });
});

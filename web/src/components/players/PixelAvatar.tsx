import type { AvatarId } from '../../lib/players';
import './players.css';

/**
 * Preset pixel avatars, drawn from character grids so they stay crisp at any size.
 * o outline · w white · p soft pink · P strawberry · k blush · y butter · m mint · l lavender · O orange
 */
const COLORS: Record<string, string> = {
  o: 'var(--ink)',
  w: '#fff6fb',
  p: '#ffb3d6',
  P: '#ff6fae',
  k: '#ff8cc0',
  y: 'var(--butter)',
  m: 'var(--mint)',
  l: 'var(--lav)',
  O: '#ff9f43',
};

const ART: Record<AvatarId, { label: string; tone: string; rows: string[] }> = {
  bunny: {
    label: 'Bunny',
    tone: 'var(--pink-light)',
    rows: [
      '..oo....oo..',
      '.owwo..owwo.',
      '.opwo..owpo.',
      '.opwo..owpo.',
      '.owwoooowwo.',
      'owwwwwwwwwwo',
      'owwowwwwowwo',
      'owwwwwwwwwwo',
      'okwwwoowwwko',
      'owwwwwwwwwwo',
      '.owwwwwwwwo.',
      '..oooooooo..',
    ],
  },
  kitty: {
    label: 'Kitty',
    tone: '#fff0a8',
    rows: [
      '.o........o.',
      'oyo......oyo',
      'oyyo....oyyo',
      'oyyyooooyyyo',
      'oyyyyyyyyyyo',
      'oyyoyyyyoyyo',
      'oyyyyyyyyyyo',
      'okyyyooyyyko',
      'oyyyyyyyyyyo',
      '.oyyyyyyyyo.',
      '..oooooooo..',
    ],
  },
  froggy: {
    label: 'Froggy',
    tone: 'var(--mint-light)',
    rows: [
      '.ooo....ooo.',
      'owowo..owowo',
      'owwwoooowwwo',
      'ommmmmmmmmmo',
      'ommmmmmmmmmo',
      'okmmmmmmmmko',
      'ommoooooommo',
      'ommmmmmmmmmo',
      '.ommmmmmmmo.',
      '..oooooooo..',
    ],
  },
  strawberry: {
    label: 'Strawberry',
    tone: 'var(--pink-light)',
    rows: [
      '...ommmmo...',
      '..ommoommo..',
      '.oPPPPPPPPo.',
      'oPPyPPPPyPPo',
      'oPPoPPPPoPPo',
      'oPkPPooPPkPo',
      '.oPPyPPyPPo.',
      '..oPPPPPPo..',
      '...oPPPPo...',
      '....oooo....',
    ],
  },
  mochi: {
    label: 'Mochi',
    tone: 'var(--lav-light)',
    rows: [
      '...oooooo...',
      '..olwlllllo.',
      '.olwllllllo.',
      'ollllllllllo',
      'ollollllollo',
      'olkllooollko',
      'ollllllllllo',
      '.ollllllllo.',
      '..oooooooo..',
    ],
  },
  chick: {
    label: 'Chick',
    tone: '#fff0a8',
    rows: [
      '....oooo....',
      '...oyyyyo...',
      '..oyyyyyyo..',
      '.oyyoyyoyyo.',
      '.oyyyOOyyyo.',
      'oykyyOOyyyko',
      'oyyyyyyyyyyo',
      'oyyyyyyyyyyo',
      '.oyyyyyyyyo.',
      '..oooooooo..',
    ],
  },
};

export function avatarLabel(id: AvatarId): string {
  return ART[id].label;
}

/** A preset avatar on its pastel tile. Decorative unless `label` is given. */
export function PixelAvatar({ avatar, size = 40, label }: { avatar: AvatarId; size?: number; label?: string }) {
  const art = ART[avatar] ?? ART.bunny;
  const h = art.rows.length;
  const pad = (12 - h) / 2; // centre shorter sprites vertically on the 12x12 grid
  return (
    <span className="px-avatar" style={{ width: size, height: size, background: art.tone }} role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <svg viewBox="-1 -1 14 14" width={size - 8} height={size - 8}>
        {art.rows.flatMap((row, y) =>
          [...row].map((c, x) =>
            c === '.' ? null : <rect key={`${x}-${y}`} x={x} y={y + pad} width="1.02" height="1.02" fill={COLORS[c]} />,
          ),
        )}
      </svg>
    </span>
  );
}

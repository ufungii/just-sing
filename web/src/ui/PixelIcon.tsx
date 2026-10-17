/**
 * Small pixel icons drawn from character grids (o = outline ink, w = white fill).
 * Each icon is 10x10 cells, so it scales crisply.
 */
const ICONS = {
  profile: [
    '...oooo...',
    '..owwwwo..',
    '..owwwwo..',
    '..owwwwo..',
    '...oooo...',
    '..oooooo..',
    '.owwwwwwo.',
    'owwwwwwwwo',
    'owwwwwwwwo',
    'oooooooooo',
  ],
  history: [
    '..oooooo..',
    '.owwwwwwo.',
    'owwwowwwwo',
    'owwwowwwwo',
    'owwwowwwwo',
    'owwwooowwo',
    'owwwwwwwwo',
    'owwwwwwwwo',
    '.owwwwwwo.',
    '..oooooo..',
  ],
  settings: [
    '....oo....',
    '.oo.oo.oo.',
    '.oooooooo.',
    '..oooooo..',
    'oooo..oooo',
    'oooo..oooo',
    '..oooooo..',
    '.oooooooo.',
    '.oo.oo.oo.',
    '....oo....',
  ],
} as const;

export type IconName = keyof typeof ICONS;

export function PixelIcon({ name, size = 28 }: { name: IconName; size?: number }) {
  return (
    <svg viewBox="0 0 10 10" width={size} height={size} aria-hidden="true" style={{ display: 'block', shapeRendering: 'crispEdges' }}>
      {ICONS[name].flatMap((row, y) =>
        [...row].map((c, x) =>
          c === '.' ? null : <rect key={`${x}-${y}`} x={x} y={y} width="1.02" height="1.02" fill={c === 'o' ? 'var(--ink)' : '#fff6fb'} />,
        ),
      )}
    </svg>
  );
}

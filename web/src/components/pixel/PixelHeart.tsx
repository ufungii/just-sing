import { HEART } from './art';
import { Px } from './Px';
import './pixel.css';

type SpriteProps = { size?: number; color?: string; className?: string };

/** Standalone 7x6 pixel heart. `size` is the width in px. */
export function PixelHeart({ size = 42, color = 'var(--hot)', className }: SpriteProps) {
  return (
    <svg
      className={className ? `px-svg ${className}` : 'px-svg'}
      viewBox="0 0 7 6"
      width={size}
      height={(size * 6) / 7}
      aria-hidden="true"
    >
      <Px d={HEART} fill={color} />
    </svg>
  );
}

import { SPARKLE_PLUS, SPARKLE_STAR } from './art';
import { Px } from './Px';
import './pixel.css';

type SparkleProps = {
  size?: number;
  color?: string;
  className?: string;
  /** 'star' is the chunky 7x7 sparkle, 'plus' the thin 5x5 one. */
  variant?: 'star' | 'plus';
};

/** Standalone square pixel sparkle. Add className="px-twinkle" to make it twinkle. */
export function PixelSparkle({ size = 42, color = 'var(--hot)', className, variant = 'star' }: SparkleProps) {
  const grid = variant === 'star' ? 7 : 5;
  return (
    <svg
      className={className ? `px-svg ${className}` : 'px-svg'}
      viewBox={`0 0 ${grid} ${grid}`}
      width={size}
      height={size}
      aria-hidden="true"
    >
      <Px d={variant === 'star' ? SPARKLE_STAR : SPARKLE_PLUS} fill={color} />
    </svg>
  );
}

import type { CSSProperties } from 'react';
import { CLOUD, COLOR, HEART, NOTE } from './art';
import { PixelSparkle } from './PixelSparkle';
import { Px } from './Px';
import './pixel.css';

/** Hearts and notes on a 1440x900 canvas that covers the layer, at the mockup's spots. */
const HEARTS = [
  'translate(1300 300) scale(6)',
  'translate(120 440) scale(5)',
  'translate(980 60) scale(4)',
];
const NOTES = [
  'translate(300 70) scale(5)',
  'translate(1350 480) scale(6)',
  'translate(210 640) scale(5)',
];

/**
 * Drifting clouds at three depths: big and slow at the back, small and quicker in front.
 * Positions are percentages so the sky fills any window size.
 */
const CLOUDS: { scale: number; opacity: number; seconds: number; style: CSSProperties }[] = [
  { scale: 7, opacity: 1, seconds: 9, style: { left: '4%', top: '13%' } },
  { scale: 6, opacity: 1, seconds: 11, style: { right: '8%', top: '10%', animationDelay: '-4s' } },
  { scale: 8, opacity: 1, seconds: 13, style: { right: '5%', top: '73%', animationDelay: '-2s' } },
  { scale: 6, opacity: 1, seconds: 10, style: { left: '2%', top: '80%', animationDelay: '-6s' } },
  { scale: 10, opacity: 0.55, seconds: 18, style: { left: '30%', top: '3%', animationDelay: '-9s' } },
  { scale: 5, opacity: 0.8, seconds: 8, style: { left: '58%', top: '48%', animationDelay: '-3s' } },
  { scale: 9, opacity: 0.5, seconds: 16, style: { left: '38%', top: '88%', animationDelay: '-7s' } },
  { scale: 4, opacity: 0.9, seconds: 7, style: { left: '16%', top: '52%', animationDelay: '-1s' } },
  { scale: 5, opacity: 0.7, seconds: 12, style: { right: '24%', top: '30%', animationDelay: '-5s' } },
];

/** Twinkling pixel sparkles. */
const SPARKLES: { variant: 'star' | 'plus'; color: string; style: CSSProperties }[] = [
  { variant: 'plus', color: COLOR.sparkleSky, style: { right: 250, top: 230, animationDelay: '.6s' } },
  { variant: 'star', color: 'var(--hot)', style: { right: 150, top: 390, animationDelay: '1.1s' } },
  { variant: 'plus', color: COLOR.sparkleMint, style: { left: 150, top: 340, animationDelay: '.3s' } },
  { variant: 'star', color: 'var(--butter)', style: { left: '44%', top: '6%', animationDelay: '1.6s' } },
  { variant: 'plus', color: 'var(--lav)', style: { left: '8%', top: '64%', animationDelay: '.9s' } },
];

/**
 * Text notes and stars that float up and fade, scattered across the sky. Only glyphs the bundled
 * DotGothic16 subset really draws (♪ ♬ ☆ ★ ♡ ˚), so none fall back to another font.
 */
type Glyph = { ch: string; left: string; top: string; size: number; color: string; seconds: number; delay: number };
const GLYPHS: Glyph[] = [
  { ch: '♪', left: '6%', top: '30%', size: 26, color: 'var(--lav)', seconds: 7, delay: 0 },
  { ch: '☆', left: '12%', top: '8%', size: 20, color: 'var(--butter)', seconds: 6, delay: -2 },
  { ch: '♬', left: '22%', top: '62%', size: 22, color: 'var(--hot)', seconds: 8, delay: -5 },
  { ch: '★', left: '27%', top: '22%', size: 14, color: 'var(--pink)', seconds: 5, delay: -1 },
  { ch: '♡', left: '33%', top: '84%', size: 20, color: 'var(--hot)', seconds: 7, delay: -3 },
  { ch: '♪', left: '41%', top: '40%', size: 18, color: 'var(--mint-dark)', seconds: 9, delay: -6 },
  { ch: '˚', left: '47%', top: '70%', size: 26, color: 'var(--lav-dark)', seconds: 6, delay: -4 },
  { ch: '☆', left: '53%', top: '16%', size: 18, color: 'var(--sky-dark)', seconds: 7, delay: -2 },
  { ch: '♬', left: '61%', top: '86%', size: 24, color: 'var(--lav)', seconds: 8, delay: -1 },
  { ch: '★', left: '67%', top: '56%', size: 16, color: 'var(--butter)', seconds: 6, delay: -5 },
  { ch: '♪', left: '72%', top: '8%', size: 22, color: 'var(--hot)', seconds: 7, delay: -3 },
  { ch: '♡', left: '78%', top: '38%', size: 18, color: 'var(--pink)', seconds: 8, delay: -6 },
  { ch: '☆', left: '84%', top: '66%', size: 22, color: 'var(--mint-dark)', seconds: 6, delay: 0 },
  { ch: '♪', left: '91%', top: '22%', size: 20, color: 'var(--sky-dark)', seconds: 9, delay: -4 },
  { ch: '★', left: '95%', top: '88%', size: 14, color: 'var(--hot)', seconds: 5, delay: -2 },
  { ch: '♬', left: '3%', top: '92%', size: 20, color: 'var(--butter)', seconds: 8, delay: -7 },
  { ch: '˚', left: '18%', top: '42%', size: 22, color: 'var(--pink)', seconds: 6, delay: -3 },
  { ch: '♡', left: '57%', top: '30%', size: 14, color: 'var(--lav-dark)', seconds: 7, delay: -5 },
];

/** Decorative background: clouds, hearts, notes, sparkles and floating glyphs. Sits behind any screen. */
export function PixelSky({ className }: { className?: string }) {
  return (
    <div className={className ? `px-sky ${className}` : 'px-sky'} aria-hidden="true">
      <svg className="px-svg" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" style={{ inset: 0, width: '100%', height: '100%' }}>
        {HEARTS.map((t) => <Px key={t} d={HEART} fill={COLOR.heartFaint} transform={t} />)}
        {NOTES.map((t) => <Px key={t} d={NOTE} fill="var(--lav)" transform={t} />)}
      </svg>

      {CLOUDS.map(({ scale, opacity, seconds, style }, i) => (
        <svg
          key={i}
          className="px-svg px-drift"
          viewBox={`0 0 ${16 * scale} ${6 * scale}`}
          width={16 * scale}
          height={6 * scale}
          style={{ ...style, opacity, animationDuration: `${seconds}s` }}
        >
          <Px d={CLOUD} fill="var(--paper)" transform={`scale(${scale})`} />
        </svg>
      ))}

      {GLYPHS.map((g, i) => (
        <span
          key={`g${i}`}
          className="px-float"
          style={{ left: g.left, top: g.top, fontSize: g.size, color: g.color, animationDuration: `${g.seconds}s`, animationDelay: `${g.delay}s` }}
        >
          {g.ch}
        </span>
      ))}

      {SPARKLES.map(({ variant, color, style }, i) => (
        <span key={i} className="px-twinkle" style={style}>
          <PixelSparkle variant={variant} color={color} size={variant === 'star' ? 42 : 30} />
        </span>
      ))}
    </div>
  );
}

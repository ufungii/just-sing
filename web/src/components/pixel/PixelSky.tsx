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

/** Drifting clouds: pixel scale, position, and phase offset. */
const CLOUDS: { scale: number; style: CSSProperties }[] = [
  { scale: 7, style: { left: 60, top: 120 } },
  { scale: 6, style: { right: 120, top: 88, animationDelay: '-4s' } },
  { scale: 8, style: { right: 70, top: 660, animationDelay: '-2s' } },
  { scale: 6, style: { left: 30, top: 720, animationDelay: '-6s' } },
];

/** Twinkling sparkles. */
const SPARKLES: { variant: 'star' | 'plus'; color: string; style: CSSProperties }[] = [
  { variant: 'plus', color: COLOR.sparkleSky, style: { right: 250, top: 230, animationDelay: '.6s' } },
  { variant: 'star', color: 'var(--hot)', style: { right: 150, top: 390, animationDelay: '1.1s' } },
  { variant: 'plus', color: COLOR.sparkleMint, style: { left: 150, top: 340, animationDelay: '.3s' } },
];

/** Decorative background: clouds, hearts, notes and sparkles. Sits behind any screen. */
export function PixelSky({ className }: { className?: string }) {
  return (
    <div className={className ? `px-sky ${className}` : 'px-sky'} aria-hidden="true">
      <svg className="px-svg" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" style={{ inset: 0, width: '100%', height: '100%' }}>
        {HEARTS.map((t) => <Px key={t} d={HEART} fill={COLOR.heartFaint} transform={t} />)}
        {NOTES.map((t) => <Px key={t} d={NOTE} fill="var(--lav)" transform={t} />)}
      </svg>

      {CLOUDS.map(({ scale, style }, i) => (
        <svg key={i} className="px-svg px-drift" viewBox={`0 0 ${16 * scale} ${6 * scale}`} width={16 * scale} height={6 * scale} style={style}>
          <Px d={CLOUD} fill="var(--paper)" transform={`scale(${scale})`} />
        </svg>
      ))}

      {SPARKLES.map(({ variant, color, style }, i) => (
        <span key={i} className="px-twinkle" style={style}>
          <PixelSparkle variant={variant} color={color} size={variant === 'star' ? 42 : 30} />
        </span>
      ))}
    </div>
  );
}

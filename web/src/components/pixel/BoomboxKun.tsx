import type { CSSProperties } from 'react';
import { MascotButton } from './MascotButton';
import { Px } from './Px';

// Only characters the bundled DotGothic16 subset contains (no ω or ₊), so nothing falls back to another font.
const LINES = ['♪ ˚☆ beat drop', '(=^･ｪ･^=) bzz', 'turn it up! ♬', '(｡-_-｡) zzz', '♬ volume 11 ♬'];

/** Rising notes: glyph, position, color, start delay and sideways drift (--dx), as in the mockup. */
const NOTES: { ch: string; style: CSSProperties }[] = [
  { ch: '♪', style: { right: -10, top: 4, fontSize: 26, color: 'var(--ink-soft)', '--dx': '24px' } as CSSProperties },
  { ch: '♪', style: { right: 34, top: 22, fontSize: 22, color: 'var(--hot)', animationDelay: '.8s', '--dx': '-10px' } as CSSProperties },
  { ch: '♬', style: { right: -26, top: 40, fontSize: 20, color: 'var(--mint-dark)', animationDelay: '1.6s', '--dx': '30px' } as CSSProperties },
];

/** Boombox-kun: the wide blue boombox mascot. Sways to the beat with notes floating up; poke it to talk. */
export function BoomboxKun({ className }: { className?: string }) {
  const notes = NOTES.map((n, i) => (
    <span key={i} className="px-note px-note-glyph" aria-hidden="true" style={n.style}>
      {n.ch}
    </span>
  ));
  return (
    <MascotButton label="Poke Boombox-kun" lines={LINES} className={className} extras={notes}>
      <svg className="px-svg px-sway" viewBox="0 0 140 110" width="140" height="110" aria-hidden="true">
        <g transform="scale(10)">
          {/* handle and body outline */}
          <Px d="M3 0h8v1h-8z M3 1h1v1h-1z M10 1h1v1h-1z M0 2h14v9h-14z" fill="var(--ink)" />
          {/* face with a light top bevel */}
          <Px d="M1 3h12v7h-12z" fill="var(--sky)" />
          <Px d="M1 3h12v1h-12z" fill="var(--sky-light)" />
          {/* speakers, eyes, nose, mouth */}
          <Px d="M1 5h3v3h-3z M10 5h3v3h-3z M5 4h1v1h-1z M8 4h1v1h-1z M6 6h2v1h-2z M5 8h4v1h-4z" fill="var(--ink)" />
          {/* speaker shine, blush */}
          <Px d="M2 6h1v1h-1z M11 6h1v1h-1z" fill="var(--sky-light)" />
          <Px d="M4 5h1v1h-1z M9 5h1v1h-1z" fill="var(--hot)" />
        </g>
      </svg>
      <span className="px-ground-shadow" aria-hidden="true" style={{ width: 112, height: 10, margin: '2px auto 0', opacity: 0.22 }} />
    </MascotButton>
  );
}

import { COLOR } from './art';
import { MascotButton } from './MascotButton';
import { Px } from './Px';

const LINES = ['sing w/ me! ♡', '(,,>﹏<,,) eek!', 'la la la~ ♪', 'ヾ(≧▽≦*)o yay!', 'one more time! ☆'];

/** Mic-chan: the pink mic mascot with a bow and headphones. Hops with squash-and-stretch; poke her to talk. */
export function MicChan({ className }: { className?: string }) {
  return (
    <MascotButton label="Poke Mic-chan" lines={LINES} className={className} marginBottom={4}>
      <svg className="px-svg px-hop" viewBox="0 0 120 160" width="120" height="160" aria-hidden="true">
        <g transform="scale(10)">
          {/* bow */}
          <Px d="M4 0h1v1h-1z M7 0h1v1h-1z M3 1h3v1h-3z M6 1h3v1h-3z M4 2h4v1h-4z" fill="var(--hot)" />
          {/* head outline */}
          <Px d="M3 3h6v1h-6z M2 4h8v1h-8z M1 5h10v5h-10z M2 10h8v1h-8z" fill="var(--ink)" />
          {/* face, shine */}
          <Px d="M3 4h6v1h-6z M2 5h8v5h-8z" fill={COLOR.micFace} />
          <Px d="M3 5h2v1h-2z M2 6h1v1h-1z" fill={COLOR.micShine} />
          {/* eyes, mouth, blush */}
          <Px d="M4 6h1v2h-1z M7 6h1v2h-1z M5 9h2v1h-2z" fill="var(--ink)" />
          <Px d="M3 8h1v1h-1z M8 8h1v1h-1z" fill="var(--hot)" />
          {/* handle and base */}
          <Px d="M5 11h2v3h-2z M3 14h6v2h-6z" fill="var(--ink)" />
          {/* headphone cups */}
          <Px d="M0 7h1v2h-1z M11 6h1v2h-1z" fill="var(--ink)" />
        </g>
      </svg>
      {/* shadow shrinks while she is mid-air */}
      <span className="px-ground-shadow px-hop-shadow" aria-hidden="true" style={{ width: 84, height: 10, margin: '0 auto', opacity: 0.25 }} />
    </MascotButton>
  );
}

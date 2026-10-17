import type { KeyboardEvent, Ref } from 'react';

export type CardIcon = 'mic' | 'say' | 'versus' | 'trophy';
export type CardColor = 'pink' | 'mint' | 'sky' | 'lav';

const MIC = 'M3 0h4v1h-4z M2 1h6v5h-6z M3 6h4v1h-4z M4 7h2v3h-2z M2 10h6v2h-6z';
const HEART = 'M1 0h2v1h-2z M4 0h2v1h-2z M0 1h7v2h-7z M1 3h5v1h-5z M2 4h3v1h-3z M3 5h1v1h-1z';

/** Pixel icons drawn on a unit grid and scaled up, so edges stay crisp at any size. */
function Icon({ icon }: { icon: CardIcon }) {
  switch (icon) {
    case 'mic':
      return (
        <svg className="pixel" aria-hidden="true" viewBox="0 0 40 48" width="40" height="48">
          <path transform="scale(4)" d={MIC} fill="var(--ink)" />
          <path transform="scale(4)" d="M3 2h1v2h-1z" fill="var(--paper)" />
        </svg>
      );
    case 'say':
      return (
        <svg className="pixel" aria-hidden="true" viewBox="0 0 48 48" width="48" height="48">
          <path transform="scale(4)" d="M0 0h12v8h-12z M2 8h3v2h-3z M2 10h1v1h-1z" fill="var(--ink)" />
          <path transform="scale(4)" d="M1 1h10v6h-10z" fill="var(--paper)" />
          <path transform="scale(4)" d="M3 4h1v1h-1z M6 4h1v1h-1z M8 4h1v1h-1z" fill="var(--ink)" />
        </svg>
      );
    case 'versus':
      return (
        <svg className="pixel" aria-hidden="true" viewBox="0 0 56 48" width="56" height="48">
          <path transform="translate(0 6) scale(3)" d={MIC} fill="var(--ink)" />
          <path transform="translate(0 6) scale(3)" d="M3 2h1v2h-1z" fill="var(--paper)" />
          <path transform="translate(32 6) scale(3)" d={MIC} fill="var(--ink)" />
          <path transform="translate(32 6) scale(3)" d="M3 2h1v2h-1z" fill="var(--paper)" />
          <path transform="translate(24 0) scale(1.2)" d={HEART} fill="var(--hot)" />
        </svg>
      );
    case 'trophy':
      return (
        <svg className="pixel" aria-hidden="true" viewBox="0 0 48 48" width="48" height="48">
          <path
            transform="scale(4)"
            d="M3 0h6v5h-6z M0 1h3v1h-3z M9 1h3v1h-3z M0 2h1v2h-1z M11 2h1v2h-1z M1 4h2v1h-2z M9 4h2v1h-2z M4 5h4v1h-4z M5 6h2v2h-2z M3 8h6v3h-6z"
            fill="var(--ink)"
          />
          <path transform="scale(4)" d="M4 1h4v3h-4z M4 9h4v1h-4z" fill="var(--butter)" />
        </svg>
      );
  }
}

/** The bouncing heart that points down at whichever card is selected. */
function HeartPointer() {
  return (
    <span className="home-key__pointer point" aria-hidden="true">
      <svg className="pixel" viewBox="0 0 40 34" width="40" height="34">
        <path transform="translate(4 4) scale(5)" d={HEART} fill="var(--ink)" />
        <path transform="scale(5)" d={HEART} fill="var(--hot)" />
        <path transform="scale(5)" d="M1 1h1v1h-1z" fill="var(--pink-light)" />
      </svg>
    </span>
  );
}

export interface KeyCardProps {
  title: string;
  sub: string;
  kao: string;
  icon: CardIcon;
  color: CardColor;
  selected: boolean;
  pressed: boolean;
  ref?: Ref<HTMLButtonElement>;
  onSelect: () => void;
  onActivate: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => void;
}

/** One 3D keycap menu entry: light bevel, dark side, plum extrude underneath. */
export function KeyCard({ title, sub, kao, icon, color, selected, pressed, ref, onSelect, onActivate, onKeyDown }: KeyCardProps) {
  const cls = ['home-key', `home-key--${color}`, selected && 'is-selected', pressed && 'is-pressed'].filter(Boolean).join(' ');
  return (
    <button
      ref={ref}
      type="button"
      className={cls}
      tabIndex={selected ? 0 : -1}
      onMouseEnter={onSelect}
      onFocus={onSelect}
      onClick={onActivate}
      onKeyDown={onKeyDown}
    >
      {selected && <HeartPointer />}
      <span className="home-key__top">
        <Icon icon={icon} />
      </span>
      <span className="home-key__title">{title}</span>
      <span className="home-key__sub">{sub}</span>
      <span className="home-key__kao" aria-hidden="true">
        {kao}
      </span>
    </button>
  );
}

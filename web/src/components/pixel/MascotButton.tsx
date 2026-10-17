import { useState, type ReactNode } from 'react';
import './pixel.css';

type MascotButtonProps = {
  label: string;
  lines: readonly string[];
  className?: string;
  /** Decorations positioned against the button (e.g. rising notes). */
  extras?: ReactNode;
  children: ReactNode;
};

/**
 * Shared mascot shell: a real button with a speech bubble that cycles through `lines` on click.
 * The bubble floats above the sprite (absolutely positioned), so a longer line never changes the
 * button's size and never nudges the layout around it.
 */
export function MascotButton({ label, lines, className, extras, children }: MascotButtonProps) {
  const [n, setN] = useState(0);
  return (
    <button
      type="button"
      className={className ? `px-mascot ${className}` : 'px-mascot'}
      aria-label={label}
      onClick={() => setN((i) => i + 1)}
    >
      <span className="px-bubble" aria-live="polite">
        {lines[n % lines.length]}
      </span>
      {extras}
      <span className="px-mascot-body">{children}</span>
    </button>
  );
}

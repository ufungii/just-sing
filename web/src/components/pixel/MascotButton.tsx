import { useState, type ReactNode } from 'react';
import './pixel.css';

type MascotButtonProps = {
  label: string;
  lines: readonly string[];
  className?: string;
  /** Extra pixels below the button, matching each mascot's spot in the mockup. */
  marginBottom?: number;
  /** Decorations positioned against the button (e.g. rising notes). */
  extras?: ReactNode;
  children: ReactNode;
};

/** Shared mascot shell: a real button with a speech bubble that cycles through `lines` on click. */
export function MascotButton({ label, lines, className, marginBottom, extras, children }: MascotButtonProps) {
  const [n, setN] = useState(0);
  return (
    <button
      type="button"
      className={className ? `px-mascot ${className}` : 'px-mascot'}
      aria-label={label}
      onClick={() => setN((i) => i + 1)}
      style={{ marginBottom }}
    >
      <span className="px-bubble" aria-live="polite">
        {lines[n % lines.length]}
      </span>
      {extras}
      <span className="px-mascot-body">{children}</span>
    </button>
  );
}

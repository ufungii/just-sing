/**
 * Shared themed building blocks for every screen: the screen shell (frame, pixel sky, back
 * button, 3D title), keycap buttons, panels, a segmented choice, and notices.
 * Screens should compose these rather than restyle buttons themselves.
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { PixelSky } from '../components/pixel';
import { useNav } from '../routes';
import './ui.css';

export type Tone = 'pink' | 'hot' | 'sky' | 'mint' | 'lav' | 'butter' | 'paper';

// ---------- screen shell ----------

interface ScreenShellProps {
  title: string;
  /** Small kaomoji next to the title. Use only glyphs DotGothic16 can draw (see styles/tokens.css). */
  kao?: string;
  /** Defaults to going home. */
  onBack?: () => void;
  backLabel?: string;
  /** Extra controls at the right of the header. */
  right?: ReactNode;
  children: ReactNode;
}

export function ScreenShell({ title, kao, onBack, backLabel = 'BACK', right, children }: ScreenShellProps) {
  const nav = useNav();
  return (
    <main className="ui-screen">
      <PixelSky />
      <div className="ui-frame" aria-hidden="true" />
      <div className="ui-inner">
        <header className="ui-header">
          <PixelButton tone="paper" size="sm" onClick={onBack ?? nav.home}>
            ◀ {backLabel}
          </PixelButton>
          <PixelTitle text={title} />
          {kao && (
            <span className="ui-kao" style={{ fontSize: 22, color: 'var(--hot)' }} aria-hidden="true">
              {kao}
            </span>
          )}
          {right && <div className="ui-header__right">{right}</div>}
        </header>
        {children}
      </div>
    </main>
  );
}

/** The layered 3D pixel title used in every screen header. */
export function PixelTitle({ text }: { text: string }) {
  return (
    <h1 className="ui-title" aria-label={text}>
      {text}
      <span className="l3" aria-hidden="true">{text}</span>
      <span className="l2" aria-hidden="true">{text}</span>
      <span className="l1" aria-hidden="true">{text}</span>
      <span className="l0" aria-hidden="true">{text}</span>
    </h1>
  );
}

// ---------- keycap button ----------

interface PixelButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: Tone;
  size?: 'sm' | 'md' | 'lg';
}

/** A 3D keycap button: lifts on hover, presses in on click, flat and dashed when disabled. */
export function PixelButton({ tone = 'pink', size = 'md', className, type = 'button', ...rest }: PixelButtonProps) {
  const cls = ['ui-key', `ui-key--${tone}`, size !== 'md' && `ui-key--${size}`, className].filter(Boolean).join(' ');
  return <button type={type} className={cls} {...rest} />;
}

// ---------- panel ----------

export function Panel({
  tone = 'paper',
  label,
  className,
  children,
}: {
  tone?: Exclude<Tone, 'hot' | 'butter'>;
  label?: string;
  className?: string;
  children: ReactNode;
}) {
  const cls = ['ui-panel', tone !== 'paper' && `ui-panel--${tone}`, className].filter(Boolean).join(' ');
  return (
    <section className={cls} aria-label={label}>
      {label && <h2 className="ui-panel__label">{label}</h2>}
      {children}
    </section>
  );
}

// ---------- segmented choice ----------

export interface Option<T> {
  value: T;
  label: string;
}

/** A row of keycaps where exactly one is chosen (the chosen one turns butter-yellow and stays lifted). */
export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  tone = 'paper',
}: {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  tone?: Tone;
}) {
  return (
    <div className="ui-seg" role="group" aria-label={label}>
      {options.map((o) => (
        <PixelButton key={String(o.value)} tone={tone} aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </PixelButton>
      ))}
    </div>
  );
}

// ---------- notice ----------

const NOTICE_KAO = { info: '(っ＾▽＾)っ', ok: '＼(^o^)／', warn: '(｡-_-｡)', error: '(,,>﹏<,,)' } as const;

/** Loading, unavailable, saved and error states. An unavailable service is never shown as a bad score. */
export function Notice({
  tone = 'info',
  kao,
  action,
  children,
}: {
  tone?: keyof typeof NOTICE_KAO;
  kao?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={`ui-notice ui-notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span className="ui-kao" aria-hidden="true">
        {kao ?? NOTICE_KAO[tone]}
      </span>
      <div className="ui-notice__body">{children}</div>
      {action}
    </div>
  );
}

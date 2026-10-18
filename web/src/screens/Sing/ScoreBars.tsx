/** Top-right HUD: one bar per singer, filling with that singer's running score. No numbers; a burst of pixels marks every gain or loss. */
import { useEffect, useRef, useState } from 'react';

/** Bar fill (0-100) for a running score; `null` (nothing rated yet) is an empty bar. */
export const barPercent = (score: number | null) => (score === null || !Number.isFinite(score) ? 0 : Math.max(0, Math.min(100, score)));

/** Effect tier: above 50% the bar glows, above 80% it glows harder and sparkles. */
export const barTier = (percent: number) => (percent > 80 ? 'hi' : percent > 50 ? 'mid' : 'low');

/** Which burst a score change earns; changes under half a point are jitter and earn none. */
export const burstKind = (from: number, to: number): 'gain' | 'loss' | null => (Math.abs(to - from) < 0.5 ? null : to > from ? 'gain' : 'loss');

/** Fixed fly-out offsets (px) of the burst's pixels, so every burst looks the same and renders deterministically. */
const PARTICLES: [number, number][] = [[-22, -26], [-10, -34], [4, -38], [16, -30], [28, -20], [-28, -8], [32, -6], [8, -22]];

const BURST_MS = 800;

export interface ScoreBarProps {
  name: string;
  /** Running score 0-100, or null before the first rated phrase. */
  score: number | null;
  /** 0 = player 1 (pink), 1 = player 2 (blue). */
  slot: 0 | 1;
  testId?: string;
}

export function ScoreBar({ name, score, slot, testId }: ScoreBarProps) {
  const pct = barPercent(score);
  const previous = useRef(pct);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [burst, setBurst] = useState<{ id: number; kind: 'gain' | 'loss'; at: number } | null>(null);
  useEffect(() => {
    const kind = burstKind(previous.current, pct);
    previous.current = pct;
    if (!kind) return;
    setBurst((b) => ({ id: (b?.id ?? 0) + 1, kind, at: pct }));
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setBurst(null), BURST_MS);
  }, [pct]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <div className={`score-bar score-bar--p${slot + 1} score-bar--${barTier(pct)}${burst ? ` score-bar--${burst.kind}` : ''}`} data-testid={testId} data-fill={Math.round(pct)} data-scored={score !== null}
      role="meter" aria-label={`${name} running score`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
      <span className="score-bar__name">{name}</span>
      <span className="score-bar__track">
        <span className="score-bar__fill" style={{ width: `${pct}%` }} />
        <i className="score-bar__spark score-bar__spark--a" aria-hidden="true" />
        <i className="score-bar__spark score-bar__spark--b" aria-hidden="true" />
        <i className="score-bar__spark score-bar__spark--c" aria-hidden="true" />
        {burst && (
          <span key={burst.id} className={`score-bar__burst score-bar__burst--${burst.kind}`} style={{ left: `${burst.at}%` }} aria-hidden="true">
            {PARTICLES.map(([dx, dy], i) => (
              <i key={i} style={{ '--dx': `${dx}px`, '--dy': `${burst.kind === 'gain' ? dy : -dy * 0.6}px`, animationDelay: `${(i % 4) * 30}ms` } as React.CSSProperties} />
            ))}
          </span>
        )}
      </span>
    </div>
  );
}

export function ScoreBars({ bars }: { bars: ScoreBarProps[] }) {
  return <div className="score-bars">{bars.map((b) => <ScoreBar key={b.slot} {...b} />)}</div>;
}

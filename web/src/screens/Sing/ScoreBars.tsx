/** Top-right HUD: one slim bar per singer, filling with that singer's running score. No numbers. */

/** Bar fill (0-100) for a running score; `null` (nothing rated yet) is an empty bar. */
export const barPercent = (score: number | null) => (score === null || !Number.isFinite(score) ? 0 : Math.max(0, Math.min(100, score)));

/** Effect tier: above 50% the bar glows, above 80% it glows harder and sparkles. */
export const barTier = (percent: number) => (percent > 80 ? 'hi' : percent > 50 ? 'mid' : 'low');

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
  return (
    <div className={`score-bar score-bar--p${slot + 1} score-bar--${barTier(pct)}`} data-testid={testId} data-fill={Math.round(pct)} data-scored={score !== null}
      role="meter" aria-label={`${name} running score`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
      <span className="score-bar__name">{name}</span>
      <span className="score-bar__track">
        <span className="score-bar__fill" style={{ width: `${pct}%` }} />
        <i className="score-bar__spark score-bar__spark--a" aria-hidden="true" />
        <i className="score-bar__spark score-bar__spark--b" aria-hidden="true" />
        <i className="score-bar__spark score-bar__spark--c" aria-hidden="true" />
      </span>
    </div>
  );
}

export function ScoreBars({ bars }: { bars: ScoreBarProps[] }) {
  return <div className="score-bars">{bars.map((b) => <ScoreBar key={b.slot} {...b} />)}</div>;
}

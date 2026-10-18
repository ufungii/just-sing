/** Big layered pixel words: the per-phrase judgement pop and the 3-2-1 countdown. */
import { useState } from 'react';
import type { Rating } from '../../lib/types';

const LABEL: Record<Rating, string> = { perfect: 'PERFECT!', great: 'GREAT', okay: 'OKAY', bad: 'BAD', miss: 'MISS' };

/** Text stacked in layers for the 3D pixel look; colours come from the `sing-pop--<tone>` class. */
export function LayeredText({ text, className }: { text: string; className: string }) {
  return (
    <div className={className} aria-label={text}>
      <span className="l3" aria-hidden="true">{text}</span>
      <span className="l2" aria-hidden="true">{text}</span>
      <span className="l1" aria-hidden="true">{text}</span>
      <span className="l0" aria-hidden="true">{text}</span>
    </div>
  );
}

/** Pops once per rated phrase; `key` it by phrase id so the animation restarts. */
export function Judgement({ rating }: { rating: Rating }) {
  // Random spot in the right part of the lane, well clear of the now line (24% across) so it can't hide the timing.
  const [spot] = useState(() => ({
    '--jx': `${56 + Math.random() * 28}%`,
    '--jy': `${14 + Math.random() * 56}%`,
    '--jr': `${(Math.random() * 16 - 8).toFixed(1)}deg`,
  } as React.CSSProperties));
  return (
    <div className="sing-judge" role="status" style={spot}>
      <LayeredText text={LABEL[rating]} className={`sing-pop sing-pop--${rating}`} />
    </div>
  );
}

export function Countdown({ value }: { value: string }) {
  return (
    <div className="sing-count" aria-live="assertive">
      <LayeredText key={value} text={value} className="sing-pop sing-pop--count" />
    </div>
  );
}

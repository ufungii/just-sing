/**
 * Guide-vocals control shared by the solo and duet screens: a toggle whose icon, fill and word all
 * agree on the state, plus a pixel-styled volume slider that is dimmed and inert while the guide is off.
 */
import { PixelButton } from './index';
import { PixelIcon } from './PixelIcon';

interface Props {
  on: boolean;
  /** 0..1 */
  volume: number;
  onToggle: () => void;
  onVolume: (volume: number) => void;
}

export function GuideControl({ on, volume, onToggle, onVolume }: Props) {
  const pct = Math.round(volume * 100);
  return (
    <div className="ui-guide" title="Hear the original vocals while you sing (use headphones)">
      <span className="ui-guide__label" aria-hidden="true">GUIDE VOCALS</span>
      <PixelButton size="sm" tone={on ? 'hot' : 'paper'} className={on ? 'ui-guide__btn' : 'ui-guide__btn ui-guide__btn--off'} aria-pressed={on} aria-label="Guide vocals" onClick={onToggle}>
        <PixelIcon name={on ? 'speaker' : 'speakerOff'} size={20} />
        {on ? 'ON' : 'OFF'}
      </PixelButton>
      <input
        type="range"
        className="ui-slider"
        min={0}
        max={100}
        value={pct}
        disabled={!on}
        aria-label="Guide vocal volume"
        style={{ '--fill': `${pct}%` } as React.CSSProperties}
        onChange={(e) => onVolume(Number(e.target.value) / 100)}
      />
    </div>
  );
}

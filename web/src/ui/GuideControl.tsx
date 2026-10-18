/**
 * Guide-vocals control shared by the solo and duet screens. The toggle looks like the ROMANIZATION and
 * ENGLISH buttons beside it (`sing-toggle`); the pixel volume slider appears only while the guide is on.
 */
import { PixelButton } from './index';

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
      <PixelButton size="sm" tone="paper" className="sing-toggle" aria-pressed={on} onClick={onToggle}>
        GUIDE VOCALS
      </PixelButton>
      {on && (
        <input
          type="range"
          className="ui-slider"
          min={0}
          max={100}
          value={pct}
          aria-label="Guide vocal volume"
          style={{ '--fill': `${pct}%` } as React.CSSProperties}
          onChange={(e) => onVolume(Number(e.target.value) / 100)}
        />
      )}
    </div>
  );
}

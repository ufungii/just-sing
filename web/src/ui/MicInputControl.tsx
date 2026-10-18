import { useSyncExternalStore } from 'react';
import { getMicGain, setMicGain, subscribeMicGain } from '../audio/micGain';

export function MicInputControl() {
  const gain = useSyncExternalStore(subscribeMicGain, getMicGain);
  return <label className="ui-guide">
    <span className="ui-guide__label">MIC INPUT {Math.round(gain * 100)}%</span>
    <input type="range" className="ui-slider" min={25} max={400} step={5} value={Math.round(gain * 100)}
      aria-label="Microphone input volume" style={{ '--fill': `${(gain - 0.25) / 3.75 * 100}%` } as React.CSSProperties}
      onChange={(event) => setMicGain(Number(event.target.value) / 100)} />
  </label>;
}

import { nameEasterEgg } from '../EasterEgg/name';
import { useState } from 'react';
import { asGuest, createMatch, savedName } from '../../lib/api';
import type { Register } from '../../lib/types';
import { useNav } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell, Segmented } from '../../ui';
import { ClipList, NAME_MAX, REGISTERS, useClips } from '../Solo/SoloSetup';
import { MicCheck } from '../Solo/MicCheck';
import { TimingCheck, loadCalibration } from '../Solo/TimingCheck';
import '../Solo/SoloSetup.css';

/**
 * Local battle setup, built from the solo setup pieces: one clip, two names and registers (one mic and one
 * timing check, since it is the same laptop), then a server match with both players. A battle needs the
 * server to decide the winner, so unlike solo there is no "sing anyway" path.
 */
export function BattleSetup() {
  const nav = useNav();
  const { clips, loadClips } = useClips();
  const [clipId, setClipId] = useState<string | null>(null);
  const [names, setNames] = useState<[string, string]>([savedName(), '']);
  const [registers, setRegisters] = useState<[Register, Register]>([0, 0]);
  const [micOk, setMicOk] = useState(false);
  const [offset, setOffset] = useState<number | null>(loadCalibration);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [n1, n2] = [names[0].trim(), names[1].trim()];
  const missing = [!clipId && 'a song', (!n1 || !n2) && 'both names', !micOk && 'a mic check'].filter(Boolean) as string[];

  async function onStart() {
    if (nameEasterEgg(nav, n1, n2)) return;
    if (!clipId || !n1 || !n2) return;
    setBusy(true);
    setError(null);
    try {
      const m = await asGuest(n1, () => createMatch(clipId, [n1, n2]));
      nav.go({ name: 'duet', setup: { matchId: m.match_id, clipId, registers, calibrationOffset: offset } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const player = (i: 0 | 1) => (
    <div className="solo-field">
      <label className="solo-field__label" htmlFor={`battle-name-${i}`}>PLAYER {i + 1}</label>
      <input
        id={`battle-name-${i}`}
        className="solo-input"
        value={names[i]}
        onBlur={(e) => { nameEasterEgg(nav, e.currentTarget.value); }}
        maxLength={NAME_MAX}
        placeholder={i ? 'e.g. Jisoo' : 'e.g. Mina'}
        onChange={(e) => setNames((n) => (i ? [n[0], e.target.value] : [e.target.value, n[1]]))}
      />
      <Segmented
        label={`Player ${i + 1} voice range`}
        options={REGISTERS}
        value={registers[i]}
        onChange={(r) => setRegisters((v) => (i ? [v[0], r] : [r, v[1]]))}
      />
    </div>
  );

  return (
    <ScreenShell title="1P VS 2P" kao="(｀∀´)ﾉ☆ヽ(＾▽＾)">
      <div className="solo-grid">
        <Panel tone="pink" label="1 · PICK A SONG" className="solo-songs">
          <ClipList clips={clips} selected={clipId} onSelect={setClipId} onRetry={loadClips} />
        </Panel>

        <div className="solo-side">
          <Panel label="2 · PLAYERS" className="solo-you">
            {player(0)}
            {player(1)}
            <p className="solo-hint">One song, one shared mic. Follow the singer cue: your sections switch automatically without stopping the music.</p>
          </Panel>
          <Panel tone="sky" label="3 · MIC CHECK">
            <MicCheck onPassedChange={setMicOk} />
          </Panel>
          <Panel tone="lav" label="4 · TIMING CHECK (OPTIONAL)">
            <TimingCheck offset={offset} onChange={setOffset} />
          </Panel>
        </div>

        <div className="solo-go">
          {error && (
            <Notice tone="error">Couldn’t start the battle: {error.replace(/\.$/, '')}. A battle needs the score server.</Notice>
          )}
          <p className="solo-go__status" aria-live="polite">
            {busy ? 'Warming up the stage…' : missing.length ? `Still need ${missing.join(', ')}.` : 'All set! Both players, get ready.'}
          </p>
          <PixelButton tone="hot" size="lg" className="solo-start" disabled={missing.length > 0 || busy} onClick={onStart}>
            {busy ? 'STARTING…' : 'FIGHT ♪'}
          </PixelButton>
        </div>
      </div>
    </ScreenShell>
  );
}

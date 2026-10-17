import { useCallback, useEffect, useState } from 'react';
import { ApiError, asGuest, createMatch, getClips, savedName } from '../../lib/api';
import type { ClipSummary, Register } from '../../lib/types';
import { useNav } from '../../routes';
import type { SingSetup } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell, Segmented } from '../../ui';
import { MicCheck } from './MicCheck';
import { TimingCheck, loadCalibration } from './TimingCheck';
import './SoloSetup.css';

/** The server's display-name limit. */
const NAME_MAX = 40;

const REGISTERS: { value: Register; label: string }[] = [
  { value: -12, label: 'LOW 8VA' },
  { value: 0, label: 'ORIGINAL' },
  { value: 12, label: 'HIGH 8VA' },
];

type Clips = { kind: 'loading' } | { kind: 'error'; detail: string | null } | { kind: 'ok'; clips: ClipSummary[] };
type Start = { kind: 'idle' } | { kind: 'starting' } | { kind: 'unsaved'; message: string };

function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  return s < 60 ? `~${s} s` : `~${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/**
 * Solo setup: pick a clip, a name and a voice range, check the mic, optionally measure the
 * device's timing offset, then create a server match and hand everything to the singing screen.
 * If the match can't be created the player can still sing; the score just isn't saved.
 */
export function SoloSetup() {
  const nav = useNav();
  const [clips, setClips] = useState<Clips>({ kind: 'loading' });
  const [clipId, setClipId] = useState<string | null>(null);
  const [name, setName] = useState(savedName);
  const [register, setRegister] = useState<Register>(0);
  const [micOk, setMicOk] = useState(false);
  const [offset, setOffset] = useState<number | null>(loadCalibration);
  const [start, setStart] = useState<Start>({ kind: 'idle' });

  const loadClips = useCallback(() => {
    setClips({ kind: 'loading' });
    getClips().then(
      (list) => {
        setClips({ kind: 'ok', clips: list });
        // One clip: nothing to choose, so pick it.
        if (list.length === 1) setClipId(list[0].id);
      },
      // A plain network failure needs no detail; a server error message might help.
      (e: Error) => setClips({ kind: 'error', detail: e instanceof ApiError && e.code === 'network' ? null : e.message }),
    );
  }, []);
  useEffect(loadClips, [loadClips]);

  const trimmed = name.trim();
  const missing = [!clipId && 'a song', !trimmed && 'your name', !micOk && 'a mic check'].filter(Boolean) as string[];
  const ready = missing.length === 0 && start.kind !== 'starting';

  function sing(match: SingSetup['match']) {
    if (!clipId) return;
    nav.go({
      name: 'sing',
      setup: { runId: crypto.randomUUID(), clipId, register, calibrationOffset: offset, playerName: trimmed, match },
    });
  }

  async function onStart() {
    if (!clipId || !trimmed) return;
    setStart({ kind: 'starting' });
    try {
      const m = await asGuest(trimmed, () => createMatch(clipId));
      sing({ matchId: m.match_id, attemptId: m.attempt_id });
    } catch (e) {
      setStart({ kind: 'unsaved', message: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <ScreenShell title="SOLO SING" kao="(ﾉ≧▽≦)ﾉ">
      <div className="solo-grid">
        <Panel tone="pink" label="1 · PICK A SONG" className="solo-songs">
          <ClipList clips={clips} selected={clipId} onSelect={setClipId} onRetry={loadClips} />
        </Panel>

        <div className="solo-side">
          <Panel label="2 · YOU" className="solo-you">
            <label className="solo-field">
              <span className="solo-field__label">YOUR NAME</span>
              <input
                className="solo-input"
                value={name}
                maxLength={NAME_MAX}
                required
                autoComplete="nickname"
                placeholder="e.g. Mina"
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <div className="solo-field">
              <span className="solo-field__label">VOICE RANGE</span>
              <Segmented label="Voice range" options={REGISTERS} value={register} onChange={setRegister} />
              <p className="solo-hint">Moves the target notes an octave up or down; the music stays in key.</p>
            </div>
          </Panel>

          <Panel tone="sky" label="3 · MIC CHECK">
            <MicCheck onPassedChange={setMicOk} />
          </Panel>

          <Panel tone="lav" label="4 · TIMING CHECK (OPTIONAL)">
            <TimingCheck offset={offset} onChange={setOffset} />
          </Panel>
        </div>

        {/* After the setup panels in the DOM so Tab reaches START last; CSS places it under the songs. */}
        <div className="solo-go">
          {start.kind === 'unsaved' ? (
            <Notice
              tone="warn"
              action={
                <div className="solo-go__actions">
                  <PixelButton tone="paper" size="sm" onClick={onStart}>
                    RETRY
                  </PixelButton>
                  <PixelButton tone="hot" size="sm" onClick={() => sing(null)}>
                    SING ANYWAY ♪
                  </PixelButton>
                </div>
              }
            >
              Couldn’t reach the score server ({start.message.replace(/\.$/, '')}). You can still sing, but this score won’t be saved.
            </Notice>
          ) : (
            <p className="solo-go__status" aria-live="polite">
              {start.kind === 'starting'
                ? 'Warming up the stage…'
                : missing.length
                  ? `Still need ${missing.join(', ')}.`
                  : 'All set! Put your headphones on.'}
            </p>
          )}
          <PixelButton tone="hot" size="lg" className="solo-start" disabled={!ready} onClick={onStart}>
            {start.kind === 'starting' ? 'STARTING…' : 'START ♪'}
          </PixelButton>
        </div>
      </div>
    </ScreenShell>
  );
}

function ClipList({
  clips,
  selected,
  onSelect,
  onRetry,
}: {
  clips: Clips;
  selected: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
}) {
  if (clips.kind === 'loading') return <Notice>Loading songs…</Notice>;
  if (clips.kind === 'error')
    return (
      <Notice
        tone="error"
        action={
          <PixelButton tone="paper" size="sm" onClick={onRetry}>
            RETRY
          </PixelButton>
        }
      >
        Can’t reach the server, so no songs yet. {clips.detail}
      </Notice>
    );
  if (clips.clips.length === 0) return <Notice tone="warn">No songs are installed on the server yet.</Notice>;

  return (
    <ul className="solo-clips" role="list">
      {clips.clips.map((c) => (
        <li key={c.id}>
          <button
            type="button"
            className={`solo-clip${c.id === selected ? ' is-selected' : ''}`}
            aria-pressed={c.id === selected}
            onClick={() => onSelect(c.id)}
          >
            <span className="solo-clip__title">{c.title}</span>
            <span className="solo-clip__artist">{c.artist}</span>
            <span className="solo-clip__meta">
              <span>{formatDuration(c.duration)}</span>
              {c.synthetic && <span className="solo-tag">TEST CLIP · NO AUDIO</span>}
              {c.id === selected && <span className="solo-clip__check">♪ PICKED</span>}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

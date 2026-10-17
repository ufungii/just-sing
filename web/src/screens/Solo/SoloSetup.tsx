import { useCallback, useEffect, useState } from 'react';
import { ApiError, asGuest, createMatch, getClips, savedName } from '../../lib/api';
import type { Register, TimeRange } from '../../lib/types';
import { useNav } from '../../routes';
import type { SingSetup } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell, Segmented } from '../../ui';
import { MicCheck } from './MicCheck';
import { TimingCheck, loadCalibration } from './TimingCheck';
import { PracticeRangePicker } from '../../components/timeline/PracticeRangePicker';
import { SongJacket } from '../../components/songs/SongJacket';
import { SongWheel, useSongEntries } from '../../components/songs/SongWheel';
import type { Clips } from '../../components/songs/SongWheel';
import './SoloSetup.css';

export type { Clips };

/** The server's display-name limit. */
export const NAME_MAX = 40;

export const REGISTERS: { value: Register; label: string }[] = [
  { value: -12, label: 'LOW 8VA' },
  { value: 0, label: 'ORIGINAL' },
  { value: 12, label: 'HIGH 8VA' },
];

type Start = { kind: 'idle' } | { kind: 'starting' } | { kind: 'unsaved'; message: string };

/**
 * Solo setup: pick a clip, a name and a voice range, check the mic, optionally measure the
 * device's timing offset, then create a server match and hand everything to the singing screen.
 * If the match can't be created the player can still sing; the score just isn't saved.
 */
export function SoloSetup() {
  const nav = useNav();
  const [clipId, setClipId] = useState<string | null>(null);
  const [range, setRange] = useState<TimeRange | null>(null);
  const [name, setName] = useState(savedName);
  const [register, setRegister] = useState<Register>(0);
  const [micOk, setMicOk] = useState(false);
  const [offset, setOffset] = useState<number | null>(loadCalibration);
  const [start, setStart] = useState<Start>({ kind: 'idle' });

  const { clips, loadClips } = useClips();
  const entries = useSongEntries(clips);
  // Start on the first playable song so the jacket isn't empty.
  useEffect(() => {
    const first = entries.find((e) => e.clip);
    if (first?.clip) setClipId((id) => id ?? first.clip!.id);
  }, [entries]);
  const chosen = entries.find((e) => e.clip?.id === clipId) ?? null;

  const trimmed = name.trim();
  const missing = [!clipId && 'a song', !trimmed && 'your name', !micOk && 'a mic check'].filter(Boolean) as string[];
  const ready = missing.length === 0 && start.kind !== 'starting';

  function sing(match: SingSetup['match']) {
    if (!clipId) return;
    nav.go({
      name: 'sing',
      setup: { runId: crypto.randomUUID(), clipId, range, register, calibrationOffset: offset, playerName: trimmed, match },
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
      <div className="solo-ribbon">
        <span className="solo-ribbon__stage">STAGE 01</span>
        <span className="solo-ribbon__title">SELECT MUSIC</span>
        <span lang="ko" className="solo-ribbon__ko">
          <span className="song-kao" aria-hidden="true">♪</span> 곡을 골라요! <span className="song-kao" aria-hidden="true">♪</span>
        </span>
      </div>

      <Panel tone="pink" label="1 · PICK A SONG" className="solo-stage">
        <div className="solo-stage__row">
          <SongJacket entry={chosen} />
          <SongWheel clips={clips} selected={clipId} onSelect={(id) => { setClipId(id); setRange(null); }} onRetry={loadClips} />
        </div>
        {clipId && <PracticeRangePicker clipId={clipId} range={range} onChange={setRange} disabled={start.kind === 'starting'} />}
      </Panel>

      <div className="solo-grid solo-grid--setup">
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

/** Loads the clip catalog (shared with battle setup). */
export function useClips() {
  const [clips, setClips] = useState<Clips>({ kind: 'loading' });
  const loadClips = useCallback(() => {
    setClips({ kind: 'loading' });
    getClips().then(
      (list) => setClips({ kind: 'ok', clips: list }),
      // A plain network failure needs no detail; a server error message might help.
      (e: Error) => setClips({ kind: 'error', detail: e instanceof ApiError && e.code === 'network' ? null : e.message }),
    );
  }, []);
  useEffect(loadClips, [loadClips]);
  return { clips, loadClips };
}

/** The song picker used by battle setup and the online lobby: the same wheel, without the jacket. */
export const ClipList = SongWheel;

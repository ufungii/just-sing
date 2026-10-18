import { nameEasterEgg } from '../EasterEgg/name';
import { useCallback, useEffect, useState } from 'react';
import { ApiError, asGuest, createMatch, getClips } from '../../lib/api';
import type { Register, TimeRange } from '../../lib/types';
import { useNav } from '../../routes';
import type { SingSetup } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell, Segmented } from '../../ui';
import { MicCheck } from './MicCheck';
import { loadCalibration } from './TimingCheck';
import { PracticeRangePicker } from '../../components/timeline/PracticeRangePicker';
import { SongJacket } from '../../components/songs/SongJacket';
import { PlayerPicker } from '../../components/players/PlayerPicker';
import { getPlayer, usePlayers } from '../../lib/players';
import { SongWheel, useSongEntries } from '../../components/songs/SongWheel';
import type { Clips } from '../../components/songs/SongWheel';
import './SoloSetup.css';

export type { Clips };

/** Voice range choices, high to low. HIGH and LOW move the target notes one octave. */
export const REGISTERS: { value: Register; label: string }[] = [
  { value: 12, label: 'HIGH' },
  { value: 0, label: 'ORIGINAL' },
  { value: -12, label: 'LOW' },
];

type Start = { kind: 'idle' } | { kind: 'starting' } | { kind: 'unsaved'; message: string } | { kind: 'failed'; message: string };

export type PlayerCount = 1 | 2;
const PLAYER_COUNTS: { value: PlayerCount; label: string }[] = [
  { value: 1, label: '1 PLAYER' },
  { value: 2, label: '2 PLAYERS' },
];

/**
 * Local setup, for one or two singers on this laptop: pick a clip, the player(s) and voice
 * range(s), check the mic, then create a server match. A timing offset measured earlier on this
 * device is still applied. One player goes to the singing screen; if the match can't be created they can still sing,
 * unsaved. Two players take turns in a duet, which needs the server to decide the winner, so there
 * is no "sing anyway" path for them.
 */
export function SoloSetup({ initialPlayers = 1 }: { initialPlayers?: PlayerCount }) {
  const nav = useNav();
  const [count, setCount] = useState<PlayerCount>(initialPlayers);
  const [clipId, setClipId] = useState<string | null>(null);
  const [range, setRange] = useState<TimeRange | null>(null);
  const { lastId } = usePlayers();
  const [ids, setIds] = useState<[string | null, string | null]>([lastId, null]);
  const [registers, setRegisters] = useState<[Register, Register]>([0, 0]);
  const player = getPlayer(ids[0]);
  const player2 = getPlayer(ids[1]);
  const [micOk, setMicOk] = useState(false);
  // One latency offset per device (CLAUDE.md), measured once and kept in this device's storage.
  const [offset] = useState<number | null>(loadCalibration);
  const [start, setStart] = useState<Start>({ kind: 'idle' });

  const { clips, loadClips } = useClips();
  const entries = useSongEntries(clips);
  // Start on the first playable song so the jacket isn't empty.
  useEffect(() => {
    const first = entries.find((e) => e.clip);
    if (first?.clip) setClipId((id) => id ?? first.clip!.id);
  }, [entries]);
  const chosen = entries.find((e) => e.clip?.id === clipId) ?? null;

  const trimmed = player?.name ?? '';
  const trimmed2 = player2?.name ?? '';
  const playersMissing = count === 1 ? !player && 'a player' : (!player || !player2) && 'two players';
  const missing = [!clipId && 'a song', playersMissing, !micOk && 'a mic check'].filter(Boolean) as string[];
  const ready = missing.length === 0 && start.kind !== 'starting';

  function sing(match: SingSetup['match']) {
    if (nameEasterEgg(nav, trimmed)) return;
    if (!clipId) return;
    nav.go({
      name: 'sing',
      setup: { runId: crypto.randomUUID(), clipId, range, register: registers[0], calibrationOffset: offset, playerName: trimmed, match },
    });
  }

  async function onStart() {
    if (count === 2) return onStartDuet();
    if (nameEasterEgg(nav, trimmed)) return;
    if (!clipId || !trimmed) return;
    setStart({ kind: 'starting' });
    try {
      const m = await asGuest(trimmed, () => createMatch(clipId));
      sing({ matchId: m.match_id, attemptId: m.attempt_id });
    } catch (e) {
      setStart({ kind: 'unsaved', message: e instanceof Error ? e.message : String(e) });
    }
  }

  async function onStartDuet() {
    if (nameEasterEgg(nav, trimmed, trimmed2)) return;
    if (!clipId || !trimmed || !trimmed2) return;
    setStart({ kind: 'starting' });
    try {
      const m = await asGuest(trimmed, () => createMatch(clipId, [trimmed, trimmed2]));
      nav.go({ name: 'duet', setup: { matchId: m.match_id, clipId, registers, calibrationOffset: offset } });
    } catch (e) {
      setStart({ kind: 'failed', message: e instanceof Error ? e.message : String(e) });
    }
  }

  const changeCount = (n: PlayerCount) => {
    setCount(n);
    setStart({ kind: 'idle' });
    if (n === 2) setRange(null); // a duet always sings the whole clip
  };

  /** Player dropdown plus voice range for seat `i`. In 2P the two seats can't pick the same player. */
  const seat = (i: 0 | 1) => (
    <div className="solo-field">
      <PlayerPicker
        label={count === 1 ? 'PLAYER' : `PLAYER ${i + 1}`}
        value={ids[i]}
        disabledId={count === 2 ? ids[i ? 0 : 1] : undefined}
        onChange={(id) => setIds((v) => (i ? [v[0], id] : [id, v[1]]))}
      />
      <span className="solo-field__label">VOICE RANGE</span>
      <Segmented
        label={count === 1 ? 'Voice range' : `Player ${i + 1} voice range`}
        options={REGISTERS}
        value={registers[i]}
        onChange={(r) => setRegisters((v) => (i ? [v[0], r] : [r, v[1]]))}
      />
    </div>
  );

  return (
    <ScreenShell title="LOCAL" kao={count === 1 ? '(ﾉ≧▽≦)ﾉ' : '(｀∀´)ﾉ☆ヽ(＾▽＾)'}>
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
        {clipId && count === 1 && <PracticeRangePicker clipId={clipId} range={range} onChange={setRange} disabled={start.kind === 'starting'} />}
      </Panel>

      <div className="solo-grid solo-grid--setup">
        <div className="solo-side">
          <Panel label="2 · WHO'S SINGING" className="solo-you">
            <Segmented label="Number of players" options={PLAYER_COUNTS} value={count} onChange={changeCount} />
            {seat(0)}
            {count === 2 && seat(1)}
            <p className="solo-hint">
              {count === 1
                ? 'Voice range moves the target notes an octave up or down; the music stays in key.'
                : 'One song, one shared mic. Follow the singer cue: your sections switch automatically without stopping the music.'}
            </p>
          </Panel>

          <Panel tone="sky" label="3 · MIC CHECK">
            <MicCheck onPassedChange={setMicOk} />
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
          ) : start.kind === 'failed' ? (
            <Notice tone="error">Couldn’t start the duet: {start.message.replace(/\.$/, '')}. Two players need the score server.</Notice>
          ) : (
            <p className="solo-go__status" aria-live="polite">
              {start.kind === 'starting'
                ? 'Warming up the stage…'
                : missing.length
                  ? `Still need ${missing.join(', ')}.`
                  : count === 1
                    ? 'All set! Put your headphones on.'
                    : 'All set! Both players, get ready.'}
            </p>
          )}
          <PixelButton tone="hot" size="lg" className="solo-start" disabled={!ready} onClick={onStart}>
            {start.kind === 'starting' ? 'STARTING…' : count === 1 ? 'START ♪' : 'FIGHT ♪'}
          </PixelButton>
        </div>
      </div>
    </ScreenShell>
  );
}

/** Loads the clip catalog (shared with the online lobby). */
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

/** The song picker used by the online lobby: the same wheel, without the jacket. */
export const ClipList = SongWheel;

import { nameEasterEgg } from '../EasterEgg/name';
import { useEffect, useState } from 'react';
import { ApiError, asGuest, retryTurn } from '../../lib/api';
import { getPlayer, usePlayers } from '../../lib/players';
import { PlayerPicker } from '../../components/players/PlayerPicker';
import { ProfileDialog } from '../../components/players/ProfileDialog';
import { SongJacket } from '../../components/songs/SongJacket';
import { SongWheel, useSongEntries } from '../../components/songs/SongWheel';
import type { Clips } from '../../components/songs/SongWheel';
import {
  abortRoom, connectRoom, createRoom, filterRooms, getRoom, joinRoomById, leaveRoom, listRooms, PASSWORD_MAX, PASSWORD_MIN, passwordProblem,
  pushSnapshot, rematchRoom, setReady, setRoomClip, setRoomRange, startRoom, useRoomLive,
} from '../../lib/rooms';
import type { RoomListItem, RoomSnapshot, RoomTab, Visibility } from '../../lib/rooms';
import type { Register } from '../../lib/types';
import { useNav } from '../../routes';
import type { RoomRef } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell, Segmented } from '../../ui';
import { MatchBoard } from '../Battle/BattleTurn';
import { CoachPanel } from '../Results/CoachPanel';
import { useManifest } from '../Results/useManifest';
import { MicCheck } from '../Solo/MicCheck';
import { REGISTERS, useClips } from '../Solo/SoloSetup';
import { loadCalibration } from '../Solo/TimingCheck';
import { PracticeRangePicker } from '../../components/timeline/PracticeRangePicker';
import { rangeLabel } from '../../components/timeline/range';
import '../Solo/SoloSetup.css';
import { Duet } from '../Duet/Duet';

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Online rooms: the create/join form, then the room itself (lobby, turns, results) driven by server snapshots. */
export function Online({ room, notice }: { room?: RoomRef; notice?: string }) {
  return room ? <RoomView room={room} notice={notice} /> : <Entry notice={notice} />;
}

const TABS: { value: RoomTab; label: string }[] = [{ value: 'all', label: 'ALL' }, { value: 'public', label: 'PUBLIC' }, { value: 'private', label: 'PRIVATE' }];
const VISIBILITY: { value: Visibility; label: string }[] = [{ value: 'public', label: 'PUBLIC' }, { value: 'private', label: 'PRIVATE' }];

/**
 * The online menu: CREATE ROOM or JOIN ROOM. The song is chosen inside the room, not here. Rooms are found in a
 * list (public ones join with a tap, private ones need their password); room codes are no longer shown, and an old
 * `?room=CODE` link just lands here.
 */
function Entry({ notice }: { notice?: string }) {
  const nav = useNav();
  const { clips } = useClips();
  const { players, lastId } = usePlayers();
  const [playerId, setPlayerId] = useState<string | null>(lastId);
  const [step, setStep] = useState<'menu' | 'create' | 'join'>('menu');
  const [visibility, setVisibility] = useState<Visibility>('public');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const who = getPlayer(playerId)?.name ?? '';
  const needsProfile = players.length === 0;

  useEffect(() => {
    if (location.search.includes('room=')) history.replaceState(null, '', location.pathname); // old invite links: just the menu
  }, []);

  async function enter(call: () => Promise<RoomSnapshot>) {
    if (nameEasterEgg(nav, who)) return;
    setBusy(true);
    setError(null);
    try {
      const snap = await asGuest(who, call);
      nav.go({ name: 'online', room: { id: snap.id, slot: snap.you ?? 0 } });
    } catch (e) {
      setError(e instanceof ApiError && e.code === 'network' ? 'Can’t reach the server. Check the connection and try again.' : msg(e));
      setBusy(false);
    }
  }

  // Playing online needs a player profile (name + avatar) on this device; make one first.
  if (needsProfile)
    return (
      <ScreenShell title="ONLINE" kao="(＾▽＾)ﾉ">
        <Panel tone="pink" label="CREATE A PLAYER FIRST">
          <p className="solo-hint">Pick a name and an avatar. It is only saved on this device.</p>
          <ProfileDialog open startAdding onClose={() => {}} onAdded={(p) => setPlayerId(p.id)} />
        </Panel>
      </ScreenShell>
    );

  const picker = (
    <Panel label="WHO'S PLAYING" className="solo-you">
      <PlayerPicker label="PLAYER" value={playerId} onChange={setPlayerId} />
    </Panel>
  );
  const problem = visibility === 'private' ? passwordProblem(password) : null;

  if (step === 'create')
    return (
      <ScreenShell title="CREATE ROOM" kao="(＾▽＾)ﾉ" onBack={() => setStep('menu')} backLabel="BACK">
        <div className="solo-side">
          {picker}
          <Panel tone="pink" label="WHO CAN JOIN?">
            <Segmented label="Room visibility" options={VISIBILITY} value={visibility} onChange={setVisibility} />
            {visibility === 'private' ? (
              <div className="solo-field">
                <input className="solo-input" aria-label="Room password" type="text" autoComplete="off" value={password}
                  maxLength={PASSWORD_MAX} placeholder="CHOOSE A PASSWORD" onChange={(e) => setPassword(e.target.value)} />
                <p className="solo-hint">{password && problem ? problem : `${PASSWORD_MIN} to ${PASSWORD_MAX} characters. Share it with your friend.`}</p>
              </div>
            ) : (
              <p className="solo-hint">Anyone on the app can join from the room list.</p>
            )}
          </Panel>
          <div className="solo-go">
            <PixelButton tone="hot" size="lg" disabled={busy || !who || !!problem}
              onClick={() => enter(() => createRoom(visibility, visibility === 'private' ? password : undefined))}>
              {busy ? 'WORKING…' : 'CREATE ROOM ♪'}
            </PixelButton>
          </div>
          {error && <Notice tone="error">{error}</Notice>}
        </div>
      </ScreenShell>
    );

  if (step === 'join')
    return (
      <ScreenShell title="JOIN ROOM" kao="ヽ(＾▽＾)" onBack={() => setStep('menu')} backLabel="BACK">
        {notice && <Notice tone="warn">{notice}</Notice>}
        <div className="solo-side">
          {picker}
          <RoomList who={who} clips={clips} busy={busy} onJoin={(id, pw) => enter(() => joinRoomById(id, pw))} />
          {error && <Notice tone="error">{error}</Notice>}
        </div>
      </ScreenShell>
    );

  return (
    <ScreenShell title="ONLINE" kao="(＾▽＾)ﾉ ⇄ ヽ(＾▽＾)">
      {notice && <Notice tone="warn">{notice}</Notice>}
      <div className="solo-side">
        {picker}
        <div className="solo-go">
          <PixelButton tone="hot" size="lg" disabled={!who} onClick={() => setStep('create')}>CREATE ROOM</PixelButton>
          <PixelButton tone="sky" size="lg" disabled={!who} onClick={() => setStep('join')}>JOIN ROOM</PixelButton>
        </div>
        {!who && <p className="solo-hint">Pick a player first.</p>}
      </div>
    </ScreenShell>
  );
}

/** Lobby rooms with an open seat (plus your own), refreshed every few seconds, with tabs and a host-name search. */
function RoomList({ who, clips, busy, onJoin }: { who: string; clips: Clips; busy: boolean; onJoin: (id: string, password?: string) => void }) {
  const [rooms, setRooms] = useState<RoomListItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<RoomTab>('all');
  const [query, setQuery] = useState('');
  const [asking, setAsking] = useState<string | null>(null); // the private room whose password is being typed
  const [password, setPassword] = useState('');
  const entries = useSongEntries(clips);
  const titleOf = (id: string) => entries.find((e) => e.clip?.id === id)?.title ?? id;

  useEffect(() => {
    if (!who) return;
    let live = true;
    const load = () => asGuest(who, listRooms).then((r) => live && (setRooms(r), setFailed(false)), () => live && setFailed(true));
    load();
    const timer = window.setInterval(load, 5000);
    return () => { live = false; window.clearInterval(timer); };
  }, [who]);

  const shown = rooms ? filterRooms(rooms, tab, query) : [];
  return (
    <Panel tone="sky" label="ROOMS">
      <Segmented label="Show rooms" options={TABS} value={tab} onChange={setTab} />
      <input className="solo-input" aria-label="Search by host name" value={query} placeholder="SEARCH BY HOST" onChange={(e) => setQuery(e.target.value)} />
      {failed && <Notice tone="warn">Can’t load rooms right now. Trying again…</Notice>}
      {rooms && !shown.length && <p className="solo-hint">{rooms.length ? 'No rooms match.' : 'No open rooms yet. Make one!'}</p>}
      <ul role="list" style={{ listStyle: 'none', padding: 0, margin: 0 }} data-testid="room-list">
        {shown.map((r) => (
          <li key={r.id} style={{ fontSize: 22, margin: '8px 0' }}>
            <PixelButton tone={r.visibility === 'private' ? 'lav' : 'mint'} size="sm" disabled={busy}
              onClick={() => (r.visibility === 'private' && !r.mine ? (setAsking(asking === r.id ? null : r.id), setPassword('')) : onJoin(r.id))}>
              {r.mine ? 'REJOIN' : r.visibility === 'private' ? '🔒 JOIN' : 'JOIN'}
            </PixelButton>{' '}
            <strong>{r.host_name}</strong> · {titleOf(r.clip_id)} · {r.players}/2
            {asking === r.id && (
              <div className="solo-field">
                <input className="solo-input" aria-label="Room password" autoFocus value={password} maxLength={PASSWORD_MAX} placeholder="PASSWORD"
                  onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && password && onJoin(r.id, password)} />
                <PixelButton tone="hot" size="sm" disabled={busy || !password} onClick={() => onJoin(r.id, password)}>ENTER</PixelButton>
              </div>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** One room, whatever state it is in. Everything shown comes from the latest server snapshot. */
function RoomView({ room, notice }: { room: RoomRef; notice?: string }) {
  const nav = useNav();
  const live = useRoomLive();
  const { clips, loadClips } = useClips();
  const [register, setRegister] = useState<Register>(room.prefs?.register ?? 0);
  const [offset] = useState<number | null>(() => (room.prefs ? room.prefs.offset : loadCalibration()));
  const [micOk, setMicOk] = useState(!!room.prefs); // coming back from singing: the mic already worked
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  const [voiceMuted, setVoiceMuted] = useState(false);

  // Connect once, and seed with a plain GET so the screen never waits on the socket.
  useEffect(() => {
    connectRoom(room.id);
    getRoom(room.id).then(pushSnapshot, (e) => setGone(e instanceof ApiError && e.status === 404 ? 'That room no longer exists.' : msg(e)));
    // Re-fetch when the socket (re)opens: the fresh snapshot is the truth after any gap.
  }, [room.id]);
  useEffect(() => {
    if (live.conn === 'open') getRoom(room.id).then(pushSnapshot, () => {});
  }, [live.conn, room.id]);

  const snap = live.snapshot;
  const isHost = room.slot === 0;
  // The host leaving the lobby closes the room for everyone.
  const leave = () => {
    if (isHost && snap?.state === 'lobby') abortRoom(room.id).catch(() => {});
    leaveRoom();
    nav.home();
  };
  // If the host closes the room, the other player lands back on the room list with a notice.
  useEffect(() => {
    if (snap?.state === 'aborted' && !isHost) {
      leaveRoom();
      nav.go({ name: 'online', notice: 'The host closed the room.' });
    }
  }, [snap?.state, isHost, nav]);
  const clip = clips.kind === 'ok' ? clips.clips.find((c) => c.id === snap?.clip_id) : undefined;
  const song = useManifest(snap?.clip_id ?? '');
  const entries = useSongEntries(clips);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(msg(e));
      setBusy(false);
      return false;
    }
    setBusy(false);
    return true;
  };

  function sing() {
    const m = snap?.match;
    const attempt = m?.attempts.filter((a) => a.slot === room.slot && a.state !== 'accepted' && a.state !== 'invalidated').pop();
    if (!snap || !m || !attempt) return setError('Your turn is not open yet. Try again in a moment.');
    nav.go({
      name: 'sing',
      setup: {
        runId: crypto.randomUUID(),
        clipId: snap.clip_id,
        range: snap.range,
        register,
        calibrationOffset: offset,
        playerName: snap.members.find((p) => p.slot === room.slot)?.display_name ?? 'Player',
        match: { matchId: m.id, attemptId: attempt.id },
        online: { roomId: room.id, slot: room.slot },
      },
    });
  }

  if (gone || live.conn === 'refused')
    return (
      <ScreenShell title="ONLINE" kao="(；へ；)" onBack={leave} backLabel="HOME">
        <Notice tone="error">{gone ?? 'This room is no longer open to you (it may have expired).'}</Notice>
        <PixelButton tone="hot" onClick={() => { leaveRoom(); nav.go({ name: 'online' }); }}>BACK TO ONLINE</PixelButton>
      </ScreenShell>
    );
  if (!snap)
    return (
      <ScreenShell title="ONLINE" kao="(・ω・)" onBack={leave} backLabel="LEAVE">
        <Notice>Opening the room…</Notice>
      </ScreenShell>
    );

  const me = snap.members.find((p) => p.slot === room.slot);
  const other = snap.members.find((p) => p.slot !== room.slot);
  const match = snap.match;
  const notices = (
    <>
      {notice && <Notice tone="error">{notice}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      {live.conn !== 'open' && <Notice tone="warn">Reconnecting to the room… what you see may be out of date.</Notice>}
      {other && !other.connected && live.conn === 'open' && <Notice tone="warn">{other.display_name} is disconnected. They can rejoin from the room list.</Notice>}
    </>
  );

  // ---- lobby ----
  if (snap.state === 'lobby') {
    const both = snap.members.length === 2 && snap.members.every((p) => p.ready);
    return (
      <ScreenShell title="ROOM" kao="(＾▽＾)ﾉ" onBack={leave} backLabel="LEAVE">
        {notices}
        <div className="solo-grid">
          <Panel tone="pink" label={isHost ? 'PICK A SONG' : 'SONG (THE HOST PICKS)'} className="solo-stage">
            <div className="solo-stage__row">
              <SongJacket entry={entries.find((e) => e.clip?.id === snap.clip_id) ?? null} />
              {isHost && (
                <SongWheel clips={clips} selected={snap.clip_id} onRetry={loadClips}
                  onSelect={(id) => id !== snap.clip_id && act(() => setRoomClip(room.id, id).then(pushSnapshot))} />
              )}
            </div>
            <PracticeRangePicker clipId={snap.clip_id} range={snap.range} disabled={busy}
              onChange={isHost ? (range) => act(() => setRoomRange(room.id, range).then(pushSnapshot)) : undefined} />
          </Panel>
          <div className="solo-side">
            <Panel label="PLAYERS" className="solo-you">
              <p className="solo-hint">{snap.visibility === 'private' ? '🔒 Private room' : 'Public room'}. Use voice chat to agree on a song; the host picks it.</p>
              <ul role="list" style={{ listStyle: 'none', padding: 0 }}>
                {[0, 1].map((slot) => {
                  const p = snap.members.find((m) => m.slot === slot);
                  return (
                    <li key={slot} style={{ fontSize: 22 }}>
                      {p ? `${p.display_name}${slot === 0 ? ' (host)' : ''}${slot === room.slot ? ' (you)' : ''}: ${p.ready ? 'READY' : 'not ready'}${p.connected ? '' : ' · offline'}` : 'Waiting for a friend to join…'}
                    </li>
                  );
                })}
              </ul>
            </Panel>
            <Panel tone="lav" label="YOUR VOICE RANGE">
              <Segmented label="Voice range" options={REGISTERS} value={register} onChange={setRegister} />
            </Panel>
            <Panel tone="sky" label="MIC CHECK">
              <p className="solo-hint">Headphones required. During the duet, your voice is shared live with the other player in your sections. It is not recorded. Muting sharing keeps your local scoring active.</p>
              <PixelButton size="sm" aria-label="Mute my mic to opponent" aria-pressed={voiceMuted}
                tone={voiceMuted ? 'paper' : 'hot'} onClick={() => setVoiceMuted((v) => !v)}>
                {voiceMuted ? 'MY VOICE MUTED' : 'SHARING MY VOICE'}
              </PixelButton>
              <MicCheck onPassedChange={setMicOk} />
            </Panel>
          </div>
          <div className="solo-go">
            <PixelButton tone="sky" size="lg" disabled={busy || !micOk} onClick={() => act(() => setReady(room.id, !me?.ready).then(pushSnapshot))}>
              {!micOk ? 'DO THE MIC CHECK FIRST' : me?.ready ? 'NOT READY' : 'READY ✓'}
            </PixelButton>
            {isHost && (
              <PixelButton tone="hot" size="lg" disabled={busy || !both} onClick={() => act(() => startRoom(room.id))}>
                {both ? 'START ♪' : 'START (BOTH MUST BE READY)'}
              </PixelButton>
            )}
          </div>
        </div>
      </ScreenShell>
    );
  }

  // ---- aborted ----
  if (snap.state === 'aborted' || !match)
    return (
      <ScreenShell title="ONLINE" kao="(；へ；)" onBack={leave} backLabel="HOME">
        <Notice tone="warn">The host ended this room.</Notice>
      </ScreenShell>
    );

  // ---- finished ----
  const myAttempt = match.attempts.find((a) => a.slot === room.slot && a.state === 'accepted');
  if (snap.state === 'finished')
    return (
      <ScreenShell title="ROOM RESULTS" kao="ヾ(＾∇＾)" onBack={leave} backLabel="LEAVE">
        {notices}
        <MatchBoard match={match} song={song} />
        {/* Each player's own tip only: the attempt of this browser's slot (1v1 turns, not duets). */}
        {!match.duet && myAttempt && <CoachPanel attemptId={myAttempt.id} />}
        <div className="results-actions">
          {isHost ? (
            <PixelButton tone="hot" size="lg" disabled={busy} onClick={() => act(() => rematchRoom(room.id))}>
              ↻ REMATCH
            </PixelButton>
          ) : (
            <p className="solo-hint">The host can start a rematch.</p>
          )}
          <PixelButton tone="mint" size="lg" onClick={leave}>HOME</PixelButton>
        </div>
      </ScreenShell>
    );

  if (match.duet) {
    if (match.state === 'retry_required') return (
      <ScreenShell title="DUET STOPPED" kao="(；へ；)" onBack={leave} backLabel="LEAVE">
        {notices}
        <Notice tone="warn">The shared performance stopped or a player missed it. Restart the whole duet together; individual sections cannot be replayed.</Notice>
        {isHost ? <PixelButton tone="hot" onClick={() => act(() => rematchRoom(room.id))}>RESTART TOGETHER</PixelButton>
          : <p>The host can restart the duet for both players.</p>}
      </ScreenShell>
    );
    return <Duet key={match.id} setup={{ matchId: match.id, clipId: snap.clip_id, registers: [register, register],
      calibrationOffset: offset, online: { roomId: room.id, slot: room.slot } }} onLeave={leave}
      voiceMuted={voiceMuted} onVoiceMuted={setVoiceMuted} />;
  }

  // ---- playing: my turn, or waiting for the other singer ----
  const myTurn = match.state === 'active' && match.active_slot === room.slot;
  const singer = snap.members.find((p) => p.slot === match.active_slot);
  const rangeStart = snap.range?.start ?? 0;
  const dur = (snap.range?.end ?? song?.duration ?? clip?.duration ?? 0) - rangeStart;
  const p = live.progress;
  return (
    <ScreenShell title="ROOM" kao="♪(^▽^)♪" onBack={leave} backLabel="LEAVE">
      {notices}
      {snap.range && <p className="solo-hint">Practice section · {rangeLabel(snap.range)}</p>}
      {match.state === 'retry_required' ? (
        match.active_slot === room.slot ? (
          <Panel tone="pink" label="TURN LOST">
            <p style={{ fontSize: 22, margin: '0 0 16px' }}>Your last turn was not saved (it was left or ran out of time). Nothing was scored.</p>
            <PixelButton tone="hot" size="lg" disabled={busy} onClick={() => act(() => retryTurn(match.id))}>TRY THAT TURN AGAIN</PixelButton>
          </Panel>
        ) : (
          <Notice tone="warn">Waiting for {singer?.display_name ?? 'the other player'} to retry their turn.</Notice>
        )
      ) : myTurn ? (
        <Panel tone="pink" label="YOUR TURN">
          <p style={{ fontSize: 24, margin: '0 0 16px' }}>{me?.display_name}, headphones on. Same song and rules for both of you.</p>
          <PixelButton tone="hot" size="lg" disabled={busy} onClick={sing}>SING ▶</PixelButton>
        </Panel>
      ) : (
        <Panel tone="sky" label={`WAITING FOR ${(singer?.display_name ?? 'THE OTHER PLAYER').toUpperCase()}`}>
          <p style={{ fontSize: 22, margin: '0 0 12px' }}>
            {match.attempts.some((a) => a.slot === room.slot && a.state === 'accepted')
              ? 'Your score is saved. The winner appears when they finish.'
              : `${singer?.display_name ?? 'They'} is singing. Your turn comes next.`}
          </p>
          <div className="sing-progress" aria-hidden="true">
            <div className="sing-progress__fill" style={{ width: `${dur && p ? Math.max(0, Math.min(1, (p.t - rangeStart) / dur)) * 100 : 0}%` }} />
          </div>
          <p data-testid="live-badges" style={{ fontSize: 22 }}>
            {p ? `Live score ${p.running.toFixed(1)} · ` : ''}
            {live.badges.length ? live.badges.map((b) => `${b.rating.toUpperCase()}`).join(' · ') : 'No phrases rated yet.'}
          </p>
          <p className="solo-hint">Live updates are provisional; only the saved score counts.</p>
        </Panel>
      )}
      {isHost && <PixelButton tone="paper" size="sm" disabled={busy} onClick={() => act(() => abortRoom(room.id))}>END ROOM (STUCK?)</PixelButton>}
    </ScreenShell>
  );
}

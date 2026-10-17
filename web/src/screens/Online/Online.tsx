import { useEffect, useState } from 'react';
import { ApiError, asGuest, retryTurn, savedName } from '../../lib/api';
import {
  abortRoom, connectRoom, createRoom, getRoom, joinRoom, leaveRoom, pushSnapshot, rematchRoom, setReady, setRoomClip, startRoom,
  useRoomLive,
} from '../../lib/rooms';
import type { RoomSnapshot } from '../../lib/rooms';
import type { Register } from '../../lib/types';
import { useNav } from '../../routes';
import type { RoomRef } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell, Segmented } from '../../ui';
import { MatchBoard } from '../Battle/BattleTurn';
import { useManifest } from '../Results/useManifest';
import { MicCheck } from '../Solo/MicCheck';
import { ClipList, NAME_MAX, REGISTERS, useClips } from '../Solo/SoloSetup';
import { TimingCheck, loadCalibration } from '../Solo/TimingCheck';
import '../Solo/SoloSetup.css';

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Online rooms: the create/join form, then the room itself (lobby, turns, results) driven by server snapshots. */
export function Online({ room, notice }: { room?: RoomRef; notice?: string }) {
  return room ? <RoomView room={room} notice={notice} /> : <Entry />;
}

/** Create a room (pick a clip) or join one by code. The code can arrive in the URL as `?room=CODE`. */
function Entry() {
  const nav = useNav();
  const { clips, loadClips } = useClips();
  const [name, setName] = useState(savedName);
  const [clipId, setClipId] = useState<string | null>(null);
  const [code, setCode] = useState(() => new URLSearchParams(location.search).get('room') ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const who = name.trim();

  async function enter(call: () => Promise<RoomSnapshot>) {
    setBusy(true);
    setError(null);
    try {
      const snap = await asGuest(who, call);
      history.replaceState(null, '', location.pathname); // the ?room= link has done its job
      nav.go({ name: 'online', room: { id: snap.id, slot: snap.you ?? 0 } });
    } catch (e) {
      setError(e instanceof ApiError && e.code === 'network' ? 'Can’t reach the server. Check the connection and try again.' : msg(e));
      setBusy(false);
    }
  }

  return (
    <ScreenShell title="ONLINE" kao="(＾▽＾)ﾉ ⇄ ヽ(＾▽＾)">
      <div className="solo-grid">
        <Panel tone="pink" label="1 · NEW ROOM: PICK A SONG" className="solo-songs">
          <ClipList clips={clips} selected={clipId} onSelect={setClipId} onRetry={loadClips} />
          <div className="solo-go">
            <PixelButton tone="hot" size="lg" disabled={busy || !who || !clipId} onClick={() => enter(() => createRoom(clipId!))}>
              {busy ? 'WORKING…' : 'CREATE ROOM ♪'}
            </PixelButton>
          </div>
        </Panel>
        <div className="solo-side">
          <Panel label="YOUR NAME" className="solo-you">
            <input
              className="solo-input"
              aria-label="Your name"
              value={name}
              maxLength={NAME_MAX}
              placeholder="e.g. Mina"
              onChange={(e) => setName(e.target.value)}
            />
          </Panel>
          <Panel tone="sky" label="2 · JOIN A FRIEND">
            <div className="solo-field">
              <input
                className="solo-input"
                aria-label="Room code"
                value={code}
                maxLength={8}
                placeholder="ROOM CODE"
                style={{ textTransform: 'uppercase' }}
                onChange={(e) => setCode(e.target.value)}
              />
              <PixelButton tone="sky" disabled={busy || !who || !code.trim()} onClick={() => enter(() => joinRoom(code.trim()))}>
                JOIN
              </PixelButton>
            </div>
          </Panel>
          {!who && <p className="solo-hint">Enter your name first.</p>}
          {error && <Notice tone="error">{error}</Notice>}
        </div>
      </div>
    </ScreenShell>
  );
}

/** One room, whatever state it is in. Everything shown comes from the latest server snapshot. */
function RoomView({ room, notice }: { room: RoomRef; notice?: string }) {
  const nav = useNav();
  const live = useRoomLive();
  const { clips, loadClips } = useClips();
  const [register, setRegister] = useState<Register>(room.prefs?.register ?? 0);
  const [offset, setOffset] = useState<number | null>(() => (room.prefs ? room.prefs.offset : loadCalibration()));
  const [micOk, setMicOk] = useState(!!room.prefs); // coming back from singing: the mic already worked
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gone, setGone] = useState<string | null>(null);

  // Connect once, and seed with a plain GET so the screen never waits on the socket.
  useEffect(() => {
    connectRoom(room.id);
    getRoom(room.id).then(pushSnapshot, (e) => setGone(e instanceof ApiError && e.status === 404 ? 'That room no longer exists.' : msg(e)));
    // Re-fetch when the socket (re)opens: the fresh snapshot is the truth after any gap.
  }, [room.id]);
  useEffect(() => {
    if (live.conn === 'open') getRoom(room.id).then(pushSnapshot, () => {});
  }, [live.conn, room.id]);

  const leave = () => {
    leaveRoom();
    nav.home();
  };
  const snap = live.snapshot;
  const isHost = room.slot === 0;
  const clip = clips.kind === 'ok' ? clips.clips.find((c) => c.id === snap?.clip_id) : undefined;
  const song = useManifest(snap?.clip_id ?? '');

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(msg(e));
    }
    setBusy(false);
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
  const link = `${location.origin}/?room=${snap.code}`;
  const notices = (
    <>
      {notice && <Notice tone="error">{notice}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      {live.conn !== 'open' && <Notice tone="warn">Reconnecting to the room… what you see may be out of date.</Notice>}
      {other && !other.connected && live.conn === 'open' && <Notice tone="warn">{other.display_name} is disconnected. They can rejoin with the code {snap.code}.</Notice>}
    </>
  );

  // ---- lobby ----
  if (snap.state === 'lobby') {
    const both = snap.members.length === 2 && snap.members.every((p) => p.ready);
    return (
      <ScreenShell title={`ROOM ${snap.code}`} kao="(＾▽＾)ﾉ" onBack={leave} backLabel="LEAVE">
        {notices}
        <div className="solo-grid">
          <Panel tone="pink" label="SONG" className="solo-songs">
            {isHost ? (
              <ClipList clips={clips} selected={snap.clip_id} onSelect={(id) => id !== snap.clip_id && act(() => setRoomClip(room.id, id).then(pushSnapshot))} onRetry={loadClips} />
            ) : (
              <p style={{ fontSize: 22, margin: 0 }}>{clip ? `${clip.title} · ${clip.artist}` : snap.clip_id}. The host picks the song.</p>
            )}
          </Panel>
          <div className="solo-side">
            <Panel label="PLAYERS" className="solo-you">
              <p className="solo-hint">Room code: <strong style={{ fontSize: 28 }} data-testid="room-code">{snap.code}</strong></p>
              <p className="solo-hint">Or send this link: <a href={link}>{link}</a></p>
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
              <MicCheck onPassedChange={setMicOk} />
            </Panel>
            <Panel tone="lav" label="TIMING CHECK (OPTIONAL)">
              <TimingCheck offset={offset} onChange={setOffset} />
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
  if (snap.state === 'finished')
    return (
      <ScreenShell title="ROOM RESULTS" kao="ヾ(＾∇＾)" onBack={leave} backLabel="LEAVE">
        {notices}
        <MatchBoard match={match} song={song} />
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

  // ---- playing: my turn, or waiting for the other singer ----
  const myTurn = match.state === 'active' && match.active_slot === room.slot;
  const singer = snap.members.find((p) => p.slot === match.active_slot);
  const dur = song?.duration ?? clip?.duration ?? 0;
  const p = live.progress;
  return (
    <ScreenShell title={`ROOM ${snap.code}`} kao="♪(^▽^)♪" onBack={leave} backLabel="LEAVE">
      {notices}
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
            <div className="sing-progress__fill" style={{ width: `${dur && p ? Math.max(0, Math.min(1, p.t / dur)) * 100 : 0}%` }} />
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

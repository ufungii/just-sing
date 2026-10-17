import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SingEngine } from '../../audio/engine';
import { openMic, stopStream } from '../../audio/sources';
import { ApiError, duetReady, getManifest, getMatch, rematch, serverTime, stopDuet, submitResult } from '../../lib/api';
import type { MatchView, PhraseScore, Song } from '../../lib/types';
import { useNav, type DuetSetup } from '../../routes';
import { aggregate, buildTargetTrack, displayNotes, phraseSettlesAt, phraseWeights, registerRatio, scorePhrase, SCORING_CONFIG } from '../../scoring';
import { Notice, Panel, PixelButton, ScreenShell } from '../../ui';
import { GuideControl } from '../../ui/GuideControl';
import { PixelIcon } from '../../ui/PixelIcon';
import { rangeLabel } from '../../components/timeline/range';
import { MatchBoard } from '../Battle/BattleTurn';
import { Lyrics } from '../Sing/Lyrics';
import { PitchLane, useLaneHeight } from '../Sing/PitchLane';
import { Countdown, Judgement } from '../Sing/Judgement';
import { bestClock, sectionAt, serverNow, type ClockSample } from './timeline';
import '../Sing/Sing.css';

type Phase = 'loading' | 'ready' | 'waiting' | 'playing' | 'saving' | 'saved' | 'error';
const message = (e: unknown) => e instanceof Error ? e.message : String(e);
/** Seconds before a handoff that the NEXT-player chip slides in (matches the 4 s the lane shows ahead). */
const HANDOFF_CUE = 4;
const EMPTY: (number | null)[] = [];

/** A single audio/capture session. Sections change ownership; audio never restarts at a handoff. */
export function Duet({ setup, onLeave }: { setup: DuetSetup; onLeave: () => void }) {
  const nav = useNav();
  const [song, setSong] = useState<Song | null>(null);
  const [match, setMatch] = useState<MatchView | null>(null);
  const [phase, setPhase] = useState<Phase>('loading');
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const [ratings, setRatings] = useState(new Map<string, PhraseScore>());
  const [judge, setJudge] = useState<PhraseScore | null>(null);
  const laneHeight = useLaneHeight();
  const [guide, setGuide] = useState(false);
  const [guideVolume, setGuideVolume] = useState(0.6);
  const engine = useRef<SingEngine | null>(null);
  const clock = useRef<ClockSample | null>(null);
  const scheduled = useRef(false);
  const finished = useRef(false);
  const rated = useRef(new Map<string, PhraseScore>());
  const saving = useRef(false);
  const guideUsed = useRef(false);
  const pendingSave = useRef<{ id: string; key: string; phrases: PhraseScore[] }[]>([]);
  const mySlot = setup.online?.slot;
  const plan = match?.duet;
  const sections = plan?.sections ?? [];
  const rangeStart = plan?.range?.start ?? 0;
  const rangeEnd = plan?.range?.end ?? song?.duration ?? 0;
  const targets = useMemo(() => song ? setup.registers.map((r) => buildTargetTrack(song, r)) : [], [song, setup.registers[0], setup.registers[1]]);
  const owner = useMemo(() => new Map(sections.flatMap((s) => s.phrase_ids.map((id) => [id, s.slot] as const))), [plan]);
  const owned = useMemo(() => song?.phrases.filter((p) => owner.has(p.id) && (mySlot === undefined || owner.get(p.id) === mySlot)) ?? [], [song, owner, mySlot]);
  const sectionIndex = sectionAt(sections, now);
  const current = sections[sectionIndex];
  const next = sections[sectionIndex + 1];
  const activeSlot = current?.slot ?? 0;
  const displaySlot = mySlot ?? activeSlot;
  const displayTarget = targets[displaySlot];
  // The next section that hands the mic to the other singer, and how long until then.
  const handoff = sections.slice(sectionIndex + 1).find((s) => s.slot !== activeSlot);
  const handoffIn = handoff ? handoff.start - now : Infinity;
  const names = (slot: number) => `P${slot + 1} ${match?.players.find((p) => p.slot === slot)?.display_name ?? 'Player'}`;
  const notes = useMemo(() => song ? displayNotes(song).flatMap((note) => song.phrases.filter((p) => owner.has(p.id) && note.start < p.end && note.end > p.start)
    .map((p) => ({ start: Math.max(note.start, p.start), end: Math.min(note.end, p.end), hz: note.hz * registerRatio(setup.registers[mySlot ?? owner.get(p.id)!]), slot: owner.get(p.id) }))) : [],
  [song, owner, mySlot, setup.registers[0], setup.registers[1]]);

  useEffect(() => {
    let live = true;
    let localEngine: SingEngine | null = null;
    (async () => {
      try {
        const [s, m] = await Promise.all([getManifest(setup.clipId), getMatch(setup.matchId)]);
        if (!live) return;
        if (!m.duet) throw new Error('This match has no duet sections. Start a new match.');
        setSong(s); setMatch(m); setNow(m.duet.range?.start ?? 0);
        localEngine = await SingEngine.create(setup.clipId, s.duration, setup.calibrationOffset, m.duet.range);
        if (!live) return localEngine.close();
        const stream = await openMic();
        if (!live) { stopStream(stream); return localEngine.close(); }
        localEngine.attachMic(stream);
        engine.current = localEngine;
        setPhase('ready');
      } catch (e) { if (live) { setError(message(e)); setPhase('error'); } }
    })();
    return () => { live = false; localEngine?.close(); engine.current = null; };
  }, [setup.matchId, setup.clipId, setup.calibrationOffset]);

  useEffect(() => {
    let live = true;
    let busy = false;
    const poll = async () => {
      if (busy) return;
      busy = true;
      try { const m = await getMatch(setup.matchId); if (live) setMatch(m); }
      catch { /* Existing WebAudio playback continues through a temporary network outage. */ }
      finally { busy = false; }
    };
    const timer = setInterval(() => void poll(), 500);
    return () => { live = false; clearInterval(timer); };
  }, [setup.matchId]);

  useEffect(() => {
    engine.current?.setGuideVolume(guide ? guideVolume : 0);
  }, [guide, guideVolume, phase]);

  async function prepare() {
    const audio = engine.current;
    if (!audio || phase !== 'ready') return;
    setPhase('waiting'); setError(null);
    try {
      await audio.ctx.resume();
      const samples: ClockSample[] = [];
      for (let i = 0; i < 3; i++) {
        const sent = performance.now();
        const result = await serverTime();
        samples.push({ sent, received: performance.now(), serverTime: result.server_time });
      }
      clock.current = bestClock(samples);
      const slots = mySlot === undefined ? [0, 1] : [mySlot];
      const m = await duetReady(setup.matchId, slots.map((slot) => ({ slot, register: setup.registers[slot], calibration_offset: setup.calibrationOffset })));
      setMatch(m);
    } catch (e) { setError(message(e)); setPhase(e instanceof ApiError && e.code === 'missed_start' ? 'error' : 'ready'); }
  }

  useEffect(() => {
    const audio = engine.current;
    if (phase !== 'waiting' || !plan?.start_at || !audio || !clock.current || scheduled.current) return;
    scheduled.current = true;
    const delay = plan.start_at - serverNow(clock.current, performance.now());
    if (delay < 0.5) {
      setError('You missed the shared start. Stop this duet and restart the whole song together.');
      setPhase('error'); return;
    }
    void audio.start(audio.ctx.currentTime + delay).then(() => setPhase('playing'), (e) => { setError(message(e)); setPhase('error'); });
  }, [phase, plan?.start_at]);

  useEffect(() => {
    if (match?.state === 'retry_required' || match?.state === 'aborted') {
      engine.current?.close();
      setError('The shared duet stopped. Restart the whole song together.'); setPhase('error');
    }
  }, [match?.state]);

  const rate = useCallback((settled: (t: number) => boolean) => {
    if (!song || !engine.current) return;
    let latest: PhraseScore | null = null;
    for (const phrase of owned) {
      if (rated.current.has(phrase.id) || !settled(phraseSettlesAt(phrase))) continue;
      latest = scorePhrase(phrase, targets[mySlot ?? owner.get(phrase.id)!], engine.current.tracker.hz);
      rated.current.set(phrase.id, latest);
    }
    if (latest) { setRatings(new Map(rated.current)); setJudge(latest); }
  }, [song, owned, targets, mySlot, owner]);

  async function save() {
    if (saving.current) return;
    saving.current = true; setPhase('saving'); setError(null);
    try {
      await Promise.all(pendingSave.current.map((entry) => submitResult(entry.id, entry.phrases, entry.key, guideUsed.current)));
      setMatch(await getMatch(setup.matchId)); setPhase('saved');
    } catch (e) { setError(`Score save failed: ${message(e)}. You can retry this save without replaying the song.`); setPhase('saved'); }
    finally { saving.current = false; }
  }

  const finish = useCallback(() => {
    if (finished.current || !song || !match) return;
    finished.current = true;
    rate(() => true);
    engine.current?.close();
    const slots = mySlot === undefined ? [0, 1] : [mySlot];
    pendingSave.current = slots.map((slot) => ({ id: match.attempts.find((a) => a.slot === slot)!.id,
      key: crypto.randomUUID(), phrases: owned.filter((p) => owner.get(p.id) === slot).map((p) => rated.current.get(p.id)!) }));
    void save();
  }, [song, match, rate, owned, owner, mySlot]);

  useEffect(() => {
    if (phase !== 'playing' || !engine.current) return;
    const audio = engine.current;
    let raf = 0;
    const tick = () => {
      const t = audio.clipTime(); setNow(t);
      if (!audio.micLive || audio.ctx.state === 'suspended') {
        audio.close(); setPhase('error'); setError('Microphone or audio playback stopped. Restart the whole duet together.');
        void stopDuet(setup.matchId).catch(() => {}); return;
      }
      if (t >= rangeStart && t < rangeEnd && guide && guideVolume > 0 && audio.vocals) guideUsed.current = true;
      rate((at) => audio.tracker.analysed * SCORING_CONFIG.hopSeconds >= at || t >= at + 0.5);
      if (t >= Math.max(rangeEnd + 0.3, ...owned.map((p) => phraseSettlesAt(p) + 0.1))) { finish(); return; }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [phase, rate, finish, rangeStart, rangeEnd, owned, guide, guideVolume, setup.matchId]);

  const getTime = useCallback(() => {
    const time = engine.current?.clipTime();
    return time === undefined || !Number.isFinite(time) ? rangeStart - 3 : time;
  }, [rangeStart]);
  async function restart() {
    engine.current?.close();
    await stopDuet(setup.matchId).catch(() => {});
    if (setup.online) return; // The room shows the explicit host restart action.
    try { const m = await rematch(setup.matchId); nav.go({ name: 'duet', setup: { ...setup, matchId: m.match_id } }); }
    catch (e) { setError(message(e)); }
  }
  async function leave() { engine.current?.close(); if (match?.state !== 'finished') await stopDuet(setup.matchId).catch(() => {}); onLeave(); }

  if (match?.state === 'finished' && song) return (
    <ScreenShell title="DUET RESULTS" kao="ヾ(＾∇＾)" onBack={onLeave} backLabel="HOME">
      <MatchBoard match={match} song={song} />
      {!setup.online && <PixelButton onClick={() => void restart()}>↻ REMATCH</PixelButton>}
    </ScreenShell>
  );
  return (
    <ScreenShell title="DUET" kao="♪(^▽^)♪" onBack={() => void leave()} backLabel="QUIT">
      {song && <p className="sing-title">{song.title} <span>· {song.artist}</span></p>}
      {plan?.range && <p className="solo-hint">Practice section · {rangeLabel(plan.range)}</p>}
      {error && <Notice tone="error">{error}</Notice>}
      <div className={`duet-bar duet-bar--p${activeSlot + 1}`} title="One song. Follow the singer cue; the music keeps playing through each switch.">
        <div className="duet-bar__who">
          <p data-testid="duet-current" data-slot={activeSlot} aria-live="polite">
            {names(activeSlot)} {mySlot === undefined || mySlot === activeSlot ? '· SING' : '· LISTEN'}
          </p>
          <p data-testid="duet-next">{next ? `Next: ${names(next.slot)} at ${next.start.toFixed(1)} s` : 'Final section'}</p>
        </div>
        <div className="sing-hud">
        {[0, 1].map((slot) => {
          const phrases = owned.filter((p) => owner.get(p.id) === slot);
          const scores = phrases.flatMap((p) => ratings.has(p.id) ? [ratings.get(p.id)!] : []);
          return <span key={slot} className="sing-chip" data-testid={`duet-score-${slot}`}>{names(slot)} · {scores.length ? aggregate(scores, phraseWeights(phrases, targets[slot])).total.toFixed(1) : '—'} · {scores.length}/{sections.filter((s) => s.slot === slot).flatMap((s) => s.phrase_ids).length} phrases </span>;
        })}
        </div>
      </div>
      <div className="sing-stage">
        {song && displayTarget ? <PitchLane height={laneHeight} song={song} notes={notes} sections={sections} target={displayTarget} getTime={getTime} userHz={engine.current?.tracker.hz ?? EMPTY} ratings={ratings} /> : <div className="sing-lane sing-lane--empty" />}
        {phase === 'playing' && handoff && handoffIn > 0 && handoffIn <= HANDOFF_CUE && (
          <div className={`duet-cue duet-cue--p${handoff.slot + 1}`} data-testid="duet-handoff" aria-hidden="true">
            <PixelIcon name="speaker" size={22} />
            <span>NEXT: PLAYER {handoff.slot + 1}</span>
            <b>{Math.ceil(handoffIn)}</b>
          </div>
        )}
        {/* one polite announcement per handoff (the visible countdown is aria-hidden so it does not chatter) */}
        <span className="sr-only" aria-live="polite">
          {phase === 'playing' && handoff && handoffIn > 0 && handoffIn <= HANDOFF_CUE ? `Next: ${names(handoff.slot)} sings in a few seconds.` : ''}
        </span>
        {phase === 'loading' && <div className="sing-overlay">LOADING AUDIO AND MIC…</div>}
        {phase === 'ready' && <div className="sing-overlay"><PixelButton tone="hot" size="lg" onClick={() => void prepare()}>READY TO SING</PixelButton></div>}
        {phase === 'waiting' && <div className="sing-overlay">Waiting for both microphones and audio…</div>}
        {phase === 'playing' && now < rangeStart - 3 && <div className="sing-overlay">Starting together…</div>}
        {phase === 'playing' && now >= rangeStart - 3 && now < rangeStart && <Countdown value={String(Math.ceil(rangeStart - now))} />}
        {phase === 'playing' && judge && <Judgement key={judge.phrase_id} rating={judge.rating} score={judge.score} />}
        <div className="sing-progress"><div className="sing-progress__fill" style={{ width: `${Math.max(0, Math.min(1, (now - rangeStart) / (rangeEnd - rangeStart))) * 100}%` }} /></div>
      </div>
      {(phase === 'saving' || phase === 'saved') && <Notice>{phase === 'saving' ? 'Saving assigned phrases…' : error ? 'The song is over. Retry saving your existing result.' : 'Your score is saved. Waiting for the other result…'}</Notice>}
      {phase === 'saved' && error && <PixelButton onClick={() => void save()}>RETRY SAVE</PixelButton>}
      {phase === 'error' && <PixelButton onClick={() => void restart()}>{setup.online ? 'STOP DUET FOR RESTART' : 'RESTART TOGETHER'}</PixelButton>}
      <Panel>
        {engine.current?.vocals && <GuideControl on={guide} volume={guideVolume} onToggle={() => setGuide((v) => !v)} onVolume={setGuideVolume} />}
        {song && <Lyrics lines={song.lines.filter((line) => line.end > rangeStart && line.start < rangeEnd)} t={now} showRoman showTrans />}
      </Panel>
    </ScreenShell>
  );
}

/**
 * The singing screen: load the clip, open the mic raw, count in, play the backing on the master
 * clock, draw the pitch lane and lyrics, rate every phrase locally as soon as it ends, then submit the
 * phrase results once and hand off to the results screen.
 *
 * A missing or failing mic is an input error with RETRY, never a score. A failed save never stops the
 * song: the run continues and the results screen explains that it was not saved.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { COUNT_IN, SingEngine } from '../../audio/engine';
import { MicError, openMic, stopStream } from '../../audio/sources';
import { ApiError, beginTurn, getManifest, submitResult } from '../../lib/api';
import type { PhraseScore, Register, Song } from '../../lib/types';
import { useNav, type SingSetup } from '../../routes';
import { aggregate, buildTargetTrack, displayNotes, phraseSettlesAt, phraseTotal, phraseWeights, registerRatio, scorePhrase, SCORING_CONFIG } from '../../scoring';
import { Notice, Panel, PixelButton, ScreenShell } from '../../ui';
import { Countdown, Judgement } from './Judgement';
import { Lyrics } from './Lyrics';
import { PitchLane } from './PitchLane';
import './Sing.css';

type Phase =
  | { k: 'loading' }
  | { k: 'load-error'; message: string }
  | { k: 'mic-error'; message: string }
  | { k: 'ready' }
  | { k: 'playing' }
  | { k: 'saving' };

const REGISTER_LABEL: Record<Register, string> = { [-12]: '-1 OCTAVE', 0: 'ORIGINAL', 12: '+1 OCTAVE' };
const NO_FRAMES: (number | null)[] = [];
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function Sing({ setup }: { setup: SingSetup }) {
  const nav = useNav();
  const [song, setSong] = useState<Song | null>(null);
  const [phase, setPhase] = useState<Phase>({ k: 'loading' });
  const [attempt, setAttempt] = useState(0); // bumping it rebuilds the audio graph (RETRY)
  const [isClick, setIsClick] = useState(false);
  const [now, setNow] = useState(-COUNT_IN);
  const [ratings, setRatings] = useState<Map<string, PhraseScore>>(() => new Map());
  const [judge, setJudge] = useState<PhraseScore | null>(null);
  const [saveWarning, setSaveWarning] = useState<string | null>(null);
  const [showRoman, setShowRoman] = useState(true);
  const [showTrans, setShowTrans] = useState(true);

  const engineRef = useRef<SingEngine | null>(null);
  const ratedRef = useRef(new Map<string, PhraseScore>());
  const beginRef = useRef<Promise<void> | null>(null);
  const saveErrorRef = useRef<string | null>(setup.match ? null : 'Playing offline, so this score was not saved.');
  const finishedRef = useRef(false);

  const target = useMemo(() => (song ? buildTargetTrack(song, setup.register) : null), [song, setup.register]);
  const notes = useMemo(() => (song ? displayNotes(song).map((n) => ({ ...n, hz: n.hz * registerRatio(setup.register) })) : []), [song, setup.register]);

  // ---------- load manifest, audio and mic (again on RETRY) ----------
  useEffect(() => {
    let cancelled = false;
    let engine: SingEngine | null = null;
    ratedRef.current = new Map();
    finishedRef.current = false;
    setRatings(new Map());
    setJudge(null);
    setNow(-COUNT_IN);
    setPhase({ k: 'loading' });

    (async () => {
      try {
        const s = await getManifest(setup.clipId);
        if (cancelled) return;
        setSong(s);
        engine = await SingEngine.create(setup.clipId, s.duration, setup.calibrationOffset);
        if (cancelled) return engine.close();
        engineRef.current = engine;
        setIsClick(engine.backing.isClick);
      } catch (e) {
        if (!cancelled) setPhase({ k: 'load-error', message: errorText(e) });
        return;
      }
      try {
        const stream = await openMic();
        if (cancelled) return stopStream(stream);
        engine.attachMic(stream);
        setPhase({ k: 'ready' });
      } catch (e) {
        if (!cancelled) setPhase({ k: 'mic-error', message: e instanceof MicError ? e.message : errorText(e) });
      }
    })();

    return () => {
      cancelled = true;
      engine?.close();
      if (engineRef.current === engine) engineRef.current = null;
    };
  }, [setup.clipId, setup.calibrationOffset, attempt]);

  // ---------- rating and finishing ----------
  const rateUpTo = useCallback(
    (settled: (settlesAt: number) => boolean) => {
      const engine = engineRef.current;
      if (!song || !target || !engine) return;
      let latest: PhraseScore | null = null;
      for (const p of song.phrases) {
        if (ratedRef.current.has(p.id) || !settled(phraseSettlesAt(p))) continue;
        latest = scorePhrase(p, target, engine.tracker.hz);
        ratedRef.current.set(p.id, latest);
      }
      if (latest) {
        setRatings(new Map(ratedRef.current));
        setJudge(latest);
      }
    },
    [song, target],
  );

  const finish = useCallback(async () => {
    if (finishedRef.current || !song || !target) return;
    finishedRef.current = true;
    rateUpTo(() => true);
    engineRef.current?.close();
    engineRef.current = null;
    setPhase({ k: 'saving' });

    const phrases = song.phrases.map((p) => ratedRef.current.get(p.id) as PhraseScore);
    const local = aggregate(phrases, phraseWeights(song.phrases, target));
    let saved = null;
    if (setup.match) {
      await beginRef.current; // its failure lands in saveErrorRef
      if (!saveErrorRef.current) {
        const key = crypto.randomUUID(); // the same key on retry, so the server counts it once
        try {
          saved = await submitResult(setup.match.attemptId, phrases, key).catch((e) => {
            if (e instanceof ApiError && e.code === 'network') return submitResult(setup.match!.attemptId, phrases, key);
            throw e;
          });
        } catch (e) {
          saveErrorRef.current = `Your score was not saved: ${errorText(e)}`;
        }
      }
    }
    const result = { setup, phrases, local, saved, saveError: saved ? null : saveErrorRef.current };
    nav.go(setup.battle ? { name: 'battleturn', result } : { name: 'results', result });
  }, [song, target, setup, nav, rateUpTo]);

  // ---------- the play loop: master clock -> UI, phrase ratings, end of clip ----------
  useEffect(() => {
    if (phase.k !== 'playing' || !song) return;
    const engine = engineRef.current;
    if (!engine) return;
    const hop = SCORING_CONFIG.hopSeconds;
    let raf = 0;
    const tick = () => {
      const t = engine.clipTime();
      setNow(t);
      if (!engine.micLive) {
        engine.close();
        setPhase({ k: 'mic-error', message: 'The microphone stopped sending audio (unplugged or blocked).' });
        return;
      }
      // A phrase is final once its user frames are analysed, or a beat later if capture has stalled.
      const analysed = engine.tracker.analysed * hop;
      rateUpTo((settlesAt) => analysed >= settlesAt || t >= settlesAt + 0.5);
      if (t >= song.duration + 0.3) {
        void finish();
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [phase.k, song, rateUpTo, finish]);

  const start = async () => {
    const engine = engineRef.current;
    if (!engine || phase.k !== 'ready') return;
    if (setup.match && !beginRef.current) {
      beginRef.current = beginTurn(setup.match.attemptId, setup.register, setup.calibrationOffset).then(
        () => undefined,
        (e) => {
          saveErrorRef.current = `Your score won't be saved: ${errorText(e)}`;
          setSaveWarning("Couldn't reach the server, so this score won't be saved. Keep singing!");
        },
      );
    }
    await engine.start();
    setPhase({ k: 'playing' });
  };

  const quit = () => {
    finishedRef.current = true;
    engineRef.current?.close();
    engineRef.current = null;
    nav.go({ name: setup.battle ? 'battle' : 'solo' });
  };

  const getTime = useCallback(() => {
    const t = engineRef.current?.clipTime();
    return t === undefined || !Number.isFinite(t) ? -COUNT_IN : t;
  }, []);

  // ---------- render ----------
  const rated = [...ratings.values()];
  const running = song && target && rated.length ? aggregate(rated, phraseWeights(song.phrases, target)).total : 0;
  const playing = phase.k === 'playing';
  const level = engineRef.current?.tracker.level ?? 0;

  return (
    <ScreenShell
      title="SING!"
      kao="♪(^▽^)♪"
      onBack={quit}
      backLabel="QUIT"
      right={
        <div className="sing-hud">
          <span className="sing-chip">{REGISTER_LABEL[setup.register]}</span>
          <span className="sing-chip sing-chip--score" aria-label="Running score">
            {running.toFixed(1)}
          </span>
        </div>
      }
    >
      {song && <p className="sing-title">{setup.battle && <>P{setup.battle.turn + 1} {setup.playerName.toUpperCase()} · </>}{song.title} <span>· {song.artist}</span></p>}

      {isClick && <Notice tone="warn">No instrumental installed, so you are singing to a click track.</Notice>}
      {saveWarning && <Notice tone="warn">{saveWarning}</Notice>}

      {phase.k === 'load-error' && (
        <Notice tone="error" action={<PixelButton tone="hot" onClick={() => setAttempt((a) => a + 1)}>RETRY</PixelButton>}>
          The clip could not load: {phase.message}
        </Notice>
      )}
      {phase.k === 'mic-error' && (
        <Notice tone="error" action={<PixelButton tone="hot" onClick={() => setAttempt((a) => a + 1)}>RETRY</PixelButton>}>
          <strong>Mic problem:</strong> {phase.message} Check the browser's mic permission and your headset, then retry. Nothing was scored.
        </Notice>
      )}

      <div className="sing-stage">
        {song && target ? (
          <PitchLane song={song} notes={notes} target={target} getTime={getTime} userHz={engineRef.current?.tracker.hz ?? NO_FRAMES} ratings={ratings} />
        ) : (
          <div className="sing-lane sing-lane--empty" />
        )}

        {phase.k === 'loading' && <div className="sing-overlay"><p className="sing-overlay__text">LOADING...</p></div>}
        {phase.k === 'ready' && (
          <div className="sing-overlay">
            <p className="sing-overlay__text">Wired headphones on? Sing along with the notes!</p>
            <PixelButton tone="hot" size="lg" onClick={start} autoFocus>
              ▶ START
            </PixelButton>
          </div>
        )}
        {phase.k === 'saving' && <div className="sing-overlay"><p className="sing-overlay__text">TALLYING UP...</p></div>}
        {playing && now < 0 && <Countdown value={String(Math.ceil(-now))} />}
        {playing && now >= 0 && now < 0.8 && <Countdown value="SING!" />}
        {judge && (playing || phase.k === 'saving') && <Judgement key={judge.phrase_id} rating={judge.rating} score={phraseTotal(judge)} />}

        <div className="sing-progress" aria-hidden="true">
          <div className="sing-progress__fill" style={{ width: `${song ? Math.max(0, Math.min(1, now / song.duration)) * 100 : 0}%` }} />
        </div>
      </div>

      <Panel className="sing-lyrics-panel">
        <div className="sing-lyrics-head">
          <div className="ui-seg" role="group" aria-label="Lyric helpers">
            <PixelButton size="sm" tone="paper" aria-pressed={showRoman} onClick={() => setShowRoman((v) => !v)}>
              ROMANIZATION
            </PixelButton>
            <PixelButton size="sm" tone="paper" aria-pressed={showTrans} onClick={() => setShowTrans((v) => !v)}>
              ENGLISH
            </PixelButton>
          </div>
          <div className="sing-meter" title="Mic level" aria-label="Mic level">
            <span className="sing-meter__label">MIC</span>
            <span className="sing-meter__bar">
              <span style={{ width: `${Math.min(1, level / 0.2) * 100}%` }} />
            </span>
          </div>
        </div>
        {song && <Lyrics lines={song.lines} t={now} showRoman={showRoman} showTrans={showTrans} />}
      </Panel>
    </ScreenShell>
  );
}

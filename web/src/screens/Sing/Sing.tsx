/**
 * The singing screen: load the clip, open the mic raw, count in, play the backing on the master
 * clock, draw the pitch lane and lyrics, rate every phrase locally as soon as it ends, then submit the
 * phrase results once and hand off to the results screen.
 *
 * A missing or failing mic is an input error with RETRY, never a score. A failed save never stops the
 * song: the run continues and the results screen explains that it was not saved.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { includedPhrases, rangeLabel } from '../../components/timeline/range';
import { COUNT_IN, SingEngine } from '../../audio/engine';
import { MicError, openMic, stopStream } from '../../audio/sources';
import { ApiError, beginTurn, getManifest, submitResult } from '../../lib/api';
import { sendLive } from '../../lib/rooms';
import type { PhraseScore, Register, Song } from '../../lib/types';
import { useNav, type SingSetup } from '../../routes';
import { aggregate, buildTargetTrack, displayNotes, phraseSettlesAt, phraseTotal, phraseWeights, registerRatio, scorePhrase, SCORING_CONFIG } from '../../scoring';
import { Notice, Panel, PixelButton, ScreenShell } from '../../ui';
import { GuideControl } from '../../ui/GuideControl';
import { ScoreBars } from './ScoreBars';
import { Countdown, Judgement } from './Judgement';
import { LiveLyricChecker } from './liveLyrics';
import { uploadTurnLyrics } from '../Results/uploadTurnLyrics';
import { Lyrics, type LineVerdicts } from './Lyrics';
import type { LyricStatus } from '../../lib/types';
import { PitchLane, useLaneHeight } from './PitchLane';
import { SongThumb } from '../../components/songs/SongJacket';
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

const GUIDE_KEY = 'just-sing.guide';

/** Guide vocals default to off at 60%; the last choice is remembered. */
function loadGuide(): { on: boolean; vol: number } {
  try {
    const g = JSON.parse(localStorage.getItem(GUIDE_KEY) ?? 'null');
    if (g && typeof g.vol === 'number') return { on: g.on === true, vol: Math.max(0, Math.min(1, g.vol)) };
  } catch {
    // no storage or bad JSON
  }
  return { on: false, vol: 0.6 };
}

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
  const [showTrans, setShowTrans] = useState(false);
  const laneHeight = useLaneHeight();
  const [guide, setGuide] = useState(loadGuide);
  const [hasGuide, setHasGuide] = useState(false);
  const [lyricTally, setLyricTally] = useState<{ matched: number; graded: number } | null>(null);
  const [lyricResults, setLyricResults] = useState<{ sent: Set<number>; done: Map<number, LyricStatus> }>(() => ({ sent: new Set(), done: new Map() }));
  const lyricRef = useRef<LiveLyricChecker | null>(null);

  const engineRef = useRef<SingEngine | null>(null);
  const ratedRef = useRef(new Map<string, PhraseScore>());
  const beginRef = useRef<Promise<void> | null>(null);
  const saveErrorRef = useRef<string | null>(setup.match ? null : 'Playing offline, so this score was not saved.');
  const finishedRef = useRef(false);
  const lastLive = useRef(0); // clip time of the last live progress message to the room
  const startedRef = useRef(false); // set synchronously so a double click cannot start twice
  const guideRef = useRef(guide);
  guideRef.current = guide;
  const guideUsedRef = useRef(false); // guide vocals were audible at some point after the count-in

  const target = useMemo(() => (song ? buildTargetTrack(song, setup.register) : null), [song, setup.register]);
  const notes = useMemo(() => (song ? displayNotes(song).map((n) => ({ ...n, hz: n.hz * registerRatio(setup.register) })) : []), [song, setup.register]);

  const selected = useMemo(() => song ? includedPhrases(song.phrases, setup.range) : [], [song, setup.range]);
  const rangeStart = setup.range?.start ?? 0;
  const rangeEnd = setup.range?.end ?? song?.duration ?? 0;

  // ---------- load manifest, audio and mic (again on RETRY) ----------
  useEffect(() => {
    let cancelled = false;
    let engine: SingEngine | null = null;
    ratedRef.current = new Map();
    finishedRef.current = false;
    startedRef.current = false;
    guideUsedRef.current = false;
    lastLive.current = 0;
    setRatings(new Map());
    setJudge(null);
    setNow(rangeStart - COUNT_IN);
    setPhase({ k: 'loading' });

    (async () => {
      try {
        const s = await getManifest(setup.clipId);
        if (cancelled) return;
        setSong(s);
        engine = await SingEngine.create(setup.clipId, s.duration, setup.calibrationOffset, setup.range ?? null);
        if (cancelled) return engine.close();
        engineRef.current = engine;
        setIsClick(engine.backing.isClick);
        setHasGuide(engine.vocals !== null);
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
  }, [setup.clipId, setup.calibrationOffset, setup.range, rangeStart, attempt]);

  // ---------- rating and finishing ----------
  const rateUpTo = useCallback(
    (settled: (settlesAt: number) => boolean) => {
      const engine = engineRef.current;
      if (!song || !target || !engine) return;
      let latest: PhraseScore | null = null;
      for (const p of selected) {
        if (ratedRef.current.has(p.id) || !settled(phraseSettlesAt(p))) continue;
        latest = scorePhrase(p, target, engine.tracker.hz);
        ratedRef.current.set(p.id, latest);
        if (setup.online) sendLive('phrase_rating', { phrase_id: p.id, rating: latest.rating, score: phraseTotal(latest) }); // provisional badge for the waiting player
      }
      if (latest) {
        setRatings(new Map(ratedRef.current));
        setJudge(latest);
      }
    },
    [song, target, selected, setup.online],
  );

  const finish = useCallback(async () => {
    if (finishedRef.current || !song || !target) return;
    finishedRef.current = true;
    rateUpTo(() => true);
    // Audio is temporary; multiplayer uploads are linked to the singer's saved attempt.
    const take = engineRef.current?.recorder.toWav() ?? null;
    const multiplayerLyrics = !!take && !!(setup.battle || setup.online);
    const lyricsLive = lyricRef.current?.finish() ?? null; // the lines checked during the song
    lyricRef.current = null;
    engineRef.current?.close();
    engineRef.current = null;
    setPhase({ k: 'saving' });

    const phrases = selected.map((p) => ratedRef.current.get(p.id) as PhraseScore);
    const local = aggregate(phrases, phraseWeights(selected, target));
    let saved = null;
    if (setup.match) {
      await beginRef.current; // its failure lands in saveErrorRef
      if (!saveErrorRef.current) {
        const key = crypto.randomUUID(); // the same key on retry, so the server counts it once
        try {
          saved = await submitResult(setup.match.attemptId, phrases, key, guideUsedRef.current, multiplayerLyrics).catch((e) => {
            if (e instanceof ApiError && e.code === 'network') return submitResult(setup.match!.attemptId, phrases, key, guideUsedRef.current, multiplayerLyrics);
            throw e;
          });
          if (multiplayerLyrics && take) void uploadTurnLyrics(setup.match.attemptId, take);
        } catch (e) {
          saveErrorRef.current = `Your score was not saved: ${errorText(e)}`;
        }
      }
    }
    const result = { setup, phrases, local, saved, saveError: saved ? null : saveErrorRef.current, take, lyricsLive };
    if (setup.online) {
      const room = { id: setup.online.roomId, slot: setup.online.slot, prefs: { register: setup.register, offset: setup.calibrationOffset } };
      return nav.go({ name: 'online', room, notice: saved ? undefined : (saveErrorRef.current ?? 'Your score was not saved.') });
    }
    nav.go(setup.battle ? { name: 'battleturn', result } : { name: 'results', result });
  }, [song, target, selected, setup, nav, rateUpTo]);

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
      if (t >= rangeStart && t < rangeEnd && guideRef.current.on && guideRef.current.vol > 0 && engine.vocals) guideUsedRef.current = true;
      if (setup.online && t - lastLive.current >= 0.5) {
        lastLive.current = t;
        const rated = [...ratedRef.current.values()];
        sendLive('progress', { t, running: rated.length ? aggregate(rated, phraseWeights(selected, target!)).total : 0 });
      }
      rateUpTo((settlesAt) => analysed >= settlesAt || t >= settlesAt + 0.5);
      lyricRef.current?.poll(t);
      if (t >= Math.max(rangeEnd + 0.3, ...selected.map((p) => phraseSettlesAt(p) + 0.1))) {
        void finish();
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [phase.k, song, target, selected, rangeStart, rangeEnd, setup.online, rateUpTo, finish]);

  const start = async () => {
    const engine = engineRef.current;
    if (!engine || phase.k !== 'ready' || startedRef.current) return;
    startedRef.current = true;
    if (setup.match && !beginRef.current) {
      beginRef.current = beginTurn(setup.match.attemptId, setup.register, setup.calibrationOffset, setup.range).then(
        () => undefined,
        (e) => {
          saveErrorRef.current = `Your score won't be saved: ${errorText(e)}`;
          setSaveWarning("Couldn't reach the server, so this score won't be saved. Keep singing!");
        },
      );
    }
    if (song && !setup.battle && !setup.online) {
      // Check each sung line on the server while the song plays (solo only), so results are ready at the end.
      const lines = [...new Set(selected.map((p) => p.line_index))].map((index) => ({ index, line: song.lines[index] })).filter((l) => l.line);
      const checker = new LiveLyricChecker(setup.clipId, lines, engine.recorder, () => {
        const statuses = [...checker.results.values()].filter((s) => s === 'match' || s === 'unclear');
        setLyricTally({ matched: statuses.filter((s) => s === 'match').length, graded: statuses.length });
        setLyricResults({ sent: new Set(checker.sent), done: new Map(checker.results) });
      }, (index) => setLyricResults((r) => ({ sent: new Set(r.sent).add(index), done: r.done })));
      lyricRef.current = checker;
      setLyricTally(null);
      setLyricResults({ sent: new Set(), done: new Map() });
    }
    await engine.start();
    setPhase({ k: 'playing' });
  };

  const quit = () => {
    finishedRef.current = true;
    engineRef.current?.close();
    engineRef.current = null;
    if (setup.online)
      nav.go({
        name: 'online',
        room: { id: setup.online.roomId, slot: setup.online.slot, prefs: { register: setup.register, offset: setup.calibrationOffset } },
        notice: 'You left the turn. If it does not reopen, the turn can be retried from the room once the time runs out.',
      });
    else nav.go({ name: setup.battle ? 'battle' : 'solo' });
  };

  const getTime = useCallback(() => {
    const t = engineRef.current?.clipTime();
    return t === undefined || !Number.isFinite(t) ? rangeStart - COUNT_IN : t;
  }, [rangeStart]);

  // ---------- render ----------
  // Live lyric check per manifest line, keyed by Line for the lyrics panel ("checking…" once sent).
  const verdicts = useMemo<LineVerdicts>(() => {
    const out: LineVerdicts = new Map();
    if (!song) return out;
    for (const i of lyricResults.sent) out.set(song.lines[i], lyricResults.done.get(i) ?? 'checking');
    for (const [i, s] of lyricResults.done) out.set(song.lines[i], s);
    return out;
  }, [song, lyricResults]);

  const rated = [...ratings.values()];
  const running = song && target && rated.length ? aggregate(rated, phraseWeights(selected, target)).total : 0;
  const playing = phase.k === 'playing';
  const level = engineRef.current?.tracker.level ?? 0;

  // The guide vocals follow the toggle and slider live; the choice is remembered per browser.
  useEffect(() => {
    engineRef.current?.setGuideVolume(guide.on ? guide.vol : 0);
    try {
      localStorage.setItem(GUIDE_KEY, JSON.stringify(guide));
    } catch {
      // storage blocked: the setting just won't be remembered
    }
  }, [guide, hasGuide]);

  return (
    <ScreenShell
      title="SING!"
      kao="♪(^▽^)♪"
      onBack={quit}
      backLabel="QUIT"
      lead={<SongThumb clipId={setup.clipId} />}
      subtitle={song && <>{setup.battle && <>P{setup.battle.turn + 1} {setup.playerName.toUpperCase()} · </>}{song.title} <span>· {song.artist}</span></>}
      right={
        <div className="sing-hud">
          <span className="sing-chip">{REGISTER_LABEL[setup.register]}</span>
          {lyricTally && lyricTally.graded > 0 && (
            <span className="sing-chip sing-chip--lyrics" title="Lines whose words sounded like the original singer (checked as you sing)">
              LYRICS {lyricTally.matched}/{lyricTally.graded}
            </span>
          )}
          <ScoreBars bars={[{ name: setup.playerName, score: running, slot: setup.battle?.turn === 1 ? 1 : 0 }]} />
        </div>
      }
    >
      {setup.range && <p className="solo-hint">Practice section · {rangeLabel(setup.range)}</p>}
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
          <PitchLane height={laneHeight} song={song} notes={notes} target={target} getTime={getTime} userHz={engineRef.current?.tracker.hz ?? NO_FRAMES} ratings={ratings} />
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
        {playing && now < rangeStart && <Countdown value={String(Math.ceil(rangeStart - now))} />}
        {playing && now >= rangeStart && now < rangeStart + 0.8 && <Countdown value="SING!" />}
        {judge && (playing || phase.k === 'saving') && <Judgement key={judge.phrase_id} rating={judge.rating} />}

        <div className="sing-progress" aria-hidden="true">
          <div className="sing-progress__fill" style={{ width: `${song ? Math.max(0, Math.min(1, (now - rangeStart) / (rangeEnd - rangeStart))) * 100 : 0}%` }} />
        </div>
      </div>

      <Panel className="sing-lyrics-panel">
        <div className="sing-lyrics-head">
          <div className="ui-seg" role="group" aria-label="Lyric helpers">
            <PixelButton size="sm" tone="paper" className="sing-toggle" aria-pressed={showRoman} onClick={() => setShowRoman((v) => !v)}>
              ROMANIZATION
            </PixelButton>
            <PixelButton size="sm" tone="paper" className="sing-toggle" aria-pressed={showTrans} onClick={() => setShowTrans((v) => !v)}>
              ENGLISH
            </PixelButton>
          </div>
          {hasGuide && (
            <GuideControl on={guide.on} volume={guide.vol} onToggle={() => setGuide((g) => ({ ...g, on: !g.on }))} onVolume={(vol) => setGuide({ on: true, vol })} />
          )}
          <div className="sing-meter" title="Mic level" aria-label="Mic level">
            <span className="sing-meter__label">MIC</span>
            <span className="sing-meter__bar">
              <span style={{ width: `${Math.min(1, level / 0.2) * 100}%` }} />
            </span>
          </div>
        </div>
        {song && <Lyrics lines={song.lines.filter((line) => line.end > rangeStart && line.start < rangeEnd)} t={now} showRoman={showRoman} showTrans={showTrans}
          singerAt={setup.battle?.turn === 1 ? () => 1 : undefined} verdicts={verdicts} />}
      </Panel>
    </ScreenShell>
  );
}

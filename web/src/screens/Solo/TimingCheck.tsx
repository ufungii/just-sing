import { useCallback, useEffect, useRef, useState } from 'react';
import { Notice, PixelButton } from '../../ui';

/** One value per device, never per take (CLAUDE.md, scoring: timing). Stored in seconds. */
export const CALIBRATION_KEY = 'just-sing.calibrationOffset';

const CLICKS = 8;
const CLICK_GAP = 0.6; // seconds between clicks (100 BPM)
const LEAD_IN = 1.0; // seconds of silence before the first click
/** A tap further than this from every click is a stray tap and is ignored. */
const MAX_TAP_DISTANCE = 0.3;
const MIN_GOOD_TAPS = 5;

export function loadCalibration(): number | null {
  try {
    const raw = localStorage.getItem(CALIBRATION_KEY);
    const v = raw === null ? NaN : Number(raw);
    return Number.isFinite(v) ? v : null;
  } catch {
    return null;
  }
}

function saveCalibration(seconds: number) {
  try {
    localStorage.setItem(CALIBRATION_KEY, String(seconds));
  } catch {
    // storage blocked: the offset still applies to this run
  }
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** Offset = median of (tap time − nearest click time). Returns null if too few taps landed near a click. */
export function measureOffset(clicks: number[], taps: number[]): number | null {
  const diffs: number[] = [];
  for (const tap of taps) {
    let best = Infinity;
    for (const c of clicks) if (Math.abs(tap - c) < Math.abs(best)) best = tap - c;
    if (Math.abs(best) <= MAX_TAP_DISTANCE) diffs.push(best);
  }
  return diffs.length >= MIN_GOOD_TAPS ? median(diffs) : null;
}

/** Schedules a short beep at an exact AudioContext time. */
function scheduleClick(ctx: AudioContext, at: number) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = 1000;
  gain.gain.setValueAtTime(0, at);
  gain.gain.linearRampToValueAtTime(0.5, at + 0.003);
  gain.gain.exponentialRampToValueAtTime(0.001, at + 0.06);
  osc.connect(gain).connect(ctx.destination);
  osc.start(at);
  osc.stop(at + 0.08);
}

type Phase = 'idle' | 'running' | 'failed';

/**
 * Optional tap-along latency check. Clicks and taps are both read from one AudioContext clock,
 * so the result covers headphone output delay plus the player's own reaction, as one offset.
 */
export function TimingCheck({ offset, onChange }: { offset: number | null; onChange: (seconds: number | null) => void }) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [beat, setBeat] = useState(-1); // index of the click that just sounded
  const [tapCount, setTapCount] = useState(0);
  const [flash, setFlash] = useState(false);
  const run = useRef<{ ctx: AudioContext; clicks: number[]; taps: number[]; frame: number } | null>(null);

  const stop = useCallback(() => {
    const r = run.current;
    if (!r) return;
    cancelAnimationFrame(r.frame);
    void r.ctx.close();
    run.current = null;
  }, []);
  useEffect(() => stop, [stop]);

  const finish = useCallback(() => {
    const r = run.current;
    if (!r) return;
    const measured = measureOffset(r.clicks, r.taps);
    stop();
    setBeat(-1);
    if (measured === null) {
      setPhase('failed');
    } else {
      saveCalibration(measured);
      onChange(measured);
      setPhase('idle');
    }
  }, [onChange, stop]);

  const tap = useCallback(() => {
    const r = run.current;
    if (!r) return;
    r.taps.push(r.ctx.currentTime);
    setTapCount(r.taps.length);
    setFlash(true);
    window.setTimeout(() => setFlash(false), 90);
  }, []);

  async function start() {
    stop();
    const ctx = new AudioContext();
    await ctx.resume();
    const t0 = ctx.currentTime + LEAD_IN;
    const clicks = Array.from({ length: CLICKS }, (_, i) => t0 + i * CLICK_GAP);
    clicks.forEach((t) => scheduleClick(ctx, t));
    const end = clicks[CLICKS - 1] + 0.8;
    const r = { ctx, clicks, taps: [] as number[], frame: 0 };
    run.current = r;
    setTapCount(0);
    setBeat(-1);
    setPhase('running');
    const tick = () => {
      if (run.current !== r) return;
      const now = ctx.currentTime;
      if (now >= end) return finish();
      setBeat(clicks.filter((c) => c <= now).length - 1);
      r.frame = requestAnimationFrame(tick);
    };
    r.frame = requestAnimationFrame(tick);
  }

  // Space taps while the check runs (ignore key repeat so a held key is one tap).
  useEffect(() => {
    if (phase !== 'running') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return;
      e.preventDefault();
      if (!e.repeat) tap();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, tap]);

  const running = phase === 'running';

  return (
    <div className="solo-timing">
      <p className="solo-hint">
        Headphones add delay: tap along to {CLICKS} clicks so we can correct for it.
      </p>

      <div className="solo-timing__row">
        <button
          type="button"
          className={`solo-tap${flash ? ' is-hit' : ''}`}
          disabled={!running}
          // pointerdown, not click: fires on press, so the measured time is the tap itself
          onPointerDown={(e) => {
            e.preventDefault();
            tap();
          }}
          aria-label="Tap on each click (or press Space)"
        >
          TAP
          <span className="solo-tap__sub">or SPACE</span>
        </button>

        <div className="solo-timing__side">
          <div className="solo-beats" aria-hidden="true">
            {Array.from({ length: CLICKS }, (_, i) => (
              <span key={i} className={`solo-beat${running && i <= beat ? ' is-on' : ''}${running && i === beat ? ' is-now' : ''}`} />
            ))}
          </div>

          {running ? (
            <p className="solo-timing__readout" aria-live="polite">
              {beat < 0 ? 'Get ready…' : `Tap! ${tapCount} tap${tapCount === 1 ? '' : 's'}`}
            </p>
          ) : (
            <p className="solo-timing__readout" aria-live="polite">
              {offset === null ? 'Not set · timing uses no correction' : `Your offset: ${offset >= 0 ? '+' : ''}${Math.round(offset * 1000)} ms`}
            </p>
          )}

          <div className="solo-timing__buttons">
            <PixelButton tone="lav" size="sm" onClick={start} disabled={running}>
              {offset === null && phase !== 'failed' ? '▶ START CHECK' : 'REDO'}
            </PixelButton>
            <PixelButton
              tone="paper"
              size="sm"
              disabled={running}
              onClick={() => {
                setPhase('idle');
                onChange(null);
              }}
            >
              SKIP
            </PixelButton>
          </div>
        </div>
      </div>

      {phase === 'failed' && (
        <Notice tone="warn">Not enough taps landed near the clicks. Try again, or skip it for now.</Notice>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import { Notice, PixelButton } from '../../ui';

/** Raw capture: the browser's voice processing would distort pitch and level (CLAUDE.md, live singing). */
const CONSTRAINTS: MediaStreamConstraints = {
  audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
};

/** RMS above this counts as "heard you" (a quiet hum is ~0.02-0.05; room hiss is well under 0.01). */
const HEARD_RMS = 0.02;
/** How long the level must sit above HEARD_RMS (in total) before the check passes. */
const HEARD_SECONDS = 0.4;
/** Give up listening after this long so the mic is never left open. */
const LISTEN_TIMEOUT_MS = 12_000;
const METER_CELLS = 16;

export type MicStatus =
  | { kind: 'idle' }
  | { kind: 'asking' }
  | { kind: 'listening' }
  | { kind: 'passed'; applied: string }
  | { kind: 'silent' }
  | { kind: 'denied' }
  | { kind: 'no-device' }
  | { kind: 'busy' }
  | { kind: 'unsupported' };

/** Describes the processing the browser actually applied, since constraints are only requests. */
function describeApplied(track: MediaStreamTrack): string {
  const s = track.getSettings();
  const on = (v: unknown) => (v === undefined ? '?' : v === false || v === 'off' ? 'off' : 'ON');
  return `echo cancel ${on(s.echoCancellation)} · noise suppress ${on(s.noiseSuppression)} · auto gain ${on(s.autoGainControl)}`;
}

/**
 * Opens the mic with raw-capture constraints, shows a live level, and passes once it hears a
 * voice. Successful capture can be handed to an online room; otherwise all resources are released.
 */
export function MicCheck({ onPassedChange, onStreamReady }: {
  onPassedChange: (passed: boolean) => void;
  /** Transfer successful capture/context ownership to the online room instead of releasing it. */
  onStreamReady?: (stream: MediaStream, ctx: AudioContext) => void;
}) {
  const [status, setStatus] = useState<MicStatus>({ kind: 'idle' });
  const [level, setLevel] = useState(0);
  const stopRef = useRef<() => void>(() => {});

  // Release everything if the player leaves mid-check.
  useEffect(() => () => stopRef.current(), []);

  useEffect(() => onPassedChange(status.kind === 'passed'), [status.kind, onPassedChange]);

  async function start() {
    stopRef.current();
    setLevel(0);
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus({ kind: 'unsupported' });
      return;
    }
    setStatus({ kind: 'asking' });
    let cancelled = false;
    stopRef.current = () => { cancelled = true; };
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
    } catch (e) {
      if (cancelled) return;
      const name = e instanceof DOMException ? e.name : '';
      if (name === 'NotAllowedError' || name === 'SecurityError') setStatus({ kind: 'denied' });
      else if (name === 'NotFoundError' || name === 'OverconstrainedError') setStatus({ kind: 'no-device' });
      else if (name === 'NotReadableError' || name === 'AbortError') setStatus({ kind: 'busy' });
      else setStatus({ kind: 'unsupported' });
      return;
    }

    if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
    const track = stream.getAudioTracks()[0];
    const ctx = new AudioContext({ latencyHint: 'interactive' });
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    const source = ctx.createMediaStreamSource(stream);
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);

    let frame = 0;
    let stopped = false;
    let heard = 0;
    let last = performance.now();
    let transferred = false;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      cancelAnimationFrame(frame);
      clearTimeout(timeout);
      source.disconnect(); analyser.disconnect();
      if (!transferred) {
        stream.getTracks().forEach((t) => t.stop());
        void ctx.close();
      }
      setLevel(0);
    };
    stopRef.current = stop;
    const timeout = window.setTimeout(() => {
      stop();
      setStatus({ kind: 'silent' });
    }, LISTEN_TIMEOUT_MS);

    setStatus({ kind: 'listening' });
    const tick = (now: number) => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += v * v;
      const rms = Math.sqrt(sum / buf.length);
      if (track.readyState !== 'live') { stop(); setStatus({ kind: 'no-device' }); return; }
      // Log-ish meter so a normal voice fills most of the bar.
      setLevel(Math.min(1, Math.max(0, (20 * Math.log10(rms + 1e-9) + 54) / 48)));
      if (rms > HEARD_RMS) heard += (now - last) / 1000;
      last = now;
      if (heard >= HEARD_SECONDS) {
        const applied = describeApplied(track);
        if (onStreamReady) { transferred = true; onStreamReady(stream, ctx); }
        stop();
        setStatus({ kind: 'passed', applied });
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    void ctx.resume();
    frame = requestAnimationFrame(tick);
  }

  const busy = status.kind === 'asking' || status.kind === 'listening';
  const lit = Math.round(level * METER_CELLS);

  return (
    <div className="solo-mic">
      <div className="solo-mic__row">
        <PixelButton tone={status.kind === 'passed' ? 'paper' : 'sky'} onClick={start} disabled={busy}>
          {status.kind === 'idle' ? 'TEST MIC' : busy ? 'LISTENING…' : 'TEST AGAIN'}
        </PixelButton>
        <div
          className="solo-meter"
          role="meter"
          aria-label="Mic level"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(level * 100)}
        >
          {Array.from({ length: METER_CELLS }, (_, i) => (
            <span
              key={i}
              className={`solo-meter__cell${i < lit ? ' is-lit' : ''}${i >= METER_CELLS * 0.75 ? ' is-hot' : i >= METER_CELLS * 0.5 ? ' is-warm' : ''}`}
            />
          ))}
        </div>
      </div>
      <MicMessage status={status} />
    </div>
  );
}

function MicMessage({ status }: { status: MicStatus }) {
  switch (status.kind) {
    case 'idle':
      return <p className="solo-hint">Plug in wired headphones, press TEST MIC, then hum or sing a note.</p>;
    case 'asking':
      return <p className="solo-hint">Allow the microphone when your browser asks.</p>;
    case 'listening':
      return <p className="solo-hint">Now hum or sing “laaa” for a moment ♪</p>;
    case 'passed':
      return (
        <Notice tone="ok">
          <strong>Mic works!</strong> <span className="solo-small">({status.applied})</span>
        </Notice>
      );
    case 'silent':
      return <Notice tone="warn">Didn’t hear anything. Check the mic is plugged in and not muted, then test again.</Notice>;
    case 'denied':
      return (
        <Notice tone="error">
          Mic access is blocked. Allow the microphone for this site (the icon by the address bar), then test again.
        </Notice>
      );
    case 'no-device':
      return <Notice tone="error">No microphone found. Plug one in, then test again.</Notice>;
    case 'busy':
      return <Notice tone="error">The mic is in use by another app. Close it, then test again.</Notice>;
    case 'unsupported':
      return (
        <Notice tone="error">
          This browser can’t record here. Use a recent Chrome or Edge, on https:// or localhost.
        </Notice>
      );
  }
}

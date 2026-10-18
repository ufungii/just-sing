import { useEffect, useRef, useState } from 'react';
import { createMicGain } from '../../audio/micGain';
import { MicInputControl } from '../../ui/MicInputControl';
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
  const [clipping, setClipping] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [recordingPreview, setRecordingPreview] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(3);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  const stopRef = useRef<() => void>(() => {});

  // Release everything if the player leaves mid-check.
  useEffect(() => () => stopRef.current(), []);

  useEffect(() => onPassedChange(status.kind === 'passed'), [status.kind, onPassedChange]);

  async function start(recordPreview = false) {
    stopRef.current();
    setLevel(0);
    setClipping(false); setPreviewError(null); setPreviewUrl(null); setSecondsLeft(3);
    if (recordPreview && typeof MediaRecorder === 'undefined') {
      setPreviewError('Recording playback is unavailable in this browser. You can still use TEST MIC.');
      return;
    }
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
    const inputGain = createMicGain(ctx);
    source.connect(inputGain.node).connect(analyser);
    let recorder: MediaRecorder | null = null;
    let recordingStream: MediaStream | null = null;
    if (recordPreview) {
      try {
        const destination = ctx.createMediaStreamDestination();
        inputGain.node.connect(destination);
        recordingStream = destination.stream;
        recorder = new MediaRecorder(recordingStream);
        const chunks: Blob[] = [];
        recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
        recorder.onstop = () => {
          if (cancelled) return;
          if (chunks.length) setPreviewUrl(URL.createObjectURL(new Blob(chunks, { type: recorder!.mimeType })));
          else setPreviewError('The recording was empty. Record another test clip.');
        };
        recorder.start();
        setRecordingPreview(true);
      } catch {
        inputGain.close(); source.disconnect(); analyser.disconnect();
        recordingStream?.getTracks().forEach((t) => t.stop());
        stream.getTracks().forEach((t) => t.stop()); void ctx.close();
        setStatus({ kind: 'idle' }); setPreviewError('Could not record a test clip. Try TEST MIC instead.');
        return;
      }
    }
    const buf = new Float32Array(analyser.fftSize);

    let frame = 0;
    let stopped = false;
    let heard = 0;
    const started = performance.now();
    let last = started;
    let transferred = false;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      cancelAnimationFrame(frame);
      clearTimeout(timeout);
      if (recorder?.state === 'recording') recorder.stop();
      recordingStream?.getTracks().forEach((t) => t.stop());
      source.disconnect(); analyser.disconnect(); inputGain.close();
      if (!transferred) {
        stream.getTracks().forEach((t) => t.stop());
        void ctx.close();
      }
      setLevel(0);
      setRecordingPreview(false);
    };
    stopRef.current = () => { cancelled = true; stop(); };
    const timeout = window.setTimeout(() => {
      stop();
      setStatus({ kind: 'silent' });
    }, LISTEN_TIMEOUT_MS);

    if (recorder) recorder.onerror = () => {
      cancelled = true;
      stop();
      setPreviewUrl(null);
      setPreviewError('Could not record a test clip. Try recording again or use TEST MIC.');
      setStatus({ kind: 'idle' });
    };
    setStatus({ kind: 'listening' });
    const tick = (now: number) => {
      if (recordPreview) setSecondsLeft(Math.max(0, Math.ceil(3 - (now - started) / 1000)));
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      let peak = 0;
      for (const v of buf) { sum += v * v; peak = Math.max(peak, Math.abs(v)); }
      setClipping(peak >= 0.98);
      const rms = Math.sqrt(sum / buf.length);
      if (track.readyState !== 'live') { stop(); setStatus({ kind: 'no-device' }); return; }
      // Log-ish meter so a normal voice fills most of the bar.
      setLevel(Math.min(1, Math.max(0, (20 * Math.log10(rms + 1e-9) + 54) / 48)));
      if (rms > HEARD_RMS) heard += (now - last) / 1000;
      last = now;
      if ((!recordPreview && heard >= HEARD_SECONDS) || (recordPreview && now - started >= 3000)) {
        if (heard < HEARD_SECONDS) { stop(); setStatus({ kind: 'silent' }); return; }
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
        <PixelButton tone={status.kind === 'passed' ? 'paper' : 'sky'} onClick={() => void start()} disabled={busy}>
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
      <MicInputControl />
      <p className="solo-hint">Raise MIC INPUT for a quiet microphone. Lower it if your voice sounds distorted.</p>
      {clipping && <Notice tone="warn">Microphone is too loud. Lower MIC INPUT to avoid distortion.</Notice>}
      <section className={`mic-preview${recordingPreview ? ' mic-preview--recording' : ''}`} aria-label="Microphone recording test">
        <div className="mic-preview__heading">
          <span>HEAR YOUR MIC</span>
          <span className="mic-preview__badge">3 SEC</span>
        </div>
        <div className="mic-preview__actions">
          <PixelButton tone="hot" className="mic-preview__record" aria-label="RECORD 3-SECOND TEST" onClick={() => void start(true)} disabled={busy}>
            <span className="mic-preview__dot" aria-hidden="true" />
            {recordingPreview ? 'RECORDING…' : previewUrl ? 'RECORD AGAIN' : 'RECORD TEST'}
          </PixelButton>
          <div className="mic-preview__countdown" aria-hidden="true">
            {[3, 2, 1].map((second) => <span key={second} className={recordingPreview && secondsLeft === second ? 'is-active' : ''}>{second}</span>)}
          </div>
        </div>
        <p className="mic-preview__hint" role="status">
          {recordingPreview ? `Recording · ${secondsLeft} seconds left. Sing a short line!` : previewUrl ? 'Ready! Play it back and check your volume.' : 'Sing a short line, then listen to your mic level.'}
        </p>
        {previewUrl && <audio className="mic-preview__audio" controls src={previewUrl} aria-label="Microphone test recording" />}
        <p className="mic-preview__privacy">Headphones on · saved only on this device</p>
      </section>
      {previewError && <Notice tone="warn">{previewError}</Notice>}
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

/**
 * Mic recorder for one spoken take: REC / STOP keycap, a live pixel level meter, auto-stop before
 * the server's 15 s limit, replay of the take, and RE-RECORD. The mic is released as soon as a take
 * ends and whenever this component unmounts (leaving the screen or switching lines).
 */
import { useEffect, useRef, useState } from 'react';
import { Notice, PixelButton } from '../../ui';

/** The server rejects anything over 15 s (api/practice.py MAX_SECONDS); stop a little early for container overhead. */
const MAX_SECONDS = 14.5;
const METER_BARS = 14;

/** Opus in WebM is what the server expects first; fall back to whatever this browser can record. */
const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return undefined;
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t));
}

type MicState = 'idle' | 'asking' | 'recording' | 'denied' | 'missing' | 'unsupported' | 'failed';

export function Recorder({ disabled, onTake }: { disabled: boolean; onTake: (blob: Blob | null) => void }) {
  const [mic, setMic] = useState<MicState>('idle');
  const [level, setLevel] = useState(0); // lit meter bars, 0..METER_BARS
  const [elapsed, setElapsed] = useState(0);
  const [takeUrl, setTakeUrl] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef(0);
  const limitRef = useRef(0); // auto-stop timer; rAF alone pauses in hidden windows
  const unmountedRef = useRef(false);

  /** Stops the meter and releases the mic and audio graph. Safe to call twice. */
  function release() {
    cancelAnimationFrame(rafRef.current);
    clearTimeout(limitRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }

  // Unmount: stop recording without keeping the take, release the mic.
  useEffect(() => {
    unmountedRef.current = false;
    return () => {
      unmountedRef.current = true;
      const rec = recorderRef.current;
      if (rec && rec.state !== 'inactive') rec.stop();
      recorderRef.current = null;
      release();
    };
  }, []);

  // Revoke the replay URL when the take changes or the recorder goes away.
  useEffect(() => {
    if (!takeUrl) return;
    return () => URL.revokeObjectURL(takeUrl);
  }, [takeUrl]);

  async function start() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setMic('unsupported');
      return;
    }
    setTakeUrl(null);
    onTake(null);
    setMic('asking');

    let stream: MediaStream;
    try {
      // Speech, not singing: the browser's default clean-up is fine here (and helps on laptop mics).
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = e instanceof DOMException ? e.name : '';
      setMic(
        name === 'NotAllowedError' || name === 'SecurityError'
          ? 'denied'
          : name === 'NotFoundError' || name === 'OverconstrainedError'
            ? 'missing'
            : 'failed',
      );
      return;
    }
    if (unmountedRef.current) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    streamRef.current = stream;

    let recorder: MediaRecorder;
    try {
      const mimeType = pickMimeType();
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch {
      release();
      setMic('unsupported');
      return;
    }
    const chunks: Blob[] = [];
    recorder.ondataavailable = (ev) => ev.data.size > 0 && chunks.push(ev.data);
    recorder.onstop = () => {
      release();
      if (unmountedRef.current) return;
      setMic('idle');
      setLevel(0);
      if (chunks.length === 0) return;
      const blob = new Blob(chunks, {
        type: recorder.mimeType || chunks[0].type,
      });
      setTakeUrl(URL.createObjectURL(blob));
      onTake(blob);
    };
    recorderRef.current = recorder;

    // Level meter: RMS of the mic signal, drawn as lit bars.
    const ctx = new AudioContext();
    audioCtxRef.current = ctx;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const t0 = performance.now();
    const tick = () => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += v * v;
      const rms = Math.sqrt(sum / buf.length);
      // ~-50 dBFS reads as empty, ~-6 dBFS as full.
      const db = 20 * Math.log10(rms + 1e-9);
      setLevel(Math.max(0, Math.min(METER_BARS, Math.round(((db + 50) / 44) * METER_BARS))));
      const secs = (performance.now() - t0) / 1000;
      setElapsed(secs);
      if (secs >= MAX_SECONDS) {
        stop();
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };

    recorder.start();
    limitRef.current = window.setTimeout(stop, MAX_SECONDS * 1000);
    setElapsed(0);
    setMic('recording');
    rafRef.current = requestAnimationFrame(tick);
  }

  function stop() {
    cancelAnimationFrame(rafRef.current);
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') rec.stop(); // onstop releases the mic and hands over the take
  }

  const recording = mic === 'recording';
  const micProblem =
    mic === 'denied'
      ? 'Mic access was blocked. Allow the microphone for this site (the icon in the address bar), then retry.'
      : mic === 'missing'
        ? 'No microphone found. Plug one in (a headset mic is great), then retry.'
        : mic === 'unsupported'
          ? "This browser can't record audio here. Try the desktop app or a recent Chrome or Edge."
          : mic === 'failed'
            ? "Couldn't start the microphone. It may be in use by another app; close it and retry."
            : null;

  return (
    <div className="practice-rec">
      <div className="practice-rec__controls">
        <span className="practice-recwrap">
          <button
            type="button"
            className={`practice-recbtn${recording ? ' is-recording' : ''}`}
            onClick={recording ? stop : start}
            disabled={disabled || mic === 'asking'}
            aria-label={recording ? 'Stop recording' : 'Start recording'}
          >
            <span className="practice-recbtn__icon" aria-hidden="true" />
            <span className="practice-recbtn__text">{recording ? 'STOP' : mic === 'asking' ? 'MIC?' : 'REC'}</span>
          </button>
        </span>

        <div className="practice-rec__side">
          <div className="practice-meter" aria-hidden="true">
            {Array.from({ length: METER_BARS }, (_, i) => (
              <span
                key={i}
                className={`practice-meter__bar${i < level ? ' is-on' : ''}${i >= METER_BARS - 3 ? ' is-peak' : ''}`}
              />
            ))}
          </div>
          <p className="practice-rec__status" aria-live="polite">
            {recording ? (
              <>
                <span className="practice-dot" aria-hidden="true" /> Recording… {elapsed.toFixed(1)} s / 15 s
              </>
            ) : mic === 'asking' ? (
              'Waiting for mic permission…'
            ) : takeUrl ? (
              'Got it! Have a listen, then check it.'
            ) : (
              'Press REC and read the line aloud. Stops by itself at 15 s.'
            )}
          </p>
          {recording && (
            <div className="practice-timebar" aria-hidden="true">
              <span
                style={{
                  width: `${Math.min(100, (elapsed / MAX_SECONDS) * 100)}%`,
                }}
              />
            </div>
          )}
          {recording && (
            <PixelButton tone="paper" size="sm" onClick={stop}>
              STOP
            </PixelButton>
          )}
        </div>
      </div>

      {micProblem && (
        <Notice
          tone="error"
          action={
            <PixelButton tone="paper" size="sm" onClick={start}>
              RETRY
            </PixelButton>
          }
        >
          {micProblem}
        </Notice>
      )}

      {takeUrl && !recording && (
        <div className="practice-take">
          <span className="practice-take__label">MY TAKE</span>
          <audio className="practice-take__audio" src={takeUrl} controls />
          <PixelButton tone="mint" size="sm" onClick={start} disabled={disabled}>
            RE-RECORD
          </PixelButton>
        </div>
      )}
    </div>
  );
}

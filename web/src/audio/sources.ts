/**
 * What the singer hears and what we capture: the instrumental (or a click track when the clip has no
 * installed audio), count-in beeps, and the raw microphone.
 */
import { ApiError, audioUrl } from '../lib/api';

export interface Backing {
  buffer: AudioBuffer;
  /** True when the clip has no instrumental and we generated a click track instead. */
  isClick: boolean;
}

/** Fetch and decode the clip's instrumental; on 404 `audio_missing`, fall back to a click track. */
export async function loadBacking(ctx: BaseAudioContext, clipId: string, duration: number): Promise<Backing> {
  let res: Response;
  try {
    res = await fetch(audioUrl(clipId), { credentials: 'same-origin' });
  } catch {
    throw new ApiError(0, 'network', 'Could not reach the server for the instrumental.', true);
  }
  if (res.status === 404) {
    let code = '';
    try {
      code = (await res.json())?.error?.code ?? '';
    } catch {
      // not the API's JSON envelope
    }
    if (code === 'audio_missing') return { buffer: clickTrack(ctx, duration), isClick: true };
  }
  if (!res.ok) throw new ApiError(res.status, 'http_' + res.status, `The instrumental failed to load (${res.status}).`, res.status >= 500);
  return { buffer: await ctx.decodeAudioData(await res.arrayBuffer()), isClick: false };
}

/** A click every half second (120 BPM), accented every 4th beat, for the whole clip. */
export function clickTrack(ctx: BaseAudioContext, duration: number, bpm = 120): AudioBuffer {
  const sr = ctx.sampleRate;
  const buffer = ctx.createBuffer(1, Math.ceil(duration * sr), sr);
  const data = buffer.getChannelData(0);
  const beat = 60 / bpm;
  for (let b = 0; b * beat < duration; b++) writeBlip(data, sr, b * beat, b % 4 === 0 ? 1500 : 1000, b % 4 === 0 ? 0.5 : 0.3);
  return buffer;
}

/** A 30 ms decaying sine blip written into `data` at time `at`. */
function writeBlip(data: Float32Array, sr: number, at: number, hz: number, gain: number) {
  const start = Math.round(at * sr);
  const len = Math.round(0.03 * sr);
  for (let i = 0; i < len && start + i < data.length; i++) data[start + i] += gain * Math.exp(-i / (0.006 * sr)) * Math.sin((2 * Math.PI * hz * i) / sr);
}

/** Schedule count-in beeps on the master clock at the given context times (the last one is higher). */
export function scheduleCountIn(ctx: AudioContext, times: number[]) {
  times.forEach((t, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = i === times.length - 1 ? 1320 : 880;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.12, t + 0.005);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.15);
  });
}

// ---------- microphone ----------

/** Why the mic could not open; an input error with a retry, never a score. */
export type MicProblem = 'denied' | 'missing' | 'busy' | 'insecure' | 'unknown';

export class MicError extends Error {
  constructor(
    readonly problem: MicProblem,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Open the mic raw: no echo cancellation, noise suppression or auto gain (they distort pitch and level).
 * Browsers may ignore these, so we log what was actually applied.
 */
export async function openMic(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) throw new MicError('insecure', 'Microphone needs HTTPS or localhost.');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
    const track = stream.getAudioTracks()[0];
    console.info('[mic] applied settings', track?.getSettings(), track?.label);
    return stream;
  } catch (e) {
    const name = e instanceof DOMException ? e.name : '';
    if (name === 'NotAllowedError' || name === 'SecurityError') throw new MicError('denied', 'Microphone permission was denied.');
    if (name === 'NotFoundError' || name === 'OverconstrainedError') throw new MicError('missing', 'No microphone was found.');
    if (name === 'NotReadableError' || name === 'AbortError') throw new MicError('busy', 'The microphone is busy in another app.');
    throw new MicError('unknown', e instanceof Error ? e.message : 'The microphone failed to open.');
  }
}

export function stopStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((t) => t.stop());
}

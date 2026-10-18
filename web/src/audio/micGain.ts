/** Manual input gain, shared by the level check, scoring capture, recording, and voice send graph. */
const KEY = 'just-sing.mic-gain';
export const clampMicGain = (value: number) => Number.isFinite(value) ? Math.max(0.25, Math.min(4, value)) : 1;
let gain = 1;
try {
  const stored = localStorage.getItem(KEY);
  if (stored !== null) gain = clampMicGain(Number(stored));
} catch { /* Browser storage is optional. */ }
const listeners = new Set<() => void>();
export const getMicGain = () => gain;
export function subscribeMicGain(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function setMicGain(value: number) {
  gain = clampMicGain(value);
  try { localStorage.setItem(KEY, String(gain)); } catch { /* Storage is optional. */ }
  listeners.forEach((listener) => listener());
}
export function createMicGain(ctx: AudioContext) {
  const node = ctx.createGain();
  node.gain.value = gain;
  const unsubscribe = subscribeMicGain(() => node.gain.setTargetAtTime(gain, ctx.currentTime, 0.02));
  return { node, close() { unsubscribe(); node.disconnect(); } };
}

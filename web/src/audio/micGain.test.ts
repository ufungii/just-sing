import { afterEach, expect, it, vi } from 'vitest';
import { clampMicGain, createMicGain, getMicGain, setMicGain } from './micGain';
afterEach(() => { setMicGain(1); vi.unstubAllGlobals(); });

it('applies the selected input gain to every active capture/voice graph and unsubscribes on close', () => {
  const nodes: any[] = [];
  const ctx = { currentTime: 12, createGain: () => {
    const node = { gain: { value: 0, setTargetAtTime: vi.fn() }, disconnect: vi.fn() };
    nodes.push(node); return node;
  } } as unknown as AudioContext;
  const capture = createMicGain(ctx), voice = createMicGain(ctx);
  expect(capture.node.gain.value).toBe(1);
  setMicGain(2.5);
  expect(getMicGain()).toBe(2.5);
  for (const node of nodes) expect(node.gain.setTargetAtTime).toHaveBeenLastCalledWith(2.5, 12, 0.02);
  capture.close();
  setMicGain(0.5);
  expect(nodes[0].gain.setTargetAtTime).toHaveBeenCalledTimes(1);
  expect(nodes[1].gain.setTargetAtTime).toHaveBeenLastCalledWith(0.5, 12, 0.02);
  voice.close();
});

it('bounds input boost and keeps working when storage is unavailable', () => {
  expect(clampMicGain(100)).toBe(4);
  expect(clampMicGain(-1)).toBe(0.25);
  expect(clampMicGain(NaN)).toBe(1);
  vi.stubGlobal('localStorage', { setItem: () => { throw new Error('disabled'); } });
  expect(() => setMicGain(2)).not.toThrow();
  expect(getMicGain()).toBe(2);
});

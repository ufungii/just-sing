import { afterEach, expect, it, vi } from 'vitest';

vi.mock('./captureWorklet', () => ({ CAPTURE_PROCESSOR: 'capture', loadCaptureWorklet: vi.fn() }));
vi.mock('./sources', () => ({
  loadBacking: vi.fn(async () => ({ buffer: {}, isClick: false })),
  loadVocals: vi.fn(async () => ({})), scheduleCountIn: vi.fn(), stopStream: vi.fn(),
}));
import { SingEngine } from './engine';
import { scheduleCountIn } from './sources';

afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

it.each([{ range: null, scheduledAt: undefined }, { range: { start: 15, end: 21 }, scheduledAt: undefined }, { range: { start: 15, end: 21 }, scheduledAt: 30 }])('schedules matching audio offsets and preserves the clip clock for %j', async ({ range, scheduledAt }) => {
  const sources: { start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn> }[] = [];
  const ctx = {
    currentTime: 10, sampleRate: 48000, destination: {}, resume: vi.fn(), close: vi.fn(),
    createGain: () => ({ gain: { value: 0 }, connect: vi.fn() }),
    createBufferSource: () => {
      const source = { buffer: null, connect: vi.fn(), disconnect: vi.fn(), start: vi.fn(), stop: vi.fn() };
      sources.push(source); return source;
    },
  };
  vi.stubGlobal('AudioContext', vi.fn(function () { return ctx; }));
  const from = range?.start ?? 0;
  const end = range?.end ?? 30;
  const engine = await SingEngine.create('test', 30, 0.07, range);
  const trackerStart = vi.spyOn(engine.tracker, 'start');
  const at = scheduledAt ?? 13.15;
  await engine.start(scheduledAt);
  expect(scheduleCountIn).toHaveBeenCalledWith(ctx, [at - 3, at - 2, at - 1]);
  expect(sources).toHaveLength(2);
  for (const source of sources) expect(source.start).toHaveBeenCalledWith(at, from, end - from);
  expect(trackerStart.mock.calls[0][0]).toBeCloseTo(at - from);
  expect(engine.clipTime()).toBeCloseTo(10 - at + from);
  ctx.currentTime = at;
  expect(engine.clipTime()).toBeCloseTo(from);
  await engine.start();
  for (const source of sources) expect(source.start).toHaveBeenCalledTimes(1);
  engine.close();
});

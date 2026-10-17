import { afterEach, expect, it, vi } from 'vitest';

vi.mock('./captureWorklet', () => ({ CAPTURE_PROCESSOR: 'capture', loadCaptureWorklet: vi.fn() }));
vi.mock('./sources', () => ({
  loadBacking: vi.fn(async () => ({ buffer: {}, isClick: false })),
  loadVocals: vi.fn(async () => ({})), scheduleCountIn: vi.fn(), stopStream: vi.fn(),
}));
import { SingEngine } from './engine';
import { scheduleCountIn } from './sources';

afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

it.each([null, { start: 15, end: 21 }])('schedules matching audio offsets and preserves the clip clock for range %j', async (range) => {
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
  await engine.start();
  expect(scheduleCountIn).toHaveBeenCalledWith(ctx, [10.15, 11.15, 12.15]);
  expect(sources).toHaveLength(2);
  for (const source of sources) expect(source.start).toHaveBeenCalledWith(13.15, from, end - from);
  expect(trackerStart.mock.calls[0][0]).toBeCloseTo(13.15 - from);
  expect(engine.clipTime()).toBeCloseTo(from - 3.15);
  ctx.currentTime = 13.15;
  expect(engine.clipTime()).toBeCloseTo(from);
  await engine.start();
  for (const source of sources) expect(source.start).toHaveBeenCalledTimes(1);
  engine.close();
});

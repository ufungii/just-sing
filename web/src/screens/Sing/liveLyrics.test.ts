import { afterEach, expect, it, vi } from 'vitest';

vi.mock('../../lib/api', () => {
  class ApiError extends Error {
    constructor(readonly status: number, readonly code: string, message: string, readonly retryable: boolean) { super(message); }
  }
  return { ApiError, checkLyricLine: vi.fn() };
});
import { checkLyricLine } from '../../lib/api';
import type { Line } from '../../lib/types';
import { TakeRecorder } from '../../audio/takeRecorder';
import { LiveLyricChecker } from './liveLyrics';

const send = vi.mocked(checkLyricLine);
afterEach(() => {
  send.mockReset();
  vi.useRealTimers();
});

const line = (start: number, end: number) => ({ start, end, text: 'x' }) as Line;
const lines = [{ index: 0, line: line(1, 3) }, { index: 1, line: line(4, 6) }];
const recorder = () => new TakeRecorder(48_000, 0, 0, 10);
/** Let the checker's request queue run (requests go out on the next tick, never inside poll()). */
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
const ok = (i: number, status: 'match' | 'unclear') => ({ clip_id: 'c', status: 'ok' as const, lyric_match_version: 't', lines: [{ line_index: i, status }] });

it('sends each line once its audio is in, in order, and collects the statuses', async () => {
  send.mockImplementation(async (_c, i) => ok(i, i === 0 ? 'match' : 'unclear'));
  const updates = vi.fn();
  const live = new LiveLyricChecker('c', lines, recorder(), updates);
  live.poll(3.5); // line 0 ended at 3 s, but its trailing audio (and capture slack) is not in yet
  await flush();
  expect(send).not.toHaveBeenCalled();
  live.poll(4.0);
  await flush();
  expect(send).toHaveBeenCalledTimes(1);
  expect(send.mock.calls[0][1]).toBe(0);
  expect(send.mock.calls[0][3]).toBeCloseTo(-0.7); // slice starts at clip 0.7 s (line start - 0.3 s)
  live.poll(4.1); // nothing new until line 1 is done
  await flush();
  expect(send).toHaveBeenCalledTimes(1);
  const result = await live.finish(); // sends what is left, waits for everything
  expect(send).toHaveBeenCalledTimes(2);
  expect(result).toEqual(new Map([[0, 'match'], [1, 'unclear']]));
  expect(updates).toHaveBeenCalledTimes(2);
});

it('stops sending and falls back when the server has no checker for this clip', async () => {
  send.mockResolvedValue({ clip_id: 'c', status: 'unavailable', lyric_match_version: null, lines: [] });
  const live = new LiveLyricChecker('c', lines, recorder());
  live.poll(100);
  expect(await live.finish()).toBeNull();
  expect(send).toHaveBeenCalledTimes(1); // the second line was never sent
});

it('falls back to the whole take when a line is lost', async () => {
  send.mockImplementationOnce(async () => ok(0, 'match')).mockRejectedValueOnce(new Error('network'));
  const live = new LiveLyricChecker('c', lines, recorder());
  expect(await live.finish()).toBeNull();
});

it('keeps a slow live queue instead of discarding it after 15 seconds', async () => {
  vi.useFakeTimers();
  send.mockImplementation(async (_c, i) => {
    await new Promise((resolve) => setTimeout(resolve, 10_000));
    return ok(i, 'match');
  });
  const live = new LiveLyricChecker('c', lines, recorder());
  const finished = vi.fn();
  const result = live.finish().then((r) => { finished(r); return r; });
  await vi.advanceTimersByTimeAsync(15_001);
  expect(live.results).toEqual(new Map([[0, 'match']]));
  expect(finished).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(5_000);
  expect(await result).toEqual(new Map([[0, 'match'], [1, 'match']]));
});

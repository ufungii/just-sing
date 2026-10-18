import { afterEach, expect, it, vi } from 'vitest';

vi.mock('../../lib/api', () => {
  class ApiError extends Error {
    constructor(readonly status: number, readonly code: string, message: string, readonly retryable: boolean) { super(message); }
  }
  return { ApiError, checkLyrics: vi.fn() };
});
import { ApiError, checkLyrics } from '../../lib/api';
import { resolveLyricCheck } from './useLyricCheck';
import type { LyricStatus } from '../../lib/types';

const send = vi.mocked(checkLyrics);
const take = () => ({ wav: new Blob(['wav']), offsetS: 0 });
afterEach(() => { send.mockReset(); vi.useRealTimers(); });

it('waits for live results without launching a competing whole-take upload', async () => {
  let finish!: (lines: Map<number, LyricStatus>) => void;
  const live = new Promise<Map<number, LyricStatus>>((r) => { finish = r; });
  const result = resolveLyricCheck('c', take(), live);
  await Promise.resolve();
  expect(send).not.toHaveBeenCalled();
  const lines = new Map<number, LyricStatus>([[0, 'match']]);
  finish(lines);
  expect(await result).toEqual({ state: 'ok', lines });
  expect(send).not.toHaveBeenCalled();
});

it('distinguishes missing song/model data from an inference failure', async () => {
  send.mockResolvedValueOnce({ clip_id: 'c', status: 'unavailable', lyric_match_version: null, lines: [] });
  expect(await resolveLyricCheck('c', take())).toEqual({ state: 'offline', reason: 'unavailable' });
  send.mockResolvedValueOnce({ clip_id: 'c', status: 'error', lyric_match_version: 't', lines: [] });
  expect(await resolveLyricCheck('c', take())).toEqual({ state: 'offline', reason: 'failed' });
});

it('retries a busy model once and reports busy rather than claiming it is offline', async () => {
  vi.useFakeTimers();
  send.mockRejectedValue(new ApiError(429, 'pronunciation_busy', 'busy', true));
  const result = resolveLyricCheck('c', take());
  await vi.advanceTimersByTimeAsync(4000);
  expect(await result).toEqual({ state: 'offline', reason: 'busy' });
  expect(send).toHaveBeenCalledTimes(2);
});

it('reports a network failure separately', async () => {
  send.mockRejectedValue(new ApiError(0, 'network', 'network', true));
  expect(await resolveLyricCheck('c', take())).toEqual({ state: 'offline', reason: 'network' });
});

it('falls back after a failed live check and uploads each take only once', async () => {
  send.mockResolvedValue({ clip_id: 'c', status: 'ok', lyric_match_version: 't', lines: [{ line_index: 0, status: 'unclear' }] });
  const recording = take();
  const result = await resolveLyricCheck('c', recording, Promise.reject(new Error('live request failed')));
  expect(result).toEqual({ state: 'ok', lines: new Map([[0, 'unclear']]) });
  expect(await resolveLyricCheck('c', recording)).toEqual(result);
  expect(send).toHaveBeenCalledTimes(1);
});

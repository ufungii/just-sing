import { afterEach, expect, it, vi } from 'vitest';
import { ApiError, asGuest } from './api';

afterEach(() => vi.unstubAllGlobals());

it('can recover a legacy blocked guest after choosing a permitted name', async () => {
  vi.stubGlobal('localStorage', { setItem: vi.fn() });
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'new', display_name: 'Mina' }), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  const call = vi.fn().mockRejectedValueOnce(new ApiError(422, 'invalid_player_name', 'Choose another name', false)).mockResolvedValueOnce('ok');
  expect(await asGuest('Mina', call)).toBe('ok');
  expect(call).toHaveBeenCalledTimes(2);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ display_name: 'Mina' });
});

it('does not create another guest to retry a blocked name', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  const error = new ApiError(422, 'invalid_player_name', 'Choose another name', false);
  await expect(asGuest('rudra', () => Promise.reject(error))).rejects.toBe(error);
  expect(fetch).not.toHaveBeenCalled();
});

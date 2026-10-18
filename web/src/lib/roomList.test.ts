import { describe, expect, it } from 'vitest';
import { filterRooms, passwordProblem, type RoomListItem } from './rooms';

const room = (host_name: string, visibility: 'public' | 'private'): RoomListItem =>
  ({ id: host_name, visibility, host_name, clip_id: 'x', players: 1, created_at: '' });
const rooms = [room('Mina', 'public'), room('mINo', 'private'), room('Joon', 'public')];

describe('room list filtering', () => {
  it('shows everything on the ALL tab', () => expect(filterRooms(rooms, 'all', '')).toHaveLength(3));
  it('splits by tab', () => {
    expect(filterRooms(rooms, 'public', '').map((r) => r.host_name)).toEqual(['Mina', 'Joon']);
    expect(filterRooms(rooms, 'private', '').map((r) => r.host_name)).toEqual(['mINo']);
  });
  it('searches the host name, ignoring case and surrounding spaces', () => {
    expect(filterRooms(rooms, 'all', '  MIN ').map((r) => r.host_name)).toEqual(['Mina', 'mINo']);
    expect(filterRooms(rooms, 'private', 'min').map((r) => r.host_name)).toEqual(['mINo']);
    expect(filterRooms(rooms, 'all', 'zzz')).toEqual([]);
  });
});

describe('private room password rule', () => {
  it.each([['', false], ['ab', false], ['abc', true], ['x'.repeat(16), true], ['x'.repeat(17), false]])('%j ok=%s', (pw, ok) => {
    expect(passwordProblem(pw) === null).toBe(ok);
  });
});

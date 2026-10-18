import { afterEach, expect, it, vi } from 'vitest';
vi.mock('./api', () => ({ bearerToken: vi.fn(async () => null), request: vi.fn() }));
import { connectRoom, leaveRoom, pushSnapshot, roomLive, sendVoice, subscribeVoice, subscribeDuetProgress, type RoomSnapshot } from './rooms';

afterEach(() => { leaveRoom(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('keeps the room identity in socket snapshots and routes ephemeral voice separately from durable state', async () => {
  const sockets: Socket[] = [];
  class Socket {
    readyState = 1;
    onopen = () => {};
    onmessage = (_event: { data: string }) => {};
    send = vi.fn(); close = vi.fn();
    constructor() { sockets.push(this); }
  }
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('window', { setInterval: () => 0 });
  vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });
  connectRoom('room-id');
  await Promise.resolve();
  const socket = sockets[0];
  socket.onopen();
  const snapshot = { id: 'room-id', code: 'ABC', state: 'playing', state_version: 3, members: [], match: null };
  socket.onmessage({ data: JSON.stringify({ type: 'room_snapshot', ...snapshot }) });
  expect(roomLive().snapshot?.id).toBe('room-id');
  const receive = vi.fn();
  const unsubscribe = subscribeVoice(receive);
  const signal = { kind: 'ready' as const, match_id: 'match-id', session: 'session' };
  sendVoice(signal);
  expect(JSON.parse(socket.send.mock.calls[0][0])).toEqual({ type: 'voice_signal', data: signal });
  socket.onmessage({ data: JSON.stringify({ type: 'voice_signal', slot: 1, data: signal }) });
  expect(receive).toHaveBeenCalledWith(1, signal);
  expect(roomLive().snapshot).toEqual(snapshot);
  unsubscribe();
});

it('ignores delayed callbacks and HTTP snapshots from a room we left without cancelling the replacement heartbeat', async () => {
  const sockets: Socket[] = [];
  class Socket {
    readyState = 1;
    onopen = () => {};
    onclose = () => {};
    onmessage = (_event: { data: string }) => {};
    send = vi.fn(); close = vi.fn();
    constructor() { sockets.push(this); }
  }
  const interval = vi.fn(() => 100001);
  const clear = vi.spyOn(globalThis, 'clearInterval');
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('window', { setInterval: interval });
  vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });
  connectRoom('old'); await Promise.resolve();
  sockets[0].onopen();
  connectRoom('new'); await Promise.resolve();
  sockets[1].onopen();
  const current = { id: 'new', state_version: 1, match: null } as RoomSnapshot;
  pushSnapshot(current);
  clear.mockClear();
  sockets[0].onclose();
  sockets[0].onopen();
  sockets[0].onmessage({ data: JSON.stringify({ type: 'room_snapshot', id: 'old', state_version: 99, match: null }) });
  pushSnapshot({ id: 'old', state_version: 99, match: null } as RoomSnapshot);
  expect(clear).not.toHaveBeenCalled();
  expect(interval).toHaveBeenCalledTimes(2);
  expect(roomLive().conn).toBe('open');
  expect(roomLive().snapshot?.id).toBe('new');
  leaveRoom();
  pushSnapshot(current);
  expect(roomLive().snapshot).toBeNull();
});

it('routes live duet scores and pitch only for the current match and server-owned seat', async () => {
  let socket: any;
  class Socket {
    readyState = 1; onmessage = (_: any) => {}; close() {};
    constructor() { socket = this; }
  }
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });
  connectRoom('room'); await Promise.resolve();
  pushSnapshot({ id: 'room', state_version: 1, match: { id: 'current' } } as RoomSnapshot);
  const receive = vi.fn(); const unsubscribe = subscribeDuetProgress(receive);
  const data = { match_id: 'current', t: 2, running: 0, pitch: { start: 90, hz: [220, null] } };
  const emit = (slot: number, value: any) => socket.onmessage({ data: JSON.stringify({ type: 'turn_progress', slot, data: value }) });
  emit(1, data);
  expect(receive).toHaveBeenCalledExactlyOnceWith(1, data);
  emit(1, { ...data, match_id: 'old' }); emit(99, data);
  emit(1, { ...data, pitch: { start: -1, hz: [220] } });
  expect(receive).toHaveBeenCalledTimes(1);
  expect(roomLive().progress).toBeNull();
  unsubscribe(); emit(1, data);
  expect(receive).toHaveBeenCalledTimes(1);
});

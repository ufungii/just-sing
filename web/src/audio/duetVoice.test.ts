import { afterEach, expect, it, vi } from 'vitest';
import { DuetVoice, scheduleVoiceGate, voiceSdp } from './duetVoice';

const room = vi.hoisted(() => ({ live: {} as any, update: () => {}, signal: (_slot: number, _data: any) => {} }));
vi.mock('../lib/rooms', () => ({
  roomLive: () => room.live,
  sendVoice: vi.fn(),
  subscribeRoomLive: (update: () => void) => { room.update = update; return () => {}; },
  subscribeVoice: (signal: typeof room.signal) => { room.signal = signal; return () => {}; },
}));

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('gates the exact authored sections on the audio clock, including gaps and consecutive ownership', () => {
  const gain = { cancelScheduledValues: vi.fn(), setValueAtTime: vi.fn() };
  scheduleVoiceGate(gain as unknown as AudioParam, { currentTime: 10 } as AudioContext, 5, [
    { id: 'a', slot: 0, start: 0, end: 4, phrase_ids: ['a'] }, // already passed
    { id: 'b', slot: 1, start: 7, end: 9, phrase_ids: ['b'] },
    { id: 'c', slot: 0, start: 9, end: 12, phrase_ids: ['c'] },
    { id: 'd', slot: 0, start: 12, end: 14, phrase_ids: ['d'] },
    { id: 'e', slot: 0, start: 16, end: 18, phrase_ids: ['e'] },
  ], 0);
  expect(gain.cancelScheduledValues).toHaveBeenCalledWith(10);
  expect(gain.setValueAtTime.mock.calls).toEqual([[0, 10], [1, 14], [0, 17], [1, 17], [0, 19], [1, 21], [0, 23]]);
});

it('opens only the remainder of a section when rescheduled after reconnect', () => {
  const gain = { cancelScheduledValues: vi.fn(), setValueAtTime: vi.fn() };
  scheduleVoiceGate(gain as unknown as AudioParam, { currentTime: 10 } as AudioContext, -5,
    [{ id: 'a', slot: 1, start: 12, end: 18, phrase_ids: ['a'] }], 1);
  expect(gain.setValueAtTime.mock.calls).toEqual([[0, 10], [1, 10], [0, 13]]);
});

it('requests short audio packets without changing other media sections or codec parameters', () => {
  const sdp = 'v=0\r\nm=audio 9 RTP/SAVPF 111\r\na=rtpmap:111 opus/48000/2\r\na=ptime:20\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n';
  expect(voiceSdp(sdp)).toBe('v=0\r\nm=audio 9 RTP/SAVPF 111\r\na=rtpmap:111 opus/48000/2\r\na=ptime:10\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n');
});


it.each(['connected', 'connecting'])('closes lobby gates immediately and keeps only established peers (%s)', async (connectionState) => {
  const node = () => ({ connect: vi.fn(function (this: unknown) { return this; }), disconnect: vi.fn(),
    gain: { value: 1, cancelScheduledValues: vi.fn(), setValueAtTime: vi.fn(), setTargetAtTime: vi.fn() } });
  const track = { stop: vi.fn() };
  const ctx = { currentTime: 20, createMediaStreamSource: node, createGain: node,
    createMediaStreamDestination: () => ({ ...node(), stream: { getAudioTracks: () => [track], getTracks: () => [track] } }) } as unknown as AudioContext;
  const close = vi.fn();
  const peers = vi.fn(function () { return { close, connectionState, addTrack: vi.fn(), createOffer: async () => ({}),
    setLocalDescription: async () => {}, localDescription: { sdp: '' } }; });
  vi.stubGlobal('RTCPeerConnection', peers);
  room.live = { conn: 'open', snapshot: { id: 'room', state: 'lobby', members: [{ connected: true }, { connected: true }] } };
  const voice = new DuetVoice(ctx, {} as MediaStream, node() as unknown as AudioNode, 'room', null, 0, vi.fn(), true);
  expect(voice.sendGate.gain.setValueAtTime).toHaveBeenLastCalledWith(1, 20);
  room.signal(1, { match_id: null, session: 'other', kind: 'ready' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  expect(peers).toHaveBeenCalledTimes(1);
  room.live.snapshot = { ...room.live.snapshot, state: 'playing', match: { id: 'match', duet: {}, state: 'preparing' } };
  room.update();
  expect(voice.sendGate.gain.setValueAtTime).toHaveBeenLastCalledWith(0, 20);
  expect(voice.receiveGate.gain.setValueAtTime).toHaveBeenLastCalledWith(0, 20);
  expect(close).toHaveBeenCalledTimes(connectionState === 'connected' ? 0 : 1);
  room.signal(1, { match_id: null, session: 'stale-lobby', kind: 'ready' });
  await Promise.resolve();
  expect(peers).toHaveBeenCalledTimes(1);
  voice.schedule(30, [{ id: 'a', slot: 0, start: 2, end: 5, phrase_ids: [] }]);
  expect(voice.sendGate.gain.setValueAtTime).toHaveBeenLastCalledWith(0, 35);
  voice.close();
  expect(close).toHaveBeenCalled();
  expect(track.stop).toHaveBeenCalled();
});

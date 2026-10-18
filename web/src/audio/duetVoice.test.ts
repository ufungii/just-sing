import { afterEach, expect, it, vi } from 'vitest';
import { scheduleVoiceGate, voiceSdp } from './duetVoice';

afterEach(() => vi.restoreAllMocks());

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

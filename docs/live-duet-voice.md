# Live voice in online duets

Online rooms support open voice chat in the lobby after each player passes the mic check. Before passing, the voice button says **MY VOICE MUTED** and is disabled; microphone testing itself is never sent to the other player. Wear wired headphones: echo cancellation is disabled, so speakers cause echo. **Mute my mic to opponent** is available in the lobby and during the song. Muting sharing leaves local pitch scoring active. **Other singer volume** changes only the received voice during the song.

The room owns the successful mic check's microphone stream and AudioContext. It transfers capture only after the check passes, then opens the lobby send and receive gates. Starting the song closes both gates synchronously on the playing room snapshot. Duet scoring uses a cloned track from that same capture and the same AudioContext, without requesting the microphone again; a connected lobby peer is retained. Its outgoing gain opens only for its own authored sections, scheduled against the instrumental's AudioContext clock. A separate mute gain can silence it immediately. The receiver also gates listening to the opposite singer's sections, including practice ranges. Count-in, gaps between sections and post-song audio remain silent. Remote audio never enters scoring. Each singer can capture their own take for the lyric check; the incoming voice never enters that recording.

A muted media element keeps Chromium's remote decoder pulling audio; all audible output still passes through WebAudio's receive gate and volume control. This works around the browser's [silent remote-stream issue](https://issues.chromium.org/issues/40094084). It is paused and detached whenever the peer is replaced or closed.

The online mix uses a shared compressor for instrumental, guide and received voice to reduce clipping. Solo and local duet playback retain their existing output route.

## Microphone level and playback check

**MIC INPUT** is a manual 25–400% input slider, remembered on the current browser. It applies the same gain once to microphone testing, pitch/lyric capture, and outgoing voice. It does not change the instrumental or the other singer's listening volume. Automatic gain control remains disabled. Raise it for a quiet mic; lower it if the check reports clipping or playback sounds distorted. It is available in setup and during singing.

**RECORD 3-SECOND TEST** in the mic check records a short sample at the selected gain. The audio controls let the player hear it before starting. The sample stays in browser memory and is released on retest or leaving the screen. A recording failure releases capture and allows another test. Wear headphones during playback.

## Live pitch and score display

Online duet clients send bounded batches of already-tracked pitch frames and their provisional running score over the existing room WebSocket, at most ten updates per second. Batches carry the match ID and original clip-frame indices; they are not shifted to packet arrival time or estimated from received audio. Both screens draw each section using its singer's selected register and microphone frames. A client never substitutes its own microphone for the opposite seat's trace. Incoming data only updates the display; saved results still use each singer's local assigned-phrase scoring.

The score bars update after scored phrases, including a valid zero score. Messages from another match, malformed/oversized batches, and writes outside the sender's sections are ignored by the display. Disconnects leave missing pitch history; later updates resume on the same timeline without restarting the song. This uses the existing room progress relay and needs no migration or speech model.

## Transport and recovery

Audio goes directly between browsers using WebRTC. The existing authenticated room WebSocket carries only ephemeral `voice_signal` messages: `ready`, `offer`, `answer` and `ice`. It never stores SDP/ICE or audio in the database. The sender seat comes from socket authentication. Signaling only reaches the opposite seat in a lobby or the current preparing/active duet, while both seats are connected. Lobby messages carry `match_id: null`; song messages carry the current match ID. Missing IDs, old song IDs, lobby messages after start and all signaling after stop/finish/abort are rejected. Normal socket Origin checks, rate limits and membership checks apply. SDP messages have a separate bounded size allowance.

Each client announces a random session ID. Offers, answers and ICE target both session IDs and the current match ID, so old events cannot alter a replacement peer. Seat 0 offers; seat 1 answers. Candidates received before a remote description are queued. Losing room connectivity closes the peer immediately. Reconnecting discovers new sessions and rebuilds the peer without restarting the music or changing scores. Failed connections periodically retry. Song completion/error/quit releases the connection, original capture and AudioContext without waiting for score saves. Leaving the room, mic recheck, device removal/revocation and unmount also release them. A late microphone permission result after leaving is stopped immediately. Shared restarts open a fresh capture/peer if the old one was released; the mute preference persists.

The initial configuration uses Google's public STUN server (`stun:stun.l.google.com:19302`). **TURN is not installed or configured.** Strict NAT/firewall combinations can prevent voice connecting; the UI reports that limitation while singing and scoring continue. The Cloudflare tunnel carries signaling only, so voice needs a direct browser-to-browser path. Future TURN credentials must be short-lived credentials issued by the backend, never permanent secrets in the web bundle.

## Latency and verification

Capture retains the existing disabled echo cancellation, noise suppression and automatic gain control. SDP requests 10 ms audio packets; supported receivers get a zero jitter-buffer/playout-delay target. These are preferences, not guarantees. See the [WebRTC specification](https://www.w3.org/TR/webrtc/#dom-rtcrtpreceiver-jitterbuffertarget).

The status line reports selected-path network round-trip time and the cumulative mean receive-buffer delay from WebRTC statistics. Neither is total microphone-to-ear delay. It excludes capture, encoding/decoding, audio graph and device playback costs; do not claim sub-50 ms from these figures. Actual Internet latency and listening quality need a physical two-computer measurement.

`e2e/voice.spec.ts` uses the built-in synthetic duet and two real Chromium contexts with generated microphone tones. It inspects decoded peer audio to check bidirectional lobby voice only after successful mic checks, lobby mute, peer/capture reuse, silent preparation/count-in, section ownership, sharing mute, continued local scoring, room-socket recovery and peer teardown. It needs no copyrighted song assets. Run against a disposable PostgreSQL database/schema, with the built web client:

```sh
(cd web && npm test -- src && npm run build)
# Set DATABASE_URL and TEST_DATABASE_URL to the same disposable test database; never use production.
.venv/bin/python -m api.seed
e2e/node_modules/.bin/playwright test -c e2e/playwright.config.ts voice.spec.ts
.venv/bin/python -m pytest api/tests/test_voice_signaling.py -q
```

Before a demo, use two physical computers on different networks with headphones. Check both handoffs and final held notes, mute and volume, quit/rejoin, and a shared restart. Measure an injected pulse from sender capture to receiver output using synchronized hardware or a common recording clock, with several samples in each direction. Record the median and worst observed delay separately from the browser network/buffer statistics. No physical-device audio-quality or end-to-end latency claim follows from the automated harness.

Verified locally on 2026-10-17 for lobby voice: 160 web source unit tests, typecheck/production build, 20 voice-signaling API tests, and four real Chromium scenarios passed. Browser checks cover lobby audio/mute, capture/peer reuse into the song, count-in and section gates, continued scoring while muted, reconnect/restart, microphone recheck/revocation, explicit connection failure, late permission cleanup, and original microphone/context release. Database writes used an explicitly selected disposable test database. Public-Internet traversal, physical-device audio quality and microphone-to-ear latency remain unverified. Existing large-chunk build and Python model-field/deprecation warnings remain.

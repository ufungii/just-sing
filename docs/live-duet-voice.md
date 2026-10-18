# Live voice in online duets

Online duets share live microphone audio with the opposite player during assigned sections. Wear wired headphones. The lobby explains sharing before readiness; **Mute my mic to opponent** is available there and during the song. Muting sharing leaves local pitch scoring active. **Other singer volume** changes only the received voice.

The browser reuses its scoring microphone as input to a separate WebAudio graph. Its outgoing gain opens only for its own authored sections, scheduled against the instrumental's AudioContext clock. A separate mute gain can silence it immediately. The receiver also gates listening to the opposite singer's sections, including practice ranges. Count-in, gaps between sections and post-song audio remain silent. Remote audio never enters scoring. Duets collect pitch tracks but do not record microphone takes or the incoming voice.

A muted media element keeps Chromium's remote decoder pulling audio; all audible output still passes through WebAudio's receive gate and volume control. This works around the browser's [silent remote-stream issue](https://issues.chromium.org/issues/40094084). It is paused and detached whenever the peer is replaced or closed.

The online mix uses a shared compressor for instrumental, guide and received voice to reduce clipping. Solo and local duet playback retain their existing output route.

## Transport and recovery

Audio goes directly between browsers using WebRTC. The existing authenticated room WebSocket carries only ephemeral `voice_signal` messages: `ready`, `offer`, `answer` and `ice`. It never stores SDP/ICE or audio in the database. The sender seat comes from socket authentication. Signaling only reaches the opposite seat in the current preparing/active duet, while both seats are connected. Normal socket Origin checks, rate limits and membership checks apply. SDP messages have a separate bounded size allowance.

Each client announces a random session ID. Offers, answers and ICE target both session IDs and the current match ID, so old events cannot alter a replacement peer. Seat 0 offers; seat 1 answers. Candidates received before a remote description are queued. Losing room connectivity closes the peer immediately. Reconnecting discovers new sessions and rebuilds the peer without restarting the music or changing scores. Failed connections periodically retry. Quit, stop, save, rematch and unmount release the connection and generated output track.

The initial configuration uses Google's public STUN server (`stun:stun.l.google.com:19302`). **TURN is not installed or configured.** Strict NAT/firewall combinations can prevent voice connecting; the UI reports that limitation while singing and scoring continue. The Cloudflare tunnel carries signaling only, so voice needs a direct browser-to-browser path. Future TURN credentials must be short-lived credentials issued by the backend, never permanent secrets in the web bundle.

## Latency and verification

Capture retains the existing disabled echo cancellation, noise suppression and automatic gain control. SDP requests 10 ms audio packets; supported receivers get a zero jitter-buffer/playout-delay target. These are preferences, not guarantees. See the [WebRTC specification](https://www.w3.org/TR/webrtc/#dom-rtcrtpreceiver-jitterbuffertarget).

The status line reports selected-path network round-trip time and the cumulative mean receive-buffer delay from WebRTC statistics. Neither is total microphone-to-ear delay. It excludes capture, encoding/decoding, audio graph and device playback costs; do not claim sub-50 ms from these figures. Actual Internet latency and listening quality need a physical two-computer measurement.

`e2e/voice.spec.ts` uses the built-in synthetic duet and two real Chromium contexts with generated microphone tones. It inspects decoded peer audio to check silent preparation/count-in, section ownership, sharing mute, continued local scoring, room-socket recovery and peer teardown. It needs no copyrighted song assets. Run against a disposable PostgreSQL database/schema, with the built web client:

```sh
(cd web && npm test && npm run build)
# Supply a disposable DATABASE_URL in the environment; never use production.
.venv/bin/python -m api.seed
e2e/node_modules/.bin/playwright test -c e2e/playwright.config.ts voice.spec.ts
.venv/bin/python -m pytest api/tests/test_voice_signaling.py -q
```

Before a demo, use two physical computers on different networks with headphones. Check both handoffs and final held notes, mute and volume, quit/rejoin, and a shared restart. Measure an injected pulse from sender capture to receiver output using synchronized hardware or a common recording clock, with several samples in each direction. Record the median and worst observed delay separately from the browser network/buffer statistics. No physical-device audio-quality or end-to-end latency claim follows from the automated harness.

Verified locally on 2026-10-17: 122 web unit tests, typecheck/production build, 22 room/signaling API tests, and both Chromium voice scenarios passed. The two browser scenarios were last run separately after correcting test selectors; the final assertions cover reload/missed-start, shared restart, persistent mute and quit cleanup as well as transport/handoffs. An earlier full API run passed 179 tests and found one oversized-message error regression, which was fixed and verified in the 22-test rerun. Every database run used a disposable schema and removed it afterward. Observed localhost network round trips were 0–1 ms and cumulative mean receive buffering ranged roughly 21–44 ms; these are not Internet or end-to-end measurements. Existing large-chunk build and Python deprecation/model-field warnings remain.

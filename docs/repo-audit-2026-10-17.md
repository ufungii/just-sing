# Repository audit — 2026-10-17

Three parallel read-only reviews covered API/persistence, web/Electron, and ML/authoring/contracts while live duet voice was implemented. Findings below are still open unless explicitly marked fixed. No production database, real recordings or Auth0 account was used in the audit.

## Highest priority

1. **P1 (fixed: `api/tests/conftest.py` now requires an explicit `TEST_DATABASE_URL` whose name contains "test" and ignores `.env`'s DATABASE_URL): ordinary API test runs can delete pre-existing database rows.** [api/db.py:8](../api/db.py#L8) loads `.env`; that enables DATABASE_URL-gated tests. [test_retention.py:33](../api/tests/test_retention.py#L33) and [test_auth.py:81](../api/tests/test_auth.py#L81) call unrestricted `cleanup_expired()`. Its selection includes every expired guest and associated history in the configured database, not only test-created rows. Require an explicit disposable test database/schema and fail closed for ordinary DATABASE_URL. All database verification in this WebRTC task used temporary schemas that were removed afterward.

2. **P1: editing and publishing a song can change grading content under the same song version.** [author/store.py:111](../author/store.py#L111) writes rebuilt content without advancing `song.version`; [api/seed.py:18](../api/seed.py#L18) overwrites the checksum at the same `(id, version)`. Frozen matches check that version, and leaderboards group by it. Reproduced with a temporary synthetic fixture: version 1 phrase `[1,3]` became `[1,3.5]` after Save/Rebuild/re-review, still version 1. Review is correctly reset during edits, but explicit re-review and the documented seed/restart flow do not establish a new release. Introduce an immutable publication/version boundary for changes affecting grading; preserve old releases or reject stale matches and separate their results.

## Other confirmed issues

| Priority | Issue and concrete trigger | Evidence / fix direction |
| --- | --- | --- |
| P2 | Local duet history renders `total: null` as **0**. Online Player 2 expands the first accepted attempt and sees Player 1's breakdown. | [History.tsx:60](../web/src/screens/History/History.tsx#L60), [History.tsx:127](../web/src/screens/History/History.tsx#L127). Consume the actual multiplayer history contract and identify the caller's seat; display both local totals. Confirmed by API/UI code paths; no live account needed. |
| P2 | Leaving setup while microphone permission is pending, then granting permission, activates capture after the component has unmounted, for up to 12 seconds. | [MicCheck.tsx:59](../web/src/screens/Solo/MicCheck.tsx#L59). Reproduced by executing the real handler with deferred permission: cleanup ran first, then one AudioContext was created and the late track remained live. Check a cancellation/generation token immediately after awaiting permission and stop late streams. |
| P2 | Electron's Auth0 login leaves the callback and tokens in the system browser rather than authenticating Electron. | [auth.tsx:32](../web/src/lib/auth.tsx#L32), [desktop/main.js:83](../desktop/main.js#L83). The shell intercepts cross-origin redirects, but there is no native callback/PKCE bridge. Confirmed structural gap; live Auth0 was not tested. |
| P2 | The documented pipeline crop loses author timing, exclusions and duet ownership. | [ml/pipeline/crop.py:49](../ml/pipeline/crop.py#L49), [line 112](../ml/pipeline/crop.py#L112). Synthetic parent phrase `[1.2,3.2]`, exclusion `[2,2.5]`, P2 assignment became `[1,3]`, no exclusion, P1 after crop `[0,4]`. Real manifest assembly; encoding mocked. Crop the effective rebuilt manifest, share the author crop implementation, or reject this path when author overrides exist. |
| P2 | Evaluation cropping renumbers surviving phrases but retains stale authored section references, producing an invalid manifest. | [ml/evals/crop_manifest.py:41](../ml/evals/crop_manifest.py#L41). Synthetic crop `[12,26]` retained/renumbered three phrases to `p1–p3` while sections still named `p1–p6`; `Song.model_validate` rejected it. Remap/filter section IDs and drop empty sections. |
| P2 | After a room's two-hour TTL, existing clients can still operate it while rejoining by code fails with 410, including for existing members. | [api/rooms.py:231](../api/rooms.py#L231) checks expiry only in join; GET/actions/socket membership omit it. Confirmed by code paths. Centralize the expiry policy and handle reconnects consistently. |
| P2 | A manifest with `reference.hop_seconds=0` passes catalog validation but crashes scoring actions. | [api/models.py:65](../api/models.py#L65). Database-free reproduction: `Song.model_validate` succeeds, then `_weights(song)` raises `ZeroDivisionError` in [ml/scoring/pitch.py:243](../ml/scoring/pitch.py#L243). Require finite positive hops at the contract boundary. |

## Fixed during the voice task

The room client discarded the room ID from WebSocket snapshots. Delayed callbacks from a departed socket could also overwrite the new room or cancel its heartbeat; an old HTTP snapshot could replace the active room. These blocked or destabilized voice connection/rejoin. The client now preserves room identity, guards socket callbacks before side effects, rejects HTTP snapshots for another/left room, and checks connection generations across pending authentication. Regression tests cover snapshot identity and delayed callbacks/HTTP responses. The voice message-size change also initially changed the legacy oversized-invalid-message error; the original behavior was restored and the room suite rerun.

## Not confirmed

Room abort and final result submission may race because abort does not acquire the match row lock in the usual order. This needs an isolated concurrency reproduction before it is treated as a confirmed bug.

## Verification limits

The frontend review used source inspection and a Node VM reproduction of late microphone/socket callbacks. The ML reviewer ran 112 passing lean tests, 9 skips and 6 passing reproduction subtests; eight other failures and four collection failures were due to missing local dependencies (`librosa`, `scipy`, `imageio_ffmpeg`, `korean_romanizer`). No dependencies or models were installed. These results do not establish physical microphone quality, human-reviewed song timing, live Auth0 behavior or Internet voice latency.

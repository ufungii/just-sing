# Tasks

Updated 2026-10-17. This is the current work list; completed implementation details are in Git history, [PR #14](https://github.com/ufungii/just-sing/pull/14), and [PR #15](https://github.com/ufungii/just-sing/pull/15). The old overnight notes have been consolidated here.

## Working rules

- Treat `CLAUDE.md` as repository instructions for Codex too. Current explicit user instructions take precedence where they conflict.
- PR #14 (earlier overnight work, task 1, teammate handoff) and PR #15 (continuous multiplayer) are merged into `main`. The verification follow-up on `overnight-extra` targets `main` through a new PR; leave it unmerged for review.
- The user authorized moving continuous multiplayer onto `overnight-extra`, committing/pushing it, and deleting the temporary `multiplayer/sections` branch. Do not modify local `main`.
- No co-author trailers or generated-by footers.
- Never commit secrets, `.env`, copyrighted lyrics/audio, or model weights. Song assets and review outputs stay in gitignored `ml/data/`.
- `.env` is the dev database. Never test against production or delete rows the agent did not create; use disposable databases/schemas for tests with cleanup.
- Report verification limits honestly. Keep the Cloudflare tunnel stopped when unattended.

## Completed: continuous multiplayer and verification — Codex

**Implementation merged into `main` through PR #15; all eight browser tests now pass.** The user confirmed both local 1P vs 2P and online rooms should play the song once, continuously, with automatic singer handoffs.

- Use one count-in, clear current/next singer cues, and per-player scoring of assigned phrases. Local uses one shared microphone/playback with each player's chosen register. Solo behavior stays unchanged.
- Support authored `duet_sections` containing section IDs, explicit player slots, and phrase IDs. Preserve whole lyric lines; validate exact ownership and chronological sections. Legacy songs fall back to alternating blocks of three scored lines. Authored consecutive same-player sections are allowed.
- Online clients load audio/open microphones before a shared start barrier, then follow a server-scheduled timeline. Concurrent saves finish the match after both results. Reconnects must not silently replay one player's song; a missed start requires an explicit shared restart.
- Online practice ranges retain authored ownership and must contain scoreable phrases for both singers. Local stays full clip. Assigned subsets must not be mislabeled as practice ranges.
- Freeze arrangement/range/schedule durably; prefer no new migration. Complete model/API ownership, start/concurrency/recovery, and local/online fake-mic browser tests before calling this done.
- Coordinate the arrangement/corrections schema with the teammate building task 2. The optional manifest field is now implemented in the runtime; the author tool’s correction/rebuild integration remains task 2 work.
- Latest checks passed: **120 API tests, 27 Vitest tests, typecheck, build, and all 8 browser tests**. Browser coverage includes local/online handoffs, shared scheduling (including a one-hour client wall-clock skew), same-key save retry, missed-start/shared restart, solo/online practice ranges, and solo good/wrong/silence regressions (98.2 / 56.1 / 0). Database checks used disposable local schemas, which were removed afterward. The follow-up publishes these tests, updated documentation, and small singer-cue/score-layout fixes. The older browser results below predate this redesign.

## Task 2: song author tool — teammate

**Implemented in this PR.** Setup and use: [author/README.md](author/README.md). Full requirements and code entry points: [author-tool handoff](docs/author-tool-handoff.md).

The standalone loopback editor imports the shared timeline, overlays the vocal waveform/reference pitch, shows original and romanized lyrics, and supports lyric/timing/phrase/exclusion/translation edits, tap-to-sync, whole-line player assignments, and undo/redo. Explicit Save preserves aligner metadata and backs up corrections/review files. Rebuild applies the namespaced author overrides through manifest assembly, including duet sections. Review marking remains an explicit human action. Synthetic unit and browser tests cover persistence and ownership validation; listening accuracy and real reference quality remain human checks. Existing song assets were only read during verification.

Build the standalone localhost-only review app in `author/`, importing the shared timeline from `web/src/`. Show original and romanized lyrics together; support waveform/reference-pitch review, lyric/timing edits, tap-to-sync, and selecting lines to assign Player 1/Player 2. Explicit Save, backups, undo/redo, Rebuild, and review marking are required. Song ingestion and note/octave editing are out of scope.

The runtime now supports the optional duet manifest field; the handoff describes its shape and the remaining author/pipeline integration. Save assignments through corrections and preserve them through Rebuild.

## Remaining bugs and maintenance

- Local catalog verification found a pre-existing incompatibility: `api.models.Song` rejects scored lines with empty `practice_text`, while the pipeline intentionally leaves mixed/English lines empty for Korean-only pronunciation practice. The author tool reads all ten prepared full/demo manifests, but the main API cannot load that catalog until singing eligibility is separated from pronunciation eligibility. Author regression tests use the built-in synthetic API catalog and do not change existing song assets.

- Verify explicit quitting mid-performance closes the shared duet promptly. Save retry and missed-start/shared-restart now have browser coverage in the verification follow-up.
- Online: an existing guest name overrides a newly typed name; the singing title omits the online player name.
- API `_weights` uses reference Hz while TypeScript can fall back to notes; stub contours can disagree. No current prepared clip is known to trigger this.
- Vocals/instrumental endpoints serve installed stems without auth. Public deployments must use permitted assets; copyrighted clips stay on the team machine.
- Unify scoring configuration with the local demo; `ml/scoring/api_integration.patch` and `API_INTEGRATION.md` are stale.
- Pipeline: remove the hardcoded Windows separation-environment path in `ml/pipeline/run.py`; supplying prepared stems bypasses that path today.
- Pronunciation: the optional scorer hook was tested with fake scorers; real model warm-up, scores, and the practice screen still need end-to-end verification. The older `live_scoring.json` fixtures cover the legacy live engine, not the current TypeScript SPEC port.
- ML B: add an exact-half rounding fixture to `contracts/fixtures`; TypeScript's half-even behavior currently has only its local rounding test.
- `CLAUDE.md` current-status text is stale. Refresh after user confirmation, in its own small PR.
- Ask DrewV2 what still needs porting from `origin/ml/pipeline` before deleting it. The earlier assessment found stale/conflicting code plus possible `/catalog` and `reference_unavailable` changes; recheck before acting. Do not send a message without authorization.

## User checks and deployment

- Listen to/review `russian-roulette` and `how-sweet`; both were last recorded as unreviewed. For `how-sweet`, check the line 8/9 split near 21–22 s, the 18–34 s stretch, phrase p8's end, and p7's long hold.
- For `russian-roulette`, recheck the draft lyrics/alignment, missing translations, phrase endings/held notes, exclusions, octave choices, and stem quality. The old overnight report did not establish review by ear; keep review corrections alongside local assets.
- Test with a real mic/headphones and two physical computers. Current browser verification uses fake microphones and two contexts on one computer.
- Keep Auth0 callback, logout, and web-origin URLs aligned with the actual app URL; live Auth0 login was not retested in this work.
- Before deployment, verify production migration status. It was last reported two revisions behind (`3e6c60a577fd`, `2822a2cbf379`). Run `alembic -c api/alembic.ini upgrade head` with production `DATABASE_URL` supplied only as an environment variable, then `python -m api.seed`. Never put production credentials in `.env`.
- Rotate the Gemini key and database password previously exposed in chat.
- Keep the tunnel stopped when unattended; the final two-computer/demo setup remains a user check.

## Completed: task 1 and pre-redesign karaoke work

**Merged into `main` through PR #14.** Solo/online practice-section editing has a reusable phrase-snapping timeline, lyric positions, preview with synchronized instrumental/vocals, full reset, aligned count-in/playback/scoring, and practice labels in results/history. Hosts choose room ranges; guest views are read-only. Ranges survive retries/rematches without a migration; failed edits restore server state. Empty-score sections are rejected early. Local battle stays full clip.

PR #14 also includes earlier reference-engine scoring/TypeScript parity, Auth0 identity/history, template coaching fallback, guide vocals, optional local pronunciation, local battle, and online lobbies. Those historical browser checks used sequential full-song multiplayer. PR #15 replaces that flow with continuous section handoffs; its verification is tracked above.

Historical verification before the continuous multiplayer redesign:

- Typecheck, production build, and **24 Vitest tests passed**; the build retains its existing large-chunk warning.
- Complete API suite: **104 passed**, with 3 existing warnings.
- Browser tests: **2 range tests + 5 full-clip tests passed**, including solo good/wrong/silence and local/online battles. Range tests used local `russian-roulette`; full-clip regressions used the synthetic song. Database tests used disposable local PostgreSQL schemas; test schemas/container were removed.
- Python score/fixture/spec/timing tests: **36 passed, 1 skipped**. Broader offline pitch extraction has 3 missing-dependency failures (`librosa`/`scipy`) in the lean API environment; no ML dependencies were changed.
- Lyric-masked visual QA passed. Real microphones, two physical computers, live Auth0, and timing accuracy by ear remain unverified.

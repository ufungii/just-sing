# Tasks

Updated 2026-10-17. This is the current work list; completed implementation details are in Git history and [PR #14](https://github.com/ufungii/just-sing/pull/14).

## Working rules

- Treat `CLAUDE.md` as repository instructions for Codex too. Current explicit user instructions take precedence where they conflict.
- PR #14 uses `overnight-extra` and targets `main`. The user authorized its push and PR; leave it unmerged. It includes the earlier overnight work, task 1, and the teammate handoff, **not the continuous multiplayer implementation**.
- Continuous multiplayer work is isolated on `multiplayer/sections` in `/tmp/just-sing-multiplayer`. Keep it separate from PR #14. Do not modify local `main`; publish additional work only with user authorization.
- No co-author trailers or generated-by footers.
- Never commit secrets, `.env`, copyrighted lyrics/audio, or model weights. Song assets and review outputs stay in gitignored `ml/data/`.
- `.env` is the dev database. Never test against production or delete rows the agent did not create; use disposable databases/schemas for tests with cleanup.
- Report verification limits honestly. Keep the Cloudflare tunnel stopped when unattended.

## Active: continuous multiplayer — Codex

**In progress on the separate branch; unverified and not in PR #14.** The user confirmed both local 1P vs 2P and online rooms should play the song once, continuously, with automatic singer handoffs.

- Use one count-in, clear current/next singer cues, and per-player scoring of assigned phrases. Local uses one shared microphone/playback with each player's chosen register. Solo behavior stays unchanged.
- Support authored `duet_sections` containing section IDs, explicit player slots, and phrase IDs. Preserve whole lyric lines; validate exact ownership and chronological sections. Legacy songs fall back to alternating blocks of three scored lines. Authored consecutive same-player sections are allowed.
- Online clients load audio/open microphones before a shared start barrier, then follow a server-scheduled timeline. Concurrent saves finish the match after both results. Reconnects must not silently replay one player's song; a missed start requires an explicit shared restart.
- Online practice ranges retain authored ownership and must contain scoreable phrases for both singers. Local stays full clip. Assigned subsets must not be mislabeled as practice ranges.
- Freeze arrangement/range/schedule durably; prefer no new migration. Complete model/API ownership, start/concurrency/recovery, and local/online fake-mic browser tests before calling this done.
- Coordinate the final arrangement/corrections schema with the teammate building task 2.

## Task 2: song author tool — teammate

**Ready to hand off.** Full requirements and code entry points: [author-tool handoff](docs/author-tool-handoff.md).

Build the standalone localhost-only review app in `author/`, importing the shared timeline from `web/src/`. Show original and romanized lyrics together; support waveform/reference-pitch review, lyric/timing edits, tap-to-sync, and selecting lines to assign Player 1/Player 2. Explicit Save, backups, undo/redo, Rebuild, and review marking are required. Song ingestion and note/octave editing are out of scope.

The duet manifest field is being implemented separately; the handoff describes the target shape and this dependency. Save assignments through corrections and preserve them through Rebuild.

## Remaining bugs and maintenance

- Online: quitting mid-turn leaves a started attempt until timeout. Retry lacks UI e2e coverage; a failed score save has no save-retry button.
- Online: an existing guest name overrides a newly typed name; the singing title omits the online player name.
- Local battle: handoff may choose an invalidated slot-1 attempt. Reassess when continuous multiplayer replaces that flow.
- API `_weights` uses reference Hz while TypeScript can fall back to notes; stub contours can disagree. No current prepared clip is known to trigger this.
- Vocals/instrumental endpoints serve installed stems without auth. Public deployments must use permitted assets; copyrighted clips stay on the team machine.
- Unify scoring configuration with the local demo; `ml/scoring/api_integration.patch` and `API_INTEGRATION.md` are stale.
- ML B: add an exact-half rounding fixture to `contracts/fixtures`; TypeScript's half-even behavior currently has only its local rounding test.
- `CLAUDE.md` current-status text is stale. Refresh after user confirmation, in its own small PR.
- Ask DrewV2 what still needs porting from `origin/ml/pipeline` before deleting it. The earlier assessment found stale/conflicting code plus possible `/catalog` and `reference_unavailable` changes; recheck before acting. Do not send a message without authorization.

## User checks and deployment

- Listen to/review `russian-roulette` and `how-sweet`; both were last recorded as unreviewed. For `how-sweet`, check the line 8/9 split near 21–22 s, the 18–34 s stretch, phrase p8's end, and p7's long hold.
- Test with a real mic/headphones and two physical computers. Current browser verification uses fake microphones and two contexts on one computer.
- Keep Auth0 callback, logout, and web-origin URLs aligned with the actual app URL; live Auth0 login was not retested in this work.
- Before deployment, verify production migration status. It was last reported two revisions behind (`3e6c60a577fd`, `2822a2cbf379`). Run `alembic -c api/alembic.ini upgrade head` with production `DATABASE_URL` supplied only as an environment variable, then `python -m api.seed`. Never put production credentials in `.env`.
- Rotate the Gemini key and database password previously exposed in chat.
- Keep the tunnel stopped when unattended; the final two-computer/demo setup remains a user check.

## Completed: task 1 and pre-redesign karaoke work

**Pushed in PR #14; unmerged.** Solo/online practice-section editing has a reusable phrase-snapping timeline, lyric positions, preview with synchronized instrumental/vocals, full reset, aligned count-in/playback/scoring, and practice labels in results/history. Hosts choose room ranges; guest views are read-only. Ranges survive retries/rematches without a migration; failed edits restore server state. Empty-score sections are rejected early. Local battle stays full clip.

The PR also includes earlier reference-engine scoring/TypeScript parity, Auth0 identity/history, template coaching fallback, guide vocals, optional local pronunciation, local battle, and online lobbies. Its multiplayer gameplay still uses sequential full-song turns; continuous section handoffs are the separate active task above.

Verification of the published gameplay:

- Typecheck, production build, and **24 Vitest tests passed**; the build retains its existing large-chunk warning.
- Complete API suite: **104 passed**, with 3 existing warnings.
- Browser tests: **2 range tests + 5 full-clip tests passed**, including solo good/wrong/silence and local/online battles. Range tests used local `russian-roulette`; full-clip regressions used the synthetic song. Database tests used disposable local PostgreSQL schemas; test schemas/container were removed.
- Python score/fixture/spec/timing tests: **36 passed, 1 skipped**. Broader offline pitch extraction has 3 missing-dependency failures (`librosa`/`scipy`) in the lean API environment; no ML dependencies were changed.
- Lyric-masked visual QA passed. Real microphones, two physical computers, live Auth0, and timing accuracy by ear remain unverified.

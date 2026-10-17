# Tasks

Updated 2026-10-17. This is the current work list; completed implementation details are in Git history and merged PRs [#14](https://github.com/ufungii/just-sing/pull/14), [#15](https://github.com/ufungii/just-sing/pull/15), [#16](https://github.com/ufungii/just-sing/pull/16), and [#17](https://github.com/ufungii/just-sing/pull/17). The old overnight notes have been consolidated here.

## Handoff to Claude Code

**The requested implementation is finished. No feature agent is still working. The user explicitly requested committing and pushing this batch after the Claude Code handoff.** Source changes and this handoff are included in that publication on `overnight-extra`; use `git log` / `git status` for the resulting commit IDs. The sections below take precedence over stale status text in `CLAUDE.md`.

- Current branch: `overnight-extra`, implementation baseline `dcc6033` (PR #17 merge), followed by this batch's desktop, compatibility, author/practice and handoff commits. This branch was previously fast-forwarded with an autostash; local `main` was not changed.
- Latest fetch found `origin/main` at `51dc876` (PR #18, Python/browser scoring 0.2.0 plus evaluation/word-feedback work). **That newer scoring work is not incorporated into this branch or its reported test results.** Inspect and integrate it before merging this batch, then run scoring/parity and relevant regression checks. Publishing this branch does not update `main`.
- An autostash remains as `stash@{0}`, commit `12e644f`. Its restored changes are already in the working tree, and the only conflict (`tasks.md`) was resolved. **Do not blindly reapply or drop it**; compare it with the working tree first if cleaning it up.
- Keep work on this branch unless the user asks otherwise. The user authorized this batch's commit/push; no new PR or merge has been requested for it yet. Root `artifacts/` contains local generated test output and is excluded from the commits. Song assets and builds remain ignored locally.
- Eight real songs are installed locally: seven Drive imports plus Apple Cider. The API lists **10 entries including two synthetic clips**; the author lists **8 songs**. The two original short clips are archived and absent from both live lists. No new schema migration was added.

Implementation map:

| Area | Changes to preserve |
| --- | --- |
| Desktop | `desktop/electron-builder.config.cjs`, package/lock changes and `main.js`: Linux AppImage packaging with build-time server URL and runtime override. Thin client; no server/assets bundled. |
| Singing/pronunciation compatibility | `api/models.py`, `api/practice.py`, practice screen and tests: empty Korean practice text is valid for singing; those phrases are skipped/rejected in spoken practice. |
| Raw audio import | New `author/ingest.py`, `author/src/AddSong.tsx`, author routes/requirements/tests: private preparation jobs, durable progress, cancel/retry, validation and publication under a new ID. Audio plus supplied lyrics required; Korean/English supported. |
| Offline pipeline | `ml/pipeline/run.py`: cross-platform separation interpreter, `--separation-python`, `--data-dir`, `--language ko|en`, stage progress and overwrite protection. Heavy inference stays out of the web server. |
| Author timing/cropping | New `author/crop.py`, shared `CropWorkspace.tsx/css`, author UI/tests: full-screen precise editor, source-preserving short clips, rebased stems/lyrics/reference/duet ownership, live drag ghost/readout, invalid overlap highlighting and Escape cancellation. |
| Player practice UI | New `PracticeSectionView.tsx/css`, shared workspace/picker: large original/romanized lyrics above the waveform bar; white current line, pink included lines, START/END badges, scrubbing, phrase-snapped handles, search, zoom, preview and read-only guests. Pausing preview retains its position. |
| Documentation/verification | `CONTEXT.md` glossary, updated author/desktop/pipeline/API/timeline READMEs and original teammate handoff; author/browser fixtures and regression checks. Test song choices distinguish similarly titled full/short songs. |

Next work, in order:

1. Have the user refresh the app and try **Open Section Editor**, and refresh `http://127.0.0.1:8010` to try **Add song** / **Open timing / crop workspace**. Both production frontend builds are already current. Fix concrete issues found during use.
2. Listen to and review the eight real-song drafts in the author tool, especially Apple Cider's automatically aligned words. Real microphone/headphone, two-computer multiplayer and live Auth0 checks remain outstanding.
3. The user has requested commit/push of `overnight-extra`; that is handled by this publication. Next, reconcile the newer PR #18 scoring work noted above and open a PR to `main` when requested. Song assets, model caches, `.env`, AppImage output and local screenshots must stay out of Git. There is no PR for this latest batch yet.
4. Replace the temporary author Python environment with a stable `author/.venv` when convenient, following [author/README.md](author/README.md). The running server currently uses the temporary environment listed below; it will not survive arbitrary `/tmp` cleanup.
5. Remaining product/pipeline issues and deployment checks are listed later in this file. Japanese support was discussed as a feasibility question only; it has **not** been implemented. Do not assume the current Korean/English import selector supports Japanese.

## Running services and local environments

Snapshot at handoff; verify process identity/port before stopping anything:

- API: `127.0.0.1:8000`, PID **77666**, root `.venv/bin/python`, one Uvicorn worker. Log: `/tmp/just-sing-active-api.log`. It was seeded and restarted after Apple Cider; all eight real songs are visible.
- Author: `127.0.0.1:8010`, PID **70409**, running **this checkout's code** with `/tmp/just-sing-author-nxg775j3/.venv/bin/python`. Log: `/tmp/just-sing-active-author.log`. Bind loopback only; do not tunnel this port.
- User-owned Cloudflare tunnel: PID **40878**, forwarding to API8000 over HTTP/2. Leave it running for the user's session; do not replace it or put its temporary hostname in public documentation. The AppImage loads its configured server URL; a new tunnel hostname requires a URL override or rebuild.
- Offline models: `/home/doa/.cache/just-sing-pipeline/venv/bin/python`, Python 3.12, CPU processing (CUDA unavailable). Both author interpreter settings currently point here. Installed compatible Torch/torchaudio, Demucs, CREPE, alignment and romanization dependencies and model caches were reused; no heavy dependencies were added for this work. **Do not resolve a virtualenv Python symlink** before invoking it, because that selects the system interpreter instead.
- Build output: `web/dist/`, `author/dist/`, and `desktop/dist/Just-Sing-0.1.0-x86_64.AppImage` (approximately 120 MB). Frontend edits require rebuilding the respective frontend; the AppImage itself needs no rebuild for server-side frontend changes.

Restart commands from the repository root, after stopping the matching old process if needed:

```sh
# Shared HTTPS/tunnel demo; use COOKIE_SECURE=0 for a separate HTTP-only local demo.
COOKIE_SECURE=1 .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# Current installed author environment; create author/.venv for durable setup later.
AUTHOR_PIPELINE_PYTHON=/home/doa/.cache/just-sing-pipeline/venv/bin/python \
AUTHOR_SEPARATION_PYTHON=/home/doa/.cache/just-sing-pipeline/venv/bin/python \
/tmp/just-sing-author-nxg775j3/.venv/bin/python -m author.server --data-dir "$PWD/ml/data" --port 8010
```

The author discovers folders dynamically. The API caches its catalog at startup: after publishing additional local songs or rebuilding them, run `.venv/bin/python -m api.seed` with the intended dev database configured, then restart the single API worker. This was already done for the current eight real songs.

## Verification handoff

- **123 API tests**, **25 author unit tests**, **27 web unit tests**, both frontend production builds and **6 pipeline runner tests** passed during this batch. The frontend retains its pre-existing large-bundle warning; Python suites retain existing warnings.
- **9 karaoke browser tests** passed: solo good/wrong/silence, continuous local/online handoffs, restart/recovery, and solo/online ranges including the full-screen picker. After the lyric-first redesign, all **3 range browser tests** and all **3 author browser tests** passed again. A final focused practice-workspace test also passed after adding real handle-drag, phone-layout and pause-position assertions. Do not mistake the earlier failed broad-title song locators in an old log for unresolved app failures; the selectors were corrected and affected tests rerun successfully.
- Live desktop/390 px phone visual checks used synthetic replacement lyrics in the browser only, without changing song files. No page errors or horizontal overflow; live waveform decoding was checked. Real raw-audio pipeline smoke passed using synthetic vocals (5.07 s, three phrases), including separation, alignment and reference pitch. Apple Cider's full pipeline and exact matching stem decode also passed.
- API/database browser checks ran in disposable PostgreSQL schemas on local container `js-duet-tests` (port 18766); schemas were removed afterward. Do not run the unwrapped browser suite against `.env` or production. `/tmp/just-sing-duet-tests.py` creates/drops an isolated schema and seeds browser fixtures. For range/duet tests, set `SONG_DIRS` to `api/catalog`, `ml/data`, and `ml/data/.archived-short-clips/20261017T190946Z` (absolute, colon-separated); this includes archived short clips **only in the test process**, never the live catalog. If temporary helpers disappear, recreate the disposable setup before running database tests.
- Useful logs: `/tmp/just-sing-drive-import-api.log`, `/tmp/just-sing-author-workspace-unit.log`, `/tmp/just-sing-lyric-view-unit.log`, `/tmp/just-sing-lyric-view-browser.log`, `/tmp/just-sing-lyric-view-interaction.log`, `/tmp/just-sing-lyric-view-author-browser.log`, `/tmp/just-sing-workspace-game-browser-retry.log`, `/tmp/just-sing-raw-import-smoke.log`. Current production build logs: `/tmp/just-sing-lyric-view-{web,author}-build.log`.

## Working rules

- Treat `CLAUDE.md` as repository instructions for Codex too. Current explicit user instructions take precedence where they conflict.
- PR #14 (earlier overnight work, task 1, teammate handoff), PR #15 (continuous multiplayer), PR #16 (verification follow-up and notes cleanup), and PR #17 (baseline author tool) are merged into `main` and incorporated into this checkout. This batch adds AppImage packaging, the song-import compatibility fix, raw-audio import and the expanded crop workspace on `overnight-extra`; it has not been merged into `main`.
- The user authorized moving continuous multiplayer onto `overnight-extra`, committing/pushing it, and deleting the temporary `multiplayer/sections` branch. Do not modify local `main`.
- No co-author trailers or generated-by footers.
- Never commit secrets, `.env`, copyrighted lyrics/audio, or model weights. Song assets and review outputs stay in gitignored `ml/data/`.
- `.env` is the dev database. Never test against production or delete rows the agent did not create; use disposable databases/schemas for tests with cleanup.
- Report verification limits honestly. Keep the Cloudflare tunnel stopped when unattended.

## Local demo: AppImage and Drive songs

- Built and launched the Linux x86-64 AppImage in gitignored `desktop/dist/`. It remembers the server URL supplied at build time and accepts a runtime `JUST_SING_URL` override. The server and tunnel must remain running. Desktop home rendering, secure context, database readiness and microphone permission were checked; real singing and Auth0 login in Electron still need user verification.
- Imported seven full-song bundles from the [team Drive folder](https://drive.google.com/drive/folders/1ol-1DKF_Y5NqpsjiiLk-wBcAF8ReHgpA): Blood Sweat & Tears, How Sweet, Love Language, Love Scenario, Russian Roulette, Love (Keyshia Cole), and Party in the USA. Full songs use separate `*-full` IDs. At the user's request, the two original short clips were removed from the live catalog and archived under `ml/data/.archived-short-clips/20261017T190946Z/`; database history was preserved. Original downloads, manifests, stems and review records remain in gitignored `ml/data/`; no song assets belong in a PR or the AppImage.
- Both stems in every imported bundle decoded successfully, durations match the manifests, and both multiplayer slots have scoreable reference frames. All imports remain **draft/unreviewed**; listening and checking lyric/pitch alignment still need human review.
- Fixed runtime validation so English/mixed-language singing phrases may have empty spoken-Korean `practice_text`, matching pipeline output. The practice screen skips those phrases and the upload API rejects them before decoding/scoring. Verification: **123 API tests, 27 web tests, and production build passed**; all five instrumental/vocal previews passed through the tunnel.
- Soda Pop and Last Christmas folders are still empty; import them when `song.json` and both stems are uploaded. The other two previously empty folders have been imported. The Drive agent's requested import pass is complete.
- A separate agent imported the user-linked YouTube song **Apple Cider — beabadoobee** as `apple-cider-beabadoobee-full` (178.887 s, 33 lyric lines, 30 scored phrases). Lyrics came from the official uploader's description. Both stems fully decode with identical frame counts; manifest/reference/catalog checks passed. It is installed, seeded and exposed by the restarted API, alongside the seven Drive imports (10 catalog entries including synthetic clips). It remains **unreviewed**: acoustic alignment flagged 76/158 words, so lyric/phrase timing and pitch need listening review. Private provenance/report: `ml/data/.youtube-import-20261017-apple-cider/`; original source/stems are retained.

## Local extension: audio import and long-song editing — Codex

- User-confirmed design: full-screen workspace in both the player practice picker and the author tool, with whole-song overview, zoom, original/romanized lyric search, time fields, playhead boundary buttons and vocal/backing preview. Player selections snap to whole phrases; author crop times are precise. Only the author tool can save a separate short clip.
- Implemented live lyric drag placement with original-position ghost, proposed time readout, invalid overlap highlighting, edge scrolling and Escape cancellation. Waveform/reference overlays use compact SVG paths to reduce rendering work on full songs.
- Updated the player practice workspace to the user's lyric-first reference: large scrolling lyrics above the waveform bar, white current line, pink included lines and START/END badges. Scrubbing, lyric clicks and range-handle drags keep the display aligned; original/romanized search, zoom, phrase snapping and guest read-only behavior remain available. Desktop/mobile visual checks and player range browser checks passed; the author keeps its detailed timing workspace.
- **Add song** accepts raw audio plus supplied lyrics, title/artist and Korean/English language. Processing runs in a separate configured Python environment with durable progress, reload recovery, cancel/retry and local logs. It validates private output before adding a new draft, and never overwrites existing IDs. A real synthetic-vocal run passed separation, alignment, pitch extraction and manifest creation using the installed CPU model environment.
- Saving a short clip works with portable Drive folders as well as pipeline outputs. Both stems, lyrics/reference and duet ownership are cropped/rebased; source files stay intact and new clips remain unreviewed. Save/Rebuild source edits first.
- The updated loopback-only author server runs from this checkout at `http://127.0.0.1:8010`, with the installed processing environment configured. It lists all eight real songs. Refresh any older tab. Setup and publishing instructions: [author README](author/README.md).
- Verification: **25 author unit tests and all 3 author browser tests passed**, including upload/reload/open, drag placement/cancellation, three-minute navigation and saving a separate clip. Both frontend production builds, **27 web unit tests and all 9 karaoke browser tests passed**. Karaoke checks cover solo good/wrong/silence (98.2 / 56.1 / 0), continuous local/online duets, recovery, practice ranges, the full-screen player workspace and read-only guests. Tests used a disposable database schema and included the archived short clip only in the test catalog; live songs stayed unchanged. Song-choice locators now distinguish a short clip from its similarly titled full song. Real microphone/listening review remains a user check.

## Completed: continuous multiplayer and verification — Codex

**Implementation merged into `main` through PR #15; all eight browser tests now pass.** The user confirmed both local 1P vs 2P and online rooms should play the song once, continuously, with automatic singer handoffs.

- Use one count-in, clear current/next singer cues, and per-player scoring of assigned phrases. Local uses one shared microphone/playback with each player's chosen register. Solo behavior stays unchanged.
- Support authored `duet_sections` containing section IDs, explicit player slots, and phrase IDs. Preserve whole lyric lines; validate exact ownership and chronological sections. Legacy songs fall back to alternating blocks of three scored lines. Authored consecutive same-player sections are allowed.
- Online clients load audio/open microphones before a shared start barrier, then follow a server-scheduled timeline. Concurrent saves finish the match after both results. Reconnects must not silently replay one player's song; a missed start requires an explicit shared restart.
- Online practice ranges retain authored ownership and must contain scoreable phrases for both singers. Local stays full clip. Assigned subsets must not be mislabeled as practice ranges.
- Freeze arrangement/range/schedule durably; prefer no new migration. Complete model/API ownership, start/concurrency/recovery, and local/online fake-mic browser tests before calling this done.
- The runtime supports the optional duet manifest field. Task 2's correction/rebuild integration is now merged through PR #17.
- Latest checks passed: **120 API tests, 27 Vitest tests, typecheck, build, and all 8 browser tests**. Browser coverage includes local/online handoffs, shared scheduling (including a one-hour client wall-clock skew), same-key save retry, missed-start/shared restart, solo/online practice ranges, and solo good/wrong/silence regressions (98.2 / 56.1 / 0). Database checks used disposable local schemas, which were removed afterward. The follow-up publishes these tests, updated documentation, and small singer-cue/score-layout fixes. The older browser results below predate this redesign.

## Completed: task 2 song author tool — teammate

**Merged into `main` through [PR #17](https://github.com/ufungii/just-sing/pull/17) and incorporated into this checkout.** Setup and use: [author README](author/README.md). Original requirements: [author-tool handoff](docs/author-tool-handoff.md).

The standalone localhost-only app in `author/` includes the shared timeline, waveform/reference pitch, original and romanized lyrics together, lyric/timing edits, tap-to-sync, whole-line Player 1/Player 2 assignment, Save/backups, undo/redo, Rebuild, and explicit review marking. Saved corrections and duet assignments pass through manifest assembly; portable handoff folders are supported. Its baseline tests pass alongside the new extension checks above. Listening accuracy and the imported songs' timing/pitch quality still need human review.

The API catalog incompatibility noted in PR #17 (singing phrases with empty Korean practice text) is fixed by this branch's compatibility commit. Raw-audio ingestion is included in this batch; note/octave editing remains future work.

## Remaining bugs and maintenance

- Verify explicit quitting mid-performance closes the shared duet promptly. Save retry and missed-start/shared-restart now have browser coverage in the verification follow-up.
- Online: an existing guest name overrides a newly typed name; the singing title omits the online player name.
- API `_weights` uses reference Hz while TypeScript can fall back to notes; stub contours can disagree. No current prepared clip is known to trigger this.
- Vocals/instrumental endpoints serve installed stems without auth. Public deployments must use permitted assets; copyrighted clips stay on the team machine.
- Unify scoring configuration with the local demo; `ml/scoring/api_integration.patch` and `API_INTEGRATION.md` are stale.
- Pipeline: this branch replaces the hardcoded Windows separation-environment path with cross-platform defaults and explicit interpreter overrides.
- Pipeline mastering: a legitimate MP3 boundary case in Apple Cider initially decoded 46 extra samples and failed the exact-frame guard. The import agent removed the final single sample from both private stems, documented the adjustment, and verified matching decoded output; original files were retained. The general encoder-padding/frame-count issue is **not fixed in application code** and could affect future raw imports. Investigate it without weakening stem synchronization or silently changing every source.
- Pronunciation: the optional scorer hook was tested with fake scorers; real model warm-up, scores, and the practice screen still need end-to-end verification. The older `live_scoring.json` fixtures cover the legacy live engine, not the current TypeScript SPEC port.
- ML B: add an exact-half rounding fixture to `contracts/fixtures`; TypeScript's half-even behavior currently has only its local rounding test.
- `CLAUDE.md` current-status text is stale. Refresh after user confirmation, in its own small PR.
- Ask DrewV2 what still needs porting from `origin/ml/pipeline` before deleting it. The earlier assessment found stale/conflicting code plus possible `/catalog` and `reference_unavailable` changes; recheck before acting. Do not send a message without authorization.

## User checks and deployment

- Listen to/review the eight real-song imports, checking lyric/phrase endings and held notes, translations, exclusions, octave choices and stem quality. The two original short clips are archived rather than active review targets. Passing decode/schema/browser checks does not establish timing accuracy by ear; keep review corrections alongside local assets.
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

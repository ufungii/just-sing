# Task 2: song author tool — teammate handoff

The baseline review app is complete and merged through [PR #17](https://github.com/ufungii/just-sing/pull/17). This document records its original acceptance requirements. Current setup and features are in [author/README.md](../author/README.md). Later local work adds raw-audio preparation jobs, a full-screen crop workspace and live drag placement; source downloads and individual note/octave editing remain future work.

## App boundary and reusable code

- Give `author/` its own frontend build and small Python server, bound only to `127.0.0.1`.
- Do not mount it under `api/`, add production routes, or expose it through the existing app's tunnel.
- Read prepared songs from gitignored `ml/data/<song-id>/`; keep copyrighted lyrics/audio and review outputs out of tracked files.
- Import the shared timeline directly from `web/src/components/timeline/ClipTimeline.tsx`. Its API is documented in `web/src/components/timeline/README.md`.
- The shared component already supplies timed lyric/phrase blocks, range handles, a playhead, and line-click callbacks. Waveform/pitch overlays and dragging lyric blocks remain author-tool work; extend the component without breaking the player.

## Review screen

- Show the vocal waveform with the reference pitch contour over it.
- Show **original text and romanization together** in the line list, timeline blocks, and selected-line details. Keep the translation box available.
- Play vocals, instrumental, or both; share one playhead and clip-relative clock. Clicking a line jumps to it.
- Edit original lyric text, line times, phrase boundaries (including sustained note ends), excluded regions, and per-line translations.
- Offer tap-to-sync: play vocals and press a key at each line entrance. Allow dragging afterward to fine-tune, with snapping to voiced onsets in the reference contour.

## Duet line distribution

- Select one or more lyric lines and assign **Player 1** or **Player 2**. Show player labels and colors together.
- Assign all scored phrases of a selected line together. Lines without scored phrases need no scoring owner.
- Show the complete distribution before playback and allow listening across singer transitions.
- Authored assignments override the default blocks of three scored lyric lines. Any authored player sequence is allowed, including consecutive sections for the same player.
- Store ownership by stable phrase IDs and player slots; derive timing from the existing phrases. Do not duplicate lyric text, timing, or player display names in the arrangement.
- Validate known phrase IDs, unique section IDs, complete and unique scored-phrase coverage, chronological sections, and no lyric line split between owners/sections. Display missing or conflicting assignments clearly.

The continuous multiplayer runtime merged through PR #15 and its browser verification through PR #16. The PR #17 author tool saves assignments and emits them through Rebuild using the optional top-level field below:

```json
{
  "duet_sections": [
    {"id": "section-1", "slot": 0, "phrase_ids": ["phrase-a", "phrase-b"]},
    {"id": "section-2", "slot": 1, "phrase_ids": ["phrase-c"]}
  ]
}
```

Slots `0` and `1` are labelled Player 1 and Player 2 in the editor. These placeholder IDs illustrate structure only. The field is optional; existing manifests remain loadable without it. Legacy arrangements default to alternating groups of three scored lyric lines.

## Save, rebuild, and review

- Explicit **Save** writes `corrections.json` and `song.review.json` next to the song. Make a `.bak` of each previous file on every save. No autosave.
- Provide in-memory undo/redo for edits and player assignments.
- Never directly edit `song.json` from the editor. **Rebuild** runs the manifest assembly step and applies saved corrections, including duet assignments, to the generated manifest.
- Preserve existing correction metadata and unrelated fields. The aligner already uses audio/text hashes and line anchors; do not replace its correction format with an incompatible editor-only object.
- **Mark reviewed** updates the review flag. Saving a correction does not by itself establish that timings were reviewed by ear.
- Ensure a rebuild preserves the saved text/timing, phrase boundaries, exclusions, translations, and part assignments.

Relevant code: `ml/pipeline/align_lyrics.py`, `ml/pipeline/manifest.py`, `ml/pipeline/romanize.py`, and `ml/pipeline/docs/WORKFLOW.md`. PR #17 includes correction/rebuild support for these author edits and duet fields.

## Acceptance checks

- Unit tests cover reading/writing corrections, preserving existing metadata, backups, and phrase ownership validation.
- A save→rebuild regression proves that timing corrections and player assignments survive.
- One Playwright smoke test loads a song, checks original/romanized display, selects lines, assigns a player, drags a line, and saves.
- Provide local setup/run instructions in `author/`.
- Sync accuracy, held-note boundaries, and exclusions are judged by listening. Passing tests must not claim those have been validated.

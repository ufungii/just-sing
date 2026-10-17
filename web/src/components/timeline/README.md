# Clip timeline

`ClipTimeline.tsx` is a controlled, audio-independent component, shared by the player and the future standalone author app. Import it directly from `web/src/components/timeline/ClipTimeline`.

- `duration`, `phrases: {id, start, end}[]`, and `lines: {start, end, text}[]` describe the full clip. All times are seconds from the original clip start.
- `range: {start, end} | null` controls the handles; `null` displays the full clip.
- `onChange(range)` receives snapped edits while dragging or using arrow/Home/End keys. Omit it to make the range read-only.
- `onCommit(range)` receives a completed pointer edit or a keyboard step. Persist here rather than on every pointer move.
- `playhead` draws the current clip time. `onSeek(time)` handles clicking a lyric line. Audio and the clock belong to the caller.
- `disabled` temporarily blocks range edits while a save is in progress.

`range.ts` exports the whole-phrase selection rule (including the API's 50 ms boundary tolerance), valid handle boundaries, nearest-boundary snapping, and a display label.

`PracticeRangePicker.tsx` is the player-specific wrapper: manifest loading, preview audio, phrase/second counts, full-clip reset, and room-save failure recovery. It stores a temporary drag value locally and restores the last server value if `onChange` returns a promise resolving to `false`.

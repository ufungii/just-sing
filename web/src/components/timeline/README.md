# Clip timeline

`ClipTimeline.tsx` is a controlled, audio-independent component, shared by the player and the standalone author app. Import it directly from `web/src/components/timeline/ClipTimeline`.

- `duration`, `phrases: {id, start, end}[]`, and `lines: {start, end, text}[]` describe the full clip. All times are seconds from the original clip start.
- `range: {start, end} | null` controls the handles; `null` displays the full clip.
- `onChange(range)` receives snapped edits while dragging or using arrow/Home/End keys. Omit it to make the range read-only.
- `onCommit(range)` receives a completed pointer edit or a keyboard step. Persist here rather than on every pointer move.
- `playhead` draws the current clip time. `onSeek(time)` handles clicking a lyric line. Audio and the clock belong to the caller.
- `disabled` temporarily blocks range edits while a save is in progress.

`range.ts` exports the whole-phrase selection rule (including the API's 50 ms boundary tolerance), valid handle boundaries, nearest-boundary snapping, and a display label.

`PracticeRangePicker.tsx` is the player-specific wrapper: manifest loading, preview audio, phrase/second counts, full-clip reset, and room-save failure recovery. It stores a temporary drag value locally and restores the last server value if `onChange` returns a promise resolving to `false`.

## Author extensions

Optional `overlay`, `onLineSelect`, `onLineMove`, `selectedLines`, and
`lineLabels` props support the standalone local reviewer. Author mode displays
original and romanized text together and emits a line index/new start on drag
release. It leaves validation, onset snapping, audio and persistence to the
caller. Existing practice-range callers retain their phrase-snapped handles.

`onLineMovePreview(index, start)` returns `{start, end, valid}` for a tentative
placement. The dragged block follows that placement, highlights invalid moves,
and leaves an origin ghost. Only valid releases call `onLineMove`; Escape or
pointer cancellation discards the preview. Near an edge, lyric dragging scrolls
the timeline automatically.

`pixelsPerSecond` controls zoom, `scrollToTime: {time, token}` requests navigation,
`followPlayhead` follows playback, and `onViewportChange` reports the visible
range after scrolling, zooming or resizing. Author callers can enable
`freeBoundaries` for precise range endpoints; player defaults remain whole phrases.

## Full-screen workspace

`CropWorkspace.tsx` supplies the modal overview/detail workspace, lyric search,
zoom, time fields, playhead boundary buttons and preview controls. Original and
romanized lyrics appear together. Callers own preview audio and persistence.
Player `onApply` saves a temporary practice range and can return `false` to keep
the workspace open after a failed save. Read-only online guests can browse and
preview. Author callers provide line-editing callbacks, an `editor` slot and
`onSaveClip` for creating a separate portable clip; this action is not offered
to players. Optional precomputed `peaks` avoid decoding audio again; otherwise
`waveformUrls` are tried in order to generate a compact waveform.

The player workspace uses `PracticeSectionView.tsx`: large original/romanized
lyrics above a waveform bar, a white current lyric, pink included lyrics, and
explicit START/END markers on the selected lines. Scrubbing or clicking a lyric
updates the current line and scrolls it into view. Dragging the pink handles
updates phrase-snapped selection highlighting immediately. Zoom, lyric search,
precise time fields and read-only guest browsing remain available. The author
workspace retains its detailed timing/editing layout.

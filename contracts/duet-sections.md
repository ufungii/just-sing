# Optional duet arrangement

Song manifests may include `duet_sections`, an ordered array of `{id, slot, phrase_ids}`. `slot` is `0` (Player 1)
or `1` (Player 2). Sections reference existing phrase IDs; never duplicate lyric text, timing, or display names.
`contracts/duet-song.example.json` and `api/catalog/duet-demo/song.json` are original synthetic examples.

Validation requires unique section IDs, nonempty phrase lists, exactly one owner for every known phrase,
chronological phrase/section order, nonoverlapping section times, and all phrases of each lyric line in one
section. Arbitrary authored ownership sequences are valid, including consecutive sections for the same player
or starting with Player 2. A multiplayer run additionally needs scoreable reference frames for both slots.

Omitting the field (or using null) preserves legacy song loading. Runtime fallback groups three scored lyric
lines at a time in chronological order, alternating slots 0, 1, 0, etc. Lines without phrases do not consume a
slot in the grouping. Practice ranges filter the authored/fallback sections without renumbering their slots.
A range leaving either player without a scoreable part is rejected.

The author tool saves selected-line assignments through corrections and emits this field on Rebuild; see
[the author-tool handoff](../docs/author-tool-handoff.md). Runtime loading does not implement that pipeline step.
Bump the manifest version when changing arrangement or timing. Match attempts freeze their arrangement,
shared practice range, and scheduled start so later manifest edits cannot reinterpret accepted results.

Score/history `duet: true` identifies assigned-part multiplayer. `range` is null for a full-song duet; a player's
assigned subset is never treated as a practice range. When practicing a section, both scores carry the same
shared normalized range while each result contains only the owning player's phrase IDs.

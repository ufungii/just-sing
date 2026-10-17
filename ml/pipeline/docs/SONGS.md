# Prepared songs and review notes

## Fixed continuous-1v1 arrangements

All thirteen local songs and demos now have explicit `duet_sections`, replacing
the legacy three-line fallback. Full-song handoffs use saved stanza/verse,
pre-chorus and chorus boundaries; short intro/ad-lib blocks are merged where
appropriate. Each scored line belongs to one singer, with stable ownership
across replays and practice-range filtering. Short demos confined to one section
use a saved whole-line midpoint handoff so both singers have scored phrases.

`DUET_HANDOFFS.json` in each preparation lists the exact timed assignments.
`ml/data/duet-arrangements-2026-10-17/` preserves the prior manifests and plans.
New manifest versions require refreshed demo fingerprints and a new match;
existing matches keep their original frozen arrangements. Lyrics, reference
pitch, audio and scoring math are unchanged by this ownership update. Musical
section labels and the underlying draft timing still require listening review.
The local `ml/data/handoff/fixed-1v1-arrangements-2026-10-17.zip` contains all
26 current manifests, saved plans and matching demo fingerprints. It updates
metadata only; preserve each preparation's existing MP3 pair and restart the API.

## Catalog timing audit — 2026-10-17

All thirteen full songs and their thirteen existing demos passed decoded audio
length, ordered line/word bounds, parent-to-demo timing, API streaming and
scoring sanity checks. Vocal excerpts from every demo were checked with
unprompted ASR; problem sections also used longer probes and selected video
frames. ASR failed to establish matching entrances in some singing excerpts,
so this is not a complete listening review or a timing-accuracy measurement.

Recording-specific corrections adjust 38 entrances: Party in the U.S.A. (17),
Soda Pop (13), Love (4), and Last Christmas (4). Their full manifests are v2;
three affected demos are v2 with regenerated fingerprints. Love's demo timing
and manifest are unchanged. Every selected MP3 is unchanged. Cached acoustic
realignment supplies word highlights inside the corrected windows.

Local evidence, prior drafts and remaining review flags are under
`ml/data/timing-audit-2026-10-17/`. The updated eight-folder handoff is
`ml/data/handoff/karaoke-timing-review-2026-10-17.zip`; it supersedes these four
songs' folders in older local archives. Keep it outside Git. Source cues used
for corrections cannot independently validate them, and all preparations remain
drafts pending listening review, including sustained notes and repeated ad-libs.

## Draft demo lyric fingerprints

The thirteen local 30-second `*-demo` preparations have
`lyric_fingerprints.npz`, generated from their current draft manifests and
selected vocal stems using ML B's lyric-match 0.1.0 implementation. Full-song
versions were intentionally skipped. `lyric_fingerprints.provenance.json`
records the input manifest/vocal hashes, line-timing hash and source commit.
These files do not freeze timings or mark a preparation reviewed: regenerate
after timing review or any lyric, timing or selected-vocal change.

`ml/data/handoff/demo-lyric-fingerprints.zip` contains these derived files,
provenance, and matching draft manifests for the team. Keep it outside Git,
and check that its input hashes match the clip assets before using it. Prioritize
listening review of the demo clips rather than the full-song versions.

## Additional local songs

The following songs use the same original htdemucs vocal estimate and enhanced
fine-tuned residual instrumental recipe. Each local folder contains matching
`song.json`, `song.review.json`, `vocals.mp3`, and `instrumental.mp3` files;
the corresponding `-demo` folder contains a matching 30-second crop.

| Folder | Title | Artist | Selected YouTube video |
| --- | --- | --- | --- |
| `love-keyshia-cole` | Love | Keyshia Cole | `YKuHdOxj46I` |
| `party-in-the-usa` | Party in the U.S.A. | Miley Cyrus | `vA2Lc9c3qN0` |
| `soda-pop` | Soda Pop | Saja Boys | `_uu_izpVSEc` |
| `last-christmas` | Last Christmas | Wham! | `KhqNTjbQ71A` |
| `zombie` | Zombie | DAY6 | `TnRdJcrCt6c` |
| `crazy` | CRAZY | LE SSERAFIM | `zRZHpWxCcYs` |
| `what-is-love` | What is Love? | TWICE | `ipOih_lghwo` |
| `surf` | Surf | NCT WISH | `rDHm-6UvUVE` |

English songs use `--language en`; their singing phrases remain available while
Korean pronunciation exercises are disabled. Soda Pop retains Korean-only
practice lines. Acoustic timestamps, stems, reference pitch, and translations
remain drafts requiring listening review. `QUALITY_HANDOFF.json`,
`INSPECTOR_REPORT.json`, and `TIMING_CROSSCHECK.json` record local checks.

For the selected Last Christmas recording, the user chose to trim unsupported
extended outro lyrics from the active timeline. All 88 supplied lines remain in
`lyrics.supplied.txt`; `lyrics.active.txt` contains 67 active lines and
`lyrics.unsupported-outro.txt` preserves the other 21. `OUTRO_REVIEW.json` records
the selection, and audio/text-bound `corrections.json` preserves alignment windows.
This decision is based on source comparisons and an automatic transcription,
with listening review still pending. These lyric-bearing files stay outside Git.

Zombie uses all 48 supplied lines / 203 words, preserving nine section breaks.
The initial acoustic entrances compared against 48 matching LRCLIB cues show a
median recording offset of 0.822 s and median absolute deviation of 0.075 s.
Source cues plus that offset anchor the display lines; acoustic realignment
places the words within those windows. Audio/text-bound corrections preserve
this choice, including the four early entrances flagged in the initial draft.
The post-adjustment source comparison is a consistency check, not independent
validation. Stems, sustained-note ends, reference pitch and draft translations
still require listening review.

CRAZY preserves all 82 supplied lines in `lyrics.supplied.txt` and uses 79 active
lines / 336 words. The user approved omitting three repeated Crazy lines before
the final Act phrase because they are absent from the selected recording.
`lyrics.active.txt`, `lyrics.omitted.txt`, and `LYRIC_SELECTION.json` record that
choice. Repeated chants needed bounded acoustic realignment; external final
chorus cues alone did not match this recording. The original draft, video-frame
inspection and automatic waveform-repeat diagnostics remain local evidence.
Repeat-derived Da windows and word highlights are provisional, with listening
review still required. Both full-song and 30-second demo folders include the
original vocal guide and enhanced instrumental on the same decoded timeline.

Local team handoffs are `ml/data/handoff/zombie-karaoke.zip` and
`ml/data/handoff/crazy-karaoke.zip`. Each archive includes the full-song and
30-second demo folders with matching JSON, MP3s, review state and diagnostics.
Copy those folders into a teammate's `ml/data/` directory and restart their API
to refresh song selection. Pulling Git alone does not install these local assets;
share the archives separately and keep their contents out of the public repo.

What is Love? retains all 64 supplied lines / 323 words; Surf retains all 54
lines / 266 words. Both preserve the supplied section breaks, Korean-only
practice lines, deterministic romanization and draft English translations.
Acoustic alignment was checked against matching lyric timestamps and selected
video frames. Audio/text-bound corrections adjust the intro and repeated
chorus/outro windows; the initial drafts remain under `alignment/history/`.
Agreement with a source used for corrections is a consistency check, not
independent validation. Surf's third display-line entrance remains flagged for
listening review, alongside word highlights, stems and pitch in both songs.

Their 30-second demos start at 44.36 s (What is Love?) and 71.58 s (Surf).
`ml/data/handoff/what-is-love-and-surf-karaoke.zip` contains the four matching
full-song/demo folders, JSON, MP3s and draft demo lyric fingerprints. Keep the
archive and its lyric-bearing contents outside Git.

## Selected audio

Russian Roulette uses:

- `ml/data/russian-roulette/vocals.mp3`: original htdemucs vocal estimate, without enhancement filters.
- `ml/data/russian-roulette/instrumental.mp3`: the improved residual instrumental selected by the user.

Both decode to 9,332,736 stereo samples at 44.1 kHz (211.626667 seconds).
`preparation.json` contains the active paths, provenance, hashes, and review status.
Cleanup copies the selected exports without re-encoding, preserving their sound.

Downloaded source audio, intermediate WAVs, comparison clips, older exports,
and synthetic test audio are removed during cleanup. Historical JSON reports
remain as evidence; their old paths are historical, not active references.
Model caches, virtual environments, and reusable scripts remain installed.
Decode the selected MP3s to temporary PCM for analysis. Repeating separation
requires downloading the source again; its URL and hash remain in metadata.
All song audio, lyric files, and model caches stay in gitignored `ml/data/`.

How Sweet by NewJeans is also prepared in `ml/data/how-sweet/`, with its own
`vocals.mp3` (original htdemucs estimate) and `instrumental.mp3` (mastered
fine-tuned residual). Choose it in the song picker or open
**http://127.0.0.1:8000/live/?song=how-sweet**.

Its selected source is `https://www.youtube.com/watch?v=KNqn_WuV2bE`. The initial
TJ Karaoke link was superseded because the sample appeared instrumental-only;
it is not the selected vocal/reference source. All 46 supplied lines match the
[studio timing source](https://lrclib.net/api/get/37129358) after normalization.
Ten independent ASR entrance matches indicate a recording offset of about 12 s
(median 11.99 s), with no meaningful tempo change detected. Fixed line anchors
therefore add 12 s, and the lyric region ends at 231 s before the video outro.
There are 406 timed words and eight supplied sections. The 20 ms reference has
12,411 frames; estimated intro/outro regions are excluded from scoring.

These are unreviewed preparation outputs. Acoustic word timing, melodic octave
errors, harmonies and the estimated boundaries still need listening review.
`corrections.json` preserves line entrances and section breaks; provenance and
the recording-offset diagnostic are retained alongside the prepared timeline.

Blood Sweat & Tears by BTS is prepared in `ml/data/blood-sweat-tears/` from
`https://www.youtube.com/watch?v=QFcJOvp5Cw0`, using the same original-vocal and
enhanced-instrumental recipe. It contains 49 supplied lines / 246 timed words
in 12 sections. The [matched line source](https://lrclib.net/api/get/942277)
includes explicit instrumental-break cues. Acoustic entrance checks support
keeping its original timing without a global offset; the estimated last lyric
ends at 202.50 s, before the recording ends. All timing remains unreviewed.
Preview: **http://127.0.0.1:8000/live/?song=blood-sweat-tears**.

## Song manifests

Love Language by TOMORROW X TOGETHER uses the same original-vocal and enhanced
residual-instrumental recipe in `ml/data/love-language/`. Its selected recording
is `https://www.youtube.com/watch?v=3Rm-_pp3Tjw`; the 52 user-supplied lyric lines
retain their 12 section breaks. Imported line anchors from
`https://lrclib.net/api/get/20856783` are checked against independent ASR and
paired with acoustic word alignment, deterministic romanization and English
translation drafts. The supplied text is preserved, including ad-libs.

Full-song preview: **http://127.0.0.1:8000/live/?song=love-language**.
The `love-language-demo` preparation uses 54.30–84.30 s of the parent recording.
Pitch, harmonies, sustained endings and translations remain unreviewed; the
manifest and review sidecar record that status. Vocal-guide and romanization
controls work through the existing song picker without special song code.

Love Scenario by iKON is prepared in `ml/data/love-scenario/` from
`https://www.youtube.com/watch?v=8pahVbnQhfA` with the same stem recipe. Its 54
supplied lyric lines, 191 words and 13 sections are preserved. The Hangul timing
source `https://lrclib.net/api/get/35017417` groups a few lines differently;
48 acoustic groups map its 49 cues back to the supplied text. Six internal line
entrances are resolved from word alignment rather than evenly spaced estimates.
Twenty nearby ASR entrance matches support the arrangement without applying a
global offset. Fixed opening/outro exclusions use the imported lyric cues.

Full-song preview: **http://127.0.0.1:8000/live/?song=love-scenario**.
The `love-scenario-demo` crop uses 66.62–96.62 s. Original vocals, enhanced
instrumental, romanization and English reading drafts use the existing playback
controls. Listening review of timing, held endings, harmonies and pitch remains
pending. The 50 Korean-only full-song lines qualify for spoken practice.

### Short demo handoff and text quality

The app demo assets are separate, exactly 30-second preparations:

| ID | Parent source window | Scoreable phrases |
| --- | --- | --- |
| `russian-roulette-demo` | 45.00–75.00 s | 11 |
| `how-sweet-demo` | 56.42–86.42 s | 5 |
| `blood-sweat-tears-demo` | 66.00–96.00 s | 5 |
| `love-language-demo` | 54.30–84.30 s | 9 |
| `love-scenario-demo` | 66.62–96.62 s | 9 |

Full songs are preserved. Each demo directory contains matching MP3s, a rebased
manifest/reference and review sidecar. Partial boundary lines are for display
only; their translations retain parent-line context and their practice/grading
is disabled. The cropper verifies exactly 1,323,000 decoded frames per stem.

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.crop --song russian-roulette --id another-demo --start 45 --duration 30
```

`practice_text` keeps the original whole line only when it contains Hangul and
no Latin letters. Mixed Korean/English and English-only lines get an empty
string; partial crop-boundary lines are also ineligible. This is
spoken-practice eligibility, not a pronunciation score. Original singing lyrics
and romanization remain available unchanged in the full songs.

All current full-song lines have English reading drafts in `translations.json`
and the manifests. These were assistant-generated from supplied lyrics, not
Gemini output, and have not been checked by a fluent reviewer. The translation
cache is text-hashed and reused on alignment reruns without overwriting existing
nonempty corrections. Gemini is not configured in this checkout.

Phrases require at least 0.5 s of voiced, non-excluded reference frames. Short or
empty phrases are listed in `song.review.json` and dropped from `phrases` while
their lines stay visible. Browser and backend scoring both use this phrase list.
The original three full-song manifests are v3 and their demo manifests v2 after
the whole-line practice fix. Love Language and Love Scenario start at full-song
v2 / demo v1.

**Still pending:** the teammate supplied four candidate backing-vocal ranges
from the contour (45.8–48.4, 50.0–51.3, 51.8–55.6 and 67.5–73.1 seconds of
Russian Roulette). The user has not listened yet. They remain recorded in
`ml/data/russian-roulette/reference.review.json` for review and have not been
applied as exclusions. Russian Roulette's backing/harmony cleanup still needs
listening review. No asset is marked reviewed.
The teammate's branch tools were fetched and copied into the gitignored
`ml/data/peer-tools/pitch-score/` directory, preserving local scoring code.
Prepared manifests are checked with the teammate's structural inspector; findings
and the source commit are in each song's `INSPECTOR_REPORT.json`. Warnings
remain about note duration and phrase coverage. These checks cannot confirm
the correct singer or pitch by ear.

The local-only `/api/demo-handoff` download contains the prepared demo packages
with manifests, audio and review notes. Do not confuse passing mechanical checks
with having completed the outstanding backing-vocal review.

Each prepared song now contains `song.json` with the exact top-level fields from
`contracts/song.example.json`: provenance, relative audio paths, timed lines and
romanization, phrases, reference Hz, display notes and excluded regions. The
reference is embedded, so this is the single-file ML handoff alongside its MP3s.
The existing shared contract is unchanged. Media and manifests remain gitignored.

`song.review.json` records review state and hashes separately. Current manifests
are drafts: phrases use lyric windows and notes are automatic pitch segments.
Neither those windows nor the imported timings establish reviewed held-note
boundaries. The API keeps generated draft manifests out of the reviewed-lyrics
endpoint; local preview still works. Hand-edited or reviewed manifests are not
overwritten. Existing human-reviewed lyric sidecars take priority when assembling.

New `ml.pipeline.run` preparations create manifests automatically. After changing
an existing song's timing corrections or reference, rebuild from cached data:

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.manifest --all
# Or: python -m ml.pipeline.manifest --id blood-sweat-tears
```

No separation or pitch inference is repeated by this command. Rebuilding is
allowed only for unchanged drafts created by this generator, protecting edits.
Explicit per-line `line_ends` in `corrections.json` preserve instrumental gaps;
the LRC exporter includes corresponding blank cues.


## Russian Roulette alignment history

Russian Roulette's recorded full-song alignment contains 73 lines / 231 words. These are acoustic
word estimates inside fixed line windows, not evenly distributed guesses. The
initial unconstrained alignment drifted within repeated choruses and is retained
under `alignment/history/`. The replacement uses normalized text matches to
[LRCLIB line timestamps](https://lrclib.net/api/get/33861377), with the four intro
entrances retained from the earlier acoustic draft. It remains unreviewed: 205
words have posterior below the diagnostic 0.2 threshold.
Speech alignment confidence is not a singing score. Listen and correct it.

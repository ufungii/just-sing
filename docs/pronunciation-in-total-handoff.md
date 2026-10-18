# Handoff: lyric check in the turn total (scoring 0.4.0)

Written 2026-10-17. PR 1 (this branch, `ml/pronunciation-in-total`) is the scoring math, shared fixtures and
the TypeScript port. **PR 2 is not started.** Nothing in the API or UI calls the new functions yet.

## The decision

The lyric check (`api/lyric_check.py`, `ml/pronunciation/lyric_match.py`) now counts toward the solo/battle/
online/duet total, mainly so that humming cannot win.

```
total = (0.7*pitch + 0.1*timing + 0.2*pronunciation) * (0.5 + 0.5*pronunciation/100)
```

- Per-line credit: `match` 100, `unclear` 0, `not_sung` 0, `not_covered` ignored; lines weighted by scoreable
  frames. `unclear` gets nothing on purpose: the checker grades a hum `unclear`, not `not_sung`.
- Checker unavailable (or no line covered): keep the old pitch/timing total, `pronunciation = null`, and say
  "lyrics not checked". A model failure never lowers a score.
- No phrase has an onset: pitch stands in for timing.
- Phrase scores and ratings stay 80% pitch / 20% timing. The **provisional** total shown before the check
  finishes is the existing 80/20 total. The final total uses 70/10/20 plus the guard, so it can move up or down
  from the provisional even with perfect lyrics.
- Weights, the 0.5 floor and the credit mapping are **unvalidated starting defaults** (`PronunciationConfig`).

## Honest limits

- `ml/pronunciation/LYRIC_MATCH.md` says the checker does **not** reliably reject real humming (a real hum
  matched 32/54 lines against 44/54 for sung words, in a best-case search). A hummer could land near 64, not 40.
  The fair test (hum along with the instrumental) is still to do. Do not claim the guard works until it is done.
- Real singing matched 89-96% of lines, from one singer.
- Honest takes lose points when the checker is unsure (one `unclear` line of two: a 65/80 take drops from 73.5 to 47.6).
- Never validated by a fluent Korean reviewer. The README must say so.

## Agreed scope for PR 2

1. The lyric check takes the `attempt_id`; the server stores `pronunciation` and recomputes the total with
   `apply_pronunciation`. The browser never sends a pronunciation value.
2. Results screen: provisional total first ("checking lyrics..."), then the final total; a third bar next to
   PITCH and TIMING labelled "Pronunciation", with a small "automated, not validated" note, and "—" when unavailable.
3. All modes: battle and online turns must record and upload the take too (`Sing.tsx` sets `take = null` for
   battle/online today). Duets check only each singer's own sections' lines.
4. Battle/rooms fairness: if either player's check is unavailable, score both with the old 80/20. Declare the
   winner only when both totals are final, with a timeout (~3 min) after which both fall back to 80/20.
5. Leaderboard: count final totals only, **and filter by `scoring_version`** (it does not today, so old
   pre-guard totals would sit on top for good).
6. Add `pronunciation` to `api/models.py` `Score` and a DB column + Alembic migration. Update the stale text that
   says the lyric check is "display only" (`api/lyric_check.py`, `api/models.py`, `web/src/lib/types.ts`).
7. Do not merge PR 1 before PR 2 (or bump nothing in prod): until the server uses it, rows would be stamped 0.4.0
   with a 0.3.0 total.
8. Not yet checked: the lyric check's `line_index` (from the fingerprints) matches the manifest phrases' `line_index`
   that `line_weights` keys on. Day 1 and `how-sweet-ytm` have no `lyric_fingerprints.npz`, so their check is
   unavailable until `python -m ml.pronunciation.lyric_match fingerprint` is run for them.

## Server setup already done (not in git)

On `app@just-sing.ink` (1.9 GB RAM was upgraded to 4 GB):
- `ffmpeg` installed with apt (practice and lyric-check uploads need it).
- The live venv was Python 3.11.0rc1, which lacks `sys.get_int_max_str_digits` and breaks transformers. A second
  venv `~/just-sing/.venv-new` runs uv-managed Python 3.11.17 with `api/requirements.txt`, CPU torch/torchaudio,
  transformers, librosa, soundfile, rapidfuzz, scipy.
- `/etc/systemd/system/just-sing.service` `ExecStart` points at `.venv-new/bin/uvicorn`; `.env` has
  `PRONUNCIATION_SCORER=1`.
- Measured: model load about 31 s, first assessment of a test tone 36 s, peak RSS 1.24 GB. No accuracy was measured
  on a real spoken recording through the live site.
- To disable: remove the `.env` line and restart `just-sing`; `/api/ready` then reports `unavailable`.

## Other findings from the review (not fixed here)

- `api/main.py` always mounts `/karaoke` (`api/local_demo.py`, `ml/scoring/live.py`): a second rubric with
  different bands, partly reachable on the public site. Breaks the "no second rubric" rule.
- FFmpeg decodes untrusted uploads before the one-at-a-time lock and with no format/protocol restriction
  (`api/practice.py` `_normalize`). Suspected, untested.
- Most API tests skip without `DATABASE_URL`; two tests call the unrestricted `cleanup_expired()` and could delete
  real rows if pointed at a real database. No CI config is tracked.
- `contracts` tests use Pydantic models without `extra="forbid"`, so contract drift passes silently.
- Leaderboard totals trust browser-submitted phrase values.

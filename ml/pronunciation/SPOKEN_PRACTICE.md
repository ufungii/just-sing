# Spoken Korean practice: integration check

Run the model with the existing speech environment; no training or model change is needed.
Keep expected text independent of its transcript. A lyric page or supplied manifest can
identify a candidate, but someone still needs to confirm what the recording was meant to say.

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ml/pronunciation/.venv/bin/python -m ml.evals.check_practice \
  /home/popchu/Downloads/love-language-speaking.wav \
  --expected-file ml/data/player_checks/expected.txt \
  --out ml/data/player_checks/practice-result.json
```

Create the UTF-8 `expected.txt` locally with the intended Korean phrase. The offline
flags use already-cached weights; omit them only when intentionally downloading models.
Do not commit recordings, actual song lyrics, or model weights.

The API requires `PRONUNCIATION_SCORER=1` at server startup and an environment with both
`api/requirements.txt` and `ml/pronunciation/requirements.txt` installed. That setting
warms the model and `/api/ready` reports whether the scorer attached. This task does
not change `.env`, restart a running server, or install API libraries into the speech
environment. The checker command above works without FastAPI or a database.

## Verified on 2026-10-17

- The supplied 8.39-second stereo/44.1 kHz recording decodes and produces word feedback
  with the cached Korean wav2vec2 CTC model. No lyric prompt was supplied to the
  independent Whisper transcription; its output was not used as expected text.
- A likely matching lyric was independently located, but the user has not confirmed
  the exact intended text. Numerical scores remain provisional.
- The actual upload handler normalized the real recording with FFmpeg, called
  `PronunciationScorer` in the speech environment, and returned HTTP 200 / `status: ok`
  with seven word confidences. Cold model subprocess plus normalization took about
  11.9 seconds on this run; this is not warm inference latency or a production SLA.
- This HTTP verification used FastAPI TestClient and an in-memory persistence stand-in.
  It exercised the real model through a subprocess to preserve separate dependency
  environments. Database writes, a running deployed server, and a real browser
  microphone session were not exercised. The detailed result and lyric candidate
  live only in gitignored `ml/data/player_checks/love-language-practice-http.json`.

## Fixes

- A singing phrase no longer requires Korean `practice_text` for catalog validation.
  English, mixed-language and disabled-practice lines can still be sung.
- Practice itself requires a Korean-only target. The API returns
  `422 practice_unavailable` before decoding/model inference, the browser hides
  unsupported lines, and an empty practice list explains how to pick another clip.
- The ML public scorer rejects unsupported target text and invalid nonfinite audio
  explicitly. No partial Korean grading of mixed-language text.
- Word chips show raw model confidence and identify the lowest-confidence word(s)
  for review. They no longer translate uncalibrated numbers into “Nice/Try again”
  pronunciation grades. There is no reliable percent-correct or phoneme diagnosis.

The singing score remains separate. Even successful speech feedback does not establish
reliable pronunciation grading on singing. Existing near-miss results and the lack
of a fluent reviewer still limit interpretation; see `ml/evals/results/pronunciation_nearmiss.md`.

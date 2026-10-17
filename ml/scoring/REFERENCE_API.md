# Reference extraction and local preview scoring

The offline pipeline calls `ml.scoring.pitch.reference_contour(audio, progress=...)`.
The implementation is shared with ML B's array-oriented `pitch_contour()`: 16 kHz input,
20 ms hops, 65–1000 Hz, chunked full CREPE, periodicity/RMS gates and median
smoothing. It returns the existing dictionary with Hz/null frames, periodicity,
backend and settings. Heavy model imports occur only inside extraction.

The extractor, configuration and pitch tests are copied unchanged from ML B's
published commit `0961eee`. The offline reference and eval extraction therefore
use the same chunking, RMS gate and smoothing path. The rest of ML B's scorer
and evaluation suite remains its separate workstream.

Run its pitch checks in the offline pipeline environment (with pytest installed):

```powershell
ml/pipeline/.venv/Scripts/python.exe -m pytest ml/scoring/tests/test_pitch.py -q
```

`live.py` and `web/live/scoring.js` are the matching, uncalibrated local-preview
baseline. Shared fixtures check parity, missing coverage, fixed register/latency,
rests and exclusions. Preview results remain provisional and are not saved
through the production match/result endpoints. This follow-up does not claim
human-validated singing accuracy or completed pronunciation integration.

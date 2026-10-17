"""Lyric check after a singing turn: did each sung line carry the right words?

The browser uploads the player's mic recording of the turn (placed on the clip clock, latency already
removed) plus `offset_s`, the time in the recording at which clip time 0 falls. The checker
(ml/pronunciation/lyric_match.py) compares each sung line with the original singer's same line using
per-song fingerprints made offline (ml/data/<song>/lyric_fingerprints.npz). Display only: it never
changes a score. Raw audio is deleted after the check and nothing is stored.

Same rules as the spoken-practice upload: FFmpeg normalization, blocking work in FastAPI's thread pool,
one model job at a time (the lock is shared with practice, which uses the same model), and
`unavailable` instead of a made-up result when the checker or the clip's fingerprints are missing.
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, Depends, File, Form, UploadFile

from . import practice
from .clip_catalog import CATALOG, SONG_DIR
from .errors import ApiError
from .models import LyricCheck, LyricLine
from .play import current_guest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MAX_BYTES = 12 * 1024 * 1024   # a 16 kHz mono WAV of a full 5-minute song is about 9.6 MB
MAX_SECONDS = 330.0
FINGERPRINTS = "lyric_fingerprints.npz"


class Checker(Protocol):
    version: str

    def check(self, wav: Path, fingerprints: Path, offset_s: float) -> list[dict]:
        """[{"line_index", "status"}] for every fingerprinted line. Raise on failure."""
        ...


class LyricMatchChecker:
    """Adapter over ml.pronunciation.lyric_match, imported only when attached (needs PyTorch)."""

    def __init__(self):
        from ml.pronunciation import lyric_match

        self._lm = lyric_match
        self.version = lyric_match.LYRIC_MATCH_VERSION
        self._cache: dict[Path, tuple[float, dict]] = {}

    def warmup(self) -> None:
        self._lm._model()

    def _fingerprints(self, path: Path) -> dict:
        mtime = path.stat().st_mtime  # reload if ML A regenerates the file while the server runs
        hit = self._cache.get(path)
        if not hit or hit[0] != mtime:
            self._cache[path] = (mtime, self._lm.load_fingerprints(path))
        return self._cache[path][1]

    def check(self, wav: Path, fingerprints: Path, offset_s: float) -> list[dict]:
        import soundfile as sf

        audio, sr = sf.read(str(wav), dtype="float32")
        result = self._lm.lyric_match(audio, sr, self._fingerprints(fingerprints), offset_s=offset_s)
        # gain/share stay in the server log for calibration; the UI only gets the status.
        log.info("lyric check: %s", result["summary"])
        return [{"line_index": r["line_index"], "status": r["status"]} for r in result["lines"]]


checker: Checker | None = None


def attach_checker() -> None:
    """Opt-in with the pronunciation scorer (PRONUNCIATION_SCORER=1): same environment, same model."""
    global checker
    if os.getenv("PRONUNCIATION_SCORER") != "1":
        return
    try:
        candidate = LyricMatchChecker()
        candidate.warmup()
        checker = candidate
    except Exception:
        log.exception("lyric checker could not start; lyric checks stay unavailable")


def fingerprint_path(clip_id: str) -> Path | None:
    path = SONG_DIR[clip_id] / FINGERPRINTS
    return path if path.is_file() else None


@router.post("/lyric-check", response_model=LyricCheck)
def lyric_check(clip_id: str = Form(), offset_s: float = Form(ge=-MAX_SECONDS, le=MAX_SECONDS),
                audio: UploadFile = File(), guest=Depends(current_guest)):
    if clip_id not in CATALOG:
        raise ApiError(404, "clip_not_found", f"No clip with id '{clip_id}'.")
    fingerprints = fingerprint_path(clip_id)
    if checker is None or fingerprints is None:
        return LyricCheck(clip_id=clip_id, status="unavailable")

    with tempfile.TemporaryDirectory() as d:  # deleted on success, error and timeout alike
        wav = practice._normalize(audio, Path(d), MAX_BYTES, MAX_SECONDS)
        if not practice._busy.acquire(blocking=False):
            raise ApiError(429, "pronunciation_busy", "The speech model is busy. Try again in a few seconds.", True)
        try:
            lines = [LyricLine(**r) for r in checker.check(wav, fingerprints, offset_s)]
            status = "ok"
        except Exception:  # details stay in the server log, not the response
            log.exception("lyric check failed")
            lines, status = [], "error"
        finally:
            practice._busy.release()
    return LyricCheck(clip_id=clip_id, status=status, lyric_match_version=checker.version, lines=lines)

"""Spoken-Korean practice upload. Audio is validated, normalized with FFmpeg, handed to a
pluggable scorer, and deleted. Raw audio is never stored; only structured word feedback is."""
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from .errors import ApiError
from .clip_catalog import CATALOG
from .models import Practice, WordFeedback
from .play import current_guest, get_db
from .tables import PracticeAttempt

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MAX_BYTES = 5 * 1024 * 1024
MAX_SECONDS = 15.0
LOCALE = "ko-KR"


class Scorer(Protocol):
    """Implemented by ml/pronunciation (ML A). Takes 16 kHz mono WAV plus the expected text and
    returns per-word scores 0-100. Raise on failure; never return a fake score."""
    provider: str

    def assess(self, wav: Path, expected_text: str) -> list[dict]: ...


scorer: Scorer | None = None  # None answers "unavailable"; attach_scorer() sets it when PRONUNCIATION_SCORER=1
_busy = threading.Lock()  # one assessment at a time, per CLAUDE.md


def attach_scorer() -> None:
    """Opt-in (PRONUNCIATION_SCORER=1): import and warm the local models. Called from startup, never at
    import, so the API starts without PyTorch. Any failure leaves the scorer unset ("unavailable")."""
    global scorer
    if os.getenv("PRONUNCIATION_SCORER") != "1":
        return
    try:
        from ml.pronunciation.api_scorer import PronunciationScorer
        candidate = PronunciationScorer()
        candidate.warmup()
        scorer = candidate
    except Exception:
        log.exception("pronunciation scorer could not start; practice stays unavailable")


def _run(args: list[str], timeout: int) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ApiError(422, "unsupported_audio", "Could not decode that audio. Try a short WAV, MP3, WebM or Ogg clip.")
    return r.stdout


def _normalize(upload: UploadFile, tmp: Path) -> Path:
    src = tmp / "upload"
    size = 0
    with src.open("wb") as f:
        while chunk := upload.file.read(64 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ApiError(413, "audio_too_large", f"Audio must be under {MAX_BYTES // 1024 // 1024} MB.")
            f.write(chunk)
    # Decode first, then measure the result: browser recordings (streamed WebM) carry no duration in
    # their header. Decoding stops just past the limit, so a long upload is cheap to reject.
    wav = tmp / "speech.wav"
    _run(["ffmpeg", "-nostdin", "-y", "-i", str(src), "-t", str(MAX_SECONDS + 1),
          "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], 30)
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)], 10)
    try:
        duration = float(out.strip())
    except ValueError:
        raise ApiError(422, "unsupported_audio", "Could not read the audio duration.")
    if duration > MAX_SECONDS:
        raise ApiError(422, "audio_too_long", f"Audio must be at most {MAX_SECONDS:.0f} seconds.")
    return wav


@router.post("/practice", response_model=Practice)
def practice(clip_id: str = Form(), phrase_id: str = Form(), audio: UploadFile = File(),
             guest=Depends(current_guest), s: Session = Depends(get_db)):
    song = CATALOG.get(clip_id)
    phrase = song and next((p for p in song.phrases if p.id == phrase_id), None)
    if not phrase:
        raise ApiError(404, "phrase_not_found", "Unknown clip or phrase.")
    expected = song.lines[phrase.line_index].practice_text
    if not expected.strip():
        raise ApiError(422, "phrase_not_practicable", "This line is available for singing only. Choose a Korean spoken-practice line.")

    provider, status, words, overall = (scorer.provider if scorer else "none"), "unavailable", [], None
    with tempfile.TemporaryDirectory() as d:  # deleted on success, error and timeout alike
        wav = _normalize(audio, Path(d))
        if scorer:
            if not _busy.acquire(blocking=False):
                raise ApiError(429, "pronunciation_busy", "The pronunciation scorer is busy. Try again in a few seconds.", True)
            try:
                words, status = [WordFeedback(**w) for w in scorer.assess(wav, expected)], "ok"
                overall = getattr(scorer, "last_overall", None)
            except Exception:  # provider details stay in the server log, not the response
                log.exception("pronunciation scorer failed")
                words, status, overall = [], "error", None
            finally:
                _busy.release()

    s.add(PracticeAttempt(guest_id=guest.id, clip_id=clip_id, phrase_id=phrase_id, locale=LOCALE,
                          provider=provider, status=status, words=[w.model_dump() for w in words]))
    s.commit()
    return Practice(clip_id=clip_id, phrase_id=phrase_id, locale=LOCALE, provider=provider,
                    status=status, overall=overall, words=words)

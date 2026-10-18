"""Lyric check after a singing turn: did each sung line carry the right words?

The browser uploads the player's mic recording of the turn (placed on the clip clock, latency already
removed) plus `offset_s`, the time in the recording at which clip time 0 falls. The checker
(ml/pronunciation/lyric_match.py) compares each sung line with the original singer's same line using
per-song fingerprints made offline (ml/data/<song>/lyric_fingerprints.npz). Display only: it never
changes a score. Raw audio is deleted after the check. Unlinked checks store nothing; multiplayer
checks keep only the model's line statuses on the saved attempt so both clients can display them.

Same rules as the spoken-practice upload: FFmpeg normalization, blocking work in FastAPI's thread pool,
one model job at a time (the lock is shared with practice, which uses the same model), and
`unavailable` instead of a made-up result when the checker or the clip's fingerprints are missing.
"""
import logging
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import play, practice
from .clip_catalog import CATALOG, SONG_DIR
from .errors import ApiError
from .models import LyricCheck, LyricLine, TurnLyrics
from .play import current_guest
from .tables import RoomMember

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MAX_BYTES = 12 * 1024 * 1024   # a 16 kHz mono WAV of a full 5-minute song is about 9.6 MB
MAX_SECONDS = 330.0
LINE_MAX_BYTES = 1024 * 1024   # one line plus margins: a few seconds of 16 kHz mono WAV
LINE_MAX_SECONDS = 30.0
LINE_WAIT_S = 20.0             # a line check waits this long for the shared model (a whole-take check holds it ~10 s), then answers busy
TAKE_YIELD_S = 15.0            # a whole-take check lets waiting line checks go first for at most this long
_lines_waiting = 0             # line checks currently waiting for the model
_lines_waiting_lock = threading.Lock()


def _yield_to_lines(max_s: float) -> None:
    """Let queued live line checks take the model before a whole-take check does (they feed the results screen)."""
    deadline = time.monotonic() + max_s
    while _lines_waiting and time.monotonic() < deadline:
        time.sleep(0.1)
FINGERPRINTS = "lyric_fingerprints.npz"


class Checker(Protocol):
    version: str

    def check(self, wav: Path, fingerprints: Path, offset_s: float, only: set[int] | None = None) -> list[dict]:
        """[{"line_index", "status"}] for every fingerprinted line (or only those in `only`). Raise on failure."""
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

    def check(self, wav: Path, fingerprints: Path, offset_s: float, only: set[int] | None = None) -> list[dict]:
        import soundfile as sf

        audio, sr = sf.read(str(wav), dtype="float32")
        result = self._lm.lyric_match(audio, sr, self._fingerprints(fingerprints), offset_s=offset_s, only=only)
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


def _lyric_turn(s, guest, attempt_id):
    match, attempt = play.lock_turn(s, attempt_id)
    play._owned_match(s, guest, match.id)
    if match.room_id and s.scalar(select(RoomMember.slot).where(
            RoomMember.room_id == match.room_id, RoomMember.guest_id == guest.id)) != attempt.slot:
        raise ApiError(403, 'not_your_seat', 'Only the assigned singer can check this recording.')
    if attempt.state != 'accepted':
        raise ApiError(409, 'attempt_not_finished', 'Save the singing result before checking its lyrics.')
    return match, attempt


@router.post('/turns/{attempt_id}/lyric-check', response_model=TurnLyrics)
def check_turn_lyrics(attempt_id: uuid.UUID, offset_s: float = Form(ge=-MAX_SECONDS, le=MAX_SECONDS),
                      audio: UploadFile = File(), guest=Depends(current_guest),
                      s: Session = Depends(play.get_db)):
    """Persist model feedback for both multiplayer clients, restricted to this singer's saved phrases.
    Audio is temporary. Score totals, ratings and the winner are never modified."""
    match, attempt = _lyric_turn(s, guest, attempt_id)
    cached = play._lyrics(attempt)
    if cached and cached.status == 'ok':
        return cached
    song = play._frozen_song(match)
    phrase_ids = {p['phrase_id'] for p in attempt.phrase_results}
    only = {p.line_index for p in song.phrases if p.id in phrase_ids}
    fingerprints = fingerprint_path(song.id)
    # Inference can take a minute. Release the match/attempt locks before waiting for the model.
    s.rollback()
    result = TurnLyrics(status='unavailable')
    if checker is not None and fingerprints is not None:
        with tempfile.TemporaryDirectory() as d:
            wav = practice._normalize(audio, Path(d), MAX_BYTES, MAX_SECONDS)
            _yield_to_lines(TAKE_YIELD_S)
            if not practice._busy.acquire(timeout=LINE_WAIT_S):
                raise ApiError(429, 'pronunciation_busy', 'The speech model is busy. Try again shortly.', True)
            try:
                lines = [LyricLine(**r) for r in checker.check(wav, fingerprints, offset_s, only=only)
                         if r['line_index'] in only]
                result = TurnLyrics(status='ok', lyric_match_version=checker.version, lines=lines)
            except Exception:
                log.exception('multiplayer lyric check failed')
                result = TurnLyrics(status='error')
            finally:
                practice._busy.release()
    match, attempt = _lyric_turn(s, guest, attempt_id)
    # Re-read under the lock: a duplicate upload must not overwrite an already successful result.
    cached = play._lyrics(attempt)
    if cached and cached.status == 'ok':
        return cached
    attempt.phrase_results = [{**p, **({'_lyrics': result.model_dump()} if i == 0 else {})}
                              for i, p in enumerate(attempt.phrase_results)]
    s.commit()
    play.notify(s, match, 'lyrics_checked', attempt)
    return result


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


@router.post("/lyric-check/line", response_model=LyricCheck)
def lyric_check_line(clip_id: str = Form(), line_index: int = Form(ge=0),
                     offset_s: float = Form(ge=-MAX_SECONDS, le=MAX_SECONDS),
                     audio: UploadFile = File(), guest=Depends(current_guest)):
    """The live path: one lyric line, uploaded by the singing screen as soon as the line has been sung, so
    the results are ready when the song ends. `audio` is a short slice around the line and `offset_s` the
    time in that slice of clip time 0 (usually negative). Same comparison as the full-take check."""
    if clip_id not in CATALOG:
        raise ApiError(404, "clip_not_found", f"No clip with id '{clip_id}'.")
    fingerprints = fingerprint_path(clip_id)
    if checker is None or fingerprints is None:
        return LyricCheck(clip_id=clip_id, status="unavailable")

    with tempfile.TemporaryDirectory() as d:
        wav = practice._normalize(audio, Path(d), LINE_MAX_BYTES, LINE_MAX_SECONDS)
        # Lines arrive every few seconds during a song, so wait briefly for the model instead of failing.
        global _lines_waiting
        with _lines_waiting_lock:
            _lines_waiting += 1
        try:
            got = practice._busy.acquire(timeout=LINE_WAIT_S)
        finally:
            with _lines_waiting_lock:
                _lines_waiting -= 1
        if not got:
            raise ApiError(429, "pronunciation_busy", "The speech model is busy. Try again in a few seconds.", True)
        try:
            lines = [LyricLine(**r) for r in checker.check(wav, fingerprints, offset_s, only={line_index})]
            status = "ok"
        except Exception:
            log.exception("lyric line check failed")
            lines, status = [], "error"
        finally:
            practice._busy.release()
    # A line too short to grade (or not fingerprinted) comes back ok with no lines.
    return LyricCheck(clip_id=clip_id, status=status, lyric_match_version=checker.version, lines=lines)

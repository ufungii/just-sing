"""Coaching blurb: Gemini turns the already-final, measured numbers into 2-3 friendly sentences.
It runs after scoring and never changes a score, a rating or a winner. Failure is a normal
"unavailable" answer, not an error, and nothing is saved so the player can retry."""
import logging
import os
import uuid

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .errors import ApiError
from .play import _owned_match, current_guest, get_db
from .tables import TurnAttempt

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_BLURB_CHARS = 400


def build_prompt(score: dict, phrase_count: int) -> str:
    """Only measured numbers go in: no lyrics, no audio, no names."""
    lines = [f"  phrase {i + 1} of {phrase_count}: rating {p['rating']}, pitch {p['pitch']:.0f}/100, "
             f"timing {p['timing']:.0f}/100, sang {p['coverage'] * 100:.0f}% of it"
             for i, p in enumerate(score["phrases"])]
    register = {0: "the original key", 12: "one octave higher", -12: "one octave lower"}[score["register"]]
    return (
        "You are a warm, encouraging singing coach for a karaoke game. A player just finished a song "
        f"in {register}. Their measured results (0-100 scale):\n"
        f"  overall {score['total']:.0f}, pitch {score['pitch']:.0f}, timing {score['timing']:.0f}\n"
        + "\n".join(lines) +
        "\n\nWrite 2 or 3 short sentences of feedback. Praise the strongest part, name the weakest phrase "
        "by its number, and give one concrete tip for it. Use only the numbers above: do not invent "
        "details about the song, lyrics, voice or pronunciation, and do not mention scores that were not "
        "given. No lists, no emoji.")


def _generate(prompt: str) -> str:
    """One Gemini call. Raises on any problem; the caller turns that into 'unavailable'."""
    key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    r = httpx.post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": key}, timeout=10,
                   json={"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"temperature": 0.7, "maxOutputTokens": 400}})
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


@router.post("/turns/{attempt_id}/coach")
def coach(attempt_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    attempt = s.get(TurnAttempt, attempt_id)
    if not attempt:
        raise ApiError(404, "attempt_not_found", "No such attempt.")
    _owned_match(s, guest, attempt.match_id)
    if attempt.state != "accepted":
        raise ApiError(409, "attempt_not_scored", "There is no result to coach yet.")
    if attempt.coach_blurb:
        return {"status": "ok", "coach_blurb": attempt.coach_blurb}  # generated once, then cached
    if not os.getenv("GEMINI_API_KEY"):
        return {"status": "unavailable", "coach_blurb": None}
    prompt = build_prompt({"total": attempt.total, "pitch": attempt.pitch, "timing": attempt.timing,
                           "register": attempt.register, "phrases": attempt.phrase_results},
                          len(attempt.phrase_results))
    try:
        text = " ".join(_generate(prompt).split())[:MAX_BLURB_CHARS]
    except Exception as e:  # key, network, quota, bad response: all just "unavailable"
        log.warning("coach blurb failed: %s", type(e).__name__)  # never log the response or key
        return {"status": "unavailable", "coach_blurb": None}
    if not text:
        return {"status": "unavailable", "coach_blurb": None}
    # ponytail: two simultaneous requests may both call Gemini; the last write wins. Add a lock if cost matters.
    attempt.coach_blurb = text
    s.commit()
    return {"status": "ok", "coach_blurb": text}

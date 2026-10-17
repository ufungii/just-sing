"""Guest sessions and solo matches. A solo run is a match with one player slot; the browser
rates phrases locally and submits the final phrase results once, with an idempotency key."""
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .auth import verify_bearer
from .db import get_engine
from .errors import ApiError
from .clip_catalog import CATALOG
from .models import PhraseScore, Score
from .tables import Clip, GuestSession, Match, MatchPlayer, PracticeAttempt, TurnAttempt

router = APIRouter(prefix="/api")

SCORING_VERSION = "0.1.0"
GUEST_TTL = timedelta(days=int(os.getenv("GUEST_TTL_DAYS", "7")))
PITCH_WEIGHT = 0.8  # CLAUDE.md default, 80% pitch / 20% timing


def get_db():
    with Session(get_engine()) as s:
        yield s


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


ACCOUNT_TTL = timedelta(days=3650)  # logged-in accounts do not expire like guests


def _account_for(s: Session, sub: str) -> GuestSession:
    """Find or create the session row that belongs to an Auth0 user."""
    acct = s.scalar(select(GuestSession).where(GuestSession.auth0_sub == sub))
    if not acct:
        acct = GuestSession(display_name="Player", auth0_sub=sub, token_hash=_hash(secrets.token_hex(32)),
                            expires_at=datetime.now(timezone.utc) + ACCOUNT_TTL)
        s.add(acct)
        s.commit()
    return acct


def _cookie_guest(request: Request, s: Session) -> GuestSession | None:
    token = request.cookies.get("guest_token")
    return token and s.scalar(select(GuestSession).where(
        GuestSession.token_hash == _hash(token), GuestSession.expires_at > datetime.now(timezone.utc)))


def current_guest(request: Request, s: Session = Depends(get_db)) -> GuestSession:
    """A valid Auth0 bearer token wins; otherwise the guest cookie."""
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        return _account_for(s, verify_bearer(bearer[7:]))
    guest = _cookie_guest(request, s)
    if not guest:
        raise ApiError(401, "not_authenticated", "Create a guest session first (POST /api/guests).")
    return guest


class GuestIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


class MatchIn(BaseModel):
    clip_id: str


class BeginIn(BaseModel):
    register: int = Field(0, description="semitones: -12, 0 or 12")
    calibration_offset: float | None = None  # seconds, from the latency setup step


class ResultIn(BaseModel):
    phrases: list[PhraseScore]


@router.post("/guests")
def create_guest(body: GuestIn, response: Response, s: Session = Depends(get_db)):
    token = secrets.token_urlsafe(32)  # only the hash is stored
    guest = GuestSession(display_name=body.display_name, token_hash=_hash(token),
                         expires_at=datetime.now(timezone.utc) + GUEST_TTL)
    s.add(guest)
    s.commit()
    response.set_cookie("guest_token", token, httponly=True, samesite="lax",
                        secure=os.getenv("COOKIE_SECURE") == "1", max_age=int(GUEST_TTL.total_seconds()))
    return {"id": guest.id, "display_name": guest.display_name}


def _new_match(s: Session, guest: GuestSession, clip_id: str, previous: uuid.UUID | None = None):
    song = CATALOG.get(clip_id)
    if not song:
        raise ApiError(404, "clip_not_found", f"No clip with id '{clip_id}'.")
    if not s.get(Clip, (song.id, song.version)):
        raise ApiError(503, "catalog_not_seeded", "Clip metadata is missing; run python -m api.seed.")
    match = Match(guest_id=guest.id, mode="solo", clip_id=song.id, clip_version=song.version,
                  scoring_version=SCORING_VERSION, previous_match_id=previous)
    s.add(match)
    s.flush()
    s.add(MatchPlayer(match_id=match.id, slot=0, display_name=guest.display_name))
    s.flush()
    attempt = TurnAttempt(match_id=match.id, slot=0)
    s.add(attempt)
    s.commit()
    return {"match_id": match.id, "attempt_id": attempt.id, "scoring_version": SCORING_VERSION}


@router.post("/matches")
def create_match(body: MatchIn, guest=Depends(current_guest), s: Session = Depends(get_db)):
    return _new_match(s, guest, body.clip_id)


def _owned_match(s: Session, guest: GuestSession, match_id: uuid.UUID) -> Match:
    match = s.get(Match, match_id)
    if not match or match.guest_id != guest.id:  # same 404 for "missing" and "not yours"
        raise ApiError(404, "match_not_found", "No such match.")
    return match


@router.post("/matches/{match_id}/rematch")
def rematch(match_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    old = _owned_match(s, guest, match_id)
    return _new_match(s, guest, old.clip_id, previous=old.id)


@router.post("/turns/{attempt_id}/begin")
def begin_turn(attempt_id: uuid.UUID, body: BeginIn, guest=Depends(current_guest),
               s: Session = Depends(get_db)):
    attempt = s.get(TurnAttempt, attempt_id, with_for_update=True)
    if not attempt:
        raise ApiError(404, "attempt_not_found", "No such attempt.")
    _owned_match(s, guest, attempt.match_id)
    if body.register not in (-12, 0, 12):
        raise ApiError(422, "invalid_register", "register must be -12, 0 or 12.")
    if attempt.state not in ("pending", "started"):
        raise ApiError(409, "attempt_closed", "This attempt already has a result.")
    attempt.state, attempt.register = "started", body.register
    attempt.calibration_offset = body.calibration_offset
    s.commit()
    return {"attempt_id": attempt.id, "state": attempt.state}


def _score(match: Match, a: TurnAttempt) -> Score:
    return Score(mode="solo", clip_id=match.clip_id, clip_version=match.clip_version,
                 scoring_version=match.scoring_version, register=a.register, total=a.total,
                 pitch=a.pitch, timing=a.timing, phrases=[PhraseScore(**p) for p in a.phrase_results])


@router.post("/turns/{attempt_id}/result", response_model=Score)
def submit_result(attempt_id: uuid.UUID, body: ResultIn, idempotency_key: str = Header(max_length=64),
                  guest=Depends(current_guest), s: Session = Depends(get_db)):
    # Row lock: concurrent duplicate submissions queue here and see the accepted state.
    attempt = s.get(TurnAttempt, attempt_id, with_for_update=True)
    if not attempt:
        raise ApiError(404, "attempt_not_found", "No such attempt.")
    match = _owned_match(s, guest, attempt.match_id)
    if attempt.state == "accepted":
        if attempt.idempotency_key == idempotency_key:
            return _score(match, attempt)  # replay: same answer, nothing advances twice
        raise ApiError(409, "already_submitted", "This attempt already has a different result.")
    if attempt.state != "started":
        raise ApiError(409, "attempt_not_started", "Begin the attempt before submitting a result.")

    durations = {p.id: p.end - p.start for p in CATALOG[match.clip_id].phrases}
    if sorted(p.phrase_id for p in body.phrases) != sorted(durations):
        raise ApiError(422, "phrase_mismatch", "Results must cover each phrase of the clip exactly once.")

    # ponytail: stand-in for ml/scoring (empty today). Duration-weighted mean of phrase scores;
    # swap for the reference engine once ML B lands it. Ratings are stored as submitted.
    total_time = sum(durations.values())
    mean = lambda f: sum(f(p) * durations[p.phrase_id] for p in body.phrases) / total_time
    attempt.pitch, attempt.timing = mean(lambda p: p.pitch), mean(lambda p: p.timing)
    attempt.total = PITCH_WEIGHT * attempt.pitch + (1 - PITCH_WEIGHT) * attempt.timing
    attempt.phrase_results = [p.model_dump() for p in body.phrases]
    attempt.idempotency_key, attempt.state = idempotency_key, "accepted"
    attempt.completed_at = datetime.now(timezone.utc)
    match.state = "finished"  # solo has one slot, so the result finishes the match
    s.commit()
    return _score(match, attempt)


@router.get("/matches/{match_id}")
def get_match(match_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    match = _owned_match(s, guest, match_id)
    attempts = s.scalars(select(TurnAttempt).where(TurnAttempt.match_id == match.id)
                         .order_by(TurnAttempt.slot, TurnAttempt.attempt_number)).all()
    return {"id": match.id, "mode": match.mode, "clip_id": match.clip_id, "state": match.state,
            "previous_match_id": match.previous_match_id,
            "attempts": [{"id": a.id, "slot": a.slot, "state": a.state,
                          "score": _score(match, a) if a.state == "accepted" else None} for a in attempts]}


@router.get("/history")
def history(guest=Depends(current_guest), s: Session = Depends(get_db)):
    rows = s.execute(select(Match, TurnAttempt.total).join(TurnAttempt, TurnAttempt.match_id == Match.id)
                     .where(Match.guest_id == guest.id, TurnAttempt.state == "accepted")
                     .order_by(Match.created_at.desc())).all()
    return [{"match_id": m.id, "clip_id": m.clip_id, "created_at": m.created_at, "total": t}
            for m, t in rows]


@router.post("/auth/claim")
def claim_guest(request: Request, account=Depends(current_guest), s: Session = Depends(get_db)):
    """After login: attach this browser's guest history to the Auth0 account.
    Send both the bearer token and the guest cookie."""
    guest = _cookie_guest(request, s)
    if not account.auth0_sub:
        raise ApiError(401, "invalid_token", "Send the Auth0 bearer token with this request.")
    moved = False
    if guest and guest.id != account.id and not guest.auth0_sub:
        for table in (Match, PracticeAttempt):
            s.execute(update(table).where(table.guest_id == guest.id).values(guest_id=account.id))
        guest.expires_at = datetime.now(timezone.utc)  # the guest cookie is spent
        moved = True
    s.commit()
    return {"id": account.id, "claimed_guest_history": moved}


@router.get("/leaderboard")
def leaderboard(clip_id: str, s: Session = Depends(get_db)):
    """Best accepted total per logged-in player on a clip. Guests are not ranked."""
    rows = s.execute(
        select(GuestSession.display_name, func.max(TurnAttempt.total).label("best"))
        .join(Match, Match.guest_id == GuestSession.id).join(TurnAttempt, TurnAttempt.match_id == Match.id)
        .where(Match.clip_id == clip_id, TurnAttempt.state == "accepted", GuestSession.auth0_sub.is_not(None))
        .group_by(GuestSession.id).order_by(func.max(TurnAttempt.total).desc()).limit(20)).all()
    return [{"display_name": n, "total": t} for n, t in rows]

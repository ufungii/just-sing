"""Guest sessions and solo matches. A solo run is a match with one player slot; the browser
rates phrases locally and submits the final phrase results once, with an idempotency key."""
import hashlib
import logging
import math
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import auth
from .auth import verify_bearer
from .db import get_engine
from .errors import ApiError
from .clip_catalog import CATALOG
from .models import PhraseResultIn, PhraseScore, Score, TimeRange
from ml.scoring.config import SCORING_VERSION  # the one source of truth for the scoring version
from ml.scoring.pitch import to_track
from ml.scoring.score import finalize_turn, phrase_weights
from .tables import Clip, GuestSession, Match, MatchPlayer, PracticeAttempt, Room, RoomMember, TurnAttempt

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Called after a match change commits: hook(session, match, event, attempt_or_None). rooms.py registers
# one to broadcast to online players. A failing hook is logged and never fails the request.
match_hooks: list = []


def notify(s: Session, match: Match, event: str, attempt: TurnAttempt | None = None):
    for hook in match_hooks:
        try:
            hook(s, match, event, attempt)
        except Exception:
            log.exception("match hook failed")

# Scoring numbers (version, weights, rating bands) live only in ml/scoring/config.py (CLAUDE.md).
GUEST_TTL = timedelta(days=int(os.getenv("GUEST_TTL_DAYS", "7")))
TIE_DECIMALS = 1  # API-level battle rule, not scoring math: totals equal at this display precision are a tie
RECONNECT_GRACE = timedelta(seconds=int(os.getenv("RECONNECT_GRACE_SECONDS", "60")))


_weight_cache: dict[tuple[str, int], list[int]] = {}


def _weights(song) -> list[int]:
    """Scoreable reference frames per phrase, from the server's own manifest (never from the client).
    Cached per clip version; rests and excluded regions have no weight."""
    key = (song.id, song.version)
    if key not in _weight_cache:
        _weight_cache[key] = phrase_weights(
            to_track(song.reference.hz), [(p.id, p.start, p.end) for p in song.phrases],
            hop_seconds=song.reference.hop_seconds, excluded=[(e.start, e.end) for e in song.reference.excluded])
    return _weight_cache[key]


RANGE_EPS = 0.05  # seconds of slack when matching phrase edges to the requested range


def _included(song, rng: TimeRange | None) -> list:
    """Phrases scored in this turn: all of them, or those fully inside [start, end] (within RANGE_EPS)."""
    if rng is None:
        return list(song.phrases)
    if not (math.isfinite(rng.start) and math.isfinite(rng.end) and 0 <= rng.start < rng.end <= song.duration):
        raise ApiError(422, "invalid_range", "range must satisfy 0 <= start < end <= clip duration.")
    inc = [p for p in song.phrases if p.start >= rng.start - RANGE_EPS and p.end <= rng.end + RANGE_EPS]
    if not inc:
        raise ApiError(422, "invalid_range", "range must fully contain at least one phrase.")
    return inc


def _range_of(song, ids) -> TimeRange | None:
    """Normalized range of a finished attempt, derived from the phrases it scored; null for the full clip."""
    ids = set(ids)
    inc = [p for p in song.phrases if p.id in ids]
    if not inc or len(inc) == len(song.phrases):
        return None
    return TimeRange(start=min(p.start for p in inc), end=max(p.end for p in inc))


def _started_range(attempt: TurnAttempt) -> TimeRange | None:
    """The range frozen at begin. A started attempt keeps it in phrase_results as {"range": {...}}
    (no migration); accepting the result replaces that with the phrase list."""
    pr = attempt.phrase_results
    return TimeRange(**pr["range"]) if isinstance(pr, dict) and pr.get("range") else None


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
        # Insert-or-nothing: if a parallel request created the row first, the unique index makes this a
        # no-op and the select below finds that row.
        s.execute(pg_insert(GuestSession).values(
            id=uuid.uuid4(), display_name="Player", auth0_sub=sub, token_hash=_hash(secrets.token_hex(32)),
            expires_at=datetime.now(timezone.utc) + ACCOUNT_TTL,
        ).on_conflict_do_nothing(index_elements=["auth0_sub"], index_where=text("auth0_sub IS NOT NULL")))
        s.commit()
        acct = s.scalar(select(GuestSession).where(GuestSession.auth0_sub == sub))
    return acct


def _cookie_guest(request: Request, s: Session) -> GuestSession | None:
    token = request.cookies.get("guest_token")
    return token and s.scalar(select(GuestSession).where(
        GuestSession.token_hash == _hash(token), GuestSession.expires_at > datetime.now(timezone.utc)))


def current_guest(request: Request, s: Session = Depends(get_db)) -> GuestSession:
    """A valid Auth0 bearer token wins; otherwise the guest cookie."""
    bearer = request.headers.get("authorization", "")
    # With Auth0 unconfigured a bearer header cannot be honoured, so fall through to the guest cookie.
    if bearer.lower().startswith("bearer ") and auth.configured():
        return _account_for(s, verify_bearer(bearer[7:]))
    guest = _cookie_guest(request, s)
    if not guest:
        raise ApiError(401, "not_authenticated", "Create a guest session first (POST /api/guests).")
    return guest


class GuestIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


class MatchIn(BaseModel):
    clip_id: str
    players: list[str] | None = Field(None, min_length=2, max_length=2)  # two names = local battle


class BeginIn(BaseModel):
    register: int = Field(0, description="semitones: -12, 0 or 12")
    calibration_offset: float | None = None  # seconds, from the latency setup step
    range: TimeRange | None = None  # practice section, solo only; omitted = full clip


class ResultIn(BaseModel):
    phrases: list[PhraseResultIn]
    guide_used: bool = False  # client-reported (not cheat-proof): guide vocals were audible during the turn


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


def require_clip(s: Session, clip_id: str):
    """The loaded song, or a 404 (unknown id) / 503 (not yet seeded into the database)."""
    song = CATALOG.get(clip_id)
    if not song:
        raise ApiError(404, "clip_not_found", f"No clip with id '{clip_id}'.")
    if not s.get(Clip, (song.id, song.version)):
        raise ApiError(503, "catalog_not_seeded", "Clip metadata is missing; run python -m api.seed.")
    return song


def _new_match(s: Session, guest: GuestSession, clip_id: str, names: list[str],
               previous: uuid.UUID | None = None, room_id: uuid.UUID | None = None):
    """Create a match and its first attempt. The caller commits, so it can join other changes."""
    song = require_clip(s, clip_id)
    match = Match(guest_id=guest.id, mode="online" if room_id else "solo" if len(names) == 1 else "local",
                  clip_id=song.id, clip_version=song.version, scoring_version=SCORING_VERSION,
                  previous_match_id=previous, room_id=room_id)
    s.add(match)
    s.flush()
    for slot, name in enumerate(names):
        s.add(MatchPlayer(match_id=match.id, slot=slot, display_name=name))
    s.flush()
    attempt = TurnAttempt(match_id=match.id, slot=0)  # later slots get theirs when the turn before is saved
    s.add(attempt)
    s.flush()
    return {"match_id": match.id, "attempt_id": attempt.id, "scoring_version": SCORING_VERSION}


@router.post("/matches")
def create_match(body: MatchIn, guest=Depends(current_guest), s: Session = Depends(get_db)):
    out = _new_match(s, guest, body.clip_id, body.players or [guest.display_name])
    s.commit()
    return out


def _owned_match(s: Session, guest: GuestSession, match_id: uuid.UUID) -> Match:
    """The creator, or either member of the match's room. Same 404 for "missing" and "not yours"."""
    match = s.get(Match, match_id)
    member = match and match.room_id and s.scalar(select(RoomMember.slot).where(
        RoomMember.room_id == match.room_id, RoomMember.guest_id == guest.id)) is not None
    if not match or not (match.guest_id == guest.id or member):
        raise ApiError(404, "match_not_found", "No such match.")
    return match


@router.post("/matches/{match_id}/rematch")
def rematch(match_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    old = _owned_match(s, guest, match_id)
    if old.room_id:
        raise ApiError(409, "use_room_rematch", "Online matches are replayed from the room.")
    names = s.scalars(select(MatchPlayer.display_name).where(MatchPlayer.match_id == old.id)
                      .order_by(MatchPlayer.slot)).all()
    out = _new_match(s, guest, old.clip_id, list(names), previous=old.id)
    s.commit()
    return out


def lock_turn(s: Session, attempt_id: uuid.UUID) -> tuple[Match, TurnAttempt]:
    """Lock order for every turn action: the match row first, then the attempt row. One fixed order
    means concurrent begin/submit/retry/recovery queue up instead of deadlocking."""
    match_id = s.scalar(select(TurnAttempt.match_id).where(TurnAttempt.id == attempt_id))
    if match_id is None:
        raise ApiError(404, "attempt_not_found", "No such attempt.")
    match = s.get(Match, match_id, with_for_update=True, populate_existing=True)
    attempt = s.get(TurnAttempt, attempt_id, with_for_update=True, populate_existing=True)
    return match, attempt


@router.post("/turns/{attempt_id}/begin")
def begin_turn(attempt_id: uuid.UUID, body: BeginIn, guest=Depends(current_guest),
               s: Session = Depends(get_db)):
    match, attempt = lock_turn(s, attempt_id)
    _owned_match(s, guest, match.id)
    _check_turn(s, guest, match, attempt)
    if body.register not in (-12, 0, 12):
        raise ApiError(422, "invalid_register", "register must be -12, 0 or 12.")
    if attempt.state not in ("pending", "started"):
        raise ApiError(409, "attempt_closed", "This attempt already has a result.")
    song = _frozen_song(match)
    if body.range is not None and match.mode != "solo":
        raise ApiError(422, "invalid_range", "A practice range is only supported in solo matches.")
    inc = _included(song, body.range)
    rng = _range_of(song, [p.id for p in inc]) if body.range else None  # normalized to whole phrases
    if attempt.state == "started":  # a repeated begin never extends the deadline or changes register/range
        if body.register != attempt.register or rng != _started_range(attempt):
            raise ApiError(409, "attempt_already_started", "This turn already started with another register or range.")
        return {"attempt_id": attempt.id, "state": attempt.state}
    now = datetime.now(timezone.utc)
    attempt.state, attempt.register = "started", body.register
    attempt.calibration_offset = body.calibration_offset
    attempt.phrase_results = {"range": rng.model_dump()} if rng else None
    # Past this deadline the attempt is treated as lost (tab closed, connection gone): see retention.
    attempt.started_at, attempt.deadline_at = now, now + timedelta(seconds=song.duration) + RECONNECT_GRACE
    s.commit()
    notify(s, match, "turn_started", attempt)
    return {"attempt_id": attempt.id, "state": attempt.state}


def _frozen_song(match: Match):
    """The manifest this match was created with. Only the current version is loaded, so a changed
    version is refused rather than graded against the wrong phrases."""
    song = CATALOG.get(match.clip_id)
    if not song or song.version != match.clip_version:
        raise ApiError(409, "clip_version_changed", "This clip was updated since the match began; start a new match.")
    return song


def _check_turn(s: Session, guest: GuestSession, match: Match, attempt: TurnAttempt):
    """Turns alternate: only the active slot's attempt may move. In a room, only that seat's guest."""
    if match.state != "active" or attempt.slot != match.active_slot:
        raise ApiError(409, "not_your_turn", "It is not this player's turn.")
    if match.room_id and s.scalar(select(RoomMember.slot).where(
            RoomMember.room_id == match.room_id, RoomMember.guest_id == guest.id)) != attempt.slot:
        raise ApiError(403, "not_your_seat", "Only the player whose turn it is can do that.")


def _guided(phrase_results) -> bool:
    """Stored as a flag on each saved phrase dict (no migration); old rows have none."""
    return bool(isinstance(phrase_results, list) and phrase_results and phrase_results[0].get("guided"))


def _score(match: Match, a: TurnAttempt) -> Score:
    song = CATALOG.get(match.clip_id)
    rng = _range_of(song, [p["phrase_id"] for p in a.phrase_results]) \
        if song and song.version == match.clip_version else None
    return Score(range=rng, guided=_guided(a.phrase_results), mode="solo" if match.mode == "solo" else "battle", clip_id=match.clip_id, clip_version=match.clip_version,
                 scoring_version=match.scoring_version, register=a.register, total=a.total,
                 pitch=a.pitch, timing=a.timing, phrases=[PhraseScore(**{"score": p.get("score", p["pitch"]), **p}) for p in a.phrase_results],
                 coach_blurb=a.coach_blurb)


@router.post("/turns/{attempt_id}/result", response_model=Score)
def submit_result(attempt_id: uuid.UUID, body: ResultIn, idempotency_key: str = Header(max_length=64),
                  guest=Depends(current_guest), s: Session = Depends(get_db)):
    # Row locks: concurrent duplicate submissions (and retries) queue here and see the latest state.
    match, attempt = lock_turn(s, attempt_id)
    _owned_match(s, guest, match.id)
    if attempt.state == "accepted":
        if attempt.idempotency_key == idempotency_key:
            return _score(match, attempt)  # replay: same answer, nothing advances twice
        raise ApiError(409, "already_submitted", "This attempt already has a different result.")
    if attempt.state == "invalidated":
        raise ApiError(409, "attempt_invalidated", "This attempt was replaced; start a new one.")
    if attempt.state != "started":
        raise ApiError(409, "attempt_not_started", "Begin the attempt before submitting a result.")
    _check_turn(s, guest, match, attempt)
    if attempt.deadline_at < datetime.now(timezone.utc):  # too late: same outcome as the recovery tick
        attempt.state, match.state = "invalidated", "retry_required"
        s.commit()
        notify(s, match, "retry_required")
        raise ApiError(409, "attempt_invalidated", "This turn ran out of time; start a new one.")

    song = _frozen_song(match)
    rng = _started_range(attempt)
    inc = _included(song, rng)
    if sorted(p.phrase_id for p in body.phrases) != sorted(p.id for p in inc):
        raise ApiError(422, "phrase_mismatch", "Results must cover each phrase of the clip (or chosen range) exactly once.")
    keep = {p.id for p in inc}

    # Reference engine (ml/scoring): ignores any client-claimed score or rating and recomputes phrase
    # scores, ratings and totals with weights from our own manifest copy.
    try:
        result = finalize_turn([p.model_dump() for p in body.phrases], [w for p, w in zip(song.phrases, _weights(song)) if p.id in keep],
                               expected_phrase_ids=[p.id for p in inc], register=attempt.register)
    except ValueError as e:
        raise ApiError(422, "invalid_result", str(e))
    attempt.pitch, attempt.timing, attempt.total = result["pitch"], result["timing"], result["total"]
    attempt.phrase_results = [{**p, "guided": body.guide_used} for p in result["phrases"]]
    attempt.idempotency_key, attempt.state = idempotency_key, "accepted"
    attempt.completed_at = datetime.now(timezone.utc)
    # Result and turn transition commit together: next player's attempt, or the match is finished.
    n_players = s.scalar(select(func.count()).select_from(MatchPlayer).where(MatchPlayer.match_id == match.id))
    if attempt.slot + 1 < n_players:
        match.active_slot = attempt.slot + 1
        s.add(TurnAttempt(match_id=match.id, slot=match.active_slot))
    else:
        match.state = "finished"
    s.commit()
    notify(s, match, "result_saved", attempt)
    return _score(match, attempt)


@router.get("/matches/{match_id}")
def get_match(match_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    return match_view(s, _owned_match(s, guest, match_id))


def match_view(s: Session, match: Match) -> dict:
    players = s.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match.id)
                        .order_by(MatchPlayer.slot)).all()
    attempts = s.scalars(select(TurnAttempt).where(TurnAttempt.match_id == match.id)
                         .order_by(TurnAttempt.slot, TurnAttempt.attempt_number)).all()
    totals = {a.slot: round(a.total, TIE_DECIMALS) for a in attempts if a.state == "accepted"}
    winner = None  # None = tie (or not finished)
    if match.state == "finished" and len(players) > 1 and len(set(totals.values())) > 1:
        winner = max(totals, key=totals.get)
    return {"id": match.id, "mode": match.mode, "clip_id": match.clip_id, "state": match.state,
            "active_slot": match.active_slot, "previous_match_id": match.previous_match_id,
            "players": [{"slot": p.slot, "display_name": p.display_name} for p in players],
            "winner_slot": winner,
            "attempts": [{"id": a.id, "slot": a.slot, "state": a.state,
                          "score": _score(match, a) if a.state == "accepted" else None} for a in attempts]}


@router.post("/matches/{match_id}/retry")
def retry_turn(match_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    """Replace a lost or abandoned turn with a fresh attempt. The old one is invalidated first, so a
    late submission from it cannot overwrite anything."""
    match = s.get(Match, match_id, with_for_update=True, populate_existing=True)  # match first, as lock_turn
    if match:
        _owned_match(s, guest, match_id)
    if not match or match.state not in ("active", "retry_required"):
        raise ApiError(409, "cannot_retry", "This match has no turn to retry.")
    last = s.scalars(select(TurnAttempt).where(TurnAttempt.match_id == match.id, TurnAttempt.slot == match.active_slot)
                     .order_by(TurnAttempt.attempt_number.desc()).limit(1)
                     .with_for_update().execution_options(populate_existing=True)).one()
    if last.state == "accepted":
        raise ApiError(409, "cannot_retry", "That turn already has a result.")
    last.state = "invalidated"
    match.state = "active"
    fresh = TurnAttempt(match_id=match.id, slot=match.active_slot, attempt_number=last.attempt_number + 1)
    _check_turn(s, guest, match, fresh)
    s.add(fresh)
    s.commit()
    notify(s, match, "retry", fresh)
    return {"attempt_id": fresh.id}


@router.get("/history")
def history(guest=Depends(current_guest), s: Session = Depends(get_db)):
    """One row per match with at least one saved result, newest first. `total` is the caller's own
    score: slot 0 in solo, their seat online, and null in a local battle (two singers, one laptop),
    where `players` carries both totals."""
    in_room = select(RoomMember.room_id).where(RoomMember.guest_id == guest.id)
    matches = s.scalars(
        select(Match).where(or_(and_(Match.room_id.is_(None), Match.guest_id == guest.id), Match.room_id.in_(in_room)),
                            Match.id.in_(select(TurnAttempt.match_id).where(TurnAttempt.state == "accepted")))
        .order_by(Match.created_at.desc()).limit(50)).all()  # ponytail: a few queries per row; fine for 50 rows
    rows = []
    for m in matches:
        names = dict(s.execute(select(MatchPlayer.slot, MatchPlayer.display_name).where(MatchPlayer.match_id == m.id)).all())
        totals = dict(s.execute(select(TurnAttempt.slot, TurnAttempt.total).where(
            TurnAttempt.match_id == m.id, TurnAttempt.state == "accepted")).all())
        own_slot = 0 if m.mode == "solo" else None
        if m.room_id:
            own_slot = s.scalar(select(RoomMember.slot).where(RoomMember.room_id == m.room_id, RoomMember.guest_id == guest.id))
        song = CATALOG.get(m.clip_id)
        pr = s.scalar(select(TurnAttempt.phrase_results).where(
            TurnAttempt.match_id == m.id, TurnAttempt.slot == own_slot, TurnAttempt.state == "accepted"))
        rng = _range_of(song, [p["phrase_id"] for p in pr]) if pr and song and song.version == m.clip_version else None
        rows.append({"match_id": m.id, "clip_id": m.clip_id, "mode": m.mode, "created_at": m.created_at,
                     "total": totals.get(own_slot), "range": rng, "guided": _guided(pr),
                     "players": [{"slot": k, "display_name": names[k], "total": totals.get(k)} for k in sorted(names)]})
    return rows


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
        # Rooms too: otherwise cleanup later deletes a room that the moved matches still point at.
        s.execute(update(Room).where(Room.host_guest_id == guest.id).values(host_guest_id=account.id))
        already_in = select(RoomMember.room_id).where(RoomMember.guest_id == account.id)
        s.execute(update(RoomMember).where(RoomMember.guest_id == guest.id, RoomMember.room_id.not_in(already_in))
                  .values(guest_id=account.id))
        guest.expires_at = datetime.now(timezone.utc)  # the guest cookie is spent
        if account.display_name == "Player":  # a new account takes the name the player already chose
            account.display_name = guest.display_name
        moved = True
    s.commit()
    return {"id": account.id, "claimed_guest_history": moved}


@router.get("/leaderboard")
def leaderboard(clip_id: str, s: Session = Depends(get_db)):
    """Best accepted total per logged-in player on the clip's current version. Only solo runs count:
    in a local battle the second singer is not the account owner. Guests are not ranked."""
    song = CATALOG.get(clip_id)
    if not song:
        return []
    rows = s.execute(
        select(GuestSession.display_name, func.max(TurnAttempt.total).label("best"))
        .join(Match, Match.guest_id == GuestSession.id).join(TurnAttempt, TurnAttempt.match_id == Match.id)
        .where(Match.clip_id == clip_id, Match.clip_version == song.version, Match.mode == "solo",
               TurnAttempt.state == "accepted", GuestSession.auth0_sub.is_not(None),
               # runs with the guide vocals audible are kept off the board (client-reported flag)
               func.coalesce(TurnAttempt.phrase_results[0]["guided"].astext, "false") != "true",
               # practice-section runs score a subset of phrases: not comparable, so full-clip results only
               case((func.jsonb_typeof(TurnAttempt.phrase_results) == "array",
                     func.jsonb_array_length(TurnAttempt.phrase_results)), else_=0) == len(song.phrases))
        .group_by(GuestSession.id).order_by(func.max(TurnAttempt.total).desc()).limit(20)).all()
    return [{"display_name": n, "total": t} for n, t in rows]

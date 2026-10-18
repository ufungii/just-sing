"""Online rooms for two guests. HTTP owns every durable action (create, join, ready, start, rematch);
the WebSocket carries presence, snapshots and provisional progress/ratings. State lives in Postgres,
so a restarted server or a reconnecting client recovers from a fresh snapshot."""
import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import logging

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import play
from .auth import verify_bearer
from .db import get_engine
from .errors import ApiError
from .models import TimeRange
from .clip_catalog import CATALOG
from .play import current_guest, get_db, match_view
from .tables import GuestSession, Match, MatchPlayer, Room, RoomMember, TurnAttempt

log = logging.getLogger(__name__)
router = APIRouter()

ROOM_TTL = timedelta(hours=2)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
MAX_MESSAGE_BYTES = 2048
MAX_VOICE_MESSAGE_BYTES = 16384  # SDP can exceed the small progress-message budget
MAX_MESSAGES_PER_SECOND = 30
HEARTBEAT_TIMEOUT = 45  # seconds of silence before a socket is dropped
JOINS_PER_MINUTE = 10
PASSWORD_MIN, PASSWORD_MAX = 3, 16
WRONG_PASSWORDS_PER_MINUTE = 5
LIST_LIMIT = 50


# ---- realtime hub: sockets and presence only, never durable state ----------------------------

def _event(type_: str, **fields) -> dict:
    return jsonable_encoder({"type": type_, "id": uuid.uuid4().hex, **fields})  # UUIDs/datetimes -> JSON


class Hub:
    def __init__(self):
        self.sockets: dict[uuid.UUID, dict[int, tuple[WebSocket, int]]] = defaultdict(dict)  # room -> id(ws) -> (ws, slot); WebSocket is unhashable
        self.active_slot: dict[uuid.UUID, int | None] = {}  # who may relay progress right now
        self.voice_match: dict[uuid.UUID, str | None] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def track_turn(self, room_id, snap: dict):
        """Remember whose turn it is, so progress from anyone else is refused without a DB read."""
        match = snap["match"]
        self.active_slot[room_id] = (-1 if match.get('duet') else match['active_slot']) if match and match['state'] == 'active' else None
        # A present None means the lobby; an absent key means signaling is forbidden.
        if snap['state'] == 'lobby':
            self.voice_match[room_id] = None
        elif (snap['state'] == 'playing' and match and match.get('duet') and
                match['state'] in ('preparing', 'active')):
            self.voice_match[room_id] = str(match['id'])
        else:
            self.voice_match.pop(room_id, None)

    def present(self, room_id) -> set[int]:
        return {slot for _, slot in self.sockets[room_id].values()}

    async def broadcast(self, room_id, event: dict, exclude: WebSocket | None = None):
        for ws, _ in list(self.sockets[room_id].values()):
            if ws is not exclude:
                try:
                    await ws.send_json(event)
                except Exception:  # dead socket: its own receive loop will clean it up
                    log.warning("websocket send failed", exc_info=True)

    def broadcast_threadsafe(self, room_id, event: dict):
        """For sync route handlers running in the threadpool."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(room_id, event), self.loop)


hub = Hub()


def _valid_voice_signal(data: object) -> bool:
    """Bound and whitelist signaling. No client-supplied destination or sender identity."""
    if not isinstance(data, dict):
        return False
    if 'match_id' not in data or (data['match_id'] is not None and
            (not isinstance(data['match_id'], str) or not 1 <= len(data['match_id']) <= 64)):
        return False
    if not isinstance(data.get('session'), str) or not 1 <= len(data['session']) <= 64:
        return False
    kind = data.get('kind')
    common = {'match_id', 'session', 'kind'}
    if kind == 'ready':
        return set(data) == common
    if not isinstance(data.get('peer'), str) or not 1 <= len(data['peer']) <= 64:
        return False
    common.add('peer')
    if kind in ('offer', 'answer'):
        return set(data) == common | {'sdp'} and isinstance(data.get('sdp'), str) and 0 < len(data['sdp']) <= 14000
    if kind == 'ice':
        c = data.get('candidate')
        return (set(data) == common | {'candidate'} and isinstance(c, dict) and
                set(c) <= {'candidate', 'sdpMid', 'sdpMLineIndex', 'usernameFragment'} and
                isinstance(c.get('candidate'), str) and len(c['candidate']) <= 2048 and
                (c.get('sdpMid') is None or isinstance(c['sdpMid'], str) and len(c['sdpMid']) <= 256) and
                (c.get('sdpMLineIndex') is None or type(c['sdpMLineIndex']) is int and 0 <= c['sdpMLineIndex'] <= 32) and
                (c.get('usernameFragment') is None or isinstance(c['usernameFragment'], str) and len(c['usernameFragment']) <= 256))
    return False


# ---- snapshots -------------------------------------------------------------------------------

def _latest_match(s: Session, room: Room):
    return s.scalars(select(Match).where(Match.room_id == room.id).order_by(Match.created_at.desc()).limit(1)).first()


def snapshot(s: Session, room: Room) -> dict:
    members = s.scalars(select(RoomMember).where(RoomMember.room_id == room.id).order_by(RoomMember.slot)).all()
    match = _latest_match(s, room)
    here = hub.present(room.id)
    return {"id": room.id, "code": room.code, "state": room.state, "state_version": room.state_version,
            "visibility": room.visibility, "clip_id": room.clip_id, "host_slot": 0,
            "range": play._match_range(s, match) if match else None,
            "members": [{"slot": m.slot, "display_name": m.display_name, "ready": m.ready,
                         "connected": m.slot in here} for m in members],
            "match": match_view(s, match) if match and match.state != "lobby" else None}


def publish(s: Session, room: Room, *extra: dict):
    """After a durable change commits: bump nothing here, just tell everyone the new truth."""
    s.refresh(room)
    snap = snapshot(s, room)
    hub.track_turn(room.id, snap)
    hub.broadcast_threadsafe(room.id, _event("room_snapshot", **snap))
    for e in extra:
        hub.broadcast_threadsafe(room.id, e)


def _bump(room: Room):
    room.state_version += 1


def _room(s: Session, room_id: uuid.UUID, lock: bool = False) -> Room:
    room = s.get(Room, room_id, with_for_update=lock)
    if not room:
        raise ApiError(404, "room_not_found", "No such room.")
    return room


def _member(s: Session, room: Room, guest: GuestSession) -> RoomMember:
    m = s.scalar(select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.guest_id == guest.id))
    if not m:
        raise ApiError(404, "room_not_found", "No such room.")  # non-members cannot tell it exists
    return m


def _host_only(room: Room, guest: GuestSession):
    if room.host_guest_id != guest.id:
        raise ApiError(403, "host_only", "Only the host can do that.")


# ---- HTTP: durable actions -------------------------------------------------------------------

class RoomIn(BaseModel):
    clip_id: str
    duet: bool = False


class CreateIn(BaseModel):
    """clip_id is optional: the host picks the song inside the room, so a default is used until then."""
    clip_id: str | None = None
    duet: bool = False
    visibility: str = Field(default="public", pattern="^(public|private)$")
    password: str | None = Field(default=None, max_length=PASSWORD_MAX)


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=8)
    password: str | None = Field(default=None, max_length=PASSWORD_MAX)


class JoinByIdIn(BaseModel):
    password: str | None = Field(default=None, max_length=PASSWORD_MAX)


def default_clip_id() -> str:
    """First real song (not a test fixture), else the first of anything; the host changes it in the lobby."""
    ids = sorted(CATALOG)
    return next((i for i in ids if not i.startswith(("synthetic", "duet-demo"))), ids[0])


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
    except ValueError:
        return False
    return hmac.compare_digest(got, bytes.fromhex(digest))


class ReadyIn(BaseModel):
    ready: bool


class RangeIn(BaseModel):
    range: TimeRange | None = None


def _draft(s: Session, room: Room, guest: GuestSession) -> Match:
    """A lobby's pending host attempt doubles as durable range settings. On start, this same
    draft becomes the real match. Old rooms without a draft are supported lazily."""
    match = _latest_match(s, room)
    if match is None:
        out = play._new_match(s, guest, room.clip_id, [guest.display_name], room_id=room.id)
        match = s.get(Match, out["match_id"])
        match.state = "lobby"
        s.flush()
    return match


@router.post("/api/rooms")
def create_room(body: CreateIn, guest=Depends(current_guest), s: Session = Depends(get_db)):
    play.require_player_name(guest.display_name)
    song = play.require_clip(s, body.clip_id or default_clip_id())
    if body.visibility == "private" and not PASSWORD_MIN <= len(body.password or "") <= PASSWORD_MAX:
        raise ApiError(422, "invalid_password", f"A private room needs a password of {PASSWORD_MIN} to {PASSWORD_MAX} characters.")
    password_hash = hash_password(body.password) if body.visibility == "private" else None
    for _ in range(5):  # a code collision is rare; retry
        room = Room(code="".join(secrets.choice(CODE_ALPHABET) for _ in range(5)), host_guest_id=guest.id,
                    clip_id=song.id, clip_version=song.version, expires_at=datetime.now(timezone.utc) + ROOM_TTL,
                    visibility=body.visibility, password_hash=password_hash)
        s.add(room)
        try:
            s.flush()
            break
        except IntegrityError:
            s.rollback()
    else:
        raise ApiError(503, "room_code_unavailable", "Could not allocate a room code. Try again.", True)
    s.add(RoomMember(room_id=room.id, slot=0, guest_id=guest.id, display_name=guest.display_name))
    if body.duet:
        out = play._new_match(s, guest, song.id, [guest.display_name], room_id=room.id, duet=True)
        s.get(Match, out['match_id']).state = 'lobby'
    s.commit()
    return {**snapshot(s, room), "you": 0}  # "you": the caller's seat (the shared snapshot cannot say)


_join_log: dict[uuid.UUID, deque] = defaultdict(deque)
_wrong_password_log: dict[str, deque] = defaultdict(deque)


def _within_limit(log_: deque, limit: int, now: float) -> bool:
    while log_ and now - log_[0] > 60:
        log_.popleft()
    return len(log_) < limit


def limit_joins_per_ip(request: Request):
    """Per network address as well as per guest, so a fresh guest cookie does not reset the limit."""
    if play.too_many("joins", play.client_ip(request), JOINS_PER_MINUTE * 3):
        raise ApiError(429, "too_many_joins", "Too many join attempts. Wait a minute.", True)


def _join(s: Session, room: Room, guest: GuestSession, password: str | None, client: str) -> dict:
    """Seat `guest` in a locked, loaded `room`. Private rooms need the password; wrong guesses are rate limited
    per player and per network address so a fresh cookie does not reset the budget."""
    if room.expires_at < datetime.now(timezone.utc):
        raise ApiError(410, "room_expired", "That room has expired.")
    mine = s.scalar(select(RoomMember.slot).where(RoomMember.room_id == room.id, RoomMember.guest_id == guest.id))
    if mine is None:
        if room.visibility == "private":
            now = time.monotonic()  # ponytail: in-memory limiter, fine for one worker
            keys = (f"g:{guest.id}", f"ip:{client}")
            if not all(_within_limit(_wrong_password_log[k], WRONG_PASSWORDS_PER_MINUTE, now) for k in keys):
                raise ApiError(429, "too_many_attempts", "Too many wrong passwords. Wait a minute.", True)
            if not (password and room.password_hash and check_password(password, room.password_hash)):
                for k in keys:
                    _wrong_password_log[k].append(now)
                raise ApiError(403, "wrong_password", "That password is not right.")
        if room.state != "lobby":
            raise ApiError(409, "room_started", "That room already started.")
        taken = s.scalars(select(RoomMember.slot).where(RoomMember.room_id == room.id)).all()
        if len(taken) >= 2:
            raise ApiError(409, "room_full", "That room is full.")
        s.add(RoomMember(room_id=room.id, slot=1, guest_id=guest.id, display_name=guest.display_name))
        _bump(room)
        s.commit()
        publish(s, room)
        mine = 1
    return {**snapshot(s, room), "you": mine}


def _count_join(guest: GuestSession):
    if not _within_limit(_join_log[guest.id], JOINS_PER_MINUTE, time.monotonic()):
        raise ApiError(429, "too_many_joins", "Too many join attempts. Wait a minute.", True)
    _join_log[guest.id].append(time.monotonic())


@router.post("/api/rooms/join", dependencies=[Depends(limit_joins_per_ip)])
def join_room(body: JoinIn, guest=Depends(current_guest), s: Session = Depends(get_db), request: Request = None):
    play.require_player_name(guest.display_name)
    _count_join(guest)
    room = s.scalar(select(Room).where(Room.code == body.code.strip().upper()).with_for_update())  # serializes racing joins
    if not room:
        raise ApiError(404, "room_not_found", "No room with that code.")
    return _join(s, room, guest, body.password, request.client.host if request and request.client else "?")


@router.post("/api/rooms/{room_id}/join", dependencies=[Depends(limit_joins_per_ip)])
def join_room_by_id(room_id: uuid.UUID, body: JoinByIdIn, guest=Depends(current_guest), s: Session = Depends(get_db),
                    request: Request = None):
    play.require_player_name(guest.display_name)
    _count_join(guest)
    room = s.get(Room, room_id, with_for_update=True)
    if not room:
        raise ApiError(404, "room_not_found", "No such room.")
    return _join(s, room, guest, body.password, request.client.host if request and request.client else "?")


@router.get("/api/rooms")
def list_rooms(visibility: str | None = None, q: str | None = None, guest=Depends(current_guest),
               s: Session = Depends(get_db)):
    """Lobby rooms with an open seat, newest first. No codes and no password data: just enough to pick one.
    `visibility` = public | private narrows the list; `q` matches the host's name (case-insensitive)."""
    stmt = (select(Room, RoomMember.display_name, RoomMember.room_id)
            .join(RoomMember, (RoomMember.room_id == Room.id) & (RoomMember.slot == 0))
            .where(Room.state == "lobby", Room.expires_at > datetime.now(timezone.utc))
            .order_by(Room.created_at.desc()).limit(LIST_LIMIT))
    if visibility in ("public", "private"):
        stmt = stmt.where(Room.visibility == visibility)
    if q and q.strip():
        stmt = stmt.where(RoomMember.display_name.ilike("%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"))
    rows = s.execute(stmt).all()
    counts = dict(s.execute(select(RoomMember.room_id, func.count()).where(RoomMember.room_id.in_([r.id for r, *_ in rows]))
                            .group_by(RoomMember.room_id)).all()) if rows else {}
    items = [{"id": r.id, "visibility": r.visibility, "host_name": host, "clip_id": r.clip_id, "players": counts.get(r.id, 1),
              "created_at": r.created_at, "mine": False} for r, host, _ in rows if counts.get(r.id, 1) < 2]
    # Rooms you already sit in come first, even when full or started, so a dropped player can find the way back
    # now that codes are not shown. Joining one of these again just returns your seat.
    seen = {i["id"] for i in items}
    for r in s.scalars(select(Room).join(RoomMember, RoomMember.room_id == Room.id)
                       .where(RoomMember.guest_id == guest.id, Room.state.in_(("lobby", "playing")),
                              Room.expires_at > datetime.now(timezone.utc))).all():
        names = s.scalars(select(RoomMember.display_name).where(RoomMember.room_id == r.id).order_by(RoomMember.slot)).all()
        mine = {"id": r.id, "visibility": r.visibility, "host_name": names[0], "clip_id": r.clip_id, "players": len(names),
                "created_at": r.created_at, "mine": True}
        items = [mine] + [i for i in items if i["id"] != r.id] if r.id in seen else [mine] + items
    return items


@router.get("/api/rooms/{room_id}")
def get_room(room_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    room = _room(s, room_id)
    me = _member(s, room, guest)
    return {**snapshot(s, room), "you": me.slot}


@router.post("/api/rooms/{room_id}/ready")
def set_ready(room_id: uuid.UUID, body: ReadyIn, guest=Depends(current_guest), s: Session = Depends(get_db)):
    room = _room(s, room_id, lock=True)
    me = _member(s, room, guest)
    if room.state != "lobby":
        raise ApiError(409, "room_started", "The room is no longer in the lobby.")
    me.ready = body.ready
    _bump(room)
    s.commit()
    publish(s, room)
    return snapshot(s, room)


@router.post("/api/rooms/{room_id}/clip")
def change_clip(room_id: uuid.UUID, body: RoomIn, guest=Depends(current_guest), s: Session = Depends(get_db)):
    room = _room(s, room_id, lock=True)
    _member(s, room, guest)
    _host_only(room, guest)
    if room.state != "lobby":
        raise ApiError(409, "room_started", "The room is no longer in the lobby.")
    song = play.require_clip(s, body.clip_id)
    room.clip_id, room.clip_version = song.id, song.version
    draft = _latest_match(s, room)
    if draft:
        duet = play._match_duet(s, draft)
        draft.clip_id, draft.clip_version = song.id, song.version
        first = s.scalar(select(TurnAttempt).where(TurnAttempt.match_id == draft.id, TurnAttempt.slot == 0))
        first.phrase_results = {'duet': play._duet_config(song, None), 'loaded': False} if duet else None
    for m in s.scalars(select(RoomMember).where(RoomMember.room_id == room.id)):
        m.ready = False  # a new clip needs a fresh yes from everyone
    _bump(room)
    s.commit()
    publish(s, room)
    return snapshot(s, room)


@router.post("/api/rooms/{room_id}/range")
def change_range(room_id: uuid.UUID, body: RangeIn, guest=Depends(current_guest), s: Session = Depends(get_db)):
    room = _room(s, room_id, lock=True)
    _member(s, room, guest)
    _host_only(room, guest)
    if room.state != "lobby":
        raise ApiError(409, "room_started", "The room is no longer in the lobby.")
    song = play.require_clip(s, room.clip_id)
    inc = play._included(song, body.range)
    rng = play._range_of(song, [p.id for p in inc]) if body.range else None
    if body.range and not any(w > 0 for p, w in zip(song.phrases, play._weights(song)) if p in inc):
        raise ApiError(422, "invalid_range", "The section must contain scoreable reference notes.")
    draft = _draft(s, room, guest)
    first = s.scalar(select(TurnAttempt).where(TurnAttempt.match_id == draft.id, TurnAttempt.slot == 0))
    first.phrase_results = {'duet': play._duet_config(song, rng), 'loaded': False} if play._match_duet(s, draft) else ({"range": rng.model_dump()} if rng else None)
    for m in s.scalars(select(RoomMember).where(RoomMember.room_id == room.id)):
        m.ready = False
    _bump(room)
    s.commit()
    publish(s, room)
    return snapshot(s, room)


def _start_match(s: Session, room: Room, host: GuestSession, previous: uuid.UUID | None = None):
    names = s.scalars(select(RoomMember.display_name).where(RoomMember.room_id == room.id)
                      .order_by(RoomMember.slot)).all()
    draft = _latest_match(s, room)
    if draft and draft.state == "lobby":
        play._frozen_song(draft)
        draft.state = "active"
        s.add(MatchPlayer(match_id=draft.id, slot=1, display_name=names[1]))
        first = s.scalar(select(TurnAttempt).where(TurnAttempt.match_id == draft.id, TurnAttempt.slot == 0))
        duet = play._match_duet(s, draft)
        if duet:
            draft.state = 'preparing'
            s.add(TurnAttempt(match_id=draft.id, slot=1, phrase_results={'duet': duet, 'loaded': False}))
        out = {"match_id": draft.id, "attempt_id": first.id, "scoring_version": draft.scoring_version}
    else:
        rng = play._match_range(s, draft) if draft else None
        duet = bool(draft and play._match_duet(s, draft))
        out = play._new_match(s, host, room.clip_id, list(names), previous=previous, room_id=room.id,
                              duet=duet, practice_range=rng)
        first = s.get(TurnAttempt, out["attempt_id"])
        if not duet:
            first.phrase_results = {"range": rng.model_dump()} if rng else None
    room.state = "playing"
    _bump(room)
    s.commit()
    publish(s, room)
    return out


@router.post("/api/rooms/{room_id}/start")
def start_room(room_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    room = _room(s, room_id, lock=True)
    _member(s, room, guest)
    _host_only(room, guest)
    members = s.scalars(select(RoomMember).where(RoomMember.room_id == room.id)).all()
    if room.state != "lobby":
        raise ApiError(409, "room_started", "The room already started.")
    if len(members) != 2 or not all(m.ready for m in members):
        raise ApiError(409, "not_ready", "Both players must be in the room and ready.")
    return _start_match(s, room, guest)


@router.post("/api/rooms/{room_id}/rematch")
def rematch_room(room_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    room = _room(s, room_id, lock=True)
    _member(s, room, guest)
    _host_only(room, guest)
    last = _latest_match(s, room)
    if room.state != "finished" and not (last and play._match_duet(s, last) and last.state == 'retry_required'):
        raise ApiError(409, "not_finished", "The current match is not finished.")
    last = s.scalars(select(Match).where(Match.room_id == room.id).order_by(Match.created_at.desc()).limit(1)).one()
    return _start_match(s, room, guest, previous=last.id)


@router.post("/api/rooms/{room_id}/abort")
def abort_room(room_id: uuid.UUID, guest=Depends(current_guest), s: Session = Depends(get_db)):
    """Unrecoverable session: end it cleanly instead of inventing a zero score."""
    room = _room(s, room_id, lock=True)
    _member(s, room, guest)
    _host_only(room, guest)
    last = s.scalars(select(Match).where(Match.room_id == room.id).order_by(Match.created_at.desc()).limit(1)).first()
    if last and last.state != "finished":
        last.state = "aborted"
    room.state = "aborted"
    _bump(room)
    s.commit()
    publish(s, room)
    return snapshot(s, room)


def _on_match_event(s: Session, match: Match, event: str, attempt):
    """Registered with play.match_hooks: mirror match changes into the room and tell both players."""
    if not match.room_id:
        return
    room = s.get(Room, match.room_id, with_for_update=True)
    if match.state == "finished":
        room.state = "finished"
    _bump(room)
    extra = []
    if event == "result_saved" and attempt:
        extra.append(_event("result_saved", slot=attempt.slot, attempt_id=str(attempt.id), match_id=str(match.id)))
        if match.state == "finished":
            extra.append(_event("match_finished", match_id=str(match.id)))
    s.commit()
    publish(s, room, *extra)


play.match_hooks.append(_on_match_event)


# ---- WebSocket: presence, snapshots, provisional progress ------------------------------------

def _origin_ok(ws: WebSocket) -> bool:
    """Browsers always send Origin on WebSockets. Allow our own host or an explicit allow-list."""
    origin = ws.headers.get("origin")
    if origin is None:
        return True  # non-browser client
    allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return origin in allowed or origin.split("://", 1)[-1] == ws.headers.get("host")


def _ws_slot(token: str | None, bearer: str | None, room_id: uuid.UUID) -> int | None:
    """Return the caller's seat in the room, or None. Runs in a thread (blocking DB)."""
    with Session(get_engine()) as s:
        guest = None
        if bearer:
            try:
                guest = s.scalar(select(GuestSession).where(GuestSession.auth0_sub == verify_bearer(bearer)))
            except ApiError:
                guest = None  # Auth0 off or a bad token: fall back to the guest cookie; still closed if that is bad too
        if guest is None and token:
            guest = s.scalar(select(GuestSession).where(GuestSession.token_hash == play._hash(token),
                                                        GuestSession.expires_at > datetime.now(timezone.utc)))
        return guest and s.scalar(select(RoomMember.slot).where(RoomMember.room_id == room_id,
                                                               RoomMember.guest_id == guest.id))


def _snapshot_event(room_id: uuid.UUID) -> dict | None:
    with Session(get_engine()) as s:
        room = s.get(Room, room_id)
        if not room:
            return None
        snap = snapshot(s, room)
        hub.track_turn(room_id, snap)
        return _event("room_snapshot", **snap)


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(ws: WebSocket, room_id: uuid.UUID):
    if not _origin_ok(ws):
        return await ws.close(code=4403)
    # Auth0 users send the token as a subprotocol pair ["bearer", token]: browsers cannot set headers, and a
    # query string would end up in server access logs.
    protos = [p.strip() for p in ws.headers.get("sec-websocket-protocol", "").split(",")]
    bearer = protos[1] if len(protos) == 2 and protos[0] == "bearer" else None
    slot = await asyncio.to_thread(_ws_slot, ws.cookies.get("guest_token"), bearer, room_id)
    if slot is None:
        return await ws.close(code=4403)  # not logged in, or not in this room

    await ws.accept(subprotocol="bearer" if bearer else None)
    hub.sockets[room_id][id(ws)] = (ws, slot)
    await hub.broadcast(room_id, await asyncio.to_thread(_snapshot_event, room_id))  # presence changed
    recent: deque = deque()
    try:
        while True:
            try:
                frame = await asyncio.wait_for(ws.receive(), HEARTBEAT_TIMEOUT)
            except asyncio.TimeoutError:
                return await ws.close(code=1001)  # silent too long: treat as gone
            if frame["type"] == "websocket.disconnect":
                break
            raw = frame.get("text")
            if raw is None:  # a binary frame: say so and keep the socket open
                await ws.send_json(_event("error", code="bad_message", message="Send JSON text frames only."))
                continue
            now = time.monotonic()
            while recent and now - recent[0] > 1:
                recent.popleft()
            recent.append(now)
            if len(raw.encode()) > MAX_VOICE_MESSAGE_BYTES or len(recent) > MAX_MESSAGES_PER_SECOND:
                await ws.send_json(_event("error", code="rate_limited", message="Message too large or too frequent."))
                continue
            try:
                msg = json.loads(raw)
                kind = msg["type"]
            except (ValueError, KeyError, TypeError):
                if len(raw.encode()) > MAX_MESSAGE_BYTES:
                    await ws.send_json(_event('error', code='rate_limited', message='Message too large.'))
                else:
                    await ws.send_json(_event("error", code="bad_message", message="Send JSON with a type."))
                continue
            if kind != 'voice_signal' and len(raw.encode()) > MAX_MESSAGE_BYTES:
                await ws.send_json(_event('error', code='rate_limited', message='Message too large.'))
                continue
            if kind == "heartbeat":
                await ws.send_json(_event("heartbeat_ack"))
            elif kind == 'voice_signal':
                data = msg.get('data')
                if not _valid_voice_signal(data):
                    await ws.send_json(_event('error', code='bad_message', message='Invalid voice signaling.'))
                    continue
                if (room_id not in hub.voice_match or hub.voice_match[room_id] != data['match_id'] or
                        hub.present(room_id) != {0, 1}):
                    await ws.send_json(_event('error', code='voice_unavailable', message='Voice needs two connected players in the lobby or current duet.'))
                    continue
                # Only the opposite seat receives SDP/ICE; another tab of the sender never does.
                event = _event('voice_signal', slot=slot, data=data)
                for target, seat in list(hub.sockets[room_id].values()):
                    if seat != slot:
                        try:
                            await target.send_json(event)
                        except Exception:
                            log.warning('voice signaling delivery failed')
            elif kind in ("progress", "phrase_rating"):
                if hub.active_slot.get(room_id) not in (slot, -1):  # duet clients share one timeline
                    await ws.send_json(_event("error", code="not_your_turn", message="It is not your turn."))
                    continue
                out = "turn_progress" if kind == "progress" else "phrase_rating"
                await hub.broadcast(room_id, _event(out, slot=slot, data=msg.get("data")), exclude=ws)
            else:
                await ws.send_json(_event("error", code="unknown_event", message=f"Unknown event '{kind}'."))
    except WebSocketDisconnect:
        pass
    finally:
        hub.sockets[room_id].pop(id(ws), None)
        event = await asyncio.to_thread(_snapshot_event, room_id)
        if event:
            await hub.broadcast(room_id, event)

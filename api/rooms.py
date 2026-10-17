"""Online rooms for two guests. HTTP owns every durable action (create, join, ready, start, rematch);
the WebSocket carries presence, snapshots and provisional progress/ratings. State lives in Postgres,
so a restarted server or a reconnecting client recovers from a fresh snapshot."""
import asyncio
import json
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import play
from .auth import verify_bearer
from .db import get_engine
from .errors import ApiError
from .models import TimeRange
from .play import current_guest, get_db, match_view
from .tables import GuestSession, Match, MatchPlayer, Room, RoomMember, TurnAttempt

log = logging.getLogger(__name__)
router = APIRouter()

ROOM_TTL = timedelta(hours=2)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
MAX_MESSAGE_BYTES = 2048
MAX_MESSAGES_PER_SECOND = 30
HEARTBEAT_TIMEOUT = 45  # seconds of silence before a socket is dropped
JOINS_PER_MINUTE = 10


# ---- realtime hub: sockets and presence only, never durable state ----------------------------

def _event(type_: str, **fields) -> dict:
    return jsonable_encoder({"type": type_, "id": uuid.uuid4().hex, **fields})  # UUIDs/datetimes -> JSON


class Hub:
    def __init__(self):
        self.sockets: dict[uuid.UUID, dict[int, tuple[WebSocket, int]]] = defaultdict(dict)  # room -> id(ws) -> (ws, slot); WebSocket is unhashable
        self.active_slot: dict[uuid.UUID, int | None] = {}  # who may relay progress right now
        self.loop: asyncio.AbstractEventLoop | None = None

    def track_turn(self, room_id, snap: dict):
        """Remember whose turn it is, so progress from anyone else is refused without a DB read."""
        match = snap["match"]
        self.active_slot[room_id] = match["active_slot"] if match and match["state"] == "active" else None

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


# ---- snapshots -------------------------------------------------------------------------------

def _latest_match(s: Session, room: Room):
    return s.scalars(select(Match).where(Match.room_id == room.id).order_by(Match.created_at.desc()).limit(1)).first()


def snapshot(s: Session, room: Room) -> dict:
    members = s.scalars(select(RoomMember).where(RoomMember.room_id == room.id).order_by(RoomMember.slot)).all()
    match = _latest_match(s, room)
    here = hub.present(room.id)
    return {"id": room.id, "code": room.code, "state": room.state, "state_version": room.state_version,
            "clip_id": room.clip_id, "host_slot": 0,
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


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=8)


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
def create_room(body: RoomIn, guest=Depends(current_guest), s: Session = Depends(get_db)):
    song = play.require_clip(s, body.clip_id)
    for _ in range(5):  # a code collision is rare; retry
        room = Room(code="".join(secrets.choice(CODE_ALPHABET) for _ in range(5)), host_guest_id=guest.id,
                    clip_id=song.id, clip_version=song.version, expires_at=datetime.now(timezone.utc) + ROOM_TTL)
        s.add(room)
        try:
            s.flush()
            break
        except IntegrityError:
            s.rollback()
    else:
        raise ApiError(503, "room_code_unavailable", "Could not allocate a room code. Try again.", True)
    s.add(RoomMember(room_id=room.id, slot=0, guest_id=guest.id, display_name=guest.display_name))
    s.commit()
    return {**snapshot(s, room), "you": 0}  # "you": the caller's seat (the shared snapshot cannot say)


_join_log: dict[uuid.UUID, deque] = defaultdict(deque)


@router.post("/api/rooms/join")
def join_room(body: JoinIn, guest=Depends(current_guest), s: Session = Depends(get_db)):
    now = time.monotonic()  # ponytail: in-memory limiter, fine for one worker
    joins = _join_log[guest.id]
    while joins and now - joins[0] > 60:
        joins.popleft()
    if len(joins) >= JOINS_PER_MINUTE:
        raise ApiError(429, "too_many_joins", "Too many join attempts. Wait a minute.", True)
    joins.append(now)

    room = s.scalar(select(Room).where(Room.code == body.code.strip().upper()).with_for_update())  # serializes racing joins
    if not room:
        raise ApiError(404, "room_not_found", "No room with that code.")
    if room.expires_at < datetime.now(timezone.utc):
        raise ApiError(410, "room_expired", "That room has expired.")
    mine = s.scalar(select(RoomMember.slot).where(RoomMember.room_id == room.id, RoomMember.guest_id == guest.id))
    if mine is None:
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
        draft.clip_id, draft.clip_version = song.id, song.version
        first = s.scalar(select(TurnAttempt).where(TurnAttempt.match_id == draft.id, TurnAttempt.slot == 0))
        first.phrase_results = None
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
    first.phrase_results = {"range": rng.model_dump()} if rng else None
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
        out = {"match_id": draft.id, "attempt_id": first.id, "scoring_version": draft.scoring_version}
    else:
        rng = play._match_range(s, draft) if draft else None
        out = play._new_match(s, host, room.clip_id, list(names), previous=previous, room_id=room.id)
        first = s.get(TurnAttempt, out["attempt_id"])
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
    if room.state != "finished":
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
            guest = s.scalar(select(GuestSession).where(GuestSession.auth0_sub == verify_bearer(bearer)))
        elif token:
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
    try:
        slot = await asyncio.to_thread(_ws_slot, ws.cookies.get("guest_token"), bearer, room_id)
    except ApiError:
        slot = None
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
            if len(raw.encode()) > MAX_MESSAGE_BYTES or len(recent) > MAX_MESSAGES_PER_SECOND:
                await ws.send_json(_event("error", code="rate_limited", message="Message too large or too frequent."))
                continue
            try:
                msg = json.loads(raw)
                kind = msg["type"]
            except (ValueError, KeyError, TypeError):
                await ws.send_json(_event("error", code="bad_message", message="Send JSON with a type."))
                continue
            if kind == "heartbeat":
                await ws.send_json(_event("heartbeat_ack"))
            elif kind in ("progress", "phrase_rating"):
                if hub.active_slot.get(room_id) != slot:  # provisional data only from the singer
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

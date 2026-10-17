"""Database tables. Solo is a match with one player slot; local/online battle add a second
slot (and later a room) without changing these tables. Audio and manifests stay out of the DB."""
import uuid
from datetime import datetime

from sqlalchemy import (DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, String,
                        UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _id():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class GuestSession(Base):
    __tablename__ = "guest_session"
    id: Mapped[uuid.UUID] = _id()
    display_name: Mapped[str] = mapped_column(String(40))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 of the cookie token
    auth0_sub: Mapped[str | None] = mapped_column(String(128), index=True)  # set when a guest logs in
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Clip(Base):
    __tablename__ = "clip"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)  # immutable asset version
    title: Mapped[str] = mapped_column(String(200))
    artist: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(8))
    duration: Mapped[float] = mapped_column(Float)
    checksum: Mapped[str] = mapped_column(String(64))  # sha256 of the manifest file


class Match(Base):
    __tablename__ = "match"
    id: Mapped[uuid.UUID] = _id()
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guest_session.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16))  # solo | local | online
    clip_id: Mapped[str] = mapped_column(String(64))
    clip_version: Mapped[int] = mapped_column(Integer)
    scoring_version: Mapped[str] = mapped_column(String(32))  # frozen for the whole match
    state: Mapped[str] = mapped_column(String(24), default="active")
    active_slot: Mapped[int] = mapped_column(Integer, default=0)
    previous_match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("match.id"))  # rematch
    created_at: Mapped[datetime] = _now()
    __table_args__ = (ForeignKeyConstraint(["clip_id", "clip_version"], ["clip.id", "clip.version"]),)


class MatchPlayer(Base):
    __tablename__ = "match_player"
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("match.id"), primary_key=True)
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)  # 0, or 0 and 1 for battle
    display_name: Mapped[str] = mapped_column(String(40))  # snapshot at match creation


class TurnAttempt(Base):
    __tablename__ = "turn_attempt"
    id: Mapped[uuid.UUID] = _id()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("match.id"), index=True)
    slot: Mapped[int] = mapped_column(Integer)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    register: Mapped[int] = mapped_column(Integer, default=0)  # -12 | 0 | 12 semitones
    calibration_offset: Mapped[float | None] = mapped_column(Float)  # seconds
    state: Mapped[str] = mapped_column(String(16), default="pending")  # pending|started|accepted|invalidated
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    phrase_results: Mapped[list | None] = mapped_column(JSONB)
    pitch: Mapped[float | None] = mapped_column(Float)
    timing: Mapped[float | None] = mapped_column(Float)
    total: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _now()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["match_id", "slot"], ["match_player.match_id", "match_player.slot"]),
        UniqueConstraint("match_id", "idempotency_key"),
        # At most one accepted result per match and slot.
        Index("one_accepted_per_slot", "match_id", "slot", unique=True,
              postgresql_where=text("state = 'accepted'")),
    )


class PracticeAttempt(Base):
    __tablename__ = "practice_attempt"
    id: Mapped[uuid.UUID] = _id()
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guest_session.id"), index=True)
    clip_id: Mapped[str] = mapped_column(String(64))
    phrase_id: Mapped[str] = mapped_column(String(32))
    locale: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # ok | unavailable | error
    words: Mapped[list | None] = mapped_column(JSONB)  # no raw audio is stored
    created_at: Mapped[datetime] = _now()

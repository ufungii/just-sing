"""Delete expired guest sessions and everything they own. Logged-in accounts (auth0_sub set)
and unexpired guests are never touched."""
import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from . import play
from .db import get_engine
from .tables import GuestSession, Match, MatchPlayer, PracticeAttempt, Room, RoomMember, TurnAttempt

log = logging.getLogger(__name__)


def cleanup_expired() -> int:
    """One transaction, so a crash never leaves half-deleted history. Returns guests removed."""
    with Session(get_engine()) as s:
        ids = select(GuestSession.id).where(GuestSession.expires_at < datetime.now(timezone.utc),
                                            GuestSession.auth0_sub.is_(None))
        matches = select(Match.id).where(Match.guest_id.in_(ids))
        s.execute(delete(TurnAttempt).where(TurnAttempt.match_id.in_(matches)))
        s.execute(delete(MatchPlayer).where(MatchPlayer.match_id.in_(matches)))
        s.execute(delete(Match).where(Match.guest_id.in_(ids)))
        s.execute(delete(PracticeAttempt).where(PracticeAttempt.guest_id.in_(ids)))
        hosted = select(Room.id).where(Room.host_guest_id.in_(ids))
        s.execute(delete(RoomMember).where(or_(RoomMember.guest_id.in_(ids), RoomMember.room_id.in_(hosted))))
        s.execute(delete(Room).where(Room.host_guest_id.in_(ids)))
        n = s.execute(delete(GuestSession).where(GuestSession.id.in_(ids))).rowcount
        s.commit()
        return n


def reconcile_attempts() -> int:
    """Turn attempts still 'started' past their deadline were lost (tab closed, connection gone).
    Invalidate them and mark the match retry_required, so players get a recovery state, not a score."""
    with Session(get_engine()) as s:
        late = s.scalars(select(TurnAttempt.id).where(TurnAttempt.state == "started",
                                                      TurnAttempt.deadline_at < datetime.now(timezone.utc))).all()
        changed = []
        for attempt_id in late:
            m, a = play.lock_turn(s, attempt_id)  # same lock order as the request handlers
            if a.state != "started" or a.deadline_at >= datetime.now(timezone.utc):
                s.commit()  # finished or retried meanwhile; release the locks
                continue
            a.state = "invalidated"
            if m.state == "active":
                m.state = "retry_required"
                changed.append(m)
            s.commit()
        for m in changed:
            play.notify(s, m, "retry_required")
        return len(late)


async def cleanup_loop(tick_seconds: int = 15, cleanup_every: int = 240):
    """Every tick: recover lost turns. Every `cleanup_every` ticks (hourly): delete expired guests.
    A database outage is logged, never fatal."""
    n = 0
    while True:
        if os.getenv("DATABASE_URL"):
            try:
                await asyncio.to_thread(reconcile_attempts)
                if n % cleanup_every == 0:
                    removed = await asyncio.to_thread(cleanup_expired)
                    log.info("retention: removed %d expired guest(s)", removed)
            except Exception:
                log.exception("background maintenance failed")
        n += 1
        await asyncio.sleep(tick_seconds)

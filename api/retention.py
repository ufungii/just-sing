"""Delete expired guest sessions and everything they own. Logged-in accounts (auth0_sub set)
and unexpired guests are never touched."""
import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import get_engine
from .tables import GuestSession, Match, MatchPlayer, PracticeAttempt, TurnAttempt

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
        n = s.execute(delete(GuestSession).where(GuestSession.id.in_(ids))).rowcount
        s.commit()
        return n


async def cleanup_loop(every_seconds: int = 3600):
    """Run at startup, then hourly. A database outage is logged, never fatal."""
    while True:
        if os.getenv("DATABASE_URL"):
            try:
                n = await asyncio.to_thread(cleanup_expired)
                log.info("retention: removed %d expired guest(s)", n)
            except Exception:
                log.exception("retention cleanup failed")
        await asyncio.sleep(every_seconds)

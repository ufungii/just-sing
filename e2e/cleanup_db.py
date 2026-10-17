"""Delete the guest rows the e2e run created (display name 'E2E Bot') and print remaining row counts.
    PYTHONPATH=. .venv/bin/python e2e/cleanup_db.py        (uses the DB from .env)"""
from dotenv import load_dotenv

load_dotenv()
from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from api.db import get_engine  # noqa: E402
from api.tables import GuestSession, Match, MatchPlayer, TurnAttempt  # noqa: E402

with Session(get_engine()) as s:
    g = select(GuestSession.id).where(GuestSession.display_name == "E2E Bot")
    m = select(Match.id).where(Match.guest_id.in_(g))
    s.execute(delete(TurnAttempt).where(TurnAttempt.match_id.in_(m)))
    s.execute(delete(MatchPlayer).where(MatchPlayer.match_id.in_(m)))
    s.execute(delete(Match).where(Match.guest_id.in_(g)))
    s.execute(delete(GuestSession).where(GuestSession.id.in_(g)))
    s.commit()
    print({t.__tablename__: s.scalar(select(func.count()).select_from(t)) for t in (GuestSession, Match, TurnAttempt)})

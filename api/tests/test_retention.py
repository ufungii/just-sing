import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import get_engine
from api.retention import cleanup_expired
from api.seed import seed
from api.tables import GuestSession, Match, MatchPlayer, TurnAttempt

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")


def test_only_expired_guests_are_removed():
    seed()
    now = datetime.now(timezone.utc)
    ids = {}
    with Session(get_engine()) as s:
        for name, delta, sub in [("old", -1, None), ("live", 1, None), ("acct", -1, "test|keep")]:
            g = GuestSession(display_name=name, token_hash=uuid.uuid4().hex, auth0_sub=sub,
                             expires_at=now + timedelta(days=delta))
            s.add(g); s.flush()
            m = Match(guest_id=g.id, mode="solo", clip_id="synthetic-demo", clip_version=1, scoring_version="t")
            s.add(m); s.flush()
            s.add(MatchPlayer(match_id=m.id, slot=0, display_name=name)); s.flush()
            s.add(TurnAttempt(match_id=m.id, slot=0))
            ids[name] = g.id
        s.commit()
    try:
        assert cleanup_expired() >= 1
        with get_engine().connect() as c:
            alive = {n for n, i in ids.items()
                     if c.execute(text("select 1 from guest_session where id=:i"), {"i": i}).first()}
            assert alive == {"live", "acct"}
            assert c.execute(text("select count(*) from match where guest_id=:i"), {"i": ids["old"]}).scalar() == 0
    finally:
        with get_engine().begin() as c:
            for i in ids.values():
                for t in ("turn_attempt", "match_player"):
                    c.execute(text(f"delete from {t} where match_id in (select id from match where guest_id=:g)"), {"g": i})
                c.execute(text("delete from match where guest_id=:g"), {"g": i})
                c.execute(text("delete from guest_session where id=:g"), {"g": i})

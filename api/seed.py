"""Idempotent catalog seed: python -m api.seed. Inserts or updates clip metadata from manifests."""
import hashlib

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db import get_engine
from .main import CATALOG, CATALOG_DIR
from .tables import Clip


def seed():
    with Session(get_engine()) as s:
        for song in CATALOG.values():
            checksum = hashlib.sha256((CATALOG_DIR / song.id / "manifest.json").read_bytes()).hexdigest()
            row = dict(id=song.id, version=song.version, title=song.title, artist=song.artist,
                       language=song.language, duration=song.duration, checksum=checksum)
            s.execute(insert(Clip).values(row).on_conflict_do_update(
                index_elements=["id", "version"], set_=row))
        s.commit()
    print(f"seeded {len(CATALOG)} clip(s)")


if __name__ == "__main__":
    seed()

"""Prepared-song catalog. Each song is a folder holding song.json (the contracts/ shape) next to its audio;
ML A's pipeline writes these to ml/data/<id>/, and a small fixture lives in api/catalog/<id>/.
Manifests are validated when the server starts, and a bad one raises with its path."""
import json
import os
from pathlib import Path

from pydantic import ValidationError

from .models import Song

CATALOG_DIR = Path(__file__).parent / "catalog"  # built-in synthetic fixture
ML_DATA_DIR = Path(__file__).parents[1] / "ml" / "data"  # pipeline output (gitignored, per machine)


def default_dirs() -> list[Path]:
    """SONG_DIRS (os.pathsep-separated) overrides the defaults."""
    env = os.getenv("SONG_DIRS")
    return [Path(p) for p in env.split(os.pathsep) if p] if env else [CATALOG_DIR, ML_DATA_DIR]


def load_catalog(dirs: list[Path] | None = None):
    """Return (songs, folders, reviewed), each keyed by song id.

    `reviewed` is True only when song.review.json next to the manifest says so. Drafts are still
    served so they can be played and tried; the flag lets the UI label them."""
    songs, folders, reviewed = {}, {}, {}
    for base in dirs if dirs is not None else default_dirs():
        for path in sorted(Path(base).glob("*/song.json")):
            try:
                song = Song.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except (ValidationError, ValueError) as e:
                raise ValueError(f"Invalid song manifest {path}: {e}") from e
            if song.id in songs:
                raise ValueError(f"Duplicate song id '{song.id}': {folders[song.id]} and {path.parent}")
            songs[song.id], folders[song.id] = song, path.parent
            review = path.with_name("song.review.json")
            reviewed[song.id] = review.is_file() and json.loads(review.read_text(encoding="utf-8")).get("reviewed") is True
    return songs, folders, reviewed


# ponytail: loaded once at startup, restart to pick up new songs
CATALOG, SONG_DIR, REVIEWED = load_catalog()

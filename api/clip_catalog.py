"""Prepared-clip catalog: manifests under api/catalog/<id>/manifest.json, validated at load."""
import json
from pathlib import Path

from .models import Song

CATALOG_DIR = Path(__file__).parent / "catalog"


def load_catalog() -> dict[str, Song]:
    """Validate every manifest at load time; a bad one raises with its path."""
    songs = {}
    for path in sorted(CATALOG_DIR.glob("*/manifest.json")):
        song = Song.model_validate(json.loads(path.read_text(encoding="utf-8")))
        songs[song.id] = song
    return songs


CATALOG = load_catalog()  # ponytail: loaded once at startup, restart to pick up new manifests

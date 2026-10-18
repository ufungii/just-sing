"""contracts/*.json examples must not carry keys the API models do not know.

Pydantic ignores unknown keys by default, so an example (or a client type) could grow a field that the API
never returns and test_contracts.py would still pass. This walks each example against its model and fails on
any key the model lacks."""
import json
import typing
from pathlib import Path

import pytest
from pydantic import BaseModel

from api.models import ErrorEnvelope, LyricCheck, Practice, Score, Song

CONTRACTS = Path(__file__).parents[2] / "contracts"

# Keys an example has before the API model learns them. Scoring/pronunciation is owned by another PR (the server
# does not return `pronunciation` yet); delete this entry when Score gets the field.
PENDING = {"score": {"pronunciation"}}


def unknown_keys(model: type[BaseModel], data, path: str = "") -> list[str]:
    """Dotted paths of keys in `data` that `model` (and the models nested in it) do not define."""
    if not isinstance(data, dict):
        return []
    found = []
    for key, value in data.items():
        field = model.model_fields.get(key)
        if field is None:
            found.append(f"{path}{key}")
            continue
        for nested in _models_in(field.annotation):
            for item in value if isinstance(value, list) else [value]:
                found += unknown_keys(nested, item, f"{path}{key}.")
    return found


def _models_in(annotation) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    return [m for arg in typing.get_args(annotation) for m in _models_in(arg)]


@pytest.mark.parametrize("name,model", [
    ("song", Song), ("score", Score), ("practice", Practice), ("error", ErrorEnvelope), ("lyric_check", LyricCheck)])
def test_example_has_no_unknown_keys(name, model):
    data = json.loads((CONTRACTS / f"{name}.example.json").read_text(encoding="utf-8"))
    assert set(unknown_keys(model, data)) - PENDING.get(name, set()) == set()


def test_the_check_catches_an_extra_key():
    found = unknown_keys(Practice, {"clip_id": "a", "words": [{"text": "x", "score": 1, "bogus": 2}], "extra": 1})
    assert sorted(found) == ["extra", "words.bogus"]

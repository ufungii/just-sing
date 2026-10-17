"""Every contracts/ example must load through its model, and the API must serve the catalog."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.models import ErrorEnvelope, Practice, Score, Song

CONTRACTS = Path(__file__).parents[2] / "contracts"


@pytest.mark.parametrize("name,model", [
    ("song", Song), ("score", Score), ("practice", Practice), ("error", ErrorEnvelope)])
def test_example_matches_model(name, model):
    model.model_validate(json.loads((CONTRACTS / f"{name}.example.json").read_text(encoding="utf-8")))


client = TestClient(app)


def test_endpoints():
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/ready").json()["catalog"] is True
    clip = client.get("/api/clips").json()[0]
    assert clip["synthetic"] is True
    assert client.get(f"/api/clips/{clip['id']}/manifest").json()["id"] == clip["id"]


def test_unknown_clip_uses_error_envelope():
    r = client.get("/api/clips/nope/manifest")
    assert r.status_code == 404
    ErrorEnvelope.model_validate(r.json())

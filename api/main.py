"""FastAPI entry point. Run from the repo root: uvicorn api.main:app --reload"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from sqlalchemy import text

from .clip_catalog import CATALOG, CATALOG_DIR
from .db import get_engine
from .errors import ApiError, error_response
from .models import ClipSummary, Song
from .retention import cleanup_loop


@asynccontextmanager
async def lifespan(_):
    from .rooms import hub
    hub.loop = asyncio.get_running_loop()
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="K-Pop Karaoke API", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, e: ApiError):
    return error_response(request, e.status, e.code, e.message, e.retryable)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, e: RequestValidationError):
    return error_response(request, 422, "invalid_request", "The request body or parameters are invalid.")




@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    """Readiness, not liveness: a missing database or scorer is reported, never a crash."""
    from . import practice
    db = "not_configured"
    if os.getenv("DATABASE_URL"):
        try:
            with get_engine().connect() as c:
                c.execute(text("select 1"))
            db = "ok"
        except Exception:
            db = "unavailable"
    return {"catalog": len(CATALOG) > 0, "database": db,
            "pronunciation": "available" if practice.scorer else "unavailable"}


@app.get("/api/clips", response_model=list[ClipSummary])
def clips():
    return [
        ClipSummary(id=s.id, version=s.version, title=s.title, artist=s.artist,
                    duration=s.duration, synthetic=s.provenance.source_version == "synthetic")
        for s in CATALOG.values()
    ]


@app.get("/api/clips/{clip_id}/manifest", response_model=Song)
def manifest(clip_id: str):
    # Lookup by ID in the validated catalog, never by filesystem path.
    if clip_id not in CATALOG:
        raise ApiError(404, "clip_not_found", f"No clip with id '{clip_id}'.")
    return CATALOG[clip_id]


@app.get("/api/clips/{clip_id}/audio")
def instrumental(clip_id: str):
    """Instrumental only (vocals stay offline). Path comes from the validated manifest, never the URL.
    FileResponse handles Range requests, which browsers use for seeking."""
    song = manifest(clip_id)
    path = (CATALOG_DIR / song.id / song.audio.instrumental).resolve()
    if not path.is_relative_to((CATALOG_DIR / song.id).resolve()) or not path.is_file():
        raise ApiError(404, "audio_missing", f"Instrumental for '{clip_id}' is not installed on this server.")
    return FileResponse(path)


from .play import router  # noqa: E402  (play.py imports CATALOG from this module)

app.include_router(router)

from .practice import router as practice_router  # noqa: E402

app.include_router(practice_router)

from .rooms import router as rooms_router  # noqa: E402

app.include_router(rooms_router)

from .coach import router as coach_router  # noqa: E402

app.include_router(coach_router)

from .local_demo import create_app as create_karaoke_demo  # noqa: E402

# Keep the local playback API isolated from production /api and /ws routes.
# Audio and draft scoring remain opt-in via JUST_SING_LOCAL_DEMO_AUDIO.
app.mount("/karaoke", create_karaoke_demo(), name="karaoke-demo")


# ---- built frontend, served from the same origin so the guest cookie and WebSockets need no CORS ----

def web_dist() -> Path:
    """Folder with the built frontend (npm run build in web/). Read per request so tests can swap it."""
    return Path(os.getenv("WEB_DIST") or Path(__file__).parents[1] / "web" / "dist")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    """Serve a built file if it exists, else index.html so client-side routes survive a reload.
    Registered last, so every /api and /ws route wins. Unknown /api paths keep the JSON error envelope."""
    if path.startswith(("api/", "ws/")) or path in ("api", "ws"):
        raise ApiError(404, "not_found", "No such endpoint.")
    root = web_dist().resolve()
    if not (root / "index.html").is_file():
        raise ApiError(404, "frontend_not_built", "The frontend is not built on this server (run npm run build in web/).")
    target = (root / path).resolve()
    if path and target.is_file() and target.is_relative_to(root):  # never serve outside the build folder
        return FileResponse(target)
    return FileResponse(root / "index.html")

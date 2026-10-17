"""Run only on loopback: python -m author.server --port 8010."""
import argparse
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .store import Store

ROOT = Path(__file__).resolve().parents[1]


def create_app(data_dir=None, dist=None):
    store = Store(data_dir or ROOT / 'ml/data')
    app = FastAPI(title='Local song author', docs_url=None, redoc_url=None)
    lock = RLock()

    @app.middleware('http')
    async def loopback_only(request: Request, call_next):
        host = request.url.hostname
        origin = request.headers.get('origin')
        if (host not in ('127.0.0.1', 'localhost') or
                (origin and origin != f'{request.url.scheme}://{request.url.netloc}') or
                (request.method not in ('GET', 'HEAD') and
                 not request.headers.get('content-type', '').startswith('application/json'))):
            return JSONResponse({'error': 'Local same-origin access only'}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({'error': str(error)}, status_code=422)

    @app.get('/api/songs')
    def catalog():
        return store.catalog()

    @app.get('/api/songs/{song_id}')
    def song(song_id: str):
        with lock:
            return store.load(song_id)

    @app.get('/api/songs/{song_id}/audio/{role}')
    def audio(song_id: str, role: str):
        return FileResponse(store.audio(song_id, role))

    @app.post('/api/songs/{song_id}/{action}')
    def edit(song_id: str, action: str, body: dict):
        with lock:
            if action == 'save':
                return store.save(song_id, body['song'], body['revision'])
            if action == 'rebuild':
                return store.rebuild(song_id, body['revision'])
            if action == 'review':
                return store.mark_reviewed(song_id, body['revision'])
            raise ValueError('Unknown author action')

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({'error': 'Missing field: ' + str(error)}, status_code=422)

    static = Path(dist or ROOT / 'author/dist')
    if static.is_dir():
        app.mount('/', StaticFiles(directory=static, html=True))
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8010)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'ml/data')
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.data_dir), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()

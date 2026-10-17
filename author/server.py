"""Run only on loopback: python -m author.server --port 8010."""
import argparse
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .store import Store
from .ingest import PreparationError, MAX_AUDIO_BYTES, SongImports

ROOT = Path(__file__).resolve().parents[1]


def create_app(data_dir=None, dist=None, imports=None):
    store = Store(data_dir or ROOT / 'ml/data')
    imports = imports or SongImports(store.root)

    @asynccontextmanager
    async def lifespan(app):
        yield
        imports.close()

    app = FastAPI(title='Local song author', docs_url=None, redoc_url=None, lifespan=lifespan)
    lock = RLock()

    @app.middleware('http')
    async def loopback_only(request: Request, call_next):
        host = request.url.hostname
        origin = request.headers.get('origin')
        uploading = request.method == 'POST' and request.url.path == '/api/imports'
        content_type = request.headers.get('content-type', '')
        if (host not in ('127.0.0.1', 'localhost') or
                (origin and origin != f'{request.url.scheme}://{request.url.netloc}') or
                (request.method not in ('GET', 'HEAD') and
                 not (content_type.startswith('application/json') or
                      (uploading and content_type.startswith('multipart/form-data'))))):
            return JSONResponse({'error': 'Local same-origin access only'}, status_code=403)
        if uploading:
            try:
                too_large = int(request.headers.get('content-length', '0')) > MAX_AUDIO_BYTES + 1024 * 1024
            except ValueError:
                return JSONResponse({'error': 'Invalid upload length'}, status_code=422)
            if too_large:
                return JSONResponse({'error': 'Audio must be 250 MB or smaller.'}, status_code=413)
        return await call_next(request)

    @app.exception_handler(PreparationError)
    async def import_error(request, error):
        return JSONResponse({'error': str(error)}, status_code=error.status)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({'error': str(error)}, status_code=422)

    @app.get('/api/imports')
    def preparation_jobs():
        return {**imports.availability(), 'jobs': imports.list()}

    @app.post('/api/imports', status_code=202)
    def add_song(audio: UploadFile = File(), song_id: str = Form(), title: str = Form(),
                 artist: str = Form(), lyrics: str = Form(), language: str = Form('ko')):
        return imports.submit(audio, song_id, title, artist, lyrics, language)

    @app.get('/api/imports/{job_id}')
    def preparation_job(job_id: str):
        return imports.get(job_id)

    @app.get('/api/imports/{job_id}/log', response_class=PlainTextResponse)
    def preparation_log(job_id: str):
        imports.get(job_id)
        path = imports.folder(job_id) / 'pipeline.log'
        if not path.is_file():
            return 'Processing has not written a log yet.'
        with path.open('rb') as log:
            log.seek(max(0, path.stat().st_size - 32_768))
            return log.read().decode('utf-8', errors='replace')

    @app.post('/api/imports/{job_id}/cancel')
    def cancel_preparation(job_id: str):
        return imports.cancel(job_id)

    @app.post('/api/imports/{job_id}/retry', status_code=202)
    def retry_preparation(job_id: str):
        return imports.retry(job_id)

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
            if action == 'crop':
                from .crop import crop_song
                return crop_song(store,song_id,body['id'],body['title'],body['start'],body['end'],body['revision'])
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

"""Local, durable audio-preparation jobs. Model inference runs in another Python process."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
from threading import RLock
import uuid

from .store import Store

ROOT = Path(__file__).resolve().parents[1]
MAX_AUDIO_BYTES = 250 * 1024 * 1024
AUDIO_TYPES = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac'}
STAGES = {
    'queued': 'Waiting to start',
    'separating': 'Separating vocals and instrumental',
    'encoding': 'Preparing synchronized audio',
    'aligning': 'Aligning the supplied lyrics',
    'pitch': 'Extracting reference pitch',
    'manifest': 'Building the playable draft',
}


class PreparationError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat()


def interpreter(configured, folder):
    if configured:
        # Resolving a virtualenv's Python symlink would invoke the system Python.
        return Path(configured).expanduser().absolute()
    return next((p for p in [folder / 'bin/python', folder / 'Scripts/python.exe'] if p.is_file()), None)


class SongImports:
    def __init__(self, data_dir, processor=None):
        self.root = Path(data_dir).resolve()
        self.jobs_dir = self.root / '.imports'
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        if not self.jobs_dir.resolve().is_relative_to(self.root):
            raise ValueError('Import jobs must stay inside the song data folder')
        self.lock = RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='song-preparation')
        self.active = None
        self.process = None
        self.closed = False
        self.processor = processor or self.process_audio
        self.pipeline = interpreter(os.getenv('AUTHOR_PIPELINE_PYTHON'), ROOT / 'ml/pipeline/.venv')
        self.separation = interpreter(os.getenv('AUTHOR_SEPARATION_PYTHON'), ROOT / 'ml/pipeline/separation/.venv')
        self._availability = None
        # A stopped server cannot resume an unknown child process safely.
        for path in self.jobs_dir.glob('*/job.json'):
            job = json.loads(path.read_text())
            if job['status'] in ('queued', 'processing'):
                job.update(status='failed', message='Processing was interrupted. Retry to start again.')
                self.write(job)

    def availability(self):
        if self._availability is not None:
            return self._availability
        if self.processor != self.process_audio:
            return {'available': True, 'message': ''}
        if not self.pipeline or not self.pipeline.is_file() or not self.separation or not self.separation.is_file():
            return {'available': False, 'message': 'Audio processing needs the pipeline and separation environments configured on this computer.'}
        script = 'import importlib.util,json; print(json.dumps([m for m in MODULES if importlib.util.find_spec(m) is None]))'
        try:
            missing = []
            for python, modules in [(self.pipeline, ['torch', 'torchaudio', 'torchcrepe', 'soundfile', 'imageio_ffmpeg', 'uroman', 'korean_romanizer']),
                                    (self.separation, ['demucs', 'soundfile', 'imageio_ffmpeg'])]:
                result = subprocess.run([str(python), '-c', script.replace('MODULES', repr(modules))],
                                        check=True, capture_output=True, text=True, timeout=20)
                missing.extend(json.loads(result.stdout))
            self._availability = {'available': not missing, 'message': 'The audio-processing environment is missing required packages.' if missing else ''}
        except (OSError, subprocess.SubprocessError, ValueError):
            self._availability = {'available': False, 'message': 'The audio-processing environment could not start.'}
        return self._availability

    def folder(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise PreparationError('Unknown preparation job', 404)
        return self.jobs_dir / job_id

    def write(self, job):
        folder = self.folder(job['id'])
        temporary = folder / 'job.json.tmp'
        temporary.write_text(json.dumps(job, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
        temporary.replace(folder / 'job.json')

    def get(self, job_id):
        with self.lock:
            path = self.folder(job_id) / 'job.json'
            if not path.is_file():
                raise PreparationError('Unknown preparation job', 404)
            return json.loads(path.read_text())

    def list(self):
        with self.lock:
            jobs = [json.loads(p.read_text()) for p in self.jobs_dir.glob('*/job.json')]
            return sorted(jobs, key=lambda j: j['created_at'], reverse=True)[:20]

    def update(self, job_id, **fields):
        with self.lock:
            job = self.get(job_id)
            job.update(fields, updated_at=now())
            self.write(job)
            return job

    def submit(self, upload, song_id, title, artist, lyrics, language):
        song_id, title, artist, lyrics = song_id.strip(), title.strip(), artist.strip(), lyrics.strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', song_id):
            raise PreparationError('Choose a song ID with letters, digits, hyphens or underscores (up to 80 characters).')
        if not title or len(title) > 200 or not artist or len(artist) > 200:
            raise PreparationError('Enter a song title and artist, each under 200 characters.')
        if not lyrics or len(lyrics) > 100_000 or '\x00' in lyrics:
            raise PreparationError('Paste lyrics with one sung line per line (up to 100,000 characters).')
        if language not in ('ko', 'en'):
            raise PreparationError('Choose Korean or English.')
        suffix = Path(upload.filename or '').suffix.lower()
        if suffix not in AUDIO_TYPES:
            raise PreparationError('Choose an MP3, WAV, FLAC, M4A, OGG or AAC audio file.')
        if not self.availability()['available']:
            raise PreparationError(self.availability()['message'], 503)
        with self.lock:
            if self.closed or self.active:
                raise PreparationError('Another song is processing. Wait for it to finish or cancel it.', 409)
            if (self.root / song_id).exists():
                raise PreparationError('That song ID already exists. Choose a new ID; existing songs cannot be replaced.', 409)
            job_id = uuid.uuid4().hex
            folder = self.folder(job_id)
            folder.mkdir()
            source = folder / ('source' + suffix)
            total = 0
            try:
                with source.open('wb') as output:
                    while chunk := upload.file.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_AUDIO_BYTES:
                            raise PreparationError('Audio must be 250 MB or smaller.', 413)
                        output.write(chunk)
                if not total:
                    raise PreparationError('The audio file is empty.')
                (folder / 'lyrics.txt').write_text(lyrics + '\n', encoding='utf-8')
            except Exception:
                import shutil
                shutil.rmtree(folder)
                raise
            job = {'id': job_id, 'song_id': song_id, 'title': title, 'artist': artist,
                   'language': language, 'source': source.name, 'status': 'queued', 'stage': 'queued',
                   'message': STAGES['queued'], 'cancel_requested': False,
                   'created_at': now(), 'updated_at': now()}
            self.write(job)
            self.active = job_id
            self.pool.submit(self.run, job_id)
            return job

    def run(self, job_id):
        import shutil
        folder = self.folder(job_id)
        prepared = folder / 'prepared'
        try:
            self.update(job_id, status='processing')
            output = self.processor(self.get(job_id), prepared)
            with self.lock:
                if self.get(job_id)['cancel_requested']:
                    raise PreparationError('Processing canceled.')
                # Validate in the private workspace before adding anything to the catalog.
                from api.models import Song
                loaded = Store(prepared).load(self.get(job_id)['song_id'])
                song = Song.model_validate(loaded['song'])
                if not song.phrases or not any(hz for hz in song.reference.hz):
                    raise PreparationError('No scoreable singing was found. Choose a recording with clear lead vocals.')
                destination = self.root / song.id
                if destination.exists():
                    raise PreparationError('That song ID was created while processing. Retry with a different ID.')
                output.rename(destination)
                self.update(job_id, status='ready', stage='ready', message='Draft ready. Listen and review before marking it reviewed.')
        except Exception as error:
            canceled = self.get(job_id)['cancel_requested']
            message = 'Processing canceled.' if canceled else str(error) if isinstance(error, PreparationError) else 'Audio processing failed. Check the preparation log, then retry.'
            with (folder / 'pipeline.log').open('a') as log:
                log.write(f'\n{type(error).__name__}: {error}\n')
            self.update(job_id, status='canceled' if canceled else 'failed', message=message)
        finally:
            if prepared.exists():
                shutil.rmtree(prepared)
            with self.lock:
                self.active = None
                self.process = None

    def process_audio(self, job, prepared):
        folder = self.folder(job['id'])
        environment = os.environ.copy()
        environment.setdefault('OMP_NUM_THREADS', '4')
        environment.setdefault('MKL_NUM_THREADS', '4')
        command = [str(self.pipeline), '-u', '-m', 'ml.pipeline.run', '--id', job['song_id'],
                   '--title', job['title'], '--artist', job['artist'], '--language', job['language'],
                   '--clip', str(folder / job['source']), '--lyrics', str(folder / 'lyrics.txt'),
                   '--data-dir', str(prepared), '--separation-python', str(self.separation)]
        with self.lock:
            if self.get(job['id'])['cancel_requested']:
                raise PreparationError('Processing canceled.')
            self.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding='utf-8', errors='replace',
                                            env=environment, start_new_session=os.name != 'nt')
            process = self.process
        with (folder / 'pipeline.log').open('a', encoding='utf-8') as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                if line.startswith('JUST_SING_STAGE:'):
                    stage = line.partition(':')[2].strip()
                    if stage in STAGES:
                        self.update(job['id'], stage=stage, message=STAGES[stage])
        if process.wait() != 0:
            raise PreparationError('Audio processing failed. Check the preparation log, then retry.')
        return prepared / job['song_id']

    def cancel(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job['status'] not in ('queued', 'processing'):
                return job
            job = self.update(job_id, cancel_requested=True, message='Stopping processing…')
            process = self.process
            if self.active == job_id and process and process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            return job

    def retry(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if self.active or self.closed or job['status'] not in ('failed', 'canceled'):
                raise PreparationError('This preparation cannot be retried right now.', 409)
            if (self.root / job['song_id']).exists():
                raise PreparationError('That song ID already exists. Add the song with a different ID.', 409)
            if not self.availability()['available']:
                raise PreparationError(self.availability()['message'], 503)
            job = self.update(job_id, status='queued', stage='queued', cancel_requested=False, message=STAGES['queued'])
            self.active = job_id
            self.pool.submit(self.run, job_id)
            return job

    def close(self):
        with self.lock:
            self.closed = True
            if self.active:
                self.cancel(self.active)
        self.pool.shutdown(wait=True)

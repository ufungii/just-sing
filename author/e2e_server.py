"""Disposable synthetic author fixture for the Playwright smoke test."""
import tempfile
from pathlib import Path
import uvicorn
from .server import create_app, ROOT
from .test_author import seed

if __name__ == '__main__':
    output = ROOT / 'ml/data/test-runs'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='author-browser-', dir=output) as folder:
        seed(Path(folder))
        uvicorn.run(create_app(Path(folder)),host='127.0.0.1',port=8011)

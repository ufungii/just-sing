# Environment setup

## Environments

Run commands from the repository root. This Intel-graphics workstation uses
Python 3.11 and two CPU environments because Demucs requires older torchaudio:

| Environment | Purpose | Requirements |
| --- | --- | --- |
| `ml/pipeline/.venv` | Downloader, pitch, transcription/alignment | `requirements.txt` |
| `ml/pipeline/separation/.venv` | Demucs separation | `requirements-demucs.txt` |

```powershell
uv --cache-dir ml/data/.uv-cache venv --python 3.11 ml/pipeline/.venv
uv --cache-dir ml/data/.uv-cache pip install --python ml/pipeline/.venv/Scripts/python.exe torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
uv --cache-dir ml/data/.uv-cache pip install --python ml/pipeline/.venv/Scripts/python.exe -r ml/pipeline/requirements.txt
uv --cache-dir ml/data/.uv-cache venv --python 3.11 ml/pipeline/separation/.venv
uv --cache-dir ml/data/.uv-cache pip install --python ml/pipeline/separation/.venv/Scripts/python.exe torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
uv --cache-dir ml/data/.uv-cache pip install --python ml/pipeline/separation/.venv/Scripts/python.exe -r ml/pipeline/requirements-demucs.txt
```

Choose and verify a compatible build separately for GPU workstations. Do not
install Demucs in the modern PyTorch environment. The backend has its own
lightweight environment and never imports the preparation stack.


"""Opt-in pronunciation attach: default stays unavailable, and the API starts without PyTorch."""
import builtins
import subprocess
import sys

from api import practice


def test_unset_env_attaches_nothing(monkeypatch):
    monkeypatch.delenv("PRONUNCIATION_SCORER", raising=False)
    monkeypatch.setattr(practice, "scorer", None)
    practice.attach_scorer()
    assert practice.scorer is None


def test_env_set_but_models_missing_stays_unavailable(monkeypatch):
    real = builtins.__import__

    def no_torch(name, *a, **k):
        if name.split(".")[0] in ("torch", "torchaudio", "transformers", "faster_whisper"):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setenv("PRONUNCIATION_SCORER", "1")
    monkeypatch.setattr(practice, "scorer", None)
    monkeypatch.setattr(builtins, "__import__", no_torch)
    practice.attach_scorer()  # warmup needs torch -> logged, not raised
    assert practice.scorer is None


def test_env_set_attaches_and_warms_fake(monkeypatch):
    import types
    warmed = []

    class Fake:
        provider = "fake"
        def warmup(self): warmed.append(1)

    mod = types.ModuleType("ml.pronunciation.api_scorer")
    mod.PronunciationScorer = Fake
    monkeypatch.setitem(sys.modules, "ml.pronunciation.api_scorer", mod)
    monkeypatch.setenv("PRONUNCIATION_SCORER", "1")
    monkeypatch.setattr(practice, "scorer", None)
    practice.attach_scorer()
    assert isinstance(practice.scorer, Fake) and warmed


def test_api_imports_without_torch():
    code = ("import sys\n"
            "class B:\n"
            "    def find_spec(self, n, p=None, t=None):\n"
            "        if n.split('.')[0] in ('torch','torchaudio','transformers','faster_whisper'): raise ImportError(n)\n"
            "sys.meta_path.insert(0, B())\n"
            "import api.main\n"
            "assert not any(m.split('.')[0]=='torch' for m in sys.modules)\n"
            "assert 'ml.pronunciation.api_scorer' not in sys.modules\n")
    subprocess.run([sys.executable, "-c", code], check=True)

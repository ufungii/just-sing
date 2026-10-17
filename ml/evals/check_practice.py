"""Check one spoken recording with the real ML adapter (no API/database required).

Run in the speech environment:
  python -m ml.evals.check_practice take.wav --expected-file expected.txt --out ml/data/check.json
Expected text must be independently supplied, not copied from the model's transcript.
"""
import argparse
import json
from pathlib import Path
import time
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording', type=Path)
    parser.add_argument('--expected-file', required=True, type=Path)
    parser.add_argument('--out', type=Path, help='Optional local result; keep recordings/lyrics out of Git')
    args = parser.parse_args()
    expected = args.expected_file.read_text(encoding='utf-8').strip()
    from ml.pronunciation.eligibility import is_spoken_korean
    if not is_spoken_korean(expected):
        parser.error('expected text must be a Korean-only spoken-practice line')
    from ml.pronunciation.api_scorer import PronunciationScorer
    from ml.pronunciation.baselines import load_audio, SR
    audio = load_audio(args.recording)
    if len(audio) > 15 * SR:
        parser.error('recording must be at most 15 seconds, as in the upload endpoint')
    scorer = PronunciationScorer()
    started = time.perf_counter()
    try:
        # Match browser-upload normalization, including PCM16 quantization.
        with tempfile.TemporaryDirectory() as temp:
            wav = Path(temp) / 'speech.wav'
            subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                            '-i', str(args.recording), '-t', '16', '-ac', '1', '-ar', '16000',
                            '-c:a', 'pcm_s16le', str(wav)], check=True, timeout=30)
            words = scorer.assess(wav, expected)
        result = dict(status='ok', provider=scorer.provider, overall=scorer.last_overall, words=words)
    except Exception as error:
        result = dict(status='error', provider=scorer.provider, overall=None, words=[], reason=str(error))
    result['seconds_including_model_load'] = round(time.perf_counter() - started, 3)
    result['interpretation'] = 'Raw model confidence, not percent correct; no accent validation.'
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding='utf-8')
    print(output, end='')
    if result['status'] != 'ok':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

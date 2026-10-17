"""Create unverified Korean lyric drafts and timestamp previews from local audio."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "ml/data/model-cache"


def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}.{milliseconds:03}"


def quality_flags(text: str, no_speech: float, compression_ratio: float) -> list[str]:
    """Conservative review flags, not a calibrated measure of lyric accuracy."""
    flags = []
    if no_speech >= 0.6:
        flags.append("high_no_speech_probability")
    words = text.split()
    compact = "".join(character for character in text if character.isalnum())
    repeated_words = len(words) >= 8 and max(words.count(w) for w in set(words)) / len(words) > 0.5
    repeated_characters = len(compact) >= 20 and len(set(compact)) <= 3
    if compression_ratio > 2.4 or repeated_words or repeated_characters:
        flags.append("excessive_repetition")
    return flags


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    if not args.download_only and (args.audio is None or args.output is None):
        parser.error("--audio and --output are required unless --download-only is used")
    if args.beam_size < 1:
        parser.error("--beam-size must be at least one")
    os.environ.setdefault("HF_HOME", str(CACHE / "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from faster_whisper import WhisperModel

    print(f"Loading {args.model} on CPU (int8).", flush=True)
    model = WhisperModel(
        args.model, device="cpu", compute_type="int8", cpu_threads=4,
        download_root=str(CACHE / "faster-whisper"),
    )
    if args.download_only:
        print("Model downloaded and loaded successfully.")
        return
    audio = args.audio.resolve(strict=True)
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "lyrics.draft.json").exists():
        raise FileExistsError("Draft already exists; choose a new output folder to preserve edits")
    started = time.monotonic()
    # No true-lyric prompt: this is an independent, explicitly unverified draft.
    # VAD is disabled because speech VAD can remove quiet or sustained singing.
    segments, info = model.transcribe(
        str(audio), language="ko", task="transcribe", beam_size=args.beam_size,
        temperature=0.0, log_progress=True,
        word_timestamps=True, condition_on_previous_text=False, vad_filter=False,
    )
    lines = []
    for segment in segments:
        text = segment.text.strip()
        if not text or segment.end <= segment.start:
            continue
        line = {
            "line_index": len(lines), "start": segment.start, "end": segment.end,
            "text": text, "reviewed": False,
            "avg_logprob": segment.avg_logprob,
            "no_speech_probability": segment.no_speech_prob,
            "compression_ratio": segment.compression_ratio,
            "quality_flags": quality_flags(text, segment.no_speech_prob, segment.compression_ratio),
            "words": [{"text": word.word.strip(), "start": word.start,
                       "end": word.end, "probability": word.probability}
                      for word in segment.words or []],
        }
        lines.append(line)
        # Report progress without dumping the full lyric text into the terminal.
        print(f"Draft line {len(lines)}: {segment.start:.2f}-{segment.end:.2f}s", flush=True)
    if not lines:
        raise RuntimeError("No transcription returned; do not publish an empty lyric track")
    repeated = sum("excessive_repetition" in line["quality_flags"] for line in lines)
    no_speech = sum("high_no_speech_probability" in line["quality_flags"] for line in lines)
    rejected = repeated > len(lines) / 2 or (repeated > 0 and no_speech >= 0.8 * len(lines))
    result = {
        "status": "rejected_asr_draft" if rejected else "unverified_asr_draft", "language": "ko",
        "usable_for_website": False,
        "quality_summary": {"repetitive_lines": repeated, "high_no_speech_lines": no_speech,
                            "heuristic_only": True},
        "source_audio": str(audio),
        "source_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
        "model": f"faster-whisper/{args.model}", "device": "cpu", "compute_type": "int8",
        "beam_size": args.beam_size, "temperature": 0.0,
        "timestamp_method": "Whisper word timestamps; not corrected-text CTC forced alignment",
        "duration_seconds": info.duration,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "notes": "Correct text and timings by listening. These are not gradeable phrase boundaries.",
        "lines": lines,
    }
    (destination / "lyrics.draft.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "lyrics.draft.txt").write_text(
        "\n".join(line["text"] for line in lines) + "\n", encoding="utf-8"
    )
    note = "Rejected repetitive ASR output; do not use as lyrics." if rejected else "Unverified automatic transcription; requires review."
    cues = ["WEBVTT", "", f"NOTE {note}", ""]
    for line in lines:
        cues += [str(line["line_index"] + 1),
                 f"{timestamp(line['start'])} --> {timestamp(line['end'])}",
                 line["text"], ""]
    (destination / "lyrics.draft.vtt").write_text("\n".join(cues), encoding="utf-8")
    print(f"Saved {len(lines)} draft lines to {destination}")


if __name__ == "__main__":
    main()

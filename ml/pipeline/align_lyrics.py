"""Align supplied text with MMS-FA; save draft timestamps and separate diagnostics."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from math import isfinite

from .romanize import romanize_text
from .text import korean_practice_text, apply_cached_translations


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATE = 16000
HOP = 320
RECEPTIVE_CENTER = 199.5


def lyric_sections(text):
    lines, starts, new_section = [], [], True
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line:
            new_section = True
            continue
        if new_section:
            starts.append(len(lines))
        lines.append(line)
        new_section = False
    return lines, starts


def lrc_track(lines, duration):
    def stamp(seconds):
        centiseconds = round(seconds * 100)
        minutes, centiseconds = divmod(centiseconds, 6000)
        seconds, centiseconds = divmod(centiseconds, 100)
        return f"[{minutes:02}:{seconds:02}.{centiseconds:02}]"
    output = "[re:Automatic alignment draft; not listening-reviewed]\n"
    for index, line in enumerate(lines):
        output += stamp(line["start"]) + line["text"] + "\n"
        next_start = lines[index + 1]["start"] if index + 1 < len(lines) else duration
        if line["end"] < next_start - 1e-6:
            output += stamp(line["end"]) + "\n"
    return output


def normalize_words(lines):
    import uroman

    romanizer = uroman.Uroman()
    words = []
    for line_index, text in enumerate(lines):
        for original in text.split():
            romanized = romanizer.romanize_string(original, lcode="kor").lower().replace("’", "'")
            normalized = re.sub(r"[^a-z']", "", romanized)
            if not normalized:
                raise ValueError(f"Unalignable word on lyric line {line_index + 1}")
            words.append({"line_index": line_index, "text": original, "normalized": normalized})
    return words


def decode_audio(path):
    import imageio_ffmpeg
    import numpy as np
    import torch

    result = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path),
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "f32le", "-",
    ], check=True, capture_output=True)
    return torch.from_numpy(np.frombuffer(result.stdout, dtype="<f4").copy())


def anchor_windows(corrections, texts, duration, audio_hash):
    """Explicit per-line anchors prevent repeated choruses drifting globally."""
    if corrections["source_audio_sha256"] != audio_hash:
        raise ValueError("Timing corrections belong to different vocal audio")
    text_hash = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()
    if corrections["lyric_lines_sha256"] != text_hash:
        raise ValueError("Timing corrections belong to different lyric lines")
    anchors = corrections["line_starts"]
    if len(anchors) != len(texts) or any(isinstance(t, bool) or not isinstance(t, (int, float)) or not isfinite(t) for t in anchors):
        raise ValueError("Provide one finite anchor per lyric line")
    anchors = [round(t, 6) for t in anchors]
    if not anchors or not 0 <= anchors[0] <= anchors[-1] < duration or any(a >= b for a, b in zip(anchors, anchors[1:])):
        raise ValueError("Line anchors must increase within the recording")
    sections = corrections.get("section_starts", [])
    if any(type(i) is not int or not 0 <= i < len(texts) for i in sections) or sections != sorted(set(sections)):
        raise ValueError("Section starts must be ordered unique lyric line indices")
    final_end = corrections.get("last_line_end", duration)
    if (isinstance(final_end, bool) or not isinstance(final_end, (int, float))
            or not isfinite(final_end) or not anchors[-1] < final_end <= duration):
        raise ValueError("Final lyric end must follow its entrance and stay inside the recording")
    ends = corrections.get("line_ends", [*anchors[1:], final_end])
    if (len(ends) != len(anchors) or any(isinstance(t, bool) or not isinstance(t, (int, float)) or not isfinite(t) or t > duration for t in ends)):
        raise ValueError("Provide one finite end per lyric line")
    ends = [min(duration, round(t, 6)) for t in ends]
    if any(not start < end <= limit for start, end, limit in zip(anchors, ends, [*anchors[1:], duration])):
        raise ValueError("Line ends must follow their entrances without overlapping the next line")
    return list(zip(anchors, ends))


def acoustic_frames(audio, cache, chunk_seconds=12, context_seconds=1):
    import torch
    from torchaudio.pipelines import MMS_FA

    model = MMS_FA.get_model(with_star=False, dl_kwargs={"model_dir": str(ROOT / "ml/data/model-cache/mms-fa")})
    parts, times = [], []
    chunk = chunk_seconds * SAMPLE_RATE
    context = context_seconds * SAMPLE_RATE
    for index, start in enumerate(range(0, len(audio), chunk)):
        end = min(len(audio), start + chunk)
        left, right = max(0, start - context), min(len(audio), end + context)
        with torch.inference_mode():
            output, _ = model(audio[left:right].unsqueeze(0))
        centers = (left + torch.arange(output.shape[1], dtype=torch.float64) * HOP + RECEPTIVE_CENTER) / SAMPLE_RATE
        keep = (centers >= start / SAMPLE_RATE) & (centers < end / SAMPLE_RATE)
        parts.append(output[0, keep].clone())
        times.append(centers[keep])
        print(f"Acoustic chunk {index + 1}: through {end / SAMPLE_RATE:.1f}s", flush=True)
    payload = {"emission": torch.cat(parts), "frame_times": torch.cat(times)}
    if not torch.allclose(torch.diff(payload["frame_times"]), torch.full_like(payload["frame_times"][1:], HOP / SAMPLE_RATE), atol=1e-8):
        raise ValueError("Acoustic chunks do not form one continuous time grid")
    torch.save(payload, cache)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--lyrics", type=Path, required=True)
    parser.add_argument("--instrumental", type=Path, help="Bind the draft to the selected playback audio")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, help="Audio/text-bound line anchors; reused on reruns")
    args = parser.parse_args()
    import torch
    import soundfile as sf
    from torchaudio.pipelines import MMS_FA

    torch.set_num_threads(4)
    args.output.mkdir(parents=True, exist_ok=True)
    texts, sections = lyric_sections(args.lyrics.read_text(encoding="utf-8-sig"))
    words = normalize_words(texts)
    if not words:
        parser.error("Lyrics must contain at least one alignable word")
    audio_hash = hashlib.sha256(args.audio.read_bytes()).hexdigest()
    audio = decode_audio(args.audio)
    # Resampling can round the final sample up. Bind display endpoints to the
    # original decoded duration, not that rounded 16 kHz analysis length.
    duration = sf.info(args.audio).duration
    cache = args.output / "acoustic-emissions.pt"
    metadata_file = args.output / "acoustic-emissions.json"
    fingerprint = {"audio_sha256": audio_hash, "model": "torchaudio/MMS_FA", "chunk_seconds": 12, "context_seconds": 1,
                   "sample_rate_hz": SAMPLE_RATE, "torch_version": torch.__version__}
    started = time.monotonic()
    if cache.exists() and metadata_file.exists() and json.loads(metadata_file.read_text()) == fingerprint:
        payload = torch.load(cache, weights_only=True)
        print("Reusing matching cached acoustic emissions.", flush=True)
    else:
        print(f"Aligning {len(texts)} lines / {len(words)} words to {duration:.2f}s of audio.", flush=True)
        payload = acoustic_frames(audio, cache)
        metadata_file.write_text(json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8")
    frame_times = payload["frame_times"]
    correction_file = args.corrections or args.output.parent / "corrections.json"
    if args.corrections and not correction_file.is_file():
        parser.error("Corrections file does not exist")
    corrections = json.loads(correction_file.read_text(encoding="utf-8")) if correction_file.exists() else None
    windows = anchor_windows(corrections, texts, duration, audio_hash) if corrections else None
    aligner, tokenizer = MMS_FA.get_aligner(), MMS_FA.get_tokenizer()
    aligned = []
    if windows:
        for line_index, (start, end) in enumerate(windows):
            local_words = [word for word in words if word["line_index"] == line_index]
            indices = torch.where((frame_times >= start) & (frame_times < end))[0]
            if not len(indices):
                raise ValueError(f"Empty acoustic window for line {line_index + 1}")
            first, last = int(indices[0]), int(indices[-1]) + 1
            spans = aligner(payload["emission"][first:last], tokenizer([w["normalized"] for w in local_words]))
            aligned.extend((word, token_spans, first) for word, token_spans in zip(local_words, spans, strict=True))
    else:
        spans = aligner(payload["emission"], tokenizer([w["normalized"] for w in words]))
        aligned = [(word, token_spans, 0) for word, token_spans in zip(words, spans, strict=True)]
    lines = [{"text": text, "start": None, "end": None, "romanized": romanize_text(text), "translation": "",
              "practice_text": korean_practice_text(text), "words": []} for text in texts]
    diagnostics = []
    for word, token_spans, offset in aligned:
        start = max(0.0, float(frame_times[offset + token_spans[0].start]) - 0.01)
        end = min(duration, float(frame_times[offset + token_spans[-1].end - 1]) + 0.01)
        if windows:
            lower, upper = windows[word["line_index"]]
            start, end = max(lower, start), min(upper, end)
        confidence = sum(span.score * len(span) for span in token_spans) / sum(len(span) for span in token_spans)
        line = lines[word["line_index"]]
        line["words"].append({"text": word["text"], "start": round(start, 6), "end": round(end, 6)})
        line["start"] = round(start, 6) if line["start"] is None else line["start"]
        line["end"] = round(end, 6)
        diagnostics.append({"line_index": word["line_index"], "word_index": len(line["words"]) - 1,
                            "confidence": confidence, "duration_seconds": end - start,
                            "review_flags": (["low_ctc_posterior"] if confidence < 0.2 else [])
                            + (["compressed_word"] if end - start < 0.06 else [])})
    suspect = sum(bool(word["review_flags"]) for word in diagnostics)
    apply_cached_translations(lines, args.output.parent / "translations.json")
    track = {"status": "alignment_draft", "reviewed": False, "duration": duration,
             "source_audio_sha256": audio_hash, "lines": lines, "section_starts": sections}
    if windows:
        for line, (start, end) in zip(lines, windows, strict=True):
            # Hold until the next entrance or an explicit instrumental-gap cue.
            # Word boundaries remain acoustic estimates, not evenly split times.
            line["start"] = start
            line["end"] = end
        track["section_starts"] = corrections.get("section_starts", sections)
        track["timing_method"] = "anchored_lines_acoustic_words"
        track["timing_source"] = corrections.get("provenance", {})
    if args.instrumental:
        track["instrumental_sha256"] = hashlib.sha256(args.instrumental.read_bytes()).hexdigest()
    (args.output / "lyrics.aligned.json").write_text(json.dumps(track, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    def vtt_time(seconds):
        milliseconds = round(seconds * 1000)
        hours, milliseconds = divmod(milliseconds, 3600000)
        minutes, milliseconds = divmod(milliseconds, 60000)
        seconds, milliseconds = divmod(milliseconds, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"
    vtt = "WEBVTT\n\nNOTE Automatic alignment draft; not listening-reviewed.\n\n"
    for line in lines:
        vtt += f"{vtt_time(line['start'])} --> {vtt_time(line['end'])}\n{line['text']}\n\n"
    (args.output / "lyrics.aligned.vtt").write_text(vtt, encoding="utf-8")
    (args.output / "lyrics.aligned.lrc").write_text(lrc_track(lines, duration), encoding="utf-8")
    report = {**fingerprint, "text_sha256": hashlib.sha256(args.lyrics.read_bytes()).hexdigest(),
              "line_count": len(lines), "word_count": len(words), "flagged_words": suspect,
              "mean_word_posterior": sum(w["confidence"] for w in diagnostics) / len(diagnostics),
              "elapsed_seconds": round(time.monotonic() - started, 2),
              "notes": "Speech-model alignment on singing is provisional. Confidence is not singing accuracy. Flags are review heuristics, not validated thresholds.",
              "anchored_lines": bool(windows),
              "words": diagnostics}
    (args.output / "alignment-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["line_count", "word_count", "flagged_words", "mean_word_posterior", "elapsed_seconds"]}))


if __name__ == "__main__":
    main()

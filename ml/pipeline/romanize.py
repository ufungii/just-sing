"""Deterministic display romanization; never changes lyric timing or source text."""

import argparse
import json
from pathlib import Path
import re


def romanize_text(text):
    from korean_romanizer.romanizer import Romanizer

    # Limit the library to Hangul runs so English spelling/case and punctuation
    # survive mixed Korean/English lyrics. Whitespace remains word-aligned.
    return re.sub(r"[가-힣]+", lambda match: Romanizer(match.group()).romanize(), text)


def romanize_track(track):
    return {**track, "lines": [{**line, "romanized": romanize_text(line["text"])}
                               for line in track["lines"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    track = romanize_track(json.loads(args.input.read_text(encoding="utf-8")))
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(json.dumps(track, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(f"Romanized {len(track['lines'])} lines; timestamps and original text preserved.")


if __name__ == "__main__":
    main()

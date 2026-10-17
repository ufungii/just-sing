"""Text eligibility for spoken Korean practice, separate from singing lyrics."""

import re
import hashlib
import json


def apply_cached_translations(lines, path):
    if not path.is_file():
        return
    cached = json.loads(path.read_text(encoding="utf-8"))
    fingerprint = hashlib.sha256("\n".join(line["text"] for line in lines).encode()).hexdigest()
    if cached.get("lyric_lines_sha256") != fingerprint or len(cached["lines"]) != len(lines):
        raise ValueError("Cached translations belong to different lyric text")
    for index, (line, item) in enumerate(zip(lines, cached["lines"], strict=True)):
        if item["line_index"] != index or item["text"] != line["text"] or not item["translation"].strip():
            raise ValueError("Invalid cached translation mapping")
        if not line.get("translation", "").strip():
            line["translation"] = item["translation"]


def korean_practice_text(text):
    """Keep the original whole line only when it has Hangul and no Latin letters."""
    return text if re.search(r"[가-힣ㄱ-ㅎㅏ-ㅣ]", text) and not re.search(r"[A-Za-z]", text) else ""

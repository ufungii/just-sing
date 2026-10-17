"""Read only prepared metadata, reviewed lyrics, and explicitly selected audio."""

import hashlib
import json
from pathlib import Path
import re

from fastapi import HTTPException
from pydantic import ValidationError

from .lyrics import ReviewedTrack, Timeline


def fail(status: int, code: str, message: str):
    raise HTTPException(status, detail={"code": code, "message": message, "retryable": False})


class SongStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def directory(self, song_id: str) -> Path:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", song_id):
            fail(404, "song_not_found", "Song not found.")
        path = (self.root / song_id).resolve()
        if not path.is_relative_to(self.root) or not path.is_dir():
            fail(404, "song_not_found", "Song not found.")
        return path

    def safe_path(self, song_id: str, relative: str) -> Path:
        directory = self.directory(song_id)
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory):
            fail(422, "invalid_asset_path", "Asset must be inside its song directory.")
        return path

    def read(self, song_id: str, relative: str) -> dict:
        path = self.safe_path(song_id, relative)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            return data
        except (OSError, ValueError):
            fail(422, "invalid_song_data", "Prepared song data is missing or invalid.")

    def metadata(self, song_id: str) -> dict:
        directory = self.directory(song_id)
        if (directory / "song.json").exists():
            data = self.read(song_id, "song.json")
        elif (directory / "preparation.json").exists():
            data = self.read(song_id, "preparation.json")
        else:
            fail(404, "song_not_found", "Song not found.")
        try:
            info = Timeline.model_validate({
                "id": data["id"], "version": data.get("version", 1),
                "language": data.get("language", "ko"),
                "duration": data.get("duration", data.get("duration_seconds")), "lines": [],
            })
            if info.id != song_id:
                raise ValueError("song ID differs from directory")
            if not isinstance(data["title"], str) or not isinstance(data["artist"], str):
                raise ValueError("invalid display metadata")
        except (KeyError, ValueError, ValidationError):
            fail(422, "invalid_song_data", "Prepared song metadata is invalid.")
        return {**data, "id": info.id, "version": info.version,
                "language": info.language, "duration": info.duration}

    def audio_path(self, song_id: str, role: str = "instrumental") -> Path:
        metadata = self.metadata(song_id)
        relative = metadata.get("playback_audio", {}).get(role) or metadata.get("audio", {}).get(role)
        if not isinstance(relative, str):
            fail(404, "audio_unavailable", "This audio asset is not prepared.")
        path = self.safe_path(song_id, relative)
        if not path.is_file() or path.suffix.lower() not in {".mp3", ".wav", ".flac", ".ogg", ".m4a"}:
            fail(404, "audio_unavailable", "This audio asset is not prepared.")
        return path

    def lyrics(self, song_id: str) -> dict:
        metadata = self.metadata(song_id)
        base = {key: metadata[key] for key in ("id", "version", "language", "duration")}
        reviewed_file = self.safe_path(song_id, "lyrics.reviewed.json")
        try:
            if reviewed_file.exists():
                track = ReviewedTrack.model_validate(self.read(song_id, "lyrics.reviewed.json"))
                if (track.id != song_id or track.version != base["version"]
                        or abs(track.duration - base["duration"]) > 0.001):
                    raise ValueError("lyric track belongs to a different clip/version")
                actual_hash = hashlib.sha256(self.audio_path(song_id).read_bytes()).hexdigest()
                if track.audio_sha256 != actual_hash:
                    raise ValueError("audio changed after lyric review")
                lines = track.lines
            elif (self.directory(song_id) / "song.json").exists() and metadata.get("lines"):
                review_path = self.safe_path(song_id, "song.review.json")
                if review_path.exists():
                    review = self.read(song_id, "song.review.json")
                    if review.get("reviewed") is not True:
                        return {**base, "status": "unavailable", "lines": [],
                                "reason": "The generated song manifest still needs lyric/timing review."}
                    if (review.get("manifest_sha256") != hashlib.sha256(self.safe_path(song_id, "song.json").read_bytes()).hexdigest()
                            or review.get("audio_sha256", {}).get("instrumental") != hashlib.sha256(self.audio_path(song_id).read_bytes()).hexdigest()):
                        raise ValueError("reviewed manifest or audio changed")
                # A final song.json is the existing, reviewed pipeline handoff.
                # Do not change its shared contract just to add this endpoint.
                lines = Timeline.model_validate({**base, "lines": metadata["lines"]}).lines
            else:
                return {**base, "status": "unavailable", "lines": [],
                        "reason": "Reviewed lyrics and timestamps have not been prepared."}
        except (ValueError, ValidationError):
            fail(422, "invalid_lyric_track", "Reviewed lyrics do not match valid timing or the current audio/version.")
        return {**base, "status": "ready", "lines": [line.model_dump() for line in lines], "reason": None}

    def catalog(self) -> list[dict]:
        if not self.root.exists():
            return []
        songs = []
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir() or not any((directory / file).exists() for file in ("song.json", "preparation.json")):
                continue
            try:
                metadata = self.metadata(directory.name)
                lyrics = self.lyrics(directory.name)
                songs.append({key: metadata[key] for key in ("id", "version", "title", "artist", "language", "duration")}
                             | {"lyrics_status": lyrics["status"],
                                "instrumental_url": f"/api/songs/{directory.name}/audio/instrumental",
                                "lyrics_url": f"/api/songs/{directory.name}/lyrics"})
            except HTTPException:
                # One unfinished/broken preparation must not hide healthy songs.
                continue
        return songs

    def preview_lyrics(self, song_id: str) -> dict:
        ready = self.lyrics(song_id)
        if ready["status"] == "ready":
            return {**ready, "reviewed": True, "phrases": self.scoring_phrases(song_id, ready["lines"])}
        path = self.safe_path(song_id, "alignment/lyrics.aligned.json")
        if not path.exists():
            metadata = self.metadata(song_id)
            if metadata.get("lines") and self.safe_path(song_id, "song.review.json").exists():
                self.checked_manifest_review(song_id)
                try:
                    timeline = Timeline.model_validate({
                        **{k: ready[k] for k in ("id", "version", "language", "duration")},
                        "lines": metadata["lines"],
                    })
                except (ValueError, ValidationError):
                    fail(422, "invalid_alignment_draft", "Portable manifest lyric timing is invalid.")
                return {**timeline.model_dump(), "status": "draft", "reviewed": False, "section_starts": [],
                        "phrases": self.scoring_phrases(song_id, metadata["lines"]),
                        "reason": "Portable supplied-text manifest; listening review is pending."}
            return ready
        draft = self.read(song_id, "alignment/lyrics.aligned.json")
        try:
            if draft.get("status") != "alignment_draft" or draft.get("reviewed") is not False:
                raise ValueError("not a supplied-text alignment draft")
            if draft.get("source_audio_sha256") != hashlib.sha256(self.audio_path(song_id, "vocals").read_bytes()).hexdigest():
                raise ValueError("vocal source changed")
            timeline = Timeline.model_validate({**{k: ready[k] for k in ("id", "version", "language", "duration")},
                                                "lines": draft["lines"]})
            if abs(draft["duration"] - timeline.duration) > 0.001:
                raise ValueError("duration changed")
            sections = draft.get("section_starts", [])
            if (not isinstance(sections, list) or any(type(i) is not int or not 0 <= i < len(timeline.lines) for i in sections)
                    or sections != sorted(set(sections))):
                raise ValueError("invalid lyric sections")
        except (KeyError, ValueError, ValidationError):
            fail(422, "invalid_alignment_draft", "Alignment draft does not match the current vocal recording.")
        return {**timeline.model_dump(), "status": "draft", "reviewed": False, "section_starts": sections,
                "phrases": self.scoring_phrases(song_id, [line.model_dump() for line in timeline.lines]),
                "reason": "Automatic supplied-text alignment; listen and review before using for judged scores."}

    def scoring_phrases(self, song_id: str, lines: list[dict]) -> list[dict]:
        from math import isfinite
        metadata = self.metadata(song_id)
        phrases = metadata.get("phrases", [{"id": f"p{i+1}", "line_index": i, "start": line["start"], "end": line["end"]}
                                            for i, line in enumerate(lines)])
        try:
            previous, ids = 0, set()
            for phrase in phrases:
                if (not isinstance(phrase["id"], str) or phrase["id"] in ids
                        or type(phrase["line_index"]) is not int or not 0 <= phrase["line_index"] < len(lines)
                        or not isfinite(phrase["start"]) or not isfinite(phrase["end"])
                        or not previous <= phrase["start"] < phrase["end"] <= metadata["duration"]):
                    raise ValueError("Invalid scoring phrase")
                previous = phrase["end"]
                ids.add(phrase["id"])
        except (KeyError, TypeError, ValueError):
            fail(422, "invalid_phrases", "Scoring phrase windows are invalid.")
        return phrases

    def checked_manifest_review(self, song_id: str) -> dict:
        """Validate a portable song.json + review sidecar + two-audio handoff."""
        review = self.read(song_id, "song.review.json")
        manifest_path = self.safe_path(song_id, "song.json")
        if (not manifest_path.is_file() or type(review.get("reviewed")) is not bool
                or review.get("manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                or any(review.get("audio_sha256", {}).get(role) != hashlib.sha256(self.audio_path(song_id, role).read_bytes()).hexdigest()
                       for role in ("vocals", "instrumental"))):
            fail(422, "invalid_manifest_package", "The manifest or audio changed after this handoff was generated.")
        return review

    def reference(self, song_id: str) -> dict:
        from math import isfinite
        metadata = self.metadata(song_id)
        path = self.safe_path(song_id, "reference.pitch.json")
        if not path.exists():
            if not metadata.get("reference") or not self.safe_path(song_id, "song.review.json").exists():
                fail(503, "reference_unavailable", "Reference pitch is not prepared.")
            review = self.checked_manifest_review(song_id)
            data = {**metadata["reference"], "duration": metadata["duration"],
                    "source_audio_sha256": review["audio_sha256"]["vocals"],
                    "reviewed": review.get("reference_reviewed") is True,
                    "status": "reviewed" if review.get("reference_reviewed") is True else "unreviewed"}
        else:
            data = self.read(song_id, "reference.pitch.json")
        try:
            valid = (data["source_audio_sha256"] == hashlib.sha256(self.audio_path(song_id, "vocals").read_bytes()).hexdigest()
                     and not isinstance(data["hop_seconds"], bool)
                     and isfinite(data["hop_seconds"]) and data["hop_seconds"] > 0
                     and isfinite(data["duration"]) and abs(data["duration"] - metadata["duration"]) < 0.001
                     and abs(len(data["hz"]) * data["hop_seconds"] - data["duration"]) <= 2 * data["hop_seconds"]
                     and all(value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)
                             and isfinite(value) and value > 0) for value in data["hz"]))
            if not valid:
                raise ValueError("invalid reference")
            for region in data.get("excluded", []):
                if not 0 <= region["start"] < region["end"] <= metadata["duration"]:
                    raise ValueError("invalid exclusion")
        except (KeyError, TypeError, ValueError):
            fail(422, "invalid_reference", "Reference pitch does not match the current recording.")
        return {key: data[key] for key in ("status", "reviewed", "duration", "hop_seconds", "hz", "excluded")}

"""Timestamp validation and clock lookup; no audio/ML dependencies."""

from bisect import bisect_right
from html import escape
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, model_validator


Time = Annotated[FiniteFloat, Field(ge=0)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Word(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Text
    start: Time
    end: Time

    @model_validator(mode="after")
    def positive_duration(self):
        if self.end <= self.start:
            raise ValueError("word end must be after start")
        return self


class Line(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Text
    start: Time
    end: Time
    romanized: str = ""
    translation: str = ""
    practice_text: str = ""
    words: list[Word] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_timing(self):
        if self.end <= self.start:
            raise ValueError("line end must be after start")
        previous_end = self.start
        for word in self.words:
            if word.start < previous_end or word.end > self.end:
                raise ValueError("words must be ordered, non-overlapping, and inside their line")
            previous_end = word.end
        return self


class Timeline(BaseModel):
    id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")]
    version: Annotated[int, Field(strict=True, ge=1)]
    language: str = "ko"
    duration: Annotated[FiniteFloat, Field(gt=0)]
    lines: list[Line]

    @model_validator(mode="after")
    def check_timing(self):
        previous_end = 0.0
        for line in self.lines:
            if line.start < previous_end or line.end > self.duration:
                raise ValueError("lines must be ordered, non-overlapping, and inside the audio duration")
            previous_end = line.end
        return self


class ReviewedTrack(Timeline):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready"]
    reviewed: Literal[True]
    audio_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def require_lines(self):
        if not self.lines:
            raise ValueError("a published lyric track must have at least one line")
        return self


def active_indices(lines: list[Line], time_seconds: float) -> tuple[int | None, int | None]:
    """Half-open intervals make exact boundaries, rests, and seeks deterministic."""
    line_index = bisect_right([line.start for line in lines], time_seconds) - 1
    if line_index < 0 or time_seconds >= lines[line_index].end:
        return None, None
    words = lines[line_index].words
    word_index = bisect_right([word.start for word in words], time_seconds) - 1
    if word_index < 0 or time_seconds >= words[word_index].end:
        return line_index, None
    return line_index, word_index


def timestamp(seconds: float) -> str:
    hours, remainder = divmod(round(seconds * 1000), 3600000)
    minutes, remainder = divmod(remainder, 60000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}.{milliseconds:03}"


def to_vtt(lines: list[Line]) -> str:
    cues = ["WEBVTT", ""]
    for index, line in enumerate(lines):
        cues.extend([str(index + 1), f"{timestamp(line.start)} --> {timestamp(line.end)}",
                     escape(line.text.replace("\n", " ")), ""])
    return "\n".join(cues) + "\n"

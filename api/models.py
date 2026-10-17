"""Pydantic models for the shapes in contracts/. Keep in sync with the examples there;
api/tests/test_contracts.py fails if they drift."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Rating = Literal["perfect", "great", "okay", "bad", "miss"]
Score100 = Field(ge=0, le=100)


class Provenance(BaseModel):
    source_url: str | None
    source_version: str  # "synthetic" marks test fixtures
    crop_start: float
    crop_end: float


class Audio(BaseModel):
    instrumental: str
    vocals: str


class Word(BaseModel):
    text: str
    start: float
    end: float


class Line(BaseModel):
    start: float
    end: float
    text: str
    romanized: str
    translation: str
    practice_text: str
    words: list[Word]


class Phrase(BaseModel):
    id: str
    line_index: int
    start: float
    end: float


class Note(BaseModel):
    start: float
    end: float
    hz: float


class Excluded(BaseModel):
    start: float
    end: float
    reason: str


class Reference(BaseModel):
    hop_seconds: float
    hz: list[float | None]  # None = unvoiced
    notes: list[Note]
    excluded: list[Excluded]


class Song(BaseModel):
    id: str
    version: int
    title: str
    artist: str
    language: str
    duration: float
    provenance: Provenance
    audio: Audio
    lines: list[Line]
    phrases: list[Phrase]
    reference: Reference

    @model_validator(mode="after")
    def check_timing(self):
        ids = [p.id for p in self.phrases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate phrase id")
        for p in self.phrases:
            if not (0 <= p.start < p.end <= self.duration):
                raise ValueError(f"phrase {p.id} outside clip duration")
            if p.line_index >= len(self.lines):
                raise ValueError(f"phrase {p.id} points at a missing line")
        for line in self.lines:
            if not line.practice_text.strip():
                raise ValueError("line missing practice_text")
        return self


class ClipSummary(BaseModel):
    id: str
    version: int
    title: str
    artist: str
    duration: float
    synthetic: bool


class PhraseScore(BaseModel):
    phrase_id: str
    rating: Rating
    pitch: float = Score100
    timing: float = Score100
    coverage: float = Field(ge=0, le=1)


class Score(BaseModel):
    mode: Literal["solo", "battle"]
    clip_id: str
    clip_version: int
    scoring_version: str
    register: Literal[-12, 0, 12]
    total: float = Score100
    pitch: float = Score100
    timing: float = Score100
    phrases: list[PhraseScore]
    coach_blurb: str | None = None  # filled by Gemini later


class WordFeedback(BaseModel):
    text: str
    score: float = Score100


class Practice(BaseModel):
    clip_id: str
    phrase_id: str
    locale: str
    provider: str
    status: Literal["ok", "unavailable", "error"]
    words: list[WordFeedback]


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody

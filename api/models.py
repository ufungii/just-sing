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


class DuetSection(BaseModel):
    id: str = Field(min_length=1)
    slot: Literal[0, 1]
    phrase_ids: list[str] = Field(min_length=1)


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
    duet_sections: list[DuetSection] | None = None

    @model_validator(mode="after")
    def check_timing(self):
        ids = [p.id for p in self.phrases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate phrase id")
        for p in self.phrases:
            if not (0 <= p.start < p.end <= self.duration):
                raise ValueError(f"phrase {p.id} outside clip duration")
            if not 0 <= p.line_index < len(self.lines):
                raise ValueError(f"phrase {p.id} points at a missing line")
        # Singing phrases and Korean pronunciation eligibility are independent.
        # English/mixed lines can have a scored melody and empty practice_text.
        if self.duet_sections is not None:
            section_ids = [section.id for section in self.duet_sections]
            if len(section_ids) != len(set(section_ids)):
                raise ValueError("duplicate duet section id")
            ordered = sorted(self.phrases, key=lambda p: (p.start, p.end, p.id))
            flattened = [pid for section in self.duet_sections for pid in section.phrase_ids]
            if flattened != [p.id for p in ordered]:
                raise ValueError("duet sections must cover every known phrase exactly once in time order")
            line_sections = {}
            by_id = {p.id: p for p in self.phrases}
            previous_end = 0.0
            for section in self.duet_sections:
                phrases = [by_id[pid] for pid in section.phrase_ids]
                if min(p.start for p in phrases) < previous_end:
                    raise ValueError("duet sections cannot overlap in time")
                previous_end = max(p.end for p in phrases)
                for phrase in phrases:
                    if line_sections.setdefault(phrase.line_index, section.id) != section.id:
                        raise ValueError("all phrases of a lyric line must share one duet section")
        return self


class ClipSummary(BaseModel):
    id: str
    version: int
    title: str
    artist: str
    duration: float
    synthetic: bool
    reviewed: bool  # false for drafts: timings and notes not yet checked by ear


class PhraseResultIn(BaseModel):
    """What the browser submits per phrase. Any `rating` or `score` it also sends is ignored."""
    phrase_id: str
    pitch: float = Score100
    timing: float | None = Field(default=None, ge=0, le=100)
    coverage: float = Field(ge=0, le=1)


class PhraseScore(BaseModel):
    phrase_id: str
    rating: Rating
    pitch: float = Score100
    timing: float | None = Field(default=None, ge=0, le=100)  # null: phrase starts mid-note, scored on pitch alone
    score: float = Score100  # this phrase's 0-100 score; ratings and totals derive from it
    coverage: float = Field(ge=0, le=1)


class TimeRange(BaseModel):
    start: float
    end: float


class LyricLine(BaseModel):
    line_index: int = Field(ge=0)
    status: Literal["match", "unclear", "not_sung", "not_covered"]


class TurnLyrics(BaseModel):
    """Saved display-only lyric feedback; it never changes totals or the winner."""
    status: Literal["pending", "ok", "unavailable", "error"]
    lyric_match_version: str | None = None
    lines: list[LyricLine] = []


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
    guided: bool = False  # guide vocals were audible during the turn (client-reported)
    range: TimeRange | None = None  # practice section (first phrase start .. last phrase end); null = full clip
    duet: bool = False
    lyrics: TurnLyrics | None = None


class WordFeedback(BaseModel):
    text: str
    score: float = Score100


class Practice(BaseModel):
    clip_id: str
    phrase_id: str
    locale: str
    provider: str
    status: Literal["ok", "unavailable", "error"]
    overall: float | None = None  # 0-100, automated and not validated by a fluent reviewer; null unless status ok
    words: list[WordFeedback]


class LyricCheck(BaseModel):
    """Did the sung lines carry the right words? Line level, display only, never part of the score.
    `unavailable` (no checker or no fingerprints for this clip) is not a result."""
    clip_id: str
    status: Literal["ok", "unavailable", "error"]
    lyric_match_version: str | None = None
    lines: list[LyricLine] = []


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody

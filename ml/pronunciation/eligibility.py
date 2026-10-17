"""Lightweight eligibility for the spoken-Korean model; safe to import in the API."""


def is_spoken_korean(text: str) -> bool:
    """Require Hangul syllables and reject other letters/digits the model cannot score.

    Empty practice_text deliberately disables spoken practice without disabling singing.
    Punctuation and whitespace are allowed; mixed-language lines are not partly graded.
    """
    return any("가" <= ch <= "힣" for ch in text) and all(
        not ch.isalnum() or "가" <= ch <= "힣" for ch in text)

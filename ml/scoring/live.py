"""Deterministic baseline for browser phrase feedback, with explicit defaults.

Timing compares voiced entrances/note changes after one fixed latency correction.
No DTW, key-offset fitting, or per-frame octave folding is performed.
"""

from math import ceil, isfinite, log2


DEFAULT_CONFIG = {"full_credit_cents": 50, "zero_credit_cents": 175,
                  "onset_change_cents": 80, "onset_min_gap_seconds": 0.1,
                  "timing_window_seconds": 0.3, "pitch_weight": 0.8,
                  "miss_coverage": 0.2,
                  "rating_bands": [[90, "Perfect!"], [75, "Great"], [55, "Okay"], [0, "Bad"]]}
SCORING_VERSION = "baseline-0.1"


def valid_hz(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value > 0


def cents(a, b):
    return abs(1200 * log2(a / b))


def onsets(values, hop, offset, config):
    events = []
    previous = None
    for index, value in enumerate(values):
        t = offset + index * hop
        if valid_hz(value):
            if previous is None or (cents(value, previous) >= config["onset_change_cents"]
                                    and (not events or t - events[-1] >= config["onset_min_gap_seconds"] - 1e-9)):
                events.append(t)
            previous = value
        else:
            previous = None
    return events


def score_phrase(reference, observations, start, end, *, register=0, latency_seconds=0, config=None):
    config = {**DEFAULT_CONFIG, **(config or {})}
    if register not in (-12, 0, 12):
        raise ValueError("register must be -12, 0, or 12")
    hop = reference["hop_seconds"]
    first = max(0, ceil(start / hop - 1e-9))
    last = min(len(reference["hz"]), ceil(end / hop - 1e-9))
    padding = ceil(config["timing_window_seconds"] / hop)
    event_first, event_last = max(0, first - padding), min(len(reference["hz"]), last + padding)
    slots = {}
    for observation in observations:
        t = observation["time"] - latency_seconds
        # Match JS Math.round for nonnegative playback positions.
        index = int(t / hop + 0.5) if t >= 0 else -1
        if event_first <= index < event_last:
            slots[index] = observation.get("hz")
    excluded = reference.get("excluded", [])
    target, user = [], []
    for index in range(first, last):
        t = index * hop
        value = reference["hz"][index]
        if any(region["start"] <= t < region["end"] for region in excluded):
            value = None
        target.append(value * 2 ** (register / 12) if valid_hz(value) else None)
        user.append(slots.get(index))
    expected = sum(valid_hz(value) for value in target)
    if not expected:
        return {"status": "unavailable", "pitch": None, "timing": None, "total": None,
                "coverage": 0, "scoreable_seconds": 0, "rating": None}
    voiced, credit = 0, 0.0
    for wanted, actual in zip(target, user):
        if valid_hz(wanted) and valid_hz(actual):
            voiced += 1
            error = cents(actual, wanted)
            credit += max(0, min(1, (config["zero_credit_cents"] - error)
                                 / (config["zero_credit_cents"] - config["full_credit_cents"])))
    coverage = voiced / expected
    pitch = 100 * credit / expected
    event_target, event_user = [], []
    for index in range(event_first, event_last):
        excluded_here = any(region["start"] <= index * hop < region["end"] for region in excluded)
        value = reference["hz"][index]
        event_target.append(value if not excluded_here else None)
        event_user.append(slots.get(index) if not excluded_here else None)
    wanted_events = [t for t in onsets(event_target, hop, event_first * hop, config)
                     if first * hop - 1e-9 <= t < last * hop - 1e-9]
    actual_events = onsets(event_user, hop, event_first * hop, config)
    used = set()
    timing_credit = 0
    for wanted in wanted_events:
        candidates = [(abs(wanted - actual), index) for index, actual in enumerate(actual_events)
                      if index not in used and abs(wanted - actual) <= config["timing_window_seconds"]]
        if candidates:
            distance, index = min(candidates)
            used.add(index)
            timing_credit += max(0, 1 - distance / config["timing_window_seconds"])
    # No event means rhythm is unmeasurable in this sustained region. Neutral
    # timing avoids penalizing a perfect held note; silence still receives zero.
    timing = (100 * timing_credit / len(wanted_events) if wanted_events else 100) if voiced else 0
    total = config["pitch_weight"] * pitch + (1 - config["pitch_weight"]) * timing
    rating = "Miss" if coverage < config["miss_coverage"] else next(
        name for threshold, name in config["rating_bands"] if total >= threshold)
    return {"status": "provisional", "pitch": pitch, "timing": timing, "total": total,
            "coverage": coverage, "scoreable_seconds": expected * hop, "rating": rating,
            "timing_events": len(wanted_events)}


def aggregate(scores):
    available = [score for score in scores if score["status"] != "unavailable"]
    duration = sum(score["scoreable_seconds"] for score in available)
    if not duration:
        return {"status": "unavailable", "total": None, "pitch": None, "timing": None}
    return {"status": "provisional", **{
        key: sum(score[key] * score["scoreable_seconds"] for score in available) / duration
        for key in ("pitch", "timing", "total")}}

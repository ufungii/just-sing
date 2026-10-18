"""Whole-take lyric checks yield to waiting live line checks, but only for a bounded time."""
import time

from api import lyric_check


def test_take_check_yields_only_while_lines_wait(monkeypatch):
    monkeypatch.setattr(lyric_check, "_lines_waiting", 0)
    start = time.monotonic()
    lyric_check._yield_to_lines(5)
    assert time.monotonic() - start < 0.1  # nothing waiting: no delay

    monkeypatch.setattr(lyric_check, "_lines_waiting", 1)
    start = time.monotonic()
    lyric_check._yield_to_lines(0.3)
    assert 0.25 < time.monotonic() - start < 1  # a line is waiting: yield, then give up

"""Fixtures every CI script's suite shares."""

import sys

import pytest


class ClosedPipe:
    """A stdout whose reader has gone, as when a command is piped into head."""

    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")


@pytest.fixture
def closed_pipe(monkeypatch):
    """A call that closes stdout's reader for the rest of the test.

    A test makes the call itself, just before main(): pytest puts its own
    capture back on sys.stdout after the fixtures are set up.
    """
    return lambda: monkeypatch.setattr(sys, "stdout", ClosedPipe())

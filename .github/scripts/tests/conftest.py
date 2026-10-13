"""Fixtures every CI script's suite shares."""

import importlib.util
import sys
from pathlib import Path

import pytest

# repo_copy and git_init, from the plugin suites' shared conftest.
_PATH = Path(__file__).resolve().parents[3] / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("repo_fixtures", _PATH)
_repos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_repos)
repo_copy = _repos.repo_copy
git_init = _repos.git_init


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

"""Fixtures every CI script's suite shares."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# The scripts import closed_pipe from their own directory, which running one
# puts on sys.path and loading one by path does not.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# repo_copy and git_init, from the plugin suites' shared conftest.
_PATH = Path(__file__).resolve().parents[3] / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("repo_fixtures", _PATH)
_repos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_repos)
repo_copy = _repos.repo_copy
git_init = _repos.git_init


class ClosedPipe:
    """A stdout whose reader has gone, as when a command is piped into head.

    It has a real descriptor underneath, a file the test owns, for the script
    to point at the null device.
    """

    def __init__(self, fd):
        self._fd = fd

    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")

    def fileno(self):
        return self._fd


@pytest.fixture
def closed_pipe(monkeypatch, tmp_path):
    """A call that closes stdout's reader for the rest of the test.

    A test makes the call itself, just before main(): pytest puts its own
    capture back on sys.stdout after the fixtures are set up.
    """
    with open(tmp_path / "closed-stdout", "w") as underneath:
        yield lambda: monkeypatch.setattr(sys, "stdout", ClosedPipe(underneath.fileno()))


@pytest.fixture
def closed_pipe_child():
    """Run a script as a child whose stdout reader has gone: (exit code, stderr).

    Python flushes stdout once more at exit, after main() has returned, and
    only a child process with a real pipe reaches that flush. A fake stdout in
    the test process does not.
    """

    def run(script, *args, env=None):
        child = subprocess.Popen(
            [sys.executable, str(script), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        child.stdout.close()
        err = child.stderr.read().decode()
        return child.wait(), err

    return run

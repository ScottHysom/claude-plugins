"""A reader that closes the pipe early leaves todos.py exiting 0, silently.

Python flushes stdout once more at exit, after main() has returned, and a
closed pipe fails that flush with a traceback and exit 120. Only a child
process with a real pipe reaches that flush, so the first test runs one. The
second drives main() in this process, so coverage sees the handler. --help
counts: argparse prints it and exits before any command runs.
"""

import json
import subprocess
import sys

import pytest

import todos

# A gh that names the repository and lists no labels, which is all a scan
# that finds no TODO asks it.
GH = """case "$1 $2" in
"repo view") echo '%s' ;;
"label list") echo '[]' ;;
*) exit 1 ;;
esac
""" % json.dumps({"nameWithOwner": "o/r", "url": "https://github.com/o/r"})


class StdoutToClosedPipe:
    """A stdout whose reader has gone, with a real descriptor underneath."""

    def __init__(self, fd):
        self._fd = fd

    def write(self, text):
        return len(text)

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")

    def fileno(self):
        return self._fd


class DescribeClosedPipe:
    @pytest.mark.spec("repo:script-ignores-closed-pipe")
    @pytest.mark.parametrize(
        "command",
        [["scan"], ["scan", "--json"], ["--help"], ["scan", "--help"]],
    )
    def it_exits_ok_without_a_traceback_when_its_reader_has_gone(self, repo, gh_on_path, command):
        # The child finds gh on PATH, since the fake gh() is in this process.
        gh_on_path(GH)
        child = subprocess.Popen(
            [sys.executable, todos.__file__, *command, "-C", str(repo.root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        child.stdout.close()
        err = child.stderr.read().decode()
        assert (child.wait(), err) == (todos.OK, "")

    @pytest.mark.spec("repo:script-ignores-closed-pipe")
    @pytest.mark.parametrize("command", [["scan"], ["--help"]])
    def it_points_stdout_at_the_null_device_when_the_flush_fails(
        self, repo, tmp_path, monkeypatch, capsys, command
    ):
        repo.write("a.py", "# TODO: one\n")
        with open(tmp_path / "out", "w") as underneath:
            monkeypatch.setattr(sys, "stdout", StdoutToClosedPipe(underneath.fileno()))
            code = todos.main([*command, "-C", str(repo.root)])
            underneath.write("after\n")
        assert code == todos.OK
        assert capsys.readouterr().err == ""
        assert (tmp_path / "out").read_text() == ""

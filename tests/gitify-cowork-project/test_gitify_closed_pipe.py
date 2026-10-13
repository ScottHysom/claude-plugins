"""A reader that closes the pipe early leaves gitify.py exiting 0, silently.

Python flushes stdout once more at exit, after main() has returned, and a
closed pipe fails that flush with a traceback and exit 120. Only a child
process with a real pipe reaches that flush, so the first test runs one. The
second drives main() in this process, so coverage sees the handler. --help
counts: argparse prints it and exits before any command runs.
"""

import subprocess
import sys

import pytest

import gitify


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
        [["preflight"], ["preflight", "--json"], ["--help"], ["preflight", "--help"]],
    )
    def it_exits_ok_without_a_traceback_when_its_reader_has_gone(self, command):
        child = subprocess.Popen(
            [sys.executable, gitify.__file__, *command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        child.stdout.close()
        err = child.stderr.read().decode()
        assert (child.wait(), err) == (gitify.OK, "")

    @pytest.mark.spec("repo:script-ignores-closed-pipe")
    @pytest.mark.parametrize("command", [["preflight", "--json"], ["--help"]])
    def it_points_stdout_at_the_null_device_when_the_flush_fails(
        self, tmp_path, monkeypatch, capsys, command
    ):
        with open(tmp_path / "out", "w") as underneath:
            monkeypatch.setattr(sys, "stdout", StdoutToClosedPipe(underneath.fileno()))
            code = gitify.main(command)
            underneath.write("after\n")
        assert code == gitify.OK
        assert capsys.readouterr().err == ""
        assert (tmp_path / "out").read_text() == ""


class DescribeUsageError:
    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    def it_exits_cannot_run_through_main_when_stdout_is_open(self, capsys):
        with pytest.raises(SystemExit) as exc:
            gitify.main(["nonsense"])
        assert exc.value.code == gitify.CANNOT_RUN
        assert "invalid choice" in capsys.readouterr().err

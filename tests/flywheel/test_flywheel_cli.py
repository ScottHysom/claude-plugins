"""What every flywheel.py command shares: the envelope, the streams, the
exit codes, and stopping cleanly when it cannot run."""

import subprocess
import sys

import pytest

import flywheel


@pytest.mark.spec("repo:command-prints-json-envelope")
class DescribeTheEnvelope:
    @pytest.mark.parametrize(
        ("argv", "command"), [(["setup"], "setup"), (["config", "init"], "config init")]
    )
    def it_prints_one_object_with_the_shared_keys(self, project, argv, command):
        code, env = project.run(*argv)
        assert code == flywheel.OK
        assert set(env) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert (env["version"], env["command"], env["ok"]) == (2, command, True)
        assert project.err == ""

    def it_carries_a_refusal_with_nothing_on_stderr(self, project):
        project.run("config", "init")
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert len(env["errors"]) == 4
        assert project.err == ""


@pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
class DescribeStopping:
    def it_stops_outside_a_clone(self, tmp_path, capsys):
        code = flywheel.main(["setup", "-C", str(tmp_path)])
        assert code == flywheel.CANNOT_RUN
        err = capsys.readouterr().err
        assert err.startswith("flywheel.py: ")
        assert "not inside a git working tree" in err
        assert "name one with -C" in err

    def it_stops_on_a_missing_directory(self, tmp_path, capsys):
        code = flywheel.main(["config", "init", "-C", str(tmp_path / "gone")])
        assert code == flywheel.CANNOT_RUN
        assert "is not a directory" in capsys.readouterr().err

    def it_stops_without_git(self, project, no_git):
        code, _ = project.run("setup")
        assert code == flywheel.CANNOT_RUN
        assert "git is not installed" in project.err

    @pytest.mark.parametrize("argv", [[], ["config"], ["nope"], ["setup", "--dry-run"]])
    def it_exits_2_on_bad_usage(self, argv, capsys):
        with pytest.raises(SystemExit) as exc:
            flywheel.main(argv)
        assert exc.value.code == flywheel.CANNOT_RUN


@pytest.mark.spec("repo:script-does-nothing-on-import")
class DescribeImporting:
    def it_does_nothing_until_main_runs(self, tmp_path):
        out = subprocess.run(
            [sys.executable, "-c", "import flywheel"],
            cwd=tmp_path,
            env={"PYTHONPATH": str(flywheel.os.path.dirname(flywheel.__file__))},
            capture_output=True,
        )
        assert (out.returncode, out.stdout, out.stderr) == (0, b"", b"")
        assert list(tmp_path.iterdir()) == []


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


@pytest.mark.spec("repo:script-ignores-closed-pipe")
class DescribeClosedPipe:
    @pytest.mark.parametrize("command", [["setup"], ["setup", "--json"], ["--help"]])
    def it_exits_ok_without_a_traceback_when_its_reader_has_gone(self, project, command):
        child = subprocess.Popen(
            [sys.executable, flywheel.__file__, *command]
            + ([] if command == ["--help"] else ["-C", str(project.root)]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        child.stdout.close()
        err = child.stderr.read().decode()
        assert (child.wait(), err) == (flywheel.OK, "")

    @pytest.mark.parametrize("command", [["setup"], ["--help"]])
    def it_points_stdout_at_the_null_device_when_the_flush_fails(
        self, project, tmp_path, monkeypatch, capsys, command
    ):
        with open(tmp_path / "out", "w") as underneath:
            monkeypatch.setattr(sys, "stdout", StdoutToClosedPipe(underneath.fileno()))
            code = flywheel.main([*command, "-C", str(project.root)])
            underneath.write("after\n")
        assert code == flywheel.OK
        assert capsys.readouterr().err == ""
        assert (tmp_path / "out").read_text() == ""

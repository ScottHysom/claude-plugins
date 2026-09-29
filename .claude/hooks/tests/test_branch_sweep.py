"""The branch sweep hook runs at every session start, so it must report in one
line and must never make a session start with an error. Each test stands a
fake issues.py in a project directory, so the hook runs a real subprocess.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "branch_sweep.py"
_spec = importlib.util.spec_from_file_location("branch_sweep", _PATH)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

SETTINGS = Path(__file__).resolve().parents[2] / "settings.json"


def envelope(deleted, kept=()):
    return {
        "version": 1,
        "command": "sweep",
        "ok": True,
        "errors": [],
        "warnings": [],
        "data": {"deleted": list(deleted), "kept": list(kept)},
    }


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project directory whose issues.py runs the given Python body."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    script = tmp_path / hook.ISSUES
    script.parent.mkdir(parents=True)

    def install(body):
        script.write_text("import json, sys, time\n" + body)
        return tmp_path

    return install


def prints(result):
    return "print(json.dumps(%r))\n" % (result,)


class DescribeBranchSweep:
    @pytest.mark.spec("branchsweep-reports-deleted-branches")
    def it_names_the_branches_it_deleted_in_one_line(self, capsys, project):
        project(prints(envelope(["claude/a", "issue/12"], [{"branch": "b", "reason": "r"}])))
        assert hook.main() == 0
        out = capsys.readouterr()
        assert out.out == (
            "The branch sweep deleted 2 local branch(es) whose work is on main: "
            "claude/a, issue/12.\n"
        )
        assert out.err == ""

    @pytest.mark.spec("branchsweep-reports-deleted-branches")
    def it_prints_nothing_when_it_deleted_nothing(self, capsys, project):
        project(prints(envelope([], [{"branch": "b", "reason": "r"}])))
        assert hook.main() == 0
        assert capsys.readouterr() == ("", "")

    @pytest.mark.spec("branchsweep-never-blocks")
    def it_passes_on_why_the_sweep_could_not_run(self, capsys, project):
        project("sys.stderr.write('issues.py: cannot run gh\\n'); sys.exit(2)\n")
        assert hook.main() == 0
        assert capsys.readouterr().out == (
            "The branch sweep did not run: issues.py: cannot run gh. "
            "Run `python3 .github/scripts/issues.py sweep` by hand.\n"
        )

    @pytest.mark.spec("branchsweep-never-blocks")
    def it_gives_up_on_a_slow_sweep(self, capsys, project, monkeypatch):
        monkeypatch.setattr(hook, "TIMEOUT", 0.5)
        project("time.sleep(10)\n")
        assert hook.main() == 0
        assert capsys.readouterr().out.startswith(
            "The branch sweep did not run: it took longer than 0.5 seconds."
        )

    @pytest.mark.spec("branchsweep-never-blocks")
    def it_names_the_exit_code_when_the_sweep_says_nothing(self, capsys, project):
        project("sys.exit(3)\n")
        assert hook.main() == 0
        assert "did not run: issues.py exited 3." in capsys.readouterr().out

    @pytest.mark.spec("branchsweep-never-blocks")
    def it_reports_a_python_it_cannot_start(self, capsys, project, monkeypatch):
        project(prints(envelope([])))
        monkeypatch.setattr(hook.sys, "executable", "/nonexistent/python3")
        assert hook.main() == 0
        assert "The branch sweep did not run: " in capsys.readouterr().out


class DescribeRegistration:
    @pytest.mark.spec("settingsjson-registers-branch-sweep")
    def it_runs_when_a_session_starts(self):
        settings = json.loads(SETTINGS.read_text())
        entries = [
            (entry.get("matcher"), h)
            for entry in settings["hooks"]["SessionStart"]
            for h in entry["hooks"]
        ]
        matcher, found = next((m, h) for m, h in entries if "hooks/branch_sweep.py" in h["command"])
        assert matcher == "startup"
        assert "$CLAUDE_PROJECT_DIR/.claude/hooks/branch_sweep.py" in found["command"]
        assert found["timeout"] == 30
        assert hook.TIMEOUT < found["timeout"]

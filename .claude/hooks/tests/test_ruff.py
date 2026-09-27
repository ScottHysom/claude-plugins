"""Where the ruff hook looks for ruff. A Claude Code session usually runs in a
git worktree with no .venv of its own, so a lookup that only checks the project
directory reports ruff missing on every edit and nothing gets formatted.
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "ruff.py"
_spec = importlib.util.spec_from_file_location("ruff_hook", _PATH)
ruff_hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ruff_hook)

ON_PATH = "/usr/local/bin/ruff"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def install_ruff(checkout):
    ruff = checkout / ruff_hook.VENV_DIR / ruff_hook.VENV_BIN / "ruff"
    ruff.parent.mkdir(parents=True)
    ruff.write_text("")
    return str(ruff)


@pytest.fixture
def repo(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    git(
        main,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    worktree = main / ".claude" / "worktrees" / "wt"
    git(main, "worktree", "add", "-q", "--detach", str(worktree))
    return main, worktree


@pytest.fixture(autouse=True)
def ruff_on_path(monkeypatch):
    monkeypatch.setattr(ruff_hook.shutil, "which", lambda name: ON_PATH)


class DescribeFindRuff:
    @pytest.mark.spec("hook-main-venv")
    def it_uses_the_main_checkouts_venv_from_a_worktree(self, repo):
        main, worktree = repo
        expected = install_ruff(main)
        assert os.path.realpath(ruff_hook.find_ruff(str(worktree))) == os.path.realpath(expected)

    @pytest.mark.spec("hook-own-venv-first")
    def it_prefers_the_worktrees_own_venv(self, repo):
        main, worktree = repo
        install_ruff(main)
        expected = install_ruff(worktree)
        assert ruff_hook.find_ruff(str(worktree)) == expected

    @pytest.mark.spec("hook-main-venv")
    def it_uses_the_venv_in_the_main_checkout_itself(self, repo):
        main, _ = repo
        expected = install_ruff(main)
        assert ruff_hook.find_ruff(str(main)) == expected

    @pytest.mark.spec("hook-path-fallback")
    def it_falls_back_to_ruff_on_path_when_no_venv_exists(self, repo):
        _, worktree = repo
        assert ruff_hook.find_ruff(str(worktree)) == ON_PATH

    @pytest.mark.spec("hook-path-fallback")
    def it_falls_back_to_ruff_on_path_outside_a_git_repo(self, tmp_path):
        assert ruff_hook.find_ruff(str(tmp_path)) == ON_PATH


# The ruff the suite itself runs with. requirements-dev.txt installs it, and
# the autouse fixture above replaces shutil.which, so this is read first.
REAL_RUFF = shutil.which("ruff") or os.path.join(os.path.dirname(sys.executable), "ruff")
SETTINGS = _PATH.parent.parent / "settings.json"


@pytest.fixture
def edit(tmp_path, monkeypatch, capsys):
    """Run the hook on a file Claude Code just wrote: (exit code, stderr, text after)."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(ruff_hook, "find_ruff", lambda root: REAL_RUFF)

    def run(name, text):
        path = tmp_path / name
        path.write_text(text)
        event = {"tool_name": "Write", "tool_input": {"file_path": str(path)}}
        monkeypatch.setattr(ruff_hook.sys, "stdin", io.StringIO(json.dumps(event)))
        code = ruff_hook.main()
        return code, capsys.readouterr().err, path.read_text()

    return run


class DescribeMain:
    @pytest.mark.spec("hook-formats-edit")
    def it_sorts_imports_and_formats_a_python_file(self, edit):
        code, err, after = edit("x.py", "import sys\nimport os\nx=[os,sys]\n")
        assert (code, err) == (0, "")
        assert after == "import os\nimport sys\n\nx = [os, sys]\n"

    @pytest.mark.spec("hook-formats-edit")
    def it_leaves_a_file_that_is_not_python_alone(self, edit):
        code, err, after = edit("notes.txt", "import sys\nimport os\nx=[os,sys]\n")
        assert (code, err) == (0, "")
        assert after == "import sys\nimport os\nx=[os,sys]\n"

    @pytest.mark.spec("hook-reports-lint")
    def it_hands_back_what_the_linter_found(self, edit):
        code, err, _ = edit("x.py", "import os\n")
        assert code == 2
        assert "ruff check found problems" in err
        assert "F401" in err

    @pytest.mark.spec("hook-reports-parse-error")
    def it_hands_back_ruffs_error_on_a_file_that_does_not_parse(self, edit):
        code, err, _ = edit("x.py", "def (:\n")
        assert code == 2
        assert "ruff format failed" in err

    @pytest.mark.spec("hook-ruff-missing")
    def it_names_the_install_command_when_no_ruff_is_found(self, edit, monkeypatch):
        monkeypatch.setattr(ruff_hook, "find_ruff", lambda root: None)
        code, err, _ = edit("x.py", "x = 1\n")
        assert code == 2
        assert "pip install -r requirements-dev.txt" in err


class DescribeRegistration:
    @pytest.mark.spec("hook-registered")
    def it_runs_after_every_write_or_edit(self):
        settings = json.loads(SETTINGS.read_text())
        entries = [
            (entry["matcher"].split("|"), hook)
            for entry in settings["hooks"]["PostToolUse"]
            for hook in entry["hooks"]
        ]
        matchers, hook = next((m, h) for m, h in entries if "hooks/ruff.py" in h["command"])
        assert {"Edit", "Write"} <= set(matchers)
        assert "$CLAUDE_PROJECT_DIR/.claude/hooks/ruff.py" in hook["command"]
        assert hook["timeout"] == 30

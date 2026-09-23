"""Where the ruff hook looks for ruff. A Claude Code session usually runs in a
git worktree with no .venv of its own, so a lookup that only checks the project
directory reports ruff missing on every edit and nothing gets formatted.
"""

import importlib.util
import os
import subprocess
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
    def it_uses_the_main_checkouts_venv_from_a_worktree(self, repo):
        main, worktree = repo
        expected = install_ruff(main)
        assert os.path.realpath(ruff_hook.find_ruff(str(worktree))) == os.path.realpath(expected)

    def it_prefers_the_worktrees_own_venv(self, repo):
        main, worktree = repo
        install_ruff(main)
        expected = install_ruff(worktree)
        assert ruff_hook.find_ruff(str(worktree)) == expected

    def it_uses_the_venv_in_the_main_checkout_itself(self, repo):
        main, _ = repo
        expected = install_ruff(main)
        assert ruff_hook.find_ruff(str(main)) == expected

    def it_falls_back_to_ruff_on_path_when_no_venv_exists(self, repo):
        _, worktree = repo
        assert ruff_hook.find_ruff(str(worktree)) == ON_PATH

    def it_falls_back_to_ruff_on_path_outside_a_git_repo(self, tmp_path):
        assert ruff_hook.find_ruff(str(tmp_path)) == ON_PATH

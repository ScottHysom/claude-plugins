"""Shared fixtures for the flywheel.py suite.

The suite sits here, outside plugins/, because everything under plugins/<name>/
is copied verbatim into every install. README.md, under "Running the tests",
says why, and `.github/scripts/check-tests.py placement` fails the build if a
test moves back.

flywheel.py is a standalone script, not an installed package, so this file
puts the plugin's scripts directory on sys.path.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# tests/<plugin>/ mirrors plugins/<plugin>/scripts. A wrong depth would surface
# as `ModuleNotFoundError: No module named 'flywheel'` at collection, which
# reads as a missing dependency, so it is checked here instead.
PLUGIN, SCRIPT = "flywheel", "flywheel.py"
PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugins" / PLUGIN
SCRIPTS = PLUGIN_ROOT / "scripts"
if not (SCRIPTS / SCRIPT).is_file():
    raise RuntimeError(
        "%s is not where %s lives. This file assumes tests/<plugin>/conftest.py, "
        "two directories below the repo root." % (SCRIPTS, SCRIPT)
    )
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import flywheel  # noqa: E402  - must follow the sys.path insert above


class Project:
    """A throwaway clone, and a way to run flywheel.py against it."""

    def __init__(self, root, capsys):
        self.root = root
        self._capsys = capsys
        self.err = ""

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.root), *args], check=True, capture_output=True
        ).stdout

    def run(self, *argv):
        """Run a command with --json. Returns (exit code, envelope).

        Driven through main() so the argparse defaults are the real ones. The
        envelope is None when nothing was printed; stderr is kept in self.err.
        """
        self._capsys.readouterr()
        code = flywheel.main([*argv, "-C", str(self.root), "--json"])
        captured = self._capsys.readouterr()
        self.err = captured.err
        return code, json.loads(captured.out) if captured.out else None

    def human(self, *argv):
        """Run a command without --json. Returns (exit code, stdout, stderr)."""
        self._capsys.readouterr()
        code = flywheel.main([*argv, "-C", str(self.root)])
        captured = self._capsys.readouterr()
        return code, captured.out, captured.err

    def read(self, rel):
        return (self.root / rel).read_bytes()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path


@pytest.fixture
def project(tmp_path, capsys, git_init):
    """A clone with no commit, which is all flywheel.py needs of one."""
    return Project(git_init(tmp_path / "project"), capsys)


@pytest.fixture
def plugin_copy(tmp_path, monkeypatch):
    """A copy of the plugin that flywheel.py reads its files from.

    The script finds its template and manifest from where it sits, so a test
    that breaks one breaks this copy rather than the plugin.
    """
    root = tmp_path / "plugin"
    shutil.copytree(PLUGIN_ROOT, root)
    monkeypatch.setattr(flywheel, "SCRIPT_PATH", str(root / "scripts" / SCRIPT))
    return root


@pytest.fixture
def no_git(monkeypatch, tmp_path):
    """A PATH on which git cannot be found."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

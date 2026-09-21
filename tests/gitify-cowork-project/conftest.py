"""Shared fixtures for the gitify.py suite.

The suite sits here, outside plugins/, because everything under plugins/<name>/
is copied verbatim into every install. README.md, under "Running the tests",
says why, and `.github/scripts/check-tests.py placement` fails the build if a
test moves back.

gitify.py is a standalone script, not an installed package, so this file puts
the plugin's scripts directory on sys.path.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# tests/<plugin>/ mirrors plugins/<plugin>/scripts. A wrong depth would surface
# as `ModuleNotFoundError: No module named 'gitify'` at collection, which reads
# as a missing dependency, so it is checked here instead.
PLUGIN, SCRIPT = "gitify-cowork-project", "gitify.py"
SCRIPTS = Path(__file__).resolve().parents[2] / "plugins" / PLUGIN / "scripts"
if not (SCRIPTS / SCRIPT).is_file():
    raise RuntimeError(
        "%s is not where %s lives. This file assumes tests/<plugin>/conftest.py, "
        "two directories below the repo root." % (SCRIPTS, SCRIPT)
    )
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402
from hypothesis import settings  # noqa: E402

import gitify  # noqa: E402  - must follow the sys.path insert above

# CI runs a fixed seed so a red build is always caused by the diff; a developer
# machine explores. The root README, under "Properties", says why.
settings.register_profile("dev", max_examples=50)
settings.register_profile("ci", derandomize=True, max_examples=200)
settings.load_profile("ci" if os.environ.get("CI") else "dev")

CONNECTED = "/Users/owner/Documents/Projects"
PROJECT = CONNECTED + "/Foo Research"
VALUES = {
    "PROJECT_NAME": "Foo Research",
    "SKILL_NAME": "foo-research-history",
    "DESCRIPTION": "Git history for Foo Research. Use when committing its files.",
}
SKILL_REL = "skills/foo-research-history/SKILL.md"


def answers(**overrides):
    """Answers render accepts as they stand. A test overrides the one field its
    guard is aimed at."""
    data = {
        "connected_folder": CONNECTED,
        "project_folder": PROJECT,
        "values": dict(VALUES),
        "instructions": None,
        "ignore": [],
    }
    data.update(overrides)
    return data


class Runner:
    """Drives gitify.py through main(), so argparse defaults are the real ones.

    run() returns (exit code, envelope); the envelope is None when nothing was
    printed, as when the command cannot run. stderr is kept in self.err.
    """

    def __init__(self, tmp_path, capsys):
        self.tmp = tmp_path
        self.stage = tmp_path / "stage"
        self._capsys = capsys
        self.out = self.err = ""

    def run(self, *argv, json_output=True):
        self._capsys.readouterr()
        code = gitify.main([*argv, *(["--json"] if json_output else [])])
        captured = self._capsys.readouterr()
        self.out, self.err = captured.out, captured.err
        if json_output and captured.out:
            return code, json.loads(captured.out)
        return code, None

    def render(self, data, *flags, raw=None):
        path = self.tmp / "answers.json"
        path.write_text(raw if raw is not None else json.dumps(data))
        return self.run("render", "--answers", str(path), "--stage", str(self.stage), *flags)

    def staged(self, rel):
        return (self.stage / rel).read_text()

    def templates_copy(self):
        """A writable copy of the shipped templates, for tests that break one."""
        dst = self.tmp / "templates"
        shutil.copytree(gitify.DEFAULT_TEMPLATES, dst)
        return dst


class Device:
    """A fake $HOME/mnt, and sh to run the device commands in it.

    The commands run on the Cowork device's Linux VM. Running them under sh
    here is the closest a test gets to that.
    """

    def __init__(self, tmp_path):
        self.home = tmp_path / "home"
        self.connected = self.home / "mnt" / "Projects"
        self.project = self.connected / "Foo Research"

    def make(self, docs=True):
        self.project.mkdir(parents=True)
        if docs:
            (self.project / "notes.md").write_text("the owner's own notes\n")
            (self.project / "drafts").mkdir()
            (self.project / "drafts" / "plan.md").write_text("# Plan\n")
        return self.project

    def copy_in(self, env_data):
        for f in env_data["files"]:
            dst = self.project / f["file"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f["staged_path"], dst)

    def sh(self, command):
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(["sh", "-c", command], capture_output=True, text=True, env=env)


@pytest.fixture
def runner(tmp_path, capsys):
    return Runner(tmp_path, capsys)


@pytest.fixture
def device(tmp_path):
    return Device(tmp_path)


# Helpers reach the tests as fixtures, never as `from conftest import ...`.
# README.md, under "Running the tests", says why.


@pytest.fixture
def make_answers():
    return answers


@pytest.fixture
def skill_rel():
    return SKILL_REL


@pytest.fixture
def project():
    return {"connected": CONNECTED, "project": PROJECT, "values": dict(VALUES)}

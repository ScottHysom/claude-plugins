"""Shared fixtures for the scaffold.py suite.

The suite sits here, outside plugins/, because everything under plugins/<name>/
is copied verbatim into every install. A test file beside the script would ship
to everyone who installs the plugin, carrying pytest and hypothesis imports
into a plugin whose scripts are standard-library-only on purpose.
`.github/scripts/check-tests.py placement` fails the build if one moves back.

scaffold.py is a standalone script, not an installed package. It lands wherever
`/plugin marketplace add` puts it and runs against the standard library alone,
so this file reaches across to the plugin's scripts directory and puts it on
sys.path. A new plugin adds tests/<plugin>/conftest.py doing the same;
pytest.ini already collects tests/, so nothing at the repo root needs editing.

pytest and hypothesis are contributor dependencies only. Nothing under plugins/
imports them.
"""

import json
import os
import shutil
import sys
from pathlib import Path

# tests/<plugin>/ mirrors plugins/<plugin>/scripts. The check is not
# decoration: with the suite in a different tree from its subject, a wrong depth
# surfaces as `ModuleNotFoundError: No module named 'scaffold'` at collection, which
# reads as a missing dependency and sends the reader to pip.
PLUGIN, SCRIPT = "cowork-project-scaffold", "scaffold.py"
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

import scaffold  # noqa: E402  - must follow the sys.path insert above

# CI runs a fixed seed so a red build is always caused by the diff; a developer
# machine explores. The root README, under "Properties", says why.
settings.register_profile("dev", max_examples=50)
settings.register_profile("ci", derandomize=True, max_examples=200)
settings.load_profile("ci" if os.environ.get("CI") else "dev")

CONNECTED = "/Users/owner/Documents/Projects"
PROJECT = CONNECTED + "/Foo Research"
VALUES = {
    "PROJECT_NAME": "Foo Research",
    "SKILL_NAME": "update-foo-research-docs",
    "ANCHOR_DOC": "current-state.md",
    "DESCRIPTION": "House style and document rules for Foo Research. Use when editing its documents.",
}
SKILL_REL = "skills/update-foo-research-docs/SKILL.md"


def shipped_markers():
    """Every marker in the shipped templates, as `markers --json` lists them."""
    templates = scaffold.load_templates(scaffold.DEFAULT_TEMPLATES)
    return [mk.as_dict() for t in templates for mk in t.markers]


def resolve_all(markers, fill="Filled.", optional="keep"):
    """A resolution for every marker: each FILL gets `fill`, each OPTIONAL
    section gets `optional`. FILLs inside a deleted section are left out, as
    render requires.
    """
    deleted = set(m["id"] for m in markers if m["kind"] == "optional" and optional == "delete")
    out = {}
    for m in markers:
        if m["inside"] in deleted:
            continue
        if m["kind"] == "optional":
            out[m["id"]] = {"digest": m["digest"], "action": optional}
        else:
            out[m["id"]] = {"digest": m["digest"], "action": "fill", "text": fill}
    return out


def answers(**overrides):
    """Answers render accepts as they stand. A test overrides the one field its
    guard is aimed at."""
    data = {
        "connected_folder": CONNECTED,
        "project_folder": PROJECT,
        "values": dict(VALUES),
        "markers": resolve_all(shipped_markers()),
    }
    data.update(overrides)
    return data


class Runner:
    """Drives scaffold.py through main(), so argparse defaults are the real ones.

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
        code = scaffold.main([*argv, *(["--json"] if json_output else [])])
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
        shutil.copytree(scaffold.DEFAULT_TEMPLATES, dst)
        return dst


@pytest.fixture
def runner(tmp_path, capsys):
    return Runner(tmp_path, capsys)


# Helpers reach the tests as fixtures, never as `from conftest import ...`.
# README.md, under "Running the tests", says why.


@pytest.fixture
def markers():
    return shipped_markers()


@pytest.fixture
def make_answers():
    return answers


@pytest.fixture
def resolve():
    return resolve_all


@pytest.fixture
def skill_rel():
    return SKILL_REL


@pytest.fixture
def project():
    return {"connected": CONNECTED, "project": PROJECT, "values": dict(VALUES)}

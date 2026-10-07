"""What holds for any Project Instructions text and any ignore patterns, not
only the few test_gitify_render.py spells out.

The instructions are the user's own words, moved out of a field they are about
to clear. So render must put them in CLAUDE.md byte for byte, whatever they
contain - braces, HTML comments, carriage returns, headings - and must
not let them leak into any other file.
"""

import contextlib
import io
import json
import os
import tempfile
from unittest import mock

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

import gitify

# Everything but lone surrogates, which JSON can carry and UTF-8 cannot.
INSTRUCTIONS = st.text(st.characters(blacklist_categories=("Cs",)), min_size=1).filter(
    lambda s: s.strip()
)
PATTERN = st.text(
    st.characters(blacklist_categories=("Cs",), blacklist_characters="\n\r"), min_size=1
).filter(lambda s: s.strip())

VALUES = {"PROJECT_NAME": "Foo Research"}


def run(argv):
    """main() with stdout captured by hand. capsys is a fixture, and Hypothesis
    would share one fixture across every example."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = gitify.main(argv)
    return code, json.loads(out.getvalue()) if out.getvalue() else None


def render(tmp, instructions, ignore):
    os.makedirs(tmp)
    answers = os.path.join(tmp, "answers.json")
    with open(answers, "w") as fh:
        json.dump(
            {
                "connected_folder": "/Users/owner/Projects",
                "values": VALUES,
                "instructions": instructions,
                "ignore": ignore,
            },
            fh,
        )
    outputs = os.path.join(tmp, "outputs")
    with mock.patch.object(gitify, "OUTPUTS_ROOT", outputs):
        code, env = run(["render", "--answers", answers, "--json"])
    stage = os.path.join(outputs, gitify.STAGE_DIR)
    assert code == gitify.OK, env["errors"]
    return stage, env


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


class DescribeRender:
    @pytest.mark.spec(
        "render-cmd-copies-instructions-verbatim", "render-cmd-appends-ignore-patterns"
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(INSTRUCTIONS, st.lists(PATTERN, unique=True, max_size=4))
    @example("{{PROJECT_NAME}}\r\n## Dates\n<!-- a note -->", ["*.mov"])
    def it_copies_any_instructions_verbatim_and_nowhere_else(self, instructions, ignore):
        with tempfile.TemporaryDirectory() as tmp:
            bare, _ = render(os.path.join(tmp, "a"), None, [])
            stage, env = render(os.path.join(tmp, "b"), instructions, ignore)

            header = read(os.path.join(bare, "CLAUDE.md"))
            tail = "" if instructions.endswith("\n") else "\n"
            assert read(os.path.join(stage, "CLAUDE.md")) == header + "\n" + instructions + tail

            gitignore = read(os.path.join(stage, ".gitignore"))
            assert gitignore.startswith(read(os.path.join(bare, ".gitignore")))
            for p in ignore:
                assert p + "\n" in gitignore

            for f in env["data"]["commit_files"]:
                rel = os.path.relpath(f["stagedPath"], stage)
                if rel not in ("CLAUDE.md", ".gitignore"):
                    assert read(f["stagedPath"]) == read(os.path.join(bare, rel))

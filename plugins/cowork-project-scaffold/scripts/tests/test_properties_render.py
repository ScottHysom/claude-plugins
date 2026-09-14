"""What holds for every way the interview can resolve the markers, not only
the few test_render.py spells out.

The generator draws a resolution for each marker - any fill text, an empty
fill, a left marker, a kept or deleted section. render either refuses it for a
reason it names, or accepts it, and then two things must be true of the
output: nothing survives that the model did not leave on purpose,
and drift sees the generated skill as the template it came from. The second is
the one worth having: it ties render and drift together, so a change to how
one of them treats markers that the other does not follow fails here.

Fill text is drawn from an alphabet with no braces, colons or `#`, so it can
never spell a marker, a placeholder or a level-2 heading. A fill that adds a
`## ` heading does show as drift, by design; test_drift.py is where that
behaviour would be pinned if it changed.
"""

import contextlib
import io
import json
import os
import tempfile

from hypothesis import HealthCheck, event, example, given, settings
from hypothesis import strategies as st

import scaffold

TEXT = st.text(alphabet="abc XY-*|`.\n", max_size=40)
LINE = st.text(alphabet="abc XY-*|`.", max_size=20)

# The markers and conftest values, fetched once. Fixtures cannot be used inside
# @given without Hypothesis reusing them across examples, which would share a
# stage directory between examples.
MARKERS = [
    mk.as_dict() for t in scaffold.load_templates(scaffold.DEFAULT_TEMPLATES) for mk in t.markers
]
VALUES = {
    "PROJECT_NAME": "Foo Research",
    "SKILL_NAME": "update-foo-research-docs",
    "ANCHOR_DOC": "current-state.md",
    "DESCRIPTION": "Document rules for Foo Research.",
}


@st.composite
def resolutions(draw):
    out, deleted = {}, set()
    for m in MARKERS:
        if m["inside"] in deleted:
            continue
        if m["kind"] == "optional":
            action = draw(st.sampled_from(["keep", "delete"]))
            if action == "delete":
                deleted.add(m["id"])
            out[m["id"]] = {"digest": m["digest"], "action": action}
            continue
        choice = draw(st.sampled_from(["fill", "empty", "leave"]))
        if choice == "leave":
            out[m["id"]] = {"digest": m["digest"], "action": "leave"}
        else:
            text = "" if choice == "empty" else draw(TEXT if m["form"] == "block" else LINE)
            out[m["id"]] = {"digest": m["digest"], "action": "fill", "text": text}
    return out


# Refusals the generator can provoke. Anything else refused is a bug.
EXPECTED_REFUSALS = ("opens a code fence it does not close",)


def fence_left_open():
    """The first counterexample this property found: a fill of three backticks
    in the maintenance skill, which opened a fence nothing closed."""
    out, deleted = {}, set()
    for m in MARKERS:
        if m["inside"] in deleted:
            continue
        if m["kind"] == "optional":
            out[m["id"]] = {"digest": m["digest"], "action": "keep"}
        else:
            text = "```" if m["id"] == "maintain-docs.md:fill-2" else ""
            out[m["id"]] = {"digest": m["digest"], "action": "fill", "text": text}
    return out


def run(argv):
    """main() with stdout captured by hand; capsys is a fixture, see above."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = scaffold.main(argv)
    return code, json.loads(out.getvalue()) if out.getvalue() else None


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(resolutions())
@example(fence_left_open())
def test_any_resolution_renders_clean_and_does_not_drift(markers):
    left = [k for k, v in markers.items() if v["action"] == "leave"]
    event("left %d" % min(len(left), 3))
    event("deleted %d" % sum(1 for v in markers.values() if v["action"] == "delete"))
    with tempfile.TemporaryDirectory() as tmp:
        answers = os.path.join(tmp, "answers.json")
        with open(answers, "w") as fh:
            json.dump(
                {
                    "connected_folder": "/Users/owner/Documents/Projects",
                    "values": VALUES,
                    "markers": markers,
                },
                fh,
            )
        stage = os.path.join(tmp, "stage")
        code, env = run(["render", "--answers", answers, "--stage", stage, "--json"])
        if code == scaffold.PROBLEMS:
            event("refused")
            assert env["errors"], "refused with no reason"
            for e in env["errors"]:
                assert e.startswith("nothing was") or any(r in e for r in EXPECTED_REFUSALS), e
            return
        assert code == scaffold.OK, env and env["errors"]
        assert sorted(x["id"] for x in env["data"]["left"]) == sorted(left)

        fills = 0
        for f in env["data"]["files"]:
            with open(f["staged_path"], encoding="utf-8") as fh:
                text = fh.read()
            assert "OPTIONAL SECTION" not in text
            assert "{{" not in text
            fills += text.count("<!-- FILL:")
        # Counted here rather than trusted from render's own check, so a render
        # that miscounts its leftovers is caught by something other than itself.
        assert fills == len(left)

        skill = os.path.join(stage, "skills", VALUES["SKILL_NAME"], "SKILL.md")
        code, env = run(["drift", "--skill", skill, "--json"])
        assert code == scaffold.OK, env["errors"]

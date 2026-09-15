"""preflight is what CI leans on to catch a template edit that breaks the
scaffold: a marker the parser cannot read would otherwise be copied into
every new project unnoticed, and a new template left out of the manifest would
never ship at all.
"""

import pytest

import scaffold


def test_the_shipped_templates_are_clean(runner):
    code, env = runner.run("preflight")
    assert code == scaffold.OK
    assert env["errors"] == []
    assert env["command"] == "preflight"


def test_human_output_goes_to_stdout(runner):
    code, _ = runner.run("preflight", json_output=False)
    assert code == scaffold.OK
    assert "ok" in runner.out
    assert runner.err == ""


def test_a_template_missing_from_disk_is_named(runner):
    templates = runner.templates_copy()
    (templates / "commit.sh").unlink()
    code, env = runner.run("preflight", "--templates", str(templates))
    assert code == scaffold.PROBLEMS
    assert any("commit.sh is in the manifest" in e for e in env["errors"])


def test_a_template_missing_from_the_manifest_is_named(runner):
    templates = runner.templates_copy()
    (templates / "extra.md").write_text("# Extra\n")
    code, env = runner.run("preflight", "--templates", str(templates))
    assert code == scaffold.PROBLEMS
    assert any("extra.md" in e and "never ship" in e for e in env["errors"])


def test_an_unknown_placeholder_is_named(runner):
    templates = runner.templates_copy()
    with open(templates / "gitignore", "a") as fh:
        fh.write("{{NOT_A_THING}}\n")
    code, env = runner.run("preflight", "--templates", str(templates))
    assert code == scaffold.PROBLEMS
    assert any("{{NOT_A_THING}}" in e for e in env["errors"])


def test_a_missing_templates_directory_is_a_problem_not_a_crash(runner):
    code, env = runner.run("preflight", "--templates", str(runner.tmp / "nowhere"))
    assert code == scaffold.PROBLEMS
    assert any("not found" in e for e in env["errors"])


BROKEN = [
    (
        "<!-- OPTIONAL SECTION. no end -->\n## A\n",
        "has no END OPTIONAL SECTION",
    ),
    (
        "text\n<!-- END OPTIONAL SECTION -->\n",
        "with no section open",
    ),
    (
        "<!-- OPTIONAL SECTION. a -->\n<!-- OPTIONAL SECTION. b -->\n"
        "<!-- END OPTIONAL SECTION -->\n<!-- END OPTIONAL SECTION -->\n",
        "opened inside",
    ),
    (
        "text <!-- OPTIONAL SECTION. inline --> more\n<!-- END OPTIONAL SECTION -->\n",
        "must stand on lines of its own",
    ),
    (
        "<!-- OPTIONAL SECTION. a -->\nbody <!-- END OPTIONAL SECTION -->\n",
        "must stand on its own line",
    ),
    (
        "Write FILL: here without a comment.\n",
        "outside any marker",
    ),
    (
        "a stray {{ brace\n",
        "outside any marker or placeholder",
    ),
    (
        "<!-- FILL: never closed\n",
        "never closed",
    ),
]


@pytest.mark.parametrize(("source", "message"), BROKEN)
def test_a_malformed_marker_is_named(source, message):
    t = scaffold.Template("x.md", source)
    assert any(message in e for e in t.errors), t.errors


def test_an_unrelated_comment_is_not_a_marker():
    t = scaffold.Template("x.md", "<!-- prose-rule: source=shipped -->\n")
    assert t.errors == []
    assert t.markers == []


def test_a_malformed_template_stops_render(runner):
    templates = runner.templates_copy()
    with open(templates / "gitignore", "a") as fh:
        fh.write("<!-- OPTIONAL SECTION. no end -->\n")
    path = runner.tmp / "answers.json"
    path.write_text("{}")
    code, env = runner.run("render", "--answers", str(path), "--templates", str(templates))
    assert code == scaffold.CANNOT_RUN
    assert env is None
    assert "template is malformed" in runner.err

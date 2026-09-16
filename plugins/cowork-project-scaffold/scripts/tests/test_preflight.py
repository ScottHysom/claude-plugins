"""preflight is what CI leans on to catch a template edit that breaks the
scaffold: a marker the parser cannot read would otherwise be copied into
every new project unnoticed, and a new template left out of the manifest would
never ship at all.
"""

import pytest

import scaffold


class DescribePreflight:
    def it_finds_the_shipped_templates_clean(self, runner):
        code, env = runner.run("preflight")
        assert code == scaffold.OK
        assert env["errors"] == []
        assert env["command"] == "preflight"

    def it_writes_human_output_to_stdout(self, runner):
        code, _ = runner.run("preflight", json_output=False)
        assert code == scaffold.OK
        assert "ok" in runner.out
        assert runner.err == ""

    def it_names_a_template_missing_from_disk(self, runner):
        templates = runner.templates_copy()
        (templates / "commit.sh").unlink()
        code, env = runner.run("preflight", "--templates", str(templates))
        assert code == scaffold.PROBLEMS
        assert any("commit.sh is in the manifest" in e for e in env["errors"])

    def it_names_a_template_missing_from_the_manifest(self, runner):
        templates = runner.templates_copy()
        (templates / "extra.md").write_text("# Extra\n")
        code, env = runner.run("preflight", "--templates", str(templates))
        assert code == scaffold.PROBLEMS
        assert any("extra.md" in e and "never ship" in e for e in env["errors"])

    def it_names_an_unknown_placeholder(self, runner):
        templates = runner.templates_copy()
        with open(templates / "gitignore", "a") as fh:
            fh.write("{{NOT_A_THING}}\n")
        code, env = runner.run("preflight", "--templates", str(templates))
        assert code == scaffold.PROBLEMS
        assert any("{{NOT_A_THING}}" in e for e in env["errors"])

    def it_reports_a_missing_templates_directory_rather_than_crashing(self, runner):
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


class DescribeTemplateErrors:
    """What preflight reads: the errors a Template collects as it parses."""

    @pytest.mark.parametrize(("source", "message"), BROKEN)
    def it_names_a_malformed_marker(self, source, message):
        t = scaffold.Template("x.md", source)
        assert any(message in e for e in t.errors), t.errors

    def it_does_not_take_an_unrelated_comment_for_a_marker(self):
        t = scaffold.Template("x.md", "<!-- prose-rule: source=shipped -->\n")
        assert t.errors == []
        assert t.markers == []


class DescribeRender:
    def it_refuses_to_render_a_malformed_template(self, runner):
        templates = runner.templates_copy()
        with open(templates / "gitignore", "a") as fh:
            fh.write("<!-- OPTIONAL SECTION. no end -->\n")
        path = runner.tmp / "answers.json"
        path.write_text("{}")
        code, env = runner.run("render", "--answers", str(path), "--templates", str(templates))
        assert code == scaffold.CANNOT_RUN
        assert env is None
        assert "template is malformed" in runner.err

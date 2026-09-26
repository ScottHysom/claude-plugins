"""preflight is what catches a template edit that breaks the plugin: a mistyped
placeholder would otherwise be copied into every project unnoticed, and a new
template left out of the manifest would never ship at all.
"""

import pytest

import gitify


class DescribePreflight:
    @pytest.mark.spec("preflight-templates")
    def it_finds_the_shipped_templates_clean(self, runner):
        code, env = runner.run("preflight")
        assert code == gitify.OK
        assert env["errors"] == []
        assert env["command"] == "preflight"

    @pytest.mark.spec("repo:plain-output-streams")
    def it_writes_human_output_to_stdout(self, runner):
        code, _ = runner.run("preflight", json_output=False)
        assert code == gitify.OK
        assert "ok" in runner.out
        assert runner.err == ""

    @pytest.mark.spec("preflight-templates")
    def it_names_a_template_missing_from_disk(self, runner):
        templates = runner.templates_copy()
        (templates / "commit.sh").unlink()
        code, env = runner.run("preflight", "--templates", str(templates))
        assert code == gitify.PROBLEMS
        assert any("commit.sh is in the manifest" in e for e in env["errors"])

    @pytest.mark.spec("preflight-templates")
    def it_names_a_template_missing_from_the_manifest(self, runner):
        templates = runner.templates_copy()
        (templates / "extra.md").write_text("# Extra\n")
        code, env = runner.run("preflight", "--templates", str(templates))
        assert code == gitify.PROBLEMS
        assert any("extra.md" in e and "never ship" in e for e in env["errors"])

    @pytest.mark.spec("preflight-templates")
    def it_names_an_unknown_placeholder(self, runner):
        templates = runner.templates_copy()
        with open(templates / "CLAUDE.md", "a") as fh:
            fh.write("{{NOT_A_THING}}\n")
        code, env = runner.run("preflight", "--templates", str(templates))
        assert code == gitify.PROBLEMS
        assert any("{{NOT_A_THING}}" in e for e in env["errors"])

    @pytest.mark.spec("preflight-templates")
    def it_names_a_stray_brace_with_its_line(self, runner):
        templates = runner.templates_copy()
        (templates / "gitignore").write_text("one\n{{PROJECT_NAME}\n")
        code, env = runner.run("preflight", "--templates", str(templates))
        assert code == gitify.PROBLEMS
        assert any(e.startswith("gitignore:2") and "'{{'" in e for e in env["errors"])

    @pytest.mark.spec("preflight-templates")
    def it_reports_a_missing_templates_directory_rather_than_crashing(self, runner):
        code, env = runner.run("preflight", "--templates", str(runner.tmp / "nowhere"))
        assert code == gitify.PROBLEMS
        assert any("not found" in e for e in env["errors"])

    @pytest.mark.spec("render-no-leftovers")
    def it_refuses_to_render_from_a_malformed_template(self, runner, make_answers):
        templates = runner.templates_copy()
        (templates / "gitignore").write_text("a stray }} brace\n")
        path = runner.tmp / "answers.json"
        path.write_text("{}")
        code, env = runner.run("render", "--answers", str(path), "--templates", str(templates))
        assert code == gitify.CANNOT_RUN
        assert env is None
        assert "template is malformed" in runner.err

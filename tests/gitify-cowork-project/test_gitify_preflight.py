"""preflight is what catches a template edit that breaks the plugin: a mistyped
placeholder would otherwise be copied into every project unnoticed, and a new
template left out of the manifest would never ship at all.
"""

import sys

import pytest

import gitify


class ClosedPipe:
    """A stdout whose reader has gone, as when a command is piped into head."""

    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")


class DescribePreflight:
    @pytest.mark.spec("preflight-cmd-names-template-problems")
    def it_finds_the_shipped_templates_clean(self, runner):
        code, env = runner.run("preflight")
        assert code == gitify.OK
        assert env["errors"] == []
        assert env["command"] == "preflight"

    @pytest.mark.spec("repo:command-splits-output-streams")
    def it_writes_human_output_to_stdout(self, runner):
        code, _ = runner.run("preflight", json_output=False)
        assert code == gitify.OK
        assert "ok" in runner.out
        assert runner.err == ""

    @pytest.mark.spec("repo:command-splits-output-streams")
    def it_writes_its_problems_to_stderr_in_plain_output(self, runner):
        templates = runner.templates_copy()
        (templates / "commit.sh").unlink()
        code, _ = runner.run("preflight", json_output=False)
        assert code == gitify.PROBLEMS
        assert runner.out == ""
        assert "commit.sh is in the manifest" in runner.err

    @pytest.mark.spec("repo:script-ignores-closed-pipe")
    def it_exits_ok_when_its_reader_closes_the_pipe(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdout", ClosedPipe())
        assert gitify.main(["preflight", "--json"]) == gitify.OK
        assert capsys.readouterr().err == ""

    @pytest.mark.spec("preflight-cmd-names-template-problems")
    @pytest.mark.parametrize("name", ["commit.sh", gitify.HISTORY_TEMPLATE])
    def it_names_a_template_missing_from_disk(self, runner, name):
        templates = runner.templates_copy()
        (templates / name).unlink()
        code, env = runner.run("preflight")
        assert code == gitify.PROBLEMS
        assert any(name + " is in the manifest" in e for e in env["errors"])

    @pytest.mark.spec("preflight-cmd-names-template-problems")
    def it_names_a_template_missing_from_the_manifest(self, runner):
        templates = runner.templates_copy()
        (templates / "extra.md").write_text("# Extra\n")
        code, env = runner.run("preflight")
        assert code == gitify.PROBLEMS
        assert any("extra.md" in e and "never ship" in e for e in env["errors"])

    @pytest.mark.spec("preflight-cmd-names-template-problems")
    def it_names_an_unknown_placeholder(self, runner):
        templates = runner.templates_copy()
        with open(templates / "CLAUDE.md", "a") as fh:
            fh.write("{{NOT_A_THING}}\n")
        code, env = runner.run("preflight")
        assert code == gitify.PROBLEMS
        assert any("{{NOT_A_THING}}" in e for e in env["errors"])

    @pytest.mark.spec("preflight-cmd-names-template-problems")
    def it_names_a_stray_brace_with_its_line(self, runner):
        templates = runner.templates_copy()
        (templates / "gitignore").write_text("one\n{{PROJECT_NAME}\n")
        code, env = runner.run("preflight")
        assert code == gitify.PROBLEMS
        assert any(e.startswith("gitignore:2") and "'{{'" in e for e in env["errors"])

    @pytest.mark.spec("preflight-cmd-names-template-problems")
    def it_names_a_section_line_that_would_end_the_heredoc(self, runner):
        templates = runner.templates_copy()
        with open(templates / gitify.HISTORY_TEMPLATE, "a") as fh:
            fh.write(gitify.HEREDOC_END + "\n")
        code, env = runner.run("preflight")
        assert code == gitify.PROBLEMS
        assert any("end history's heredoc" in e for e in env["errors"])

    @pytest.mark.spec("preflight-cmd-names-template-problems")
    def it_names_a_section_without_its_heading(self, runner):
        templates = runner.templates_copy()
        (templates / gitify.HISTORY_TEMPLATE).write_text("## History\n")
        code, env = runner.run("preflight")
        assert code == gitify.PROBLEMS
        assert any("would append it again" in e for e in env["errors"])

    @pytest.mark.spec("preflight-cmd-names-template-problems")
    def it_reports_a_missing_templates_directory_rather_than_crashing(self, runner):
        runner.use_templates(runner.tmp / "nowhere")
        code, env = runner.run("preflight")
        assert code == gitify.PROBLEMS
        assert any("not found" in e for e in env["errors"])

    @pytest.mark.spec("render-cmd-refuses-leftover-placeholders")
    def it_refuses_to_render_from_a_malformed_template(self, runner, make_answers):
        templates = runner.templates_copy()
        (templates / "gitignore").write_text("a stray }} brace\n")
        path = runner.tmp / "answers.json"
        path.write_text("{}")
        code, env = runner.run("render", "--answers", str(path))
        assert code == gitify.CANNOT_RUN
        assert env is None
        assert "template is malformed" in runner.err

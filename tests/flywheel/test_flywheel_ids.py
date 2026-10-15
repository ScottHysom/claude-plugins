"""What `flywheel.py ids` finds when a method id is cited and not defined."""

import os

import pytest

import flywheel

SPEC = "specs/flywheel.md"
DEFINED = "one-home-per-artifact"


@pytest.fixture
def plugin(plugin_copy):
    """A copy of the plugin, whose docs, skills and templates a test can change."""
    return plugin_copy


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.mark.spec("ids-cmd-fails-unknown-id")
class DescribeAnUnknownId:
    def it_names_an_id_the_spec_cites_and_the_docs_do_not_define(self, project, plugin):
        project.write(SPEC, "# flywheel\n\nSource: #1, and the method's `no-such-rule`.\n")
        code, env = project.run("ids")
        assert code == flywheel.PROBLEMS
        assert env["data"]["unknown"] == [{"id": "no-such-rule", "file": SPEC, "line": 3}]
        assert env["errors"] == [
            "specs/flywheel.md:3: `no-such-rule` is cited as the method's, and no document"
            " under docs/ defines it. Correct the citation, or define the id in the method's"
            " docs."
        ]

    def it_names_an_id_a_skill_cites(self, project, plugin):
        write(plugin, "skills/run/SKILL.md", "# Run\n\nThis follows the method's `made-up-id`.\n")
        code, env = project.run("ids")
        assert code == flywheel.PROBLEMS
        assert env["data"]["unknown"] == [
            {"id": "made-up-id", "file": "skills/run/SKILL.md", "line": 3}
        ]

    def it_names_an_id_a_template_cites(self, project, plugin):
        write(plugin, "templates/policy.md", "Per the method's\n`made-up-id`.\n")
        code, env = project.run("ids")
        assert code == flywheel.PROBLEMS
        assert env["data"]["unknown"] == [
            {"id": "made-up-id", "file": "templates/policy.md", "line": 2}
        ]

    def it_reads_every_id_in_the_citing_sentence(self, project, plugin):
        project.write(SPEC, "Source: the method's `%s`, `bad-one` and\n`bad-two`.\n" % DEFINED)
        code, env = project.run("ids")
        assert code == flywheel.PROBLEMS
        assert [(u["id"], u["line"]) for u in env["data"]["unknown"]] == [
            ("bad-one", 1),
            ("bad-two", 2),
        ]

    def it_names_the_unknown_id_in_text_on_stderr(self, project, plugin):
        project.write(SPEC, "Source: the method's `no-such-rule`.\n")
        code, out, err = project.human("ids")
        assert code == flywheel.PROBLEMS
        assert out == ""
        assert err.startswith("specs/flywheel.md:1: `no-such-rule` is cited")


@pytest.mark.spec("ids-cmd-fails-unknown-id")
class DescribeWhatCountsAsACitation:
    def it_passes_an_id_the_docs_define(self, project, plugin):
        project.write(SPEC, "Source: the method's `%s`.\n" % DEFINED)
        code, env = project.run("ids")
        assert code == flywheel.OK
        assert env["data"] == {"files": ["templates/roles.json", SPEC], "unknown": []}

    def it_passes_a_stage_rule_id(self, project, plugin):
        project.write(SPEC, "Source: the method's `one-command-per-gate`.\n")
        assert project.run("ids")[0] == flywheel.OK

    def it_ignores_backticks_outside_the_citing_sentence(self, project, plugin):
        project.write(
            SPEC,
            "Source: the method's `%s`. Then `setup-cmd-copies-script`.\n\n"
            "the method's\n\n`other-id` sits in the next paragraph.\n" % DEFINED,
        )
        code, env = project.run("ids")
        assert code == flywheel.OK, env["errors"]

    def it_ignores_backticked_text_that_is_not_an_id(self, project, plugin):
        project.write(SPEC, "Source: the method's `roles.md` and `README`.\n")
        assert project.run("ids")[0] == flywheel.OK

    def it_runs_without_a_spec_in_the_repo(self, project, plugin):
        code, env = project.run("ids")
        assert code == flywheel.OK
        assert env["data"]["files"] == ["templates/roles.json"]

    def it_says_what_it_checked_in_text(self, project, plugin):
        code, out, err = project.human("ids")
        assert code == flywheel.OK
        assert out == "every method id cited in 1 files is defined\n"
        assert err == ""


@pytest.mark.spec("ids-cmd-fails-unknown-id")
class DescribeTheShippedPlugin:
    def it_finds_every_id_this_repo_cites_defined(self, capsys):
        repo = os.path.dirname(os.path.abspath(__file__))
        code = flywheel.main(["ids", "-C", str(repo)])
        assert code == flywheel.OK, capsys.readouterr().err


@pytest.mark.spec("ids-cmd-fails-unknown-id")
class DescribeWhenItCannotRun:
    def it_stops_when_run_from_the_copy(self, project, monkeypatch):
        project.run("setup")
        copy = project.root / ".flywheel" / "flywheel.py"
        monkeypatch.setattr(flywheel, "SCRIPT_PATH", str(copy))
        code, _ = project.run("ids")
        assert code == flywheel.CANNOT_RUN
        assert "Run the plugin's own scripts/flywheel.py" in project.err

    def it_stops_when_the_docs_define_no_id(self, project, plugin):
        for doc in (plugin / "docs").iterdir():
            doc.write_text("# Empty\n\n| Stage | Rule |\n| --- | --- |\n| Spec | not-an-id |\n")
        code, _ = project.run("ids")
        assert code == flywheel.CANNOT_RUN
        assert "defines a method id" in project.err

    def it_stops_on_a_file_that_is_not_utf8(self, project, plugin):
        (project.root / "specs").mkdir()
        (project.root / SPEC).write_bytes(b"\xff\xfe")
        code, _ = project.run("ids")
        assert code == flywheel.CANNOT_RUN
        assert "is not UTF-8 text" in project.err


@pytest.mark.spec("ids-cmd-fails-unknown-id")
class DescribeWhereIdsAreDefined:
    def it_reads_definitions_only_from_markdown(self, project, plugin):
        write(plugin, "docs/extra.txt", "| ID |\n| --- |\n| txt-only-id |\n")
        project.write(SPEC, "Source: the method's `txt-only-id`.\n")
        assert project.run("ids")[0] == flywheel.PROBLEMS

    def it_reads_definitions_from_any_markdown_under_docs(self, project, plugin):
        write(plugin, "docs/extra.md", "| Stage | ID |\n| --- | --- |\n| Spec | extra-rule |\n")
        project.write(SPEC, "Source: the method's `extra-rule`.\n")
        assert project.run("ids")[0] == flywheel.OK

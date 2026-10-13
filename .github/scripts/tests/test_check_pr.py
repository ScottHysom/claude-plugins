"""What check-pr.py promises about a pull request's description.

The tests of `description` in CI write the event GitHub Actions would, with
the description as the pull request's body. The tests of a draft write it to
a file, and the tests of `open` replace git and gh with a fake that records
each call.
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-pr.py"
_spec = importlib.util.spec_from_file_location("check_pr", _PATH)
cpr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpr)

SCENARIO = (
    "## Scenario\n\n"
    "An agent opens a pull request.\n\n"
    "### Before\n\n"
    "CI passed any description.\n\n"
    "### After\n\n"
    "CI fails one that does not open with its scenario.\n\n"
    "## Change\n\n"
    "Adds `check-pr.py description`.\n\n"
    "Closes #566\n"
)


@pytest.fixture
def run(capsys, tmp_path):
    """Run `description` through main() on a pull request with `body`."""

    def go(body, *argv, event=None):
        path = tmp_path / "event.json"
        if event is None:
            event = {"pull_request": {"title": "t", "body": body}}
        path.write_text(json.dumps(event))
        capsys.readouterr()
        code = cpr.main(["description", *argv], environ={cpr.EVENT_ENV: str(path)})
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


class DescribeDescription:
    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_passes_a_description_that_opens_with_its_scenario(self, run):
        code, out, err = run(SCENARIO)
        assert code == cpr.OK
        assert out == "The description opens with `## Scenario`.\n"
        assert err == ""

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_fails_a_description_that_opens_with_another_heading(self, run):
        code, out, err = run("## Summary\n\n- Adds a check.\n\n" + SCENARIO)
        assert code == cpr.PROBLEMS
        assert out == ""
        assert "first heading is `## Summary`" in err
        assert 'CLAUDE.md, under "Workflow"' in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_fails_a_scenario_heading_at_another_level(self, run):
        code, _, err = run("#" + SCENARIO)
        assert code == cpr.PROBLEMS
        assert "first heading is `### Scenario`" in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    @pytest.mark.parametrize("body", ["", "Adds a check.\n\nCloses #566\n"])
    def it_fails_a_description_without_a_heading(self, run, body):
        code, _, err = run(body)
        assert code == cpr.PROBLEMS
        assert "has no heading" in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_fails_a_pull_request_without_a_body(self, run):
        code, _, err = run(None, event={"pull_request": {"title": "t", "body": None}})
        assert code == cpr.PROBLEMS
        assert "has no heading" in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    @pytest.mark.parametrize(
        "before",
        [
            "```markdown\n## Summary\n```\n\n",
            "~~~~\n## Summary\n~~~\nstill fenced\n~~~~\n\n",
            "```\n``` text after a fence does not close it\n## Summary\n```\n\n",
            "<!-- ## Summary -->\n",
            "<!--\n# Summary\n-->\n",
            "    ## Summary, indented as code\n\n",
            "#Summary is not a heading\n\n",
        ],
    )
    def it_ignores_what_github_does_not_render_as_a_heading(self, run, before):
        code, _, err = run(before + SCENARIO)
        assert code == cpr.OK, err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_reads_a_heading_with_closing_hashes(self, run):
        code, _, err = run(SCENARIO.replace("## Scenario", "## Scenario ##", 1))
        assert code == cpr.OK, err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    @pytest.mark.parametrize(
        "section",
        ["", "\n\n   \n", "<!-- who, before, after -->\n"],
    )
    def it_fails_an_empty_scenario(self, run, section):
        body = "## Scenario\n" + section + "## Change\n\nAdds a check.\n"
        code, _, err = run(body)
        assert code == cpr.PROBLEMS
        assert "`## Scenario` section is empty" in err
        assert 'CLAUDE.md, under "Workflow"' in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_fails_a_scenario_that_ends_the_description_empty(self, run):
        code, _, err = run("## Scenario\n\n")
        assert code == cpr.PROBLEMS
        assert "section is empty" in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_counts_a_subheading_as_part_of_the_scenario(self, run):
        body = "## Scenario\n\n### Before\n\nCI passed it.\n\n## Change\n\nA check.\n"
        code, _, err = run(body)
        assert "section is empty" not in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_ends_the_scenario_at_a_top_level_heading(self, run):
        code, _, err = run("## Scenario\n\n# Change\n\nA check.\n")
        assert code == cpr.PROBLEMS
        assert "section is empty" in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_reads_a_description_written_with_crlf(self, run):
        code, _, err = run(SCENARIO.replace("\n", "\r\n"))
        assert code == cpr.OK, err


def scenario(before="CI passed it.\n\n", after="CI fails it.\n\n"):
    """A description whose Scenario holds `before` and `after` as given."""
    return "## Scenario\n\nAn agent opens a pull request.\n\n" + before + after + "## Change\n"


class DescribeBeforeAndAfter:
    @pytest.mark.spec("description-cmd-requires-before-after")
    def it_passes_a_before_and_an_after_of_several_paragraphs(self, run):
        body = scenario("### Before\n\nOne.\n\nTwo.\n\n", "### After\n\nThree.\n\n- four\n\n")
        code, _, err = run(body)
        assert code == cpr.OK, err

    @pytest.mark.spec("description-cmd-requires-before-after")
    @pytest.mark.parametrize(
        ("before", "after", "missing"),
        [
            ("Before: CI passed it.\n\n", "### After\n\nCI fails it.\n\n", "### Before"),
            ("### Before\n\nCI passed it.\n\n", "After: CI fails it.\n\n", "### After"),
            ("#### Before\n\nCI passed it.\n\n", "### After\n\nCI fails it.\n\n", "### Before"),
        ],
    )
    def it_fails_a_scenario_without_either_subsection(self, run, before, after, missing):
        code, out, err = run(scenario(before, after))
        assert code == cpr.PROBLEMS
        assert out == ""
        assert "has no `%s` subsection" % missing in err
        assert 'CLAUDE.md, under "Workflow"' in err

    @pytest.mark.spec("description-cmd-requires-before-after")
    def it_fails_a_subsection_after_the_scenario_ends(self, run):
        body = scenario("### Before\n\nCI passed it.\n\n", "") + "\n### After\n\nCI fails it.\n"
        code, _, err = run(body)
        assert code == cpr.PROBLEMS
        assert "has no `### After` subsection" in err

    @pytest.mark.spec("description-cmd-requires-before-after")
    @pytest.mark.parametrize(
        ("before", "after", "empty"),
        [
            ("### Before\n\n", "### After\n\nCI fails it.\n\n", "### Before"),
            ("### Before\n\n<!-- todo -->\n\n", "### After\n\nCI fails it.\n\n", "### Before"),
            ("### Before\n\nCI passed it.\n\n", "### After\n\n", "### After"),
        ],
    )
    def it_fails_an_empty_subsection(self, run, before, after, empty):
        code, _, err = run(scenario(before, after))
        assert code == cpr.PROBLEMS
        assert "the `%s` subsection is empty" % empty in err

    @pytest.mark.spec("description-cmd-requires-before-after")
    def it_fails_an_after_that_comes_first(self, run):
        body = scenario("### After\n\nCI fails it.\n\n", "### Before\n\nCI passed it.\n\n")
        code, _, err = run(body)
        assert code == cpr.PROBLEMS
        assert "puts `### After` before `### Before`" in err

    @pytest.mark.spec("description-cmd-requires-before-after")
    def it_reads_a_deeper_heading_as_part_of_the_subsection(self, run):
        after = "### After\n\nCI fails it.\n\n"
        code, _, err = run(scenario("### Before\n\n#### Detail\n\nCI passed it.\n\n", after))
        assert code == cpr.OK, err


class DescribeSplitLines:
    @pytest.mark.spec("description-cmd-refuses-split-lines")
    def it_names_each_line_that_continues_a_paragraph(self, run):
        body = SCENARIO.replace("CI passed any description.", "CI passed\nany\ndescription.")
        code, out, err = run(body)
        assert code == cpr.PROBLEMS
        assert out == ""
        lines = body.splitlines()
        named = [int(e.split()[1]) for e in err.splitlines() if e.startswith("line ")]
        assert [lines[n - 1] for n in named] == ["any", "description."]
        assert "join the line to the one above" in err

    @pytest.mark.spec("description-cmd-refuses-split-lines")
    def it_names_a_line_that_continues_a_list_item(self, run):
        body = SCENARIO + "\n- adds a check\n  that fails it\n- and a test\n"
        code, _, err = run(body)
        assert code == cpr.PROBLEMS
        assert "line %d continues" % len(body.splitlines()[:-1]) in err
        assert err.count("continues the paragraph") == 1

    @pytest.mark.spec("description-cmd-refuses-split-lines")
    @pytest.mark.parametrize(
        "block",
        [
            "- one\n- two\n  - nested\n1. three\n2) four\n",
            "| a | b |\n|---|---|\n| 1 | 2 |\n",
            "> quoted\n> still quoted\n",
            "<details>\n<summary>more</summary>\n</details>\n",
            "Text\n---\n",
            "Text\n===\n",
            "```sh\npython3 x.py\n  --json\n```\n",
            "<!--\nnote\nmore note\n-->\n",
            "Text\n\n    code line\n    more code\n\n    still code\n",
            "Text\n<!-- spec: x -->\n",
            "Text\n### Heading\nText\n",
        ],
    )
    def it_passes_lines_that_github_does_not_join(self, run, block):
        code, _, err = run(SCENARIO + "\n" + block)
        assert code == cpr.OK, err

    @pytest.mark.spec("description-cmd-refuses-split-lines")
    def it_names_the_line_the_author_wrote_after_a_long_comment(self, run):
        body = "<!--\none\ntwo\n-->\n" + SCENARIO + "\nfirst\nsecond\n"
        code, _, err = run(body)
        assert code == cpr.PROBLEMS
        assert "line %d continues" % len(body.splitlines()) in err

    @pytest.mark.spec("description-cmd-refuses-split-lines", "open-cmd-refuses-failing-draft")
    def it_stops_open_from_pushing_a_split_draft(self, capsys, draft, shell):
        fake = shell()
        body = SCENARIO.replace("CI passed any description.", "CI passed\nany description.")
        code = cpr.main(["open", "--title", "t", "--body-file", draft(body)])
        assert code == cpr.PROBLEMS
        assert fake.calls == []
        assert "continues the paragraph" in capsys.readouterr().err


class DescribeDescriptionOutput:
    @pytest.mark.spec("command-prints-json-envelope")
    def it_prints_the_envelope_with_what_it_read(self, run):
        code, out, err = run(SCENARIO, "--json")
        assert code == cpr.OK
        assert err == ""
        result = json.loads(out)
        assert sorted(result) == ["command", "data", "errors", "ok", "version", "warnings"]
        assert result["command"] == "description"
        assert result["data"]["first_heading"] == "## Scenario"
        assert result["data"]["scenario"].startswith("An agent opens a pull request.")

    @pytest.mark.spec("command-prints-json-envelope")
    def it_prints_problems_in_the_envelope(self, run):
        code, out, err = run("## Summary\n", "--json")
        assert code == cpr.PROBLEMS
        assert err == ""
        result = json.loads(out)
        assert result["ok"] is False
        assert result["data"] == {"first_heading": "## Summary", "scenario": None}
        assert "`## Summary`" in result["errors"][0]


class DescribeDescriptionOutsideCI:
    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_stops_outside_a_pull_request_event(self, capsys):
        assert cpr.main(["description"], environ={}) == cpr.CANNOT_RUN
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("check-pr.py: GITHUB_EVENT_PATH is not set")

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_stops_on_an_event_it_cannot_read(self, capsys, tmp_path):
        path = tmp_path / "event.json"
        path.write_text("{")
        assert cpr.main(["description"], environ={cpr.EVENT_ENV: str(path)}) == cpr.CANNOT_RUN
        assert "cannot read the event" in capsys.readouterr().err

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_stops_on_an_event_that_is_not_a_pull_requests(self, run, capsys):
        code, _, err = run(None, event={"push": {}})
        assert code == cpr.CANNOT_RUN
        assert "is not a pull request's" in err

    @pytest.mark.spec("script-ignores-closed-pipe")
    def it_exits_ok_when_its_reader_closes_the_pipe(self, tmp_path, capsys, closed_pipe):
        path = tmp_path / "event.json"
        path.write_text(json.dumps({"pull_request": {"body": SCENARIO}}))
        closed_pipe()
        assert cpr.main(["description"], environ={cpr.EVENT_ENV: str(path)}) == cpr.OK
        assert capsys.readouterr().err == ""

    @pytest.mark.spec("script-ignores-closed-pipe")
    @pytest.mark.parametrize("command", [["description"], ["--help"], ["description", "--help"]])
    def it_exits_ok_without_a_traceback_when_its_reader_has_gone(
        self, tmp_path, closed_pipe_child, command
    ):
        path = tmp_path / "event.json"
        path.write_text(json.dumps({"pull_request": {"body": SCENARIO}}))
        env = dict(os.environ, **{cpr.EVENT_ENV: str(path)})
        assert closed_pipe_child(_PATH, *command, env=env) == (cpr.OK, "")


@pytest.fixture
def draft(tmp_path):
    """Write `body` to a draft file and return its path."""

    def write(body):
        path = tmp_path / "pr.md"
        path.write_text(body)
        return str(path)

    return write


class DescribeDescriptionOfADraft:
    @pytest.mark.spec("description-cmd-reads-body-file")
    def it_checks_the_file_in_place_of_the_event(self, capsys, draft):
        code = cpr.main(["description", "--body-file", draft(SCENARIO)], environ={})
        assert code == cpr.OK
        assert capsys.readouterr().out == "The description opens with `## Scenario`.\n"

    @pytest.mark.spec("description-cmd-reads-body-file")
    def it_fails_a_draft_the_event_check_would_fail(self, capsys, draft):
        code = cpr.main(["description", "--body-file", draft("## Summary\n")], environ={})
        assert code == cpr.PROBLEMS
        assert "first heading is `## Summary`" in capsys.readouterr().err

    @pytest.mark.spec("script-exits-2-when-unrunnable", "script-names-remedy-on-stop")
    def it_stops_on_a_draft_it_cannot_read(self, capsys, tmp_path):
        missing = str(tmp_path / "missing.md")
        code = cpr.main(["description", "--body-file", missing], environ={})
        assert code == cpr.CANNOT_RUN
        err = capsys.readouterr().err
        assert err.startswith("check-pr.py: cannot read the description at %s" % missing)
        assert "Write the draft there" in err


class DescribeDraft:
    @pytest.mark.spec("draft-cmd-makes-own-file")
    def it_makes_an_empty_file_in_the_temporary_directory(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setattr(cpr.tempfile, "tempdir", str(tmp_path))
        code = cpr.main(["draft", "--json"], environ={})
        assert code == cpr.OK
        path = Path(json.loads(capsys.readouterr().out)["data"]["path"])
        assert path.parent == tmp_path
        assert path.name.startswith("pr-")
        assert path.suffix == ".md"
        assert path.read_bytes() == b""

    @pytest.mark.spec("draft-cmd-makes-own-file")
    def it_gives_each_run_a_file_of_its_own(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setattr(cpr.tempfile, "tempdir", str(tmp_path))
        paths = set()
        for _ in range(5):
            assert cpr.main(["draft"], environ={}) == cpr.OK
            paths.add(capsys.readouterr().out.strip())
        assert len(paths) == 5
        assert all(Path(p).is_file() for p in paths)

    @pytest.mark.spec("script-exits-2-when-unrunnable", "script-names-remedy-on-stop")
    def it_stops_when_the_temporary_directory_cannot_take_a_file(
        self, capsys, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(cpr.tempfile, "tempdir", str(tmp_path / "missing"))
        code = cpr.main(["draft"], environ={})
        assert code == cpr.CANNOT_RUN
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("check-pr.py: cannot make a file for the draft in ")
        assert "Set TMPDIR" in captured.err


class FakeShell:
    """Stands in for git and gh, recording each call."""

    def __init__(self, fail=None, url="https://github.com/o/r/pull/7\n"):
        self.calls = []
        self.fail = fail
        self.url = url

    def __call__(self, repo, cmd):
        self.calls.append((repo, cmd))
        if self.fail and cmd[:2] == self.fail:
            raise cpr.Fatal("`%s` failed: boom. Fix what it names and run `open` again." % cmd[0])
        if cmd[:2] == ["git", "rev-parse"]:
            return "issue/567\n"
        if cmd[:2] == ["gh", "pr"]:
            return self.url
        return ""


@pytest.fixture
def shell(monkeypatch):
    def install(**kwargs):
        fake = FakeShell(**kwargs)
        monkeypatch.setattr(cpr, "run", fake)
        return fake

    return install


class DescribeOpen:
    @pytest.mark.spec("open-cmd-opens-from-file")
    def it_pushes_the_branch_and_opens_the_pull_request_from_the_file(self, capsys, draft, shell):
        fake = shell()
        path = draft(SCENARIO)
        code = cpr.main(["open", "--title", "feat: x", "--body-file", path, "-C", "/clone"])
        assert code == cpr.OK
        assert [cmd for _, cmd in fake.calls] == [
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            ["git", "push", "-u", "origin", "HEAD"],
            ["gh", "pr", "create", "--base", "main", "--title", "feat: x", "--body-file", path],
        ]
        assert {repo for repo, _ in fake.calls} == {"/clone"}
        captured = capsys.readouterr()
        assert captured.out == "https://github.com/o/r/pull/7\n"
        assert captured.err == ""

    @pytest.mark.spec("open-cmd-opens-from-file", "command-prints-json-envelope")
    def it_prints_the_address_and_branch_in_the_envelope(self, capsys, draft, shell):
        shell()
        code = cpr.main(["open", "--title", "t", "--body-file", draft(SCENARIO), "--json"])
        assert code == cpr.OK
        captured = capsys.readouterr()
        assert captured.err == ""
        result = json.loads(captured.out)
        assert result["command"] == "open"
        assert result["data"]["url"] == "https://github.com/o/r/pull/7"
        assert result["data"]["branch"] == "issue/567"
        assert result["data"]["first_heading"] == "## Scenario"

    @pytest.mark.spec("open-cmd-refuses-failing-draft")
    @pytest.mark.parametrize("body", ["## Summary\n\nA check.\n", "## Scenario\n\n## Change\n"])
    def it_refuses_a_draft_that_description_fails_without_pushing(self, capsys, draft, shell, body):
        fake = shell()
        code = cpr.main(["open", "--title", "t", "--body-file", draft(body)])
        assert code == cpr.PROBLEMS
        assert fake.calls == []
        captured = capsys.readouterr()
        assert captured.out == ""
        assert 'CLAUDE.md, under "Workflow"' in captured.err

    @pytest.mark.spec("script-exits-2-when-unrunnable", "script-names-remedy-on-stop")
    def it_stops_when_the_push_fails_without_opening(self, capsys, draft, shell):
        fake = shell(fail=["git", "push"])
        code = cpr.main(["open", "--title", "t", "--body-file", draft(SCENARIO)])
        assert code == cpr.CANNOT_RUN
        assert not [cmd for _, cmd in fake.calls if cmd[0] == "gh"]
        assert "run `open` again" in capsys.readouterr().err


class DescribeRun:
    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_stops_when_the_clone_is_missing(self, tmp_path):
        with pytest.raises(cpr.Fatal, match="cannot run git"):
            cpr.run(str(tmp_path / "missing"), ["git", "status"])

    @pytest.mark.spec("script-names-remedy-on-stop")
    def it_names_the_failed_command_and_the_remedy(self, tmp_path):
        with pytest.raises(cpr.Fatal) as exc:
            cpr.run(str(tmp_path), ["git", "rev-parse", "--show-toplevel"])
        assert "`git rev-parse --show-toplevel` failed" in str(exc.value)
        assert "run `open` again" in str(exc.value)

    @pytest.mark.spec("open-cmd-opens-from-file")
    def it_returns_the_command_output(self, tmp_path):
        assert cpr.run(str(tmp_path), ["git", "--version"]).startswith("git version")

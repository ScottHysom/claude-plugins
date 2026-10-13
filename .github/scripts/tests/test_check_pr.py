"""What check-pr.py promises about a pull request's description.

Each test writes the event GitHub Actions would, with the description as the
pull request's body, and runs `description` on it.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-pr.py"
_spec = importlib.util.spec_from_file_location("check_pr", _PATH)
cpr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpr)

SCENARIO = (
    "## Scenario\n\n"
    "An agent opens a pull request. Before, CI passed any description. After, "
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
        assert code == cpr.OK, err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_ends_the_scenario_at_a_top_level_heading(self, run):
        code, _, err = run("## Scenario\n\n# Change\n\nA check.\n")
        assert code == cpr.PROBLEMS
        assert "section is empty" in err

    @pytest.mark.spec("description-cmd-requires-scenario-first")
    def it_reads_a_description_written_with_crlf(self, run):
        code, _, err = run(SCENARIO.replace("\n", "\r\n"))
        assert code == cpr.OK, err


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

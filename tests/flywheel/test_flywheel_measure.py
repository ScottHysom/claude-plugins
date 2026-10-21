"""What `measure` reports about the pull requests merged over a period.

gh is faked here with the merged pull requests each test names, and the
usage records with JSON lines written under a CLAUDE_CONFIG_DIR of the
test's own.
"""

import json
import os

import pytest

import flywheel

SINCE = "2026-10-10"


def merged_pull(number, head, merged_at):
    return {
        "number": number,
        "title": "pull %d" % number,
        "url": "https://github.com/owner/project/pull/%d" % number,
        "headRefName": head,
        "mergedAt": merged_at,
    }


def approved_at(*times, label="approved"):
    return [{"createdAt": t, "label": {"name": label}} for t in times]


def detail(rollups=(), threads=(), issues=()):
    """A pull request as MEASURE_QUERY returns it.

    rollups is the state of each commit's checks, None where CI did not run;
    threads the first comment of each review thread; issues each closing
    issue's number and labeled events.
    """
    return {
        "commits": {
            "nodes": [
                {"commit": {"statusCheckRollup": None if s is None else {"state": s}}}
                for s in rollups
            ]
        },
        "reviewThreads": {
            "nodes": [
                {"comments": {"nodes": [] if body is None else [{"body": body}]}}
                for body in threads
            ]
        },
        "closingIssuesReferences": {
            "nodes": [{"number": n, "timelineItems": {"nodes": events}} for n, events in issues]
        },
    }


@pytest.fixture
def github(monkeypatch):
    """Answer gh with the merged pull requests given and each one's detail."""

    def install(merged=(), details=None):
        details = details or {}

        def fake(root, *args):
            if args[:2] == ("pr", "list"):
                return json.dumps(list(merged))
            number = int(next(a for a in args if a.startswith("number="))[len("number=") :])
            pull = details.get(number, detail())
            return json.dumps({"data": {"repository": {"pullRequest": pull}}})

        monkeypatch.setattr(flywheel, "gh", fake)

    return install


@pytest.fixture
def usage(tmp_path, monkeypatch):
    """Write usage records where Claude Code keeps them, under a config dir of the test's."""
    config = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    def write(project, records, folder=None, name="session.jsonl", raw=()):
        root = flywheel.project_root(str(project.root))
        folder = folder or flywheel.usage_slug(root)
        path = config / "projects" / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(r) for r in records] + list(raw)
        with open(path, "a") as f:
            f.write("".join(line + "\n" for line in lines))
        return root

    return write


def record(root, branch, message_id, input_tokens=0, output=0, write=0, read=0, kind="assistant"):
    return {
        "type": kind,
        "cwd": root,
        "gitBranch": branch,
        "message": {
            "id": message_id,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output,
                "cache_creation_input_tokens": write,
                "cache_read_input_tokens": read,
            },
        },
    }


def pulls_of(env):
    return {p["number"]: p for p in env["data"]["pulls"]}


@pytest.mark.spec("measure-cmd-reports-starting-measures")
class DescribeMeasure:
    def it_reports_each_pull_request_merged_since_the_date(self, project, github):
        github(
            merged=[
                merged_pull(42, "issue/14", "2026-10-12T09:00:00Z"),
                merged_pull(40, "issue/12", "2026-10-09T23:59:59Z"),
                merged_pull(41, "docs/readme", "2026-10-10T00:00:00Z"),
            ]
        )
        code, env = project.run("measure", "--since", SINCE)
        assert code == flywheel.OK
        assert env["command"] == "measure"
        assert env["data"]["since"] == SINCE
        assert [(p["number"], p["branch"], p["merged_at"]) for p in env["data"]["pulls"]] == [
            (41, "docs/readme", "2026-10-10T00:00:00Z"),
            (42, "issue/14", "2026-10-12T09:00:00Z"),
        ]

    def it_reports_each_pull_request_merged_at_or_after_a_time(self, project, github):
        github(
            merged=[
                merged_pull(42, "issue/14", "2026-10-12T06:03:00Z"),
                merged_pull(40, "issue/12", "2026-10-12T03:00:00Z"),
                merged_pull(41, "docs/readme", "2026-10-12T06:02:59Z"),
            ]
        )
        code, env = project.run("measure", "--since", "2026-10-12T06:03:00Z")
        assert code == flywheel.OK
        assert env["data"]["since"] == "2026-10-12T06:03:00Z"
        assert [p["number"] for p in env["data"]["pulls"]] == [42]

    @pytest.mark.parametrize(
        ("rollups", "green"),
        [
            ([None, "SUCCESS", "FAILURE"], True),
            (["FAILURE", "SUCCESS"], False),
            ([None, "ERROR", "SUCCESS"], False),
        ],
    )
    def it_reads_first_pass_ci_from_the_first_commit_ci_ran_on(
        self, project, github, rollups, green
    ):
        github(
            merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")],
            details={42: detail(rollups=rollups)},
        )
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["first_pass_ci"] is green
        assert "first_pass_ci" not in pull["missing"]

    @pytest.mark.parametrize(
        ("rollups", "reason"),
        [([None, None], "CI did not run"), (["PENDING", "SUCCESS"], "PENDING")],
    )
    def it_says_why_first_pass_ci_is_unknown(self, project, github, rollups, reason):
        github(
            merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")],
            details={42: detail(rollups=rollups)},
        )
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["first_pass_ci"] is None
        assert reason in pull["missing"]["first_pass_ci"]

    def it_counts_the_reviewers_findings_by_level(self, project, github):
        threads = [
            "**Claude:** P1 The lock can be lost.",
            "**Claude:** P3 A typo.",
            "**Claude:** P3 Another.",
            "Why this name?",
            "**Claude:** Fixed in 3f9a1c0.",
            None,
        ]
        github(
            merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")],
            details={42: detail(threads=threads)},
        )
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["findings"] == {"P0": 0, "P1": 1, "P2": 0, "P3": 2}

    def it_measures_lead_time_from_the_last_approval_before_the_merge(self, project, github):
        events = (
            approved_at("2026-10-11T00:00:00Z", "2026-10-11T21:00:00Z", "2026-10-13T00:00:00Z")
            + approved_at("2026-10-01T00:00:00Z", label="bug")
            + [None]
        )
        github(
            merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")],
            details={42: detail(issues=[(14, events)])},
        )
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["issues"] == [14]
        assert pull["lead_time_hours"] == 12.0

    @pytest.mark.spec("labelsfile-maps-roles")
    def it_measures_lead_time_from_the_mapped_approval_label(self, project, github):
        project.write(flywheel.LABELS_FILE, json.dumps({"roles": {"approval": "ready"}}))
        events = approved_at("2026-10-11T00:00:00Z") + approved_at(
            "2026-10-11T21:00:00Z", label="Ready"
        )
        github(
            merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")],
            details={42: detail(issues=[(14, events)])},
        )
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["lead_time_hours"] == 12.0

    def it_measures_lead_time_from_the_earliest_of_its_issues_approvals(self, project, github):
        github(
            merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")],
            details={
                42: detail(
                    issues=[
                        (14, approved_at("2026-10-12T06:00:00Z")),
                        (15, approved_at("2026-10-11T09:00:00Z")),
                    ]
                )
            },
        )
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["issues"] == [14, 15]
        assert pull["lead_time_hours"] == 24.0

    @pytest.mark.parametrize(
        ("issues", "reason"),
        [
            ([], "does not close an issue"),
            ([(14, approved_at("2026-10-13T00:00:00Z"))], "#14 was not labeled approved"),
            ([(14, []), (15, [])], "#14 and #15 were not labeled approved"),
        ],
    )
    def it_says_why_lead_time_is_unknown(self, project, github, issues, reason):
        github(
            merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")],
            details={42: detail(issues=issues)},
        )
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["lead_time_hours"] is None
        assert reason in pull["missing"]["lead_time_hours"]

    def it_sums_spend_from_the_usage_records_on_the_head_branch(self, project, github, usage):
        root = flywheel.project_root(str(project.root))
        worktree = os.path.join(root, ".claude", "worktrees", "issue-14")
        usage(
            project,
            [
                record(root, "issue/14", "msg_1", 10, 20, 30, 40),
                # One message is written once per content block, with the same usage.
                record(root, "issue/14", "msg_1", 10, 20, 30, 40),
                record(root, "issue/14", "msg_2", 1, 2, 3, 4),
                record(root, "issue/14", "msg_3", 5, 5, 5, 5, kind="user"),
                record(root, "issue/13", "msg_4", 100, 100, 100, 100),
                record("/elsewhere", "issue/14", "msg_5", 100, 100, 100, 100),
                {"type": "assistant", "cwd": root, "gitBranch": "issue/14", "usage": {}},
                dict(record(root, "issue/14", "msg_8", 9, 9, 9, 9), cwd=None),
            ],
            raw=['not json "usage"', '["usage"]', "a line without the key"],
        )
        usage(
            project,
            [record(worktree, "issue/14", "msg_6", 1000, 0, 0, 0)],
            folder=flywheel.usage_slug(worktree),
            name="session/subagents/agent.jsonl",
        )
        usage(project, [record(root, "issue/14", "msg_7", 7, 7, 7, 7)], folder="-somewhere-else")
        github(merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")])
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["spend"] == {
            "input_tokens": 1011,
            "output_tokens": 22,
            "cache_creation_input_tokens": 33,
            "cache_read_input_tokens": 44,
            "total": 1110,
        }
        assert "spend" not in pull["missing"]

    def it_says_why_spend_is_unknown(self, project, github, usage, tmp_path):
        github(merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")])
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["spend"] is None
        assert "No usage records are at" in pull["missing"]["spend"]
        assert str(tmp_path / "config" / "projects") in pull["missing"]["spend"]
        usage(project, [record(flywheel.project_root(str(project.root)), "main", "m")])
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert pull["spend"] is None
        assert "issue/14" in pull["missing"]["spend"]

    def it_reads_usage_records_from_the_home_config_without_claude_config_dir(
        self, project, github, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        github(merged=[merged_pull(42, "issue/14", "2026-10-12T09:00:00Z")])
        pull = pulls_of(project.run("measure", "--since", SINCE)[1])[42]
        assert str(tmp_path / "home" / ".claude" / "projects") in pull["missing"]["spend"]

    def it_sums_up_the_period(self, project, github, usage):
        root = flywheel.project_root(str(project.root))
        usage(
            project,
            [
                record(root, "issue/14", "a", 1, 1, 1, 1),
                record(root, "issue/15", "b", 2, 2, 2, 2),
            ],
        )
        github(
            merged=[
                merged_pull(42, "issue/14", "2026-10-12T09:00:00Z"),
                merged_pull(43, "issue/15", "2026-10-12T10:00:00Z"),
                merged_pull(44, "issue/16", "2026-10-12T11:00:00Z"),
            ],
            details={
                42: detail(
                    rollups=["SUCCESS"],
                    threads=["**Claude:** P2 x"],
                    issues=[(14, approved_at("2026-10-12T08:00:00Z"))],
                ),
                43: detail(
                    rollups=["FAILURE"],
                    threads=["**Claude:** P2 y", "**Claude:** P0 z"],
                    issues=[(15, approved_at("2026-10-12T07:00:00Z"))],
                ),
                44: detail(issues=[(16, approved_at("2026-10-12T05:00:00Z"))]),
            },
        )
        summary = project.run("measure", "--since", SINCE)[1]["data"]["summary"]
        assert summary == {
            "pulls": 3,
            "spend": {
                "pulls": 2,
                "input_tokens": 3,
                "output_tokens": 3,
                "cache_creation_input_tokens": 3,
                "cache_read_input_tokens": 3,
                "total": 12,
            },
            "first_pass_ci": {"pulls": 2, "green": 1, "rate": 0.5},
            "findings": {"P0": 1, "P1": 0, "P2": 2, "P3": 0},
            "lead_time_hours": {"pulls": 3, "median": 3.0, "min": 1.0, "max": 6.0},
        }

    def it_takes_the_middle_two_for_the_median_of_an_even_count(self, project, github):
        github(
            merged=[
                merged_pull(42, "issue/14", "2026-10-12T09:00:00Z"),
                merged_pull(43, "issue/15", "2026-10-12T09:00:00Z"),
            ],
            details={
                42: detail(issues=[(14, approved_at("2026-10-12T08:00:00Z"))]),
                43: detail(issues=[(15, approved_at("2026-10-12T06:00:00Z"))]),
            },
        )
        summary = project.run("measure", "--since", SINCE)[1]["data"]["summary"]
        assert summary["lead_time_hours"]["median"] == 2.0

    def it_sums_up_an_empty_period(self, project, github):
        github()
        code, env = project.run("measure", "--since", SINCE)
        assert code == flywheel.OK
        assert env["data"]["summary"] == {
            "pulls": 0,
            "spend": None,
            "first_pass_ci": {"pulls": 0, "green": 0, "rate": None},
            "findings": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
            "lead_time_hours": None,
        }

    def it_prints_each_measure_and_why_any_is_missing(self, project, github, usage):
        root = flywheel.project_root(str(project.root))
        usage(project, [record(root, "issue/14", "a", 1000, 200, 30, 4)])
        github(
            merged=[
                merged_pull(42, "issue/14", "2026-10-12T09:00:00Z"),
                merged_pull(43, "issue/15", "2026-10-12T10:00:00Z"),
                merged_pull(44, "issue/16", "2026-10-12T11:00:00Z"),
            ],
            details={
                42: detail(
                    rollups=["SUCCESS"],
                    threads=["**Claude:** P3 x"],
                    issues=[(14, approved_at("2026-10-11T21:00:00Z"))],
                ),
                43: detail(rollups=["FAILURE"]),
            },
        )
        code, out, err = project.human("measure", "--since", SINCE)
        assert code == flywheel.OK
        assert err == ""
        assert "Since %s: 3 merged pull requests." % SINCE in out
        assert "#42 issue/14, merged 2026-10-12T09:00:00Z" in out
        assert "spend: 1,234 tokens (input 1,000, output 200, cache write 30, cache read 4)" in out
        assert "first-pass CI: green" in out
        assert "first-pass CI: not green" in out
        assert "findings: P0 0, P1 0, P2 0, P3 1" in out
        assert "lead time: 12.0 hours" in out
        assert "spend: not computed. No usage record" in out
        assert "lead time: not computed. #43 does not close an issue" in out
        assert "first-pass CI: not computed. CI did not run on any of #44's commits" in out
        assert "first-pass CI: 1 of 2 green (50%)" in out
        assert "spend: 1,234 tokens over 1 of 3 pull requests" in out
        assert "lead time: median 12.0 hours, from 12.0 to 12.0, over 1 of 3" in out

    def it_prints_an_empty_period(self, project, github):
        github()
        code, out, _ = project.human("measure", "--since", SINCE)
        assert code == flywheel.OK
        assert "Since %s: 0 merged pull requests." % SINCE in out
        assert "first-pass CI: 0 of 0 green" in out
        assert "spend: not computed for any pull request" in out
        assert "lead time: not computed for any pull request" in out

    @pytest.mark.parametrize("since", ["last week", "2026-10-12T06:03", "2026-10-12 06:03:00"])
    def it_refuses_a_since_that_is_neither_a_date_nor_a_utc_time(
        self, project, github, capsys, since
    ):
        github()
        with pytest.raises(SystemExit) as exc:
            flywheel.main(["measure", "--since", since, "-C", str(project.root)])
        assert exc.value.code == flywheel.CANNOT_RUN
        assert (
            "is not a date such as 2026-10-15 or a UTC time such as 2026-10-15T09:00:00Z"
            in capsys.readouterr().err
        )

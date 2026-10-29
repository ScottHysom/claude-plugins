"""What the dispatcher reads to run a round: a role's model and effort, and events.

`check-role` reads only the project's roles file. `events` reads only gh, which is
faked here with the pull requests each test names.
"""

import json

import pytest

import flywheel

SINCE = "2026-10-15T10:00:00Z"


def check_run(status="COMPLETED", conclusion="SUCCESS", **more):
    return {"__typename": "CheckRun", "status": status, "conclusion": conclusion, **more}


def status(state):
    return {"__typename": "StatusContext", "state": state}


def open_pull(number, head, checks=(), review=""):
    return {
        "number": number,
        "title": "pull %d" % number,
        "url": "https://github.com/owner/project/pull/%d" % number,
        "headRefName": head,
        "statusCheckRollup": list(checks),
        "reviewDecision": review,
    }


NEXT_STEP = {
    "head": "abc1234",
    "verdict": "hold",
    "next": "wait",
    "reasons": [],
    "only_running_check": False,
}


def merged_pull(number, head, merged_at):
    return {
        "number": number,
        "title": "pull %d" % number,
        "url": "https://github.com/owner/project/pull/%d" % number,
        "headRefName": head,
        "mergedAt": merged_at,
    }


@pytest.fixture
def pulls(monkeypatch):
    """Answer gh pr list with the pull requests given, and each plan issue's sub-issues."""

    def install(opened=(), merged=(), subs=None, steps=None):
        steps = steps or {}
        calls = []

        def fake(root, *args):
            calls.append(args)
            if args[0] == "api" and "/sub_issues" in args[1]:
                number = int(args[1].split("/")[-2])
                return json.dumps([{"number": n, "state": "open"} for n in subs[number]])
            state = args[args.index("--state") + 1]
            return json.dumps(list(opened if state == "open" else merged))

        def fake_assess(root, number):
            return dict(NEXT_STEP, **steps.get(number, {}))

        monkeypatch.setattr(flywheel, "gh", fake)
        monkeypatch.setattr(flywheel, "assess", fake_assess)
        return calls

    return install


def write_roles(project, roles):
    project.write(flywheel.ROLES_FILE, json.dumps({"roles": roles}))


@pytest.mark.spec("checkrole-cmd-names-unset-fields")
class DescribeCheckRole:
    def it_prints_the_model_and_effort_the_roles_file_gives(self, project):
        write_roles(
            project, {"implementer": {"tier": 3, "model": "claude-sonnet-5-5", "effort": "high"}}
        )
        code, env = project.run("check-role", "implementer")
        assert code == flywheel.OK
        assert env["command"] == "check-role"
        assert env["data"] == {
            "name": "implementer",
            "tier": 3,
            "model": "claude-sonnet-5-5",
            "effort": "high",
        }
        code, out, err = project.human("check-role", "implementer")
        assert (code, out, err) == (
            flywheel.OK,
            "implementer: model claude-sonnet-5-5, effort high, tier 3\n",
            "",
        )

    def it_names_each_field_the_owner_has_not_filled_in(self, project):
        write_roles(project, {"implementer": {"tier": 3, "model": None, "effort": " "}})
        code, out, err = project.human("check-role", "implementer")
        assert code == flywheel.PROBLEMS
        assert out == ""
        assert err == (
            "roles.implementer.model is not set in .flywheel/roles.json. The owner fills it in"
            " before a session starts as the implementer\n"
            "roles.implementer.effort is not set in .flywheel/roles.json. The owner fills it in"
            " before a session starts as the implementer\n"
        )

    def it_names_a_role_the_file_does_not_have(self, project):
        write_roles(project, {"implementer": {"tier": 3, "model": "m", "effort": "e"}})
        code, env = project.run("check-role", "reviewer")
        assert code == flywheel.PROBLEMS
        assert env["errors"] == [
            '.flywheel/roles.json does not name the reviewer role. Add it under "roles", with'
            " its model and effort"
        ]
        assert env["data"]["model"] is None

    def it_says_to_run_config_init_without_a_roles_file(self, project):
        code, env = project.run("check-role", "implementer")
        assert code == flywheel.PROBLEMS
        assert env["errors"] == [
            ".flywheel/roles.json is missing. Run config init to write it, then fill in each"
            " field it names"
        ]


@pytest.mark.spec("checkrole-cmd-exits-1-above-session")
class DescribeCheckRoleAgainstSession:
    @pytest.fixture(autouse=True)
    def roles(self, project):
        write_roles(project, {"reviewer": {"tier": 2, "model": "opus", "effort": "high"}})

    def it_passes_a_session_that_matches_by_family(self, project):
        code, env = project.run(
            "check-role", "reviewer", "--model", "claude-opus-5-5", "--effort", "high"
        )
        assert code == flywheel.OK
        assert env["errors"] == []

    def it_exits_1_when_the_effort_is_above_the_session(self, project):
        code, env = project.run(
            "check-role", "reviewer", "--model", "claude-opus-5-5", "--effort", "medium"
        )
        assert code == flywheel.PROBLEMS
        assert env["errors"] == [
            "The reviewer role's effort high is above this session's medium. Run the skill"
            " from a session at least that strong"
        ]

    def it_exits_1_when_the_model_is_above_the_session(self, project):
        code, env = project.run(
            "check-role", "reviewer", "--model", "claude-sonnet-5-5", "--effort", "max"
        )
        assert code == flywheel.PROBLEMS
        assert len(env["errors"]) == 1
        assert "model opus is above this session's claude-sonnet-5-5" in env["errors"][0]

    def it_names_the_session_model_it_cannot_rank(self, project):
        code, env = project.run("check-role", "reviewer", "--model", "gpt", "--effort", "high")
        assert code == flywheel.PROBLEMS
        assert env["errors"] == [
            "The session's model gpt is not one check-role can rank (haiku, sonnet, opus,"
            " fable). Pass the model that get_session reports"
        ]

    def it_names_the_session_effort_it_cannot_rank(self, project):
        code, env = project.run(
            "check-role", "reviewer", "--model", "claude-opus-5-5", "--effort", "extreme"
        )
        assert code == flywheel.PROBLEMS
        assert len(env["errors"]) == 1
        assert "The session's effort extreme is not one check-role can rank" in env["errors"][0]

    def it_does_not_match_an_effort_by_substring(self, project):
        write_roles(project, {"reviewer": {"tier": 2, "model": "opus", "effort": "xhigh"}})
        code, env = project.run(
            "check-role", "reviewer", "--model", "claude-opus-5-5", "--effort", "high"
        )
        assert code == flywheel.PROBLEMS
        assert "effort xhigh is above this session's high" in env["errors"][0]

    def it_names_the_role_value_it_cannot_rank(self, project):
        write_roles(project, {"reviewer": {"tier": 2, "model": "gpt-5", "effort": "high"}})
        code, env = project.run(
            "check-role", "reviewer", "--model", "claude-opus-5-5", "--effort", "high"
        )
        assert code == flywheel.PROBLEMS
        assert env["errors"] == [
            "The reviewer role's model gpt-5 is not one check-role can rank (haiku, sonnet,"
            " opus, fable). Set it in .flywheel/roles.json to one of those"
        ]

    def it_refuses_one_of_the_two_options_alone(self, project):
        code, out, err = project.human("check-role", "reviewer", "--model", "opus")
        assert code == flywheel.CANNOT_RUN
        assert "together" in err


@pytest.mark.spec("events-cmd-lists-claim-prs")
class DescribeEvents:
    def it_lists_each_open_claim_pull_request_with_its_ci_and_review(self, project, pulls):
        pulls(
            opened=[
                open_pull(31, "issue/12", [check_run()], review="APPROVED"),
                open_pull(30, "issue/9", [check_run(conclusion="FAILURE")]),
                open_pull(32, "feature/x", [check_run()]),
                open_pull(33, "issue/12-old"),
            ]
        )
        code, env = project.run("events")
        assert code == flywheel.OK
        assert env["command"] == "events"
        assert env["data"]["open"] == [
            {
                "number": 30,
                "issue": 9,
                "branch": "issue/9",
                "title": "pull 30",
                "url": "https://github.com/owner/project/pull/30",
                "ci": "failing",
                "review": None,
                "head": "abc1234",
                "verdict": "hold",
                "next": "wait",
                "reasons": [],
                "only_running_check": False,
            },
            {
                "number": 31,
                "issue": 12,
                "branch": "issue/12",
                "title": "pull 31",
                "url": "https://github.com/owner/project/pull/31",
                "ci": "passing",
                "review": "approved",
                "head": "abc1234",
                "verdict": "hold",
                "next": "wait",
                "reasons": [],
                "only_running_check": False,
            },
        ]

    def it_names_the_next_step_merge_check_gives_each_open_pull_request(self, project, pulls):
        pulls(
            opened=[open_pull(31, "issue/12", [check_run()])],
            steps={31: {"next": "review", "reasons": ["the reviewer has not reviewed it"]}},
        )
        _, env = project.run("events")
        row = env["data"]["open"][0]
        assert (row["next"], row["reasons"]) == ("review", ["the reviewer has not reviewed it"])

    def it_holds_for_the_owner_a_pull_request_it_cannot_assess(self, project, pulls, monkeypatch):
        pulls(opened=[open_pull(31, "issue/12"), open_pull(32, "issue/13")])

        def assess(root, number):
            if number == 31:
                raise flywheel.Fatal("no merge policy")
            return dict(NEXT_STEP)

        monkeypatch.setattr(flywheel, "assess", assess)
        code, env = project.run("events")
        first, second = env["data"]["open"]
        assert code == flywheel.OK
        assert (first["next"], first["reasons"]) == ("ask", ["no merge policy"])
        assert second["next"] == "wait"

    @pytest.mark.parametrize(
        ("checks", "ci"),
        [
            ([], "none"),
            ([check_run(), check_run(conclusion="SKIPPED"), status("SUCCESS")], "passing"),
            ([check_run(), check_run(status="IN_PROGRESS", conclusion="")], "pending"),
            ([check_run(), status("PENDING")], "pending"),
            ([check_run(status="QUEUED", conclusion=""), status("ERROR")], "failing"),
            (
                [check_run(status="QUEUED", conclusion=""), check_run(conclusion="CANCELLED")],
                "failing",
            ),
        ],
    )
    def it_sums_up_the_checks_with_a_failure_first(self, project, pulls, checks, ci):
        pulls(opened=[open_pull(31, "issue/12", checks)])
        assert project.run("events")[1]["data"]["open"][0]["ci"] == ci

    @pytest.mark.spec("mergecheck-cmd-ignores-replaced-cancelled-check")
    @pytest.mark.parametrize(
        ("checks", "ci"),
        [
            (
                [
                    check_run(
                        conclusion="CANCELLED", name="validate", startedAt="2026-10-29T09:29:37Z"
                    ),
                    check_run(
                        status="IN_PROGRESS",
                        conclusion="",
                        name="validate",
                        startedAt="2026-10-29T09:29:58Z",
                    ),
                ],
                "pending",
            ),
            (
                [
                    check_run(name="validate", startedAt="2026-10-29T09:29:58Z"),
                    check_run(
                        conclusion="CANCELLED", name="validate", startedAt="2026-10-29T09:29:37Z"
                    ),
                ],
                "passing",
            ),
            (
                [
                    check_run(
                        conclusion="CANCELLED", name="validate", startedAt="2026-10-29T09:29:37Z"
                    ),
                    check_run(
                        conclusion="FAILURE", name="validate", startedAt="2026-10-29T09:29:58Z"
                    ),
                ],
                "failing",
            ),
            (
                [
                    check_run(
                        conclusion="CANCELLED", name="validate", startedAt="2026-10-29T09:29:37Z"
                    ),
                    check_run(name="other", startedAt="2026-10-29T09:29:58Z"),
                ],
                "failing",
            ),
        ],
    )
    def it_reads_a_cancelled_check_through_its_later_run(self, project, pulls, checks, ci):
        pulls(opened=[open_pull(31, "issue/12", checks)])
        assert project.run("events")[1]["data"]["open"][0]["ci"] == ci

    def it_names_each_claim_merged_since_the_last_look(self, project, pulls):
        pulls(
            merged=[
                merged_pull(41, "issue/14", "2026-10-15T12:00:00Z"),
                merged_pull(40, "issue/13", "2026-10-15T11:00:00Z"),
                merged_pull(39, "issue/11", SINCE),
                merged_pull(42, "docs/readme", "2026-10-15T13:00:00Z"),
            ]
        )
        code, env = project.run("events", "--since", SINCE)
        assert code == flywheel.OK
        assert [(m["number"], m["issue"], m["merged_at"]) for m in env["data"]["merged"]] == [
            (40, 13, "2026-10-15T11:00:00Z"),
            (41, 14, "2026-10-15T12:00:00Z"),
        ]
        assert env["data"]["since"] == SINCE

    def it_gives_the_newest_merge_as_the_start_of_the_next_look(self, project, pulls):
        pulls(merged=[merged_pull(41, "issue/14", "2026-10-15T12:00:00Z")])
        _, first = project.run("events", "--since", SINCE)
        assert first["data"]["as_of"] == "2026-10-15T12:00:00Z"
        _, second = project.run("events", "--since", first["data"]["as_of"])
        assert second["data"]["merged"] == []
        assert second["data"]["as_of"] == "2026-10-15T12:00:00Z"

    def it_keeps_the_since_when_nothing_newer_has_merged(self, project, pulls):
        pulls(merged=[merged_pull(41, "issue/14", "2026-10-14T12:00:00Z")])
        _, env = project.run("events", "--since", SINCE)
        assert env["data"]["as_of"] == SINCE

    def it_names_no_merge_on_the_first_look(self, project, pulls):
        pulls(merged=[merged_pull(41, "issue/14", "2026-10-15T12:00:00Z")])
        _, env = project.run("events")
        assert env["data"]["merged"] == []
        assert env["data"]["as_of"] == "2026-10-15T12:00:00Z"

    def it_reads_the_clock_only_when_no_claim_has_merged(self, project, pulls, monkeypatch):
        pulls(merged=[merged_pull(42, "docs/readme", "2026-10-15T13:00:00Z")])
        monkeypatch.setattr(flywheel.time, "gmtime", lambda: (2026, 10, 15, 14, 5, 6, 3, 288, 0))
        _, env = project.run("events")
        assert env["data"]["as_of"] == "2026-10-15T14:05:06Z"

    def it_prints_each_pull_request_and_the_next_look_in_plain_output(self, project, pulls):
        pulls(
            opened=[open_pull(31, "issue/12", [check_run()])],
            merged=[merged_pull(41, "issue/14", "2026-10-15T12:00:00Z")],
        )
        code, out, err = project.human("events", "--since", SINCE)
        assert (code, err) == (flywheel.OK, "")
        assert out == (
            "open #31 issue/12: ci passing, review none, next wait\n"
            "merged #41 issue/14 at 2026-10-15T12:00:00Z\n"
            "Next look: flywheel.py events --since 2026-10-15T12:00:00Z\n"
        )

    def it_says_when_there_is_nothing_to_act_on(self, project, pulls):
        pulls()
        code, out, _ = project.human("events", "--since", SINCE)
        assert code == flywheel.OK
        assert out == (
            "No claim has an open pull request or a new merge.\n"
            "Next look: flywheel.py events --since %s\n" % SINCE
        )

    def it_refuses_a_since_that_is_not_a_utc_time(self, project, pulls, capsys):
        calls = pulls()
        with pytest.raises(SystemExit) as exc:
            flywheel.main(["events", "--since", "yesterday", "-C", str(project.root)])
        assert exc.value.code == flywheel.CANNOT_RUN
        assert (
            "'yesterday' is not a UTC time such as 2026-10-15T09:00:00Z" in capsys.readouterr().err
        )
        assert calls == []


@pytest.mark.spec("events-cmd-scopes-to-round")
class DescribeEventsForOneRound:
    @pytest.fixture
    def two_rounds(self, pulls):
        """Plan #70 holds issues 12 and 14, and a round started by a count holds 20 and 22."""
        return pulls(
            opened=[
                open_pull(31, "issue/12"),
                open_pull(33, "issue/20"),
                open_pull(35, "issue/30"),
            ],
            merged=[
                merged_pull(41, "issue/14", "2026-10-15T11:00:00Z"),
                merged_pull(43, "issue/22", "2026-10-15T12:00:00Z"),
                merged_pull(45, "issue/30", "2026-10-15T13:00:00Z"),
            ],
            subs={70: [12, 14, 16]},
        )

    def it_lists_only_the_pull_requests_from_a_plans_sub_issues(self, project, two_rounds):
        code, env = project.run("events", "--plan", "70", "--since", SINCE)
        assert code == flywheel.OK
        assert [p["number"] for p in env["data"]["open"]] == [31]
        assert [p["number"] for p in env["data"]["merged"]] == [41]

    def it_lists_only_the_pull_requests_from_the_issues_it_names(self, project, two_rounds):
        code, env = project.run("events", "--issue", "20", "--issue", "22", "--since", SINCE)
        assert code == flywheel.OK
        assert [p["number"] for p in env["data"]["open"]] == [33]
        assert [p["number"] for p in env["data"]["merged"]] == [43]

    def it_takes_the_next_look_from_every_claims_merge(self, project, two_rounds):
        _, env = project.run("events", "--issue", "20", "--since", SINCE)
        assert env["data"]["merged"] == []
        assert env["data"]["as_of"] == "2026-10-15T13:00:00Z"

    def it_reads_no_sub_issues_without_a_plan(self, project, two_rounds):
        project.run("events", "--issue", "20")
        assert not [c for c in two_rounds if c[0] == "api"]

    def it_takes_a_plan_or_issues_but_not_both(self, project, pulls, capsys):
        calls = pulls()
        with pytest.raises(SystemExit) as exc:
            flywheel.main(["events", "--plan", "70", "--issue", "20", "-C", str(project.root)])
        assert exc.value.code == flywheel.CANNOT_RUN
        assert "not allowed with argument" in capsys.readouterr().err
        assert calls == []

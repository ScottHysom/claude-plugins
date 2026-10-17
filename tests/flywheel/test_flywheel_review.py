"""What the reviewer and the merge policy read and write: `review-policy`,
`review-brief`, `review-post` and `merge-check`.

The policies are the ones `config init` writes, with `areas` filled in. gh is
faked here with one pull request, its review threads and its issue, which a
test changes to break one condition at a time.
"""

import io
import json

import pytest

import flywheel

HEAD = "a" * 40
OLD = "b" * 40
REVIEWED_AT = "2026-10-16T10:00:00Z"
BEFORE = "2026-10-16T09:00:00Z"
AFTER = "2026-10-16T11:00:00Z"
AREAS = {"plugin:demo": ["plugins/demo/", "tests/demo/"]}
CLEAN_BODY = (
    "## Scenario\n\nAn owner runs it.\n\n### Before\n\nIt broke.\n\n"
    "## Requirements\n\nDoes not change any requirement.\n\n"
    "## Test plan\n\n- `tests-demo` ran.\n"
)


def check_run(status="COMPLETED", conclusion="SUCCESS"):
    return {"__typename": "CheckRun", "status": status, "conclusion": conclusion}


def review(head=HEAD, at=REVIEWED_AT, body=None):
    return {
        "body": flywheel.REVIEW_MARK + "`%s`: no findings." % head if body is None else body,
        "submittedAt": at,
        "commit": {"oid": head},
    }


def thread(tid, first, *replies, resolved=False, path="plugins/demo/app.py", line=3):
    """A review thread: its first comment at BEFORE, then each (body, time) reply."""
    comments = [{"body": first, "createdAt": BEFORE}]
    comments += [{"body": body, "createdAt": at} for body, at in replies]
    return {
        "id": tid,
        "isResolved": resolved,
        "path": path,
        "line": line,
        "originalLine": line,
        "comments": {"nodes": comments},
    }


def finding(level, text="It breaks."):
    return "%s %s: %s" % (flywheel.AGENT_MARK, level, text)


ANSWER = flywheel.AGENT_MARK + " Fixed in 3e1a9c0."


class FakeGitHub:
    """gh, answering for pull request #71, from issue/12, which closes #12."""

    def __init__(self):
        self.pull = {
            "number": 71,
            "title": "Fix the thing",
            "url": "https://github.com/owner/project/pull/71",
            "state": "OPEN",
            "headRefName": "issue/12",
            "headRefOid": HEAD,
            "body": CLEAN_BODY,
            "files": [{"path": "plugins/demo/app.py"}, {"path": "tests/demo/test_app.py"}],
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [check_run()],
            "closingIssuesReferences": [{"number": 12}],
            "reviews": [review()],
        }
        self.threads = []
        self.labels = ["approved", "plugin:demo", "enhancement"]
        self.diff = "diff --git a/plugins/demo/app.py b/plugins/demo/app.py\n+fixed\n"
        self.missing = False
        self.merge_error = None
        self.calls = []
        self.posted = []
        self.resolved = []
        self.merged = []

    def __call__(self, root, *args, stdin=None):
        self.calls.append(args)
        if args[:2] == ("pr", "view"):
            return json.dumps(self.pull)
        if args[:2] == ("pr", "diff"):
            return self.diff
        if args[:2] == ("pr", "merge"):
            if self.merge_error:
                raise flywheel.Fatal(self.merge_error)
            self.merged.append(args)
            return ""
        if args[:2] == ("issue", "view"):
            return json.dumps(
                {
                    "number": int(args[2]),
                    "title": "issue",
                    "state": "OPEN",
                    "labels": [{"name": n} for n in self.labels],
                    "comments": [],
                }
            )
        if args[:2] == ("api", "graphql"):
            query = next(a for a in args if a.startswith("query="))
            if "resolveReviewThread" in query:
                self.resolved.append(next(a for a in args if a.startswith("id="))[3:])
                return "{}"
            pull = None if self.missing else {"reviewThreads": {"nodes": self.threads}}
            return json.dumps({"data": {"repository": {"pullRequest": pull}}})
        if args[0] == "api" and args[1] == flywheel.REVIEWS_PATH % 71:
            self.posted.append(json.loads(stdin))
            return "{}"
        raise AssertionError("unexpected gh call: %r" % (args,))


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(flywheel, "gh", fake)
    return fake


def set_setting(project, rel, key, value):
    """Put value under key in the settings of the policy at rel."""
    path = project.root / rel
    text = path.read_text()
    m = flywheel.SETTINGS_RE.search(text)
    settings = json.loads(m.group(1))
    settings[key] = value
    path.write_text(text[: m.start(1)] + json.dumps(settings) + "\n" + text[m.end(1) :])


@pytest.fixture
def policies(project):
    """The policies config init writes, with areas filled in."""
    project.run("config", "init")
    set_setting(project, flywheel.MERGE_POLICY, "areas", AREAS)
    return project


# --------------------------------------------------------------------------
# review-policy
# --------------------------------------------------------------------------


@pytest.mark.spec("reviewpolicy-cmd-prints-policy")
class DescribeReviewPolicy:
    def it_prints_the_policy_whole_in_text(self, policies):
        code, out, err = policies.human("review-policy")
        assert code == flywheel.OK
        assert out == policies.read(flywheel.REVIEW_POLICY).decode()
        assert "| P3 | Nice to have, such as a nit |" in out
        assert (
            err
            == 'warning: .flywheel/review-policy.md leaves "rules" unset. The owner fills it in.\n'
        )

    def it_gives_the_cap_and_the_rules(self, policies):
        set_setting(policies, flywheel.REVIEW_POLICY, "rules", ["CLAUDE.md"])
        set_setting(policies, flywheel.REVIEW_POLICY, "p3_cap", 5)
        code, env = policies.run("review-policy")
        assert code == flywheel.OK
        assert env["data"]["p3_cap"] == 5
        assert env["data"]["rules"] == ["CLAUDE.md"]
        assert env["data"]["text"] == policies.read(flywheel.REVIEW_POLICY).decode()
        assert env["warnings"] == []

    def it_stops_when_the_policy_is_missing(self, project):
        code, env = project.run("review-policy")
        assert (code, env) == (flywheel.CANNOT_RUN, None)
        assert ".flywheel/review-policy.md is missing. Run config init" in project.err

    @pytest.mark.parametrize("cap", [-1, "3", True, None, 1.5])
    def it_stops_on_a_cap_that_is_not_a_count(self, policies, cap):
        set_setting(policies, flywheel.REVIEW_POLICY, "p3_cap", cap)
        code, _ = policies.run("review-policy")
        assert code == flywheel.CANNOT_RUN
        assert 'gives "p3_cap" as' in policies.err

    @pytest.mark.parametrize("rules", ["CLAUDE.md", [1], [""]])
    def it_stops_on_rules_that_are_not_paths(self, policies, rules):
        set_setting(policies, flywheel.REVIEW_POLICY, "rules", rules)
        code, _ = policies.run("review-policy")
        assert code == flywheel.CANNOT_RUN
        assert 'gives "rules" as' in policies.err

    def it_stops_on_settings_it_cannot_read(self, policies):
        policies.write(flywheel.REVIEW_POLICY, "# Review policy\n\n```json\n{oops\n```\n")
        code, _ = policies.run("review-policy")
        assert code == flywheel.CANNOT_RUN
        assert "are not valid JSON" in policies.err
        assert "Fix it, then run again." in policies.err


# --------------------------------------------------------------------------
# review-brief
# --------------------------------------------------------------------------


@pytest.mark.spec("reviewbrief-cmd-prints-pull-request")
class DescribeReviewBrief:
    def it_gives_the_head_description_requirements_threads_and_diff(self, project, github):
        github.pull["body"] = CLEAN_BODY.replace(
            "Does not change any requirement.", "Adds `demo-cmd-works` and `repo:demo-thing`."
        )
        github.threads = [thread("T1", finding("P1"), (ANSWER, AFTER))]
        code, env = project.run("review-brief", "71")
        assert code == flywheel.OK
        data = env["data"]
        assert data["head"] == HEAD
        assert data["reviewed"] == HEAD
        assert data["requirements"] == ["demo-cmd-works", "repo:demo-thing"]
        assert data["diff"] == github.diff
        assert data["threads"] == [
            {
                "id": "T1",
                "path": "plugins/demo/app.py",
                "line": 3,
                "resolved": False,
                "level": "P1",
                "comments": [
                    {"body": finding("P1"), "created_at": BEFORE},
                    {"body": ANSWER, "created_at": AFTER},
                ],
            }
        ]

    def it_shows_the_unresolved_threads_and_the_diff_in_text(self, project, github):
        github.pull["reviews"] = []
        github.threads = [
            thread("T1", finding("P2", "Name it.")),
            thread("T2", finding("P3", "Gone."), resolved=True),
        ]
        code, out, _ = project.human("review-brief", "71")
        assert code == flywheel.OK
        assert "The reviewer has not reviewed it before." in out
        assert "### plugins/demo/app.py:3, thread T1" in out
        assert "Name it." in out
        assert "Gone." not in out
        assert "```diff\n%s```" % github.diff in out
        assert "> ## Requirements" in out

    def it_says_when_no_thread_is_open(self, project, github):
        code, out, _ = project.human("review-brief", "71")
        assert code == flywheel.OK
        assert "The reviewer last reviewed %s." % HEAD in out
        assert "## Unresolved threads\n\nNone." in out

    def it_names_the_requirement_ids_in_text(self, project, github):
        github.pull["body"] = "## Requirements\n\nChanges `demo-cmd-works`.\n"
        _, out, _ = project.human("review-brief", "71")
        assert "Requirement ids it lists: demo-cmd-works\n" in out

    def it_marks_an_empty_description(self, project, github):
        github.pull["body"] = ""
        _, out, _ = project.human("review-brief", "71")
        assert "## Description\n\n(empty)" in out

    def it_refuses_a_closed_pull_request(self, project, github):
        github.pull["state"] = "MERGED"
        code, out, err = project.human("review-brief", "71")
        assert code == flywheel.PROBLEMS
        assert out == ""
        assert "#71 is merged. The reviewer reviews an open pull request" in err

    def it_stops_on_a_number_that_is_not_a_pull_request(self, project, github):
        github.missing = True
        code, _ = project.run("review-brief", "71")
        assert code == flywheel.CANNOT_RUN
        assert "#71 is not a pull request in this repository" in project.err


# --------------------------------------------------------------------------
# review-post
# --------------------------------------------------------------------------


def post(project, findings, *extra):
    path = project.write("findings.json", json.dumps(findings))
    return project.run("review-post", "71", "--findings", str(path), *extra)


def one(level="P1", **change):
    item = {"path": "plugins/demo/app.py", "line": 3, "level": level, "body": "It breaks."}
    item.update(change)
    return item


@pytest.mark.spec("reviewpost-cmd-posts-comment-review", "reviewpr-never-approves")
class DescribeReviewPostPosting:
    def it_posts_one_review_of_the_head_that_only_comments(self, policies, github):
        code, env = post(
            policies, {"head": HEAD, "findings": [one("P1"), one("P3", line=9, body="A nit.")]}
        )
        assert code == flywheel.OK
        assert env["data"] == {"number": 71, "posted": True, "findings": 2, "resolved": []}
        [payload] = github.posted
        assert payload["event"] == "COMMENT"
        assert payload["commit_id"] == HEAD
        assert payload["body"] == "%s`%s`: 2 findings (P1 1, P3 1)." % (flywheel.REVIEW_MARK, HEAD)
        assert payload["comments"] == [
            {"path": "plugins/demo/app.py", "line": 3, "side": "RIGHT", "body": finding("P1")},
            {
                "path": "plugins/demo/app.py",
                "line": 9,
                "side": "RIGHT",
                "body": finding("P3", "A nit."),
            },
        ]

    def it_posts_a_review_without_findings_with_its_summary(self, policies, github):
        code, out, _ = policies.human(
            "review-post",
            "71",
            "--findings",
            str(
                policies.write(
                    "f.json", json.dumps({"head": HEAD, "summary": "  Read all three passes.\n"})
                )
            ),
        )
        assert code == flywheel.OK
        assert out == "posted a review of #71 at aaaaaaa with 0 findings, and resolved 0 threads\n"
        assert github.posted[0]["body"] == "%s`%s`: no findings.\n\nRead all three passes." % (
            flywheel.REVIEW_MARK,
            HEAD,
        )
        assert github.posted[0]["comments"] == []

    def it_resolves_each_thread_the_reviewer_accepts(self, policies, github):
        github.threads = [
            thread("T1", finding("P1"), (ANSWER, AFTER)),
            thread("T2", finding("P2"), (ANSWER, AFTER)),
        ]
        code, env = post(policies, {"head": HEAD, "resolve": ["T2"]})
        assert code == flywheel.OK
        assert github.resolved == ["T2"]
        assert env["data"]["resolved"] == ["T2"]
        assert len(github.posted) == 1

    def it_reads_the_findings_from_stdin(self, policies, github, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"head": HEAD})))
        code, _ = policies.run("review-post", "71", "--findings", "-")
        assert code == flywheel.OK
        assert len(github.posted) == 1


@pytest.mark.spec("reviewpost-cmd-checks-findings")
class DescribeReviewPostRefusing:
    @pytest.mark.parametrize(
        ("findings", "fault"),
        [
            ({"head": OLD}, 'the findings are for "%s", but the head of #71 is %s' % (OLD, HEAD)),
            (
                {"head": HEAD, "extra": 1},
                'the findings hold "extra", which review-post does not take',
            ),
            ({"head": HEAD, "summary": 3}, '"summary" is not text'),
            ({"head": HEAD, "findings": {}}, '"findings" is not a list'),
            ({"head": HEAD, "findings": [{"path": "x"}]}, "finding 1 does not hold exactly"),
            ({"head": HEAD, "findings": ["P1"]}, "finding 1 does not hold exactly"),
            (
                {"head": HEAD, "findings": [one(path="README.md")]},
                'finding 1 is on "README.md", which #71 does not change',
            ),
            (
                {"head": HEAD, "findings": [one(line=0)]},
                "finding 1 gives line 0, not a line number",
            ),
            ({"head": HEAD, "findings": [one(line=True)]}, "finding 1 gives line true"),
            ({"head": HEAD, "findings": [one(level="P4")]}, 'finding 1 gives level "P4"'),
            ({"head": HEAD, "findings": [one(body=" ")]}, "finding 1 has an empty body"),
            ({"head": HEAD, "findings": [one(body=finding("P1"))]}, "finding 1 opens with"),
            ({"head": HEAD, "resolve": "T1"}, '"resolve" is not a list'),
            ({"head": HEAD, "resolve": ["T9"]}, '"T9" is not an unresolved thread on #71'),
            ({"head": HEAD, "resolve": ["T3"]}, '"T3" is not an unresolved thread on #71'),
            ({"head": HEAD, "resolve": ["T1", "T1"]}, '"resolve" names a thread more than once'),
        ],
    )
    def it_refuses_findings_that_break_a_rule_and_posts_nothing(
        self, policies, github, findings, fault
    ):
        github.threads = [
            thread("T1", finding("P1"), (ANSWER, AFTER)),
            thread("T3", finding("P2"), resolved=True),
        ]
        code, env = post(policies, findings)
        assert code == flywheel.PROBLEMS
        assert env["data"]["posted"] is False
        assert any(fault in e for e in env["errors"]), env["errors"]
        assert github.posted == []
        assert github.resolved == []

    def it_refuses_more_nits_than_the_cap(self, policies, github):
        set_setting(policies, flywheel.REVIEW_POLICY, "p3_cap", 1)
        code, env = post(policies, {"head": HEAD, "findings": [one("P3"), one("P3", line=4)]})
        assert code == flywheel.PROBLEMS
        assert env["errors"] == [
            "the findings hold 2 P3 findings, more than the review policy's cap of 1. Post the 1"
            " that matter most"
        ]
        assert github.posted == []

    def it_posts_as_many_nits_as_the_cap(self, policies, github):
        set_setting(policies, flywheel.REVIEW_POLICY, "p3_cap", 2)
        code, _ = post(policies, {"head": HEAD, "findings": [one("P3"), one("P3", line=4)]})
        assert code == flywheel.OK

    def it_refuses_findings_on_a_closed_pull_request(self, policies, github):
        github.pull["state"] = "CLOSED"
        code, env = post(policies, {"head": HEAD})
        assert code == flywheel.PROBLEMS
        assert env["errors"] == ["#71 is closed, not open"]

    def it_refuses_findings_that_are_not_an_object(self, policies, github):
        code, env = post(policies, [])
        assert code == flywheel.PROBLEMS
        assert env["errors"][0].startswith("the findings are not a JSON object")

    def it_names_every_fault_in_one_run(self, policies, github):
        code, env = post(policies, {"head": OLD, "findings": [one(level="P9", line=-2)]})
        assert code == flywheel.PROBLEMS
        assert len(env["errors"]) == 3

    def it_says_nothing_on_stdout_in_text(self, policies, github):
        path = policies.write("f.json", json.dumps({"head": OLD}))
        code, out, err = policies.human("review-post", "71", "--findings", str(path))
        assert code == flywheel.PROBLEMS
        assert out == ""
        assert "Read review-brief again" in err

    def it_stops_on_findings_that_are_not_json(self, policies, github):
        path = policies.write("f.json", "{oops")
        code, _ = policies.run("review-post", "71", "--findings", str(path))
        assert code == flywheel.CANNOT_RUN
        assert "the findings are not valid JSON" in policies.err


# --------------------------------------------------------------------------
# merge-check
# --------------------------------------------------------------------------


def check(project, *extra):
    code, env = project.run("merge-check", "71", *extra)
    return code, env["data"] if env else None


@pytest.mark.spec("mergecheck-cmd-flows-clean-pr")
class DescribeACleanPullRequest:
    def it_flows(self, policies, github):
        code, data = check(policies)
        assert code == flywheel.OK
        assert data["verdict"] == flywheel.FLOW
        assert data["next"] == flywheel.NEXT_MERGE
        assert data["reasons"] == []
        assert data["merged"] is False
        assert github.merged == []

    def it_says_so_in_text(self, policies, github):
        code, out, err = policies.human("merge-check", "71")
        assert code == flywheel.OK
        assert out == "#71 flows at aaaaaaa\n"
        assert err == ""

    def it_flows_with_resolved_findings_and_answered_threads(self, policies, github):
        github.threads = [
            thread("T1", finding("P1"), (ANSWER, BEFORE), resolved=True),
            thread("T2", "Why this name?", ("Because.", BEFORE)),
        ]
        code, data = check(policies)
        assert (code, data["verdict"]) == (flywheel.OK, flywheel.FLOW)

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"headRefName": "feature"}, "its branch feature is not a claim branch, issue/N"),
            ({"closingIssuesReferences": []}, "it does not close #12, the issue its branch claims"),
            ({"state": "CLOSED"}, "#71 is closed, not open"),
            ({"statusCheckRollup": []}, "no check ran on its head"),
        ],
    )
    def it_holds_when_a_flow_condition_fails(self, policies, github, change, reason):
        github.pull.update(change)
        code, data = check(policies)
        assert code == flywheel.PROBLEMS
        assert data["verdict"] == flywheel.HOLD
        assert reason in data["reasons"]

    def it_holds_an_issue_that_lost_its_approval(self, policies, github):
        github.labels = ["plugin:demo"]
        _, data = check(policies)
        assert "#12 is not labeled approved" in data["reasons"]


@pytest.mark.spec("mergecheck-cmd-holds-requirement-changes")
class DescribeARequirementChange:
    def it_holds_a_pull_request_that_names_requirement_ids(self, policies, github):
        github.pull["body"] = CLEAN_BODY.replace(
            "Does not change any requirement.",
            "Adds `demo-cmd-works`, and changes `repo:demo-thing` and `demo-cmd-works`.",
        )
        code, data = check(policies)
        assert code == flywheel.PROBLEMS
        assert data["reasons"] == [
            "it changes requirements: its ## Requirements section names demo-cmd-works,"
            " repo:demo-thing"
        ]
        assert data["next"] == flywheel.NEXT_ASK

    def it_holds_a_pull_request_without_the_section(self, policies, github):
        github.pull["body"] = "## Scenario\n\nAn owner runs it.\n"
        _, data = check(policies)
        assert data["reasons"] == [
            "its description has no ## Requirements section, so it may change a requirement"
        ]

    def it_reads_only_the_requirements_section(self, policies, github):
        github.pull["body"] = (
            "## Change\n\nTouches `demo-cmd-works`.\n\n## Requirements\n\nNone change.\n"
            "### Detail\n\nStill none.\n\n# Notes\n\n`after-the-section`\n"
        )
        code, data = check(policies)
        assert (code, data["reasons"]) == (flywheel.OK, [])

    def it_holds_an_id_under_a_subheading_of_the_section(self, policies, github):
        github.pull["body"] = "## Requirements\n\n### Added\n\n- `demo-cmd-works`\n"
        _, data = check(policies)
        assert data["reasons"][0].endswith("names demo-cmd-works")


@pytest.mark.spec("mergecheck-cmd-holds-protected-paths")
class DescribeAProtectedPath:
    @pytest.mark.parametrize(
        ("path", "pattern"),
        [
            ("specs/demo.md", "specs/"),
            ("CLAUDE.md", "CLAUDE.md"),
            (".github/workflows/ci.yml", ".github/"),
            ("plugins/demo/templates/policy.md", "plugins/*/templates/"),
        ],
    )
    def it_holds_and_names_the_path(self, policies, github, path, pattern):
        set_setting(policies, flywheel.MERGE_POLICY, "areas", {"plugin:demo": ["*"]})
        github.pull["files"].append({"path": path})
        code, data = check(policies)
        assert code == flywheel.PROBLEMS
        assert data["reasons"] == [
            "it touches %s, which the merge policy protects as %s" % (path, pattern)
        ]

    def it_leaves_a_file_that_only_shares_a_name_with_a_protected_one(self, policies, github):
        set_setting(policies, flywheel.MERGE_POLICY, "areas", {"plugin:demo": ["*"]})
        github.pull["files"] = [{"path": "plugins/demo/CLAUDE.md"}, {"path": "specs.txt"}]
        code, data = check(policies)
        assert (code, data["reasons"]) == (flywheel.OK, [])

    @pytest.mark.parametrize("protected", ["specs/", [3], None])
    def it_stops_on_protected_paths_it_cannot_read(self, policies, github, protected):
        set_setting(policies, flywheel.MERGE_POLICY, "protected", protected)
        code, _ = check(policies)
        assert code == flywheel.CANNOT_RUN
        assert 'gives "protected" as' in policies.err


@pytest.mark.spec("mergecheck-cmd-holds-outside-area")
class DescribeTheIssuesArea:
    def it_holds_a_file_outside_the_area(self, policies, github):
        github.pull["files"].append({"path": "plugins/other/app.py"})
        _, data = check(policies)
        assert data["reasons"] == [
            "it changes plugins/other/app.py, outside the paths areas gives plugin:demo"
        ]

    def it_takes_the_paths_of_every_area_label_the_issue_has(self, policies, github):
        set_setting(
            policies,
            flywheel.MERGE_POLICY,
            "areas",
            {"Plugin:Demo": ["plugins/demo/"], "repo": ["tests/"]},
        )
        github.labels.append("repo")
        code, data = check(policies)
        assert (code, data["reasons"]) == (flywheel.OK, [])

    def it_holds_an_issue_without_an_area_the_policy_names(self, policies, github):
        github.labels = ["approved"]
        _, data = check(policies)
        assert data["reasons"] == ["#12 has no area label that the merge policy's areas name"]

    def it_holds_everything_while_areas_is_unset(self, project, github):
        project.run("config", "init")
        _, data = check(project)
        assert data["reasons"] == [
            '.flywheel/merge-policy.md leaves "areas" unset, so no file lies inside an area.'
            " The owner fills it in"
        ]

    @pytest.mark.parametrize("areas", [[], {"plugin:demo": "plugins/demo/"}])
    def it_stops_on_areas_it_cannot_read(self, policies, github, areas):
        set_setting(policies, flywheel.MERGE_POLICY, "areas", areas)
        code, _ = check(policies)
        assert code == flywheel.CANNOT_RUN
        assert 'gives "areas" as' in policies.err

    def it_stops_when_the_merge_policy_is_missing(self, project, github):
        code, _ = check(project)
        assert code == flywheel.CANNOT_RUN
        assert ".flywheel/merge-policy.md is missing. Run config init" in project.err


@pytest.mark.spec("mergecheck-cmd-holds-open-findings")
class DescribeOpenFindings:
    @pytest.mark.parametrize("level", ["P0", "P1", "P2"])
    def it_holds_a_finding_left_open_after_the_reviewers_look(self, policies, github, level):
        github.threads = [thread("T1", finding(level), (ANSWER, BEFORE))]
        code, data = check(policies)
        assert code == flywheel.PROBLEMS
        assert data["reasons"] == ["a %s finding is open at plugins/demo/app.py:3" % level]
        assert data["next"] == flywheel.NEXT_ASK

    def it_holds_a_nit_the_reviewer_did_not_accept_the_answer_to(self, policies, github):
        github.threads = [thread("T1", finding("P3"), (ANSWER, BEFORE))]
        _, data = check(policies)
        assert data["reasons"] == [
            "the thread at plugins/demo/app.py:3 is unresolved after the reviewer looked at its"
            " answer, so the reviewer and the implementer disagree"
        ]

    def it_holds_a_thread_without_an_answer(self, policies, github):
        github.threads = [thread("T1", "Why?")]
        _, data = check(policies)
        assert data["reasons"] == ["the thread at plugins/demo/app.py:3 has no answer"]

    def it_holds_until_the_reviewer_has_reviewed(self, policies, github):
        github.pull["reviews"] = [{"body": "LGTM", "submittedAt": AFTER, "commit": {"oid": HEAD}}]
        _, data = check(policies)
        assert data["reasons"] == ["the reviewer has not reviewed it"]

    def it_holds_a_review_of_an_older_head(self, policies, github):
        github.pull["reviews"] = [review(OLD)]
        github.threads = [thread("T1", finding("P1"), (ANSWER, BEFORE))]
        _, data = check(policies)
        assert data["reasons"] == [
            "the reviewer's last review is of bbbbbbb, not of the head, aaaaaaa"
        ]

    def it_takes_the_reviewers_latest_review(self, policies, github):
        github.pull["reviews"] = [review(HEAD, BEFORE), review(OLD, AFTER)]
        _, data = check(policies)
        assert data["reasons"] == [
            "the reviewer's last review is of bbbbbbb, not of the head, aaaaaaa"
        ]

    def it_holds_an_answer_the_reviewer_has_not_looked_at(self, policies, github):
        github.threads = [thread("T1", finding("P2"), (ANSWER, AFTER))]
        _, data = check(policies)
        assert data["reasons"] == [
            "the thread at plugins/demo/app.py:3 has an answer the reviewer has not looked at"
        ]


@pytest.mark.spec("mergecheck-cmd-names-next-step")
class DescribeTheNextStep:
    def it_asks_for_a_review_first(self, policies, github):
        github.pull["reviews"] = []
        github.pull["statusCheckRollup"] = [check_run(status="IN_PROGRESS")]
        _, data = check(policies)
        assert data["next"] == flywheel.NEXT_REVIEW

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"statusCheckRollup": [check_run(conclusion="FAILURE")]}, "a check fails on its head"),
            (
                {"statusCheckRollup": [check_run(status="QUEUED")]},
                "a check is still running on its head",
            ),
            ({"mergeable": "CONFLICTING"}, "it conflicts with its base branch"),
        ],
    )
    def it_waits_on_the_implementer(self, policies, github, change, reason):
        github.pull.update(change)
        github.pull["reviews"] = [review(OLD)]
        _, data = check(policies)
        assert data["next"] == flywheel.NEXT_WAIT
        assert reason in data["reasons"]

    def it_waits_for_an_answer_to_each_thread(self, policies, github):
        github.threads = [thread("T1", finding("P1"))]
        _, data = check(policies)
        assert data["next"] == flywheel.NEXT_WAIT

    @pytest.mark.parametrize(
        ("reviews", "replied_at"), [([review(OLD)], BEFORE), ([review()], AFTER)]
    )
    def it_asks_for_a_second_look_once_every_thread_is_answered(
        self, policies, github, reviews, replied_at
    ):
        github.pull["reviews"] = reviews
        github.threads = [thread("T1", finding("P1"), (ANSWER, replied_at))]
        _, data = check(policies)
        assert data["next"] == flywheel.NEXT_REVIEW

    def it_asks_the_owner_once_nobody_else_has_a_step(self, policies, github):
        github.pull["files"].append({"path": "specs/demo.md"})
        _, data = check(policies)
        assert data["next"] == flywheel.NEXT_ASK

    def it_asks_the_owner_about_a_pull_request_that_is_not_open(self, policies, github):
        github.pull["state"] = "MERGED"
        github.pull["reviews"] = []
        _, data = check(policies)
        assert data["next"] == flywheel.NEXT_ASK

    def it_lists_the_reasons_on_stderr_in_text(self, policies, github):
        github.pull["reviews"] = []
        code, out, err = policies.human("merge-check", "71")
        assert code == flywheel.PROBLEMS
        assert out == "#71 holds at aaaaaaa, next: review\n"
        assert err == "the reviewer has not reviewed it\n"


@pytest.mark.spec("mergecheck-cmd-merges-on-flow")
class DescribeMerging:
    def it_squashes_a_pull_request_that_flows_at_the_head_it_checked(self, policies, github):
        code, data = check(policies, "--merge")
        assert code == flywheel.OK
        assert data["merged"] is True
        assert github.merged == [("pr", "merge", "71", "--squash", "--match-head-commit", HEAD)]

    def it_says_so_in_text(self, policies, github):
        code, out, _ = policies.human("merge-check", "71", "--merge")
        assert (code, out) == (flywheel.OK, "#71 merged at aaaaaaa\n")

    def it_merges_nothing_that_holds(self, policies, github):
        github.pull["files"].append({"path": "specs/demo.md"})
        code, data = check(policies, "--merge")
        assert code == flywheel.PROBLEMS
        assert data["merged"] is False
        assert not any(c[:2] == ("pr", "merge") for c in github.calls)

    def it_holds_for_the_owner_when_the_merge_fails(self, policies, github):
        github.merge_error = "`gh pr merge` failed: head branch was modified"
        code, data = check(policies, "--merge")
        assert code == flywheel.PROBLEMS
        assert data["merged"] is False
        assert data["verdict"] == flywheel.HOLD
        assert data["next"] == flywheel.NEXT_ASK
        assert data["reasons"] == [
            "the merge failed: `gh pr merge` failed: head branch was modified"
        ]

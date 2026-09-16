"""The linked-issue check is what holds "work only on approved issues" for
every agent, whatever surface it runs on. It fails in two directions: a link it
misses lets unapproved work merge, and a link it invents blocks a PR for an
issue it never named. Both are covered.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-linked-issues.py"
_spec = importlib.util.spec_from_file_location("check_linked_issues", _PATH)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

REPO = "ScottHysom/claude-plugins"
API = cli.API + "/repos/" + REPO

LINKED = [
    ("Closes #12", [12]),
    ("closes #12", [12]),
    ("Closed #12", [12]),
    ("Close #12", [12]),
    ("Fixes #12", [12]),
    ("fixed #12", [12]),
    ("Fix #12", [12]),
    ("Resolves #12", [12]),
    ("resolved #12", [12]),
    ("Resolve #12", [12]),
    ("Closes: #12", [12]),
    ("Fixes #12 and closes #13", [12, 13]),
    ("Fixes #12. Also fixes #12.", [12]),
    ("Closes ScottHysom/claude-plugins#12", [12]),
    ("Closes scotthysom/Claude-Plugins#12", [12]),
    ("Line one\n\nFixes #7\n", [7]),
]

NOT_LINKED = [
    "See #12",
    "Related to #12",
    "Closes 12",
    "prefixes #12",
    "Closes #12a",
    "`Closes #12`",
    "```\nCloses #12\n```",
    "~~~\nFixes #12\n~~~",
    "<!-- Closes #12 -->",
    "",
    None,
]


class DescribeLinkedIssues:
    @pytest.mark.parametrize(("text", "numbers"), LINKED)
    def it_links_an_issue_named_by_a_closing_keyword(self, text, numbers):
        assert cli.linked_issues(text, REPO) == (numbers, [])

    @pytest.mark.parametrize("text", NOT_LINKED)
    def it_links_nothing_without_a_closing_keyword(self, text):
        assert cli.linked_issues(text, REPO) == ([], [])

    def it_keeps_a_link_to_another_repository_apart(self):
        assert cli.linked_issues("Fixes other/repo#3", REPO) == ([], [("other/repo", 3)])


class FakeGitHub:
    """Canned API responses, keyed by URL. Records what was asked for."""

    def __init__(self, issues=None, commits=None, branches=()):
        self.issues = issues or {}
        self.commits = commits or []
        self.branches = set(branches)
        self.urls = []

    def __call__(self, url, token):
        self.urls.append(url)
        if "/pulls/" in url:
            page = int(url.rsplit("page=", 1)[1])
            start = (page - 1) * cli.PER_PAGE
            return [{"commit": {"message": m}} for m in self.commits[start : start + cli.PER_PAGE]]
        if "/git/ref/heads/" in url:
            name = url.split("/git/ref/heads/", 1)[1]
            return {"ref": "refs/heads/" + name} if name in self.branches else None
        number = int(url.rsplit("/", 1)[1])
        return self.issues.get(number)


def issue(*labels, pr=False):
    data = {"labels": [{"name": n} for n in labels]}
    if pr:
        data["pull_request"] = {}
    return data


def event(title="t", body="", head="issue/12", head_repo=REPO):
    return {
        "pull_request": {
            "number": 99,
            "title": title,
            "body": body,
            "head": {"ref": head, "repo": {"full_name": head_repo}},
        }
    }


class DescribeTheApprovedLabelRule:
    """The half of `problems` that asks whether each linked issue may be worked
    on at all - it exists, it is an issue rather than a pull request, and Scott
    has labelled it approved.
    """

    def it_passes_an_approved_issue(self):
        gh = FakeGitHub(issues={12: issue("bug", "approved")})
        assert cli.problems(event(body="Closes #12"), REPO, "tok", gh) == ([12], [])

    def it_fails_an_unapproved_issue_with_the_way_to_fix_it(self):
        gh = FakeGitHub(issues={12: issue("bug")})
        linked, found = cli.problems(event(body="Closes #12"), REPO, "tok", gh)
        assert linked == [12]
        assert len(found) == 1
        assert "#12 is not labelled approved" in found[0]
        assert "re-run this job" in found[0]

    def it_compares_label_names_without_case(self):
        gh = FakeGitHub(issues={12: issue("Approved")})
        assert cli.problems(event(body="Fixes #12"), REPO, "tok", gh)[1] == []

    def it_counts_a_link_in_the_title(self):
        gh = FakeGitHub(issues={12: issue()})
        assert cli.problems(event(title="fix: thing (fixes #12)"), REPO, "tok", gh)[1]

    def it_counts_a_link_in_a_commit_message(self):
        gh = FakeGitHub(issues={12: issue()}, commits=["fix: a\n\nFixes #12"])
        assert cli.problems(event(), REPO, "tok", gh)[1]

    def it_reads_commit_messages_past_the_first_page(self):
        commits = ["chore: %d" % i for i in range(cli.PER_PAGE)] + ["fix: last\n\nFixes #12"]
        gh = FakeGitHub(issues={12: issue()}, commits=commits)
        assert cli.problems(event(), REPO, "tok", gh)[1]

    def it_names_a_missing_issue_and_a_pull_request(self):
        gh = FakeGitHub(issues={13: issue("approved", pr=True)})
        _, found = cli.problems(event(body="Fixes #12, fixes #13"), REPO, "tok", gh)
        assert found == ["#12 does not exist", "#13 is a pull request, not an issue"]

    def it_fails_another_repository_without_fetching_it(self):
        gh = FakeGitHub()
        _, found = cli.problems(event(body="Fixes other/repo#3"), REPO, "tok", gh)
        assert "another repository" in found[0]
        assert not any("/issues/" in u for u in gh.urls)


class DescribeTheClaimBranchRule:
    """The other half of `problems`: an issue may only be closed from the
    `issue/N` branch that claiming made, so two agents cannot both work it.
    """

    def it_passes_an_issue_closed_from_its_claim_branch(self):
        gh = FakeGitHub(issues={12: issue("approved")}, branches={"issue/12"})
        assert cli.problems(event(body="Closes #12"), REPO, "tok", gh) == ([12], [])

    @pytest.mark.parametrize(
        ("head", "head_repo"),
        [
            ("feat/thing", REPO),
            ("issue/13", REPO),
            ("issue/12-slug", REPO),
            ("issue/12", "someone/fork"),
        ],
    )
    def it_fails_an_issue_closed_from_any_other_branch(self, head, head_repo):
        gh = FakeGitHub(issues={12: issue("approved")})
        _, found = cli.problems(
            event(body="Closes #12", head=head, head_repo=head_repo), REPO, "tok", gh
        )
        assert len(found) == 1
        assert "closes #12 from branch" in found[0]
        assert "issues.py claim N" in found[0]

    def it_fails_a_second_issue_claimed_by_someone_else(self):
        gh = FakeGitHub(
            issues={12: issue("approved"), 13: issue("approved")}, branches={"issue/13"}
        )
        _, found = cli.problems(event(body="Closes #12, closes #13"), REPO, "tok", gh)
        assert found == ["#13 is claimed on its own branch, issue/13"]

    def it_passes_a_second_unclaimed_issue(self):
        gh = FakeGitHub(
            issues={12: issue("approved"), 13: issue("approved")}, branches={"issue/12"}
        )
        assert cli.problems(event(body="Closes #12, closes #13"), REPO, "tok", gh)[1] == []

    def it_needs_no_claim_branch_when_nothing_is_closed(self):
        gh = FakeGitHub()
        assert cli.problems(event(body="Just a change.", head="feat/thing"), REPO, "tok", gh) == (
            [],
            [],
        )

    def it_passes_a_pull_request_with_no_link(self):
        gh = FakeGitHub()
        assert cli.problems(event(body="Just a change."), REPO, "tok", gh) == ([], [])


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def run(tmp_path, capsys, payload, fetch, environ=None):
    path = tmp_path / "event.json"
    path.write_text(json.dumps(payload))
    env = {"GITHUB_EVENT_PATH": str(path), "GITHUB_REPOSITORY": REPO, "GITHUB_TOKEN": "tok"}
    env.update(environ or {})
    code = cli.main([], env, fetch)
    return code, capsys.readouterr()


class DescribeMain:
    def it_exits_ok_with_no_links(self, tmp_path, capsys):
        code, out = run(tmp_path, capsys, event(), FakeGitHub())
        assert code == cli.OK
        assert out.out == "No linked issues.\n"
        assert out.err == ""

    def it_exits_problems_with_the_reason_on_stderr(self, tmp_path, capsys):
        code, out = run(
            tmp_path, capsys, event(body="Closes #12"), FakeGitHub(issues={12: issue()})
        )
        assert code == cli.PROBLEMS
        assert "#12 linked" in out.out
        assert "not labelled approved" in out.err

    def it_cannot_run_without_its_environment(self, tmp_path, capsys):
        code, out = run(tmp_path, capsys, event(), FakeGitHub(), {"GITHUB_TOKEN": ""})
        assert code == cli.CANNOT_RUN
        assert out.err.startswith("check-linked-issues.py: needs")

    def it_cannot_run_on_a_non_pull_request_event(self, tmp_path, capsys):
        code, out = run(tmp_path, capsys, {"push": {}}, FakeGitHub())
        assert code == cli.CANNOT_RUN
        assert "pull_request" in out.err

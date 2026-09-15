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


@pytest.mark.parametrize(("text", "numbers"), LINKED)
def test_a_closing_keyword_links_the_issue(text, numbers):
    assert cli.linked_issues(text, REPO) == (numbers, [])


@pytest.mark.parametrize("text", NOT_LINKED)
def test_text_that_is_not_a_closing_link_links_nothing(text):
    assert cli.linked_issues(text, REPO) == ([], [])


def test_a_link_to_another_repository_is_kept_apart():
    assert cli.linked_issues("Fixes other/repo#3", REPO) == ([], [("other/repo", 3)])


class FakeGitHub:
    """Canned API responses, keyed by URL. Records what was asked for."""

    def __init__(self, issues=None, commits=None):
        self.issues = issues or {}
        self.commits = commits or []
        self.urls = []

    def __call__(self, url, token):
        self.urls.append(url)
        if "/pulls/" in url:
            page = int(url.rsplit("page=", 1)[1])
            start = (page - 1) * cli.PER_PAGE
            return [{"commit": {"message": m}} for m in self.commits[start : start + cli.PER_PAGE]]
        number = int(url.rsplit("/", 1)[1])
        return self.issues.get(number)


def issue(*labels, pr=False):
    data = {"labels": [{"name": n} for n in labels]}
    if pr:
        data["pull_request"] = {}
    return data


def event(title="t", body=""):
    return {"pull_request": {"number": 99, "title": title, "body": body}}


def test_an_approved_issue_passes():
    gh = FakeGitHub(issues={12: issue("bug", "approved")})
    assert cli.problems(event(body="Closes #12"), REPO, "tok", gh) == ([12], [])


def test_an_unapproved_issue_fails_with_the_way_to_fix_it():
    gh = FakeGitHub(issues={12: issue("bug")})
    linked, found = cli.problems(event(body="Closes #12"), REPO, "tok", gh)
    assert linked == [12]
    assert len(found) == 1
    assert "#12 is not labelled approved" in found[0]
    assert "re-run this job" in found[0]


def test_label_names_compare_without_case():
    gh = FakeGitHub(issues={12: issue("Approved")})
    assert cli.problems(event(body="Fixes #12"), REPO, "tok", gh)[1] == []


def test_a_link_in_the_title_counts():
    gh = FakeGitHub(issues={12: issue()})
    assert cli.problems(event(title="fix: thing (fixes #12)"), REPO, "tok", gh)[1]


def test_a_link_in_a_commit_message_counts():
    gh = FakeGitHub(issues={12: issue()}, commits=["fix: a\n\nFixes #12"])
    assert cli.problems(event(), REPO, "tok", gh)[1]


def test_commit_messages_are_read_past_the_first_page():
    commits = ["chore: %d" % i for i in range(cli.PER_PAGE)] + ["fix: last\n\nFixes #12"]
    gh = FakeGitHub(issues={12: issue()}, commits=commits)
    assert cli.problems(event(), REPO, "tok", gh)[1]


def test_a_missing_issue_and_a_pull_request_are_named():
    gh = FakeGitHub(issues={13: issue("approved", pr=True)})
    _, found = cli.problems(event(body="Fixes #12, fixes #13"), REPO, "tok", gh)
    assert found == ["#12 does not exist", "#13 is a pull request, not an issue"]


def test_another_repository_fails_without_being_fetched():
    gh = FakeGitHub()
    _, found = cli.problems(event(body="Fixes other/repo#3"), REPO, "tok", gh)
    assert "another repository" in found[0]
    assert not any("/issues/" in u for u in gh.urls)


def test_no_link_passes():
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


def test_main_exits_ok_with_no_links(tmp_path, capsys):
    code, out = run(tmp_path, capsys, event(), FakeGitHub())
    assert code == cli.OK
    assert out.out == "No linked issues.\n"
    assert out.err == ""


def test_main_exits_problems_with_the_reason_on_stderr(tmp_path, capsys):
    code, out = run(tmp_path, capsys, event(body="Closes #12"), FakeGitHub(issues={12: issue()}))
    assert code == cli.PROBLEMS
    assert "#12 linked" in out.out
    assert "not labelled approved" in out.err


def test_main_cannot_run_without_its_environment(tmp_path, capsys):
    code, out = run(tmp_path, capsys, event(), FakeGitHub(), {"GITHUB_TOKEN": ""})
    assert code == cli.CANNOT_RUN
    assert out.err.startswith("check-linked-issues.py: needs")


def test_main_cannot_run_on_a_non_pull_request_event(tmp_path, capsys):
    code, out = run(tmp_path, capsys, {"push": {}}, FakeGitHub())
    assert code == cli.CANNOT_RUN
    assert "pull_request" in out.err

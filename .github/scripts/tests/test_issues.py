"""issues.py is what keeps two agents off the same issue. The claim has to be
atomic - two agents claiming at once, one wins - and release must never throw
away work. Both run against real git, with a bare repository standing in for
GitHub's; only gh is faked.
"""

import datetime
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "issues.py"
_spec = importlib.util.spec_from_file_location("issues", _PATH)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

MAIN_DATE = "2026-01-01T00:00:00+00:00"
NOW = datetime.datetime(2026, 3, 1, tzinfo=datetime.timezone.utc)


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Keep the developer's git config (signing, hooks, default branch) out."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv("GIT_%s_NAME" % who, "Test")
        monkeypatch.setenv("GIT_%s_EMAIL" % who, "test@example.com")
        monkeypatch.setenv("GIT_%s_DATE" % who, MAIN_DATE)
    monkeypatch.setattr(cli, "now", lambda: NOW)


@pytest.fixture
def remote(tmp_path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--quiet", "--bare", "-b", cli.BASE, str(bare))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "--quiet", str(bare), str(seed))
    (seed / "README").write_text("seed\n")
    git(seed, "add", "README")
    git(seed, "commit", "--quiet", "-m", "seed")
    git(seed, "push", "--quiet", cli.REMOTE, "HEAD:" + cli.BASE)
    return bare


@pytest.fixture
def clone(tmp_path, remote):
    def make(name):
        path = tmp_path / name
        git(tmp_path, "clone", "--quiet", str(remote), str(path))
        return path

    return make


def remote_branches(remote):
    out = git(remote, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    return set(out.split())


class FakeGitHub:
    """gh, answering from a dict of issues. Records every call."""

    def __init__(self, issues=None, pulls=None, fail=()):
        self.issues = issues or {}
        self.pulls = pulls or []
        self.fail = fail
        self.calls = []

    def __call__(self, repo, *args):
        self.calls.append(args)
        if any(word in args for word in self.fail):
            raise cli.Fatal("gh %s failed" % args[1])
        kind, verb = args[0], args[1]
        if kind == "pr":
            return json.dumps([{"headRefName": b} for b in self.pulls])
        if verb == "view":
            return json.dumps(self.issues[int(args[2])])
        if verb == "list":
            label = args[args.index("--label") + 1]
            return json.dumps(
                [
                    i
                    for _, i in sorted(self.issues.items())
                    if i["state"] == "OPEN" and label in names(i)
                ]
            )
        return ""

    def writes(self):
        return [c for c in self.calls if c[1] in ("edit", "comment")]


def names(item):
    return [lbl["name"] for lbl in item["labels"]]


def make_issue(number, *labels, state="OPEN", comments=()):
    return {
        "number": number,
        "title": "issue %d" % number,
        "state": state,
        "labels": [{"name": n} for n in labels],
        "comments": list(comments),
    }


@pytest.fixture
def github(monkeypatch):
    def install(*issues, **kwargs):
        fake = FakeGitHub({i["number"]: i for i in issues}, **kwargs)
        monkeypatch.setattr(cli, "gh", fake)
        return fake

    return install


def run(capsys, repo, *argv):
    code = cli.main([*argv, "-C", str(repo)])
    return code, capsys.readouterr()


def run_json(capsys, repo, *argv):
    code, out = run(capsys, repo, *argv, "--json")
    return code, json.loads(out.out)


# --------------------------------------------------------------------------
# claim
# --------------------------------------------------------------------------


def test_claim_pushes_the_branch_switches_to_it_and_says_so(capsys, remote, clone, github):
    a = clone("a")
    gh = github(make_issue(12, "approved"))
    code, out = run(capsys, a, "claim", "12")
    assert code == cli.OK
    assert out.out == "Claimed #12 on branch issue/12\n"
    assert "issue/12" in remote_branches(remote)
    assert git(a, "branch", "--show-current") == "issue/12"
    assert git(a, "rev-parse", "HEAD") == git(remote, "rev-parse", cli.BASE)
    assert ("issue", "edit", "12", "--add-label", cli.IN_PROGRESS) in gh.calls
    assert any(c[1] == "comment" and cli.CLAIM_MARK in c[-1] for c in gh.calls)


@pytest.mark.parametrize("main_moved", [False, True], ids=["same-main", "main-moved"])
def test_two_agents_claiming_at_once_cannot_both_win(
    capsys, remote, clone, github, monkeypatch, main_moved
):
    """B read the branch list before A pushed, so only the push can stop it.

    Off the same main, B's push is "up to date"; after main moves, it is a
    different commit. Git reports those two differently, and both must lose.
    """
    a, b = clone("a"), clone("b")
    github(make_issue(12, "approved"))
    assert run(capsys, a, "claim", "12")[0] == cli.OK
    before = git(remote, "rev-parse", "issue/12")
    if main_moved:
        seed = remote.parent / "seed"
        git(seed, "commit", "--quiet", "--allow-empty", "-m", "later")
        git(seed, "push", "--quiet", cli.REMOTE, "HEAD:" + cli.BASE)

    real, calls = cli.claims, []

    def stale_first_view(repo):
        calls.append(repo)
        return {} if len(calls) == 1 else real(repo)

    monkeypatch.setattr(cli, "claims", stale_first_view)
    gh = github(make_issue(12, "approved"))
    code, out = run(capsys, b, "claim", "12")

    assert code == cli.PROBLEMS
    assert "#12 is held" in out.err
    assert git(remote, "rev-parse", "issue/12") == before
    assert gh.writes() == []


def test_a_held_issue_is_refused_before_pushing(capsys, remote, clone, github):
    a, b = clone("a"), clone("b")
    github(make_issue(12, "approved"))
    run(capsys, a, "claim", "12")
    gh = github(make_issue(12, "approved", "in-progress"))
    code, out = run(capsys, b, "claim", "12")
    assert code == cli.PROBLEMS
    assert "#12 is held: branch issue/12 already exists" in out.err
    assert out.out == ""
    assert gh.writes() == []
    assert git(b, "branch", "--show-current") == cli.BASE


@pytest.mark.parametrize(
    ("item", "message"),
    [
        (make_issue(12), "#12 is not labelled approved"),
        (make_issue(12, "approved", state="CLOSED"), "#12 is closed"),
    ],
)
def test_claim_refuses_an_issue_that_may_not_be_worked_on(
    capsys, remote, clone, github, item, message
):
    gh = github(item)
    code, out = run(capsys, clone("a"), "claim", "12")
    assert code == cli.PROBLEMS
    assert message in out.err
    assert remote_branches(remote) == {cli.BASE}
    assert gh.writes() == []


def test_claim_dry_run_changes_nothing(capsys, remote, clone, github):
    a = clone("a")
    gh = github(make_issue(12, "approved"))
    code, out = run(capsys, a, "claim", "12", "--dry-run")
    assert code == cli.OK
    assert out.out == "Would claim #12 on branch issue/12\n"
    assert remote_branches(remote) == {cli.BASE}
    assert gh.writes() == []


def test_a_failed_label_after_the_push_is_a_warning(capsys, remote, clone, github):
    github(make_issue(12, "approved"), fail=("--add-label",))
    code, out = run(capsys, clone("a"), "claim", "12")
    assert code == cli.OK
    assert "warning: claimed, but could not add the in-progress label" in out.err
    assert "issue/12" in remote_branches(remote)


def test_a_push_refused_for_another_reason_cannot_run(capsys, remote, clone, github):
    """Only a branch that now exists means someone else holds the issue."""
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'no pushes today' >&2\nexit 1\n")
    hook.chmod(0o755)
    gh = github(make_issue(12, "approved"))
    code, out = run(capsys, clone("a"), "claim", "12")
    assert code == cli.CANNOT_RUN
    assert out.err.startswith("issues.py: could not push issue/12")
    assert gh.writes() == []


# --------------------------------------------------------------------------
# next
# --------------------------------------------------------------------------


def test_next_skips_labelled_and_branch_held_issues(capsys, remote, clone, github):
    a = clone("a")
    github(make_issue(10, "approved"))
    run(capsys, a, "claim", "10")
    github(
        make_issue(10, "approved"),  # held by branch, label not added yet
        make_issue(11, "approved", "in-progress"),
        make_issue(12),
        make_issue(14, "approved"),
        make_issue(13, "approved"),
    )
    code, data = run_json(capsys, a, "next")
    assert code == cli.OK
    assert data["data"]["issue"] == {"number": 13, "title": "issue 13"}


def test_next_with_nothing_free_is_not_a_problem(capsys, clone, github):
    github(make_issue(11, "approved", "in-progress"))
    code, out = run(capsys, clone("a"), "next")
    assert code == cli.OK
    assert out.out == "No approved issue is free.\n"


# --------------------------------------------------------------------------
# release
# --------------------------------------------------------------------------


def test_release_deletes_an_empty_branch_and_the_label(capsys, remote, clone, github):
    a = clone("a")
    github(make_issue(12, "approved"))
    run(capsys, a, "claim", "12")
    gh = github(make_issue(12, "approved", "in-progress"))
    code, out = run(capsys, a, "release", "12", "--reason", "blocked on #9")
    assert code == cli.OK
    assert remote_branches(remote) == {cli.BASE}
    assert ("issue", "edit", "12", "--remove-label", cli.IN_PROGRESS) in gh.calls
    assert ("issue", "comment", "12", "--body", "Released issue/12. blocked on #9") in gh.calls


def test_release_never_deletes_work(capsys, remote, clone, github):
    a = clone("a")
    github(make_issue(12, "approved"))
    run(capsys, a, "claim", "12")
    (a / "work").write_text("work\n")
    git(a, "add", "work")
    git(a, "commit", "--quiet", "-m", "work")
    git(a, "push", "--quiet")
    gh = github(make_issue(12, "approved", "in-progress"))
    code, out = run(capsys, clone("b"), "release", "12")
    assert code == cli.PROBLEMS
    assert "issue/12 has 1 commit(s) not on main" in out.err
    assert "issue/12" in remote_branches(remote)
    assert gh.writes() == []


def test_release_of_an_unclaimed_issue_is_a_problem(capsys, clone, github):
    github(make_issue(12, "approved"))
    code, out = run(capsys, clone("a"), "release", "12")
    assert code == cli.PROBLEMS
    assert "#12 is not claimed" in out.err


def test_release_dry_run_changes_nothing(capsys, remote, clone, github):
    a = clone("a")
    github(make_issue(12, "approved"))
    run(capsys, a, "claim", "12")
    gh = github(make_issue(12, "approved", "in-progress"))
    code, out = run(capsys, a, "release", "12", "--dry-run")
    assert code == cli.OK
    assert out.out == "Would release #12\n"
    assert "issue/12" in remote_branches(remote)
    assert gh.writes() == []


def test_a_released_issue_is_free_again(capsys, remote, clone, github):
    a = clone("a")
    github(make_issue(12, "approved"))
    run(capsys, a, "claim", "12")
    github(make_issue(12, "approved", "in-progress"))
    run(capsys, a, "release", "12")
    github(make_issue(12, "approved"))
    assert run_json(capsys, a, "next")[1]["data"]["issue"]["number"] == 12


# --------------------------------------------------------------------------
# stale
# --------------------------------------------------------------------------


def claim_comment(when):
    return {"body": "%s `issue/12`." % cli.CLAIM_MARK, "createdAt": when}


def claimed(capsys, clone, github):
    a = clone("a")
    github(make_issue(12, "approved"))
    run(capsys, a, "claim", "12")
    return a


def test_an_idle_claim_is_stale(capsys, clone, github):
    a = claimed(capsys, clone, github)
    github(
        make_issue(12, "approved", "in-progress", comments=[claim_comment("2026-02-01T00:00:00Z")])
    )
    code, out = run(capsys, a, "stale")
    assert code == cli.PROBLEMS
    assert "#12: issue/12 idle for 28 days" in out.err


def test_a_recent_claim_on_an_old_main_is_not_stale(capsys, clone, github):
    a = claimed(capsys, clone, github)
    github(
        make_issue(12, "approved", "in-progress", comments=[claim_comment("2026-02-28T00:00:00Z")])
    )
    code, out = run(capsys, a, "stale")
    assert code == cli.OK
    assert out.out == "No stale claims.\n"


def test_a_claim_with_an_open_pull_request_is_not_stale(capsys, clone, github):
    a = claimed(capsys, clone, github)
    github(make_issue(12, "approved", "in-progress"), pulls=["issue/12"])
    assert run(capsys, a, "stale")[0] == cli.OK


def test_a_branch_left_after_the_issue_closed_is_reported(capsys, clone, github):
    a = claimed(capsys, clone, github)
    github(make_issue(12, "approved", state="CLOSED"))
    code, out = run(capsys, a, "stale")
    assert code == cli.PROBLEMS
    assert "#12 is closed but issue/12 still exists" in out.err


def test_a_label_without_a_branch_is_reported(capsys, clone, github):
    github(make_issue(12, "approved", "in-progress"))
    code, out = run(capsys, clone("a"), "stale")
    assert code == cli.PROBLEMS
    assert "#12 is labelled in-progress but issue/12 does not exist" in out.err


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv", [["next"], ["claim", "12", "--dry-run"], ["release", "12"], ["stale"]]
)
def test_every_command_prints_the_same_envelope(capsys, clone, github, argv):
    github(make_issue(12, "approved"))
    _, data = run_json(capsys, clone("a"), *argv)
    assert set(data) == {"version", "command", "ok", "errors", "warnings", "data"}
    assert data["version"] == cli.ENVELOPE_VERSION
    assert data["command"] == argv[0]


def test_a_gh_failure_cannot_run(capsys, clone, github):
    github(fail=("view",))
    code, out = run(capsys, clone("a"), "claim", "12")
    assert code == cli.CANNOT_RUN
    assert out.out == ""
    assert out.err == "issues.py: gh view failed\n"


def test_outside_a_clone_cannot_run(capsys, tmp_path, github):
    github()
    code, out = run(capsys, tmp_path, "next")
    assert code == cli.CANNOT_RUN
    assert out.err.startswith("issues.py: ")

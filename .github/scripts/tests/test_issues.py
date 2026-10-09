"""issues.py is what keeps two agents off the same issue. The claim has to be
atomic - two agents claiming at once, one wins - and neither release nor clear
may throw away work. Both run against real git, with a bare repository standing in for
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

    def __init__(self, issues=None, pulls=None, merged=(), fail=(), blockers=None, subs=None):
        self.issues = issues or {}
        self.blockers = blockers or {}
        self.subs = subs or {}
        self.pulls = pulls or []
        self.merged = merged
        self.fail = fail
        self.calls = []

    def __call__(self, repo, *args):
        self.calls.append(args)
        if any(word in args for word in self.fail):
            raise cli.Fatal("gh %s failed" % args[1])
        kind, verb = args[0], args[1]
        if kind == "api" and "/sub_issues" in args[1]:
            # The REST API spells state in lower case, unlike gh issue list.
            number = int(args[1].split("/")[-2])
            return json.dumps(
                [
                    dict(self.issues[n], state=self.issues[n]["state"].lower())
                    for n in self.subs[number]
                ]
            )
        if kind == "api":
            number = int(args[1].split("/")[-3])
            return json.dumps(
                [{"number": n, "state": st} for n, st in self.blockers.get(number, [])]
            )
        if kind == "pr" and "merged" in args:
            head = args[args.index("--head") + 1] if "--head" in args else None
            return json.dumps(
                [
                    {"number": n, "headRefName": b, "headRefOid": sha}
                    for n, b, sha in self.merged
                    if head in (None, b)
                ]
            )
        if kind == "pr":
            return json.dumps([{"headRefName": b} for b in self.pulls])
        if verb == "view":
            return json.dumps(self.issues[int(args[2])])
        if verb == "list":
            label = args[args.index("--label") + 1]
            state = args[args.index("--state") + 1].upper()
            return json.dumps(
                [
                    i
                    for _, i in sorted(self.issues.items())
                    if state in ("ALL", i["state"]) and label in names(i)
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


class DescribeClaim:
    @pytest.mark.spec("claim-cmd-switches-to-issue-branch", "claim-cmd-adds-in-progress-label")
    def it_pushes_the_branch_switches_to_it_and_says_so(self, capsys, remote, clone, github):
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
    @pytest.mark.spec("claim-cmd-picks-one-winner")
    def it_lets_only_one_of_two_agents_claiming_at_once_win(
        self, capsys, remote, clone, github, monkeypatch, main_moved
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

    @pytest.mark.spec("claim-cmd-picks-one-winner")
    def it_refuses_a_held_issue_before_pushing(self, capsys, remote, clone, github):
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
            (make_issue(12), "#12 is not labeled approved"),
            (make_issue(12, "approved", state="CLOSED"), "#12 is closed"),
        ],
    )
    @pytest.mark.spec("claim-cmd-refuses-unapproved-issues")
    def it_refuses_an_issue_that_may_not_be_worked_on(
        self, capsys, remote, clone, github, item, message
    ):
        gh = github(item)
        code, out = run(capsys, clone("a"), "claim", "12")
        assert code == cli.PROBLEMS
        assert message in out.err
        assert remote_branches(remote) == {cli.BASE}
        assert gh.writes() == []

    @pytest.mark.spec("command-never-writes-in-preview")
    def it_changes_nothing_on_a_dry_run(self, capsys, remote, clone, github):
        a = clone("a")
        gh = github(make_issue(12, "approved"))
        code, out = run(capsys, a, "claim", "12", "--dry-run")
        assert code == cli.OK
        assert out.out == "Would claim #12 on branch issue/12\n"
        assert remote_branches(remote) == {cli.BASE}
        assert gh.writes() == []

    @pytest.mark.spec(
        "claim-cmd-adds-in-progress-label", "command-splits-output-streams-without-json"
    )
    def it_warns_when_the_label_fails_after_the_push(self, capsys, remote, clone, github):
        github(make_issue(12, "approved"), fail=("--add-label",))
        code, out = run(capsys, clone("a"), "claim", "12")
        assert code == cli.OK
        assert "warning: claimed, but could not add the in-progress label" in out.err
        assert "issue/12" in remote_branches(remote)

    @pytest.mark.spec("claim-cmd-stops-when-nobody-wins")
    def it_cannot_run_when_the_push_is_refused_for_another_reason(
        self, capsys, remote, clone, github
    ):
        """Only a branch that now exists means someone else holds the issue."""
        hook = remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho 'no pushes today' >&2\nexit 1\n")
        hook.chmod(0o755)
        gh = github(make_issue(12, "approved"))
        code, out = run(capsys, clone("a"), "claim", "12")
        assert code == cli.CANNOT_RUN
        assert out.err.startswith("issues.py: could not push issue/12")
        assert gh.writes() == []

    @pytest.mark.spec(
        "claim-cmd-switches-to-issue-branch", "command-splits-output-streams-without-json"
    )
    def it_warns_when_it_cannot_switch_to_the_branch(self, capsys, remote, clone, github):
        a = clone("a")
        git(a, "branch", "issue/12")
        github(make_issue(12, "approved"))
        code, out = run(capsys, a, "claim", "12")
        assert code == cli.OK
        assert "warning: claimed, but could not switch to issue/12" in out.err
        assert "issue/12" in remote_branches(remote)


class DescribeNext:
    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_skips_labeled_and_branch_held_issues(self, capsys, remote, clone, github):
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

    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_never_offers_a_closed_issue(self, capsys, clone, github):
        github(make_issue(12, "approved", state="CLOSED"))
        assert run_json(capsys, clone("a"), "next")[1]["data"]["issue"] is None

    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_is_not_a_problem_when_nothing_is_free(self, capsys, clone, github):
        github(make_issue(11, "approved", "in-progress"))
        code, out = run(capsys, clone("a"), "next")
        assert code == cli.OK
        assert out.out == "No approved issue is free.\n"

    @pytest.mark.spec("next-cmd-offers-free-issue", "command-splits-output-streams-without-json")
    def it_names_the_free_issue_on_stdout(self, capsys, clone, github):
        github(make_issue(13, "approved"))
        code, out = run(capsys, clone("a"), "next")
        assert code == cli.OK
        assert (out.out, out.err) == ("#13 issue 13\n", "")


class DescribeNextBlockers:
    @pytest.mark.spec("next-cmd-skips-blocked-issues")
    def it_skips_an_issue_whose_blocker_is_open(self, capsys, clone, github):
        github(
            make_issue(10, "approved"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            blockers={10: [(9, "open")], 11: [(8, "closed")]},
        )
        code, data = run_json(capsys, clone("a"), "next")
        assert code == cli.OK
        assert data["data"]["issue"] == {"number": 11, "title": "issue 11"}

    @pytest.mark.spec("next-cmd-skips-blocked-issues")
    def it_names_each_blocked_issue_with_its_open_blockers_when_all_are_blocked(
        self, capsys, clone, github
    ):
        github(
            make_issue(10, "approved"),
            make_issue(11, "approved"),
            blockers={10: [(9, "open"), (8, "open"), (7, "closed")], 11: [(10, "open")]},
        )
        code, out = run(capsys, clone("a"), "next")
        assert code == cli.OK
        assert out.out == (
            "Every free approved issue is blocked by an open issue:\n"
            "#10 issue 10, blocked by #8, #9\n"
            "#11 issue 11, blocked by #10\n"
        )

    @pytest.mark.spec("next-cmd-skips-blocked-issues")
    def it_leaves_claim_unchanged_for_a_blocked_issue(self, capsys, remote, clone, github):
        gh = github(make_issue(10, "approved"), blockers={10: [(9, "open")]})
        code, _ = run(capsys, clone("a"), "claim", "10")
        assert code == cli.OK
        assert not any(c[0] == "api" for c in gh.calls)


class DescribeNextTracking:
    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    def it_offers_sub_issues_in_the_order_the_tracking_issue_lists_them(
        self, capsys, clone, github
    ):
        github(
            make_issue(20, "approved", "tracking"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            subs={20: [12, 11]},
        )
        code, data = run_json(capsys, clone("a"), "next", "--tracking", "20")
        assert code == cli.OK
        assert data["data"]["issue"] == {"number": 12, "title": "issue 12"}
        assert data["data"]["tracking"] == {"number": 20, "title": "issue 20"}

    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    def it_passes_over_closed_held_and_blocked_sub_issues(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(13, "approved"))
        run(capsys, a, "claim", "13")
        github(
            make_issue(20, "approved", "tracking"),
            make_issue(10, "approved", state="CLOSED"),
            make_issue(11, "approved", "in-progress"),
            make_issue(13, "approved"),
            make_issue(14, "approved"),
            make_issue(15, "approved"),
            make_issue(16, "approved"),
            subs={20: [10, 11, 13, 14, 16, 15]},
            blockers={14: [(99, "open")]},
        )
        code, data = run_json(capsys, a, "next", "--tracking", "20")
        assert code == cli.OK
        assert data["data"]["issue"] == {"number": 16, "title": "issue 16"}
        assert data["data"]["blocked"] == [{"number": 14, "title": "issue 14", "blocked_by": [99]}]

    @pytest.mark.spec(
        "next-cmd-follows-tracking-issue", "command-splits-output-streams-without-json"
    )
    def it_fails_on_an_unapproved_sub_issue_rather_than_skip_it(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "tracking"),
            make_issue(11),
            make_issue(12, "approved"),
            subs={20: [11, 12]},
        )
        code, out = run(capsys, clone("a"), "next", "--tracking", "20")
        assert code == cli.PROBLEMS
        assert out.out == ""
        assert "#11 issue 11 is next in #20's order" in out.err

    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    @pytest.mark.parametrize(
        ("labels", "state", "says"),
        [
            (("tracking",), "OPEN", "not labeled approved"),
            (("approved",), "OPEN", "not labeled tracking"),
            (("approved", "tracking"), "CLOSED", "is closed"),
        ],
    )
    def it_refuses_an_issue_that_is_not_an_open_approved_plan(
        self, capsys, clone, github, labels, state, says
    ):
        gh = github(make_issue(20, *labels, state=state), subs={20: []})
        code, out = run(capsys, clone("a"), "next", "--tracking", "20")
        assert code == cli.PROBLEMS
        assert says in out.err
        assert not any(c[0] == "api" for c in gh.calls)

    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    def it_names_each_blocked_sub_issue_when_all_are_blocked(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "tracking"),
            make_issue(11, "approved"),
            make_issue(12),
            subs={20: [11, 12]},
            blockers={11: [(9, "open")], 12: [(11, "open")]},
        )
        code, out = run(capsys, clone("a"), "next", "--tracking", "20")
        assert code == cli.OK
        assert out.out == (
            "Every free sub-issue of #20 is blocked by an open issue:\n"
            "#11 issue 11, blocked by #9\n"
            "#12 issue 12, blocked by #11\n"
        )

    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    def it_is_not_a_problem_when_the_plan_has_nothing_left(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "tracking"),
            make_issue(11, "approved", state="CLOSED"),
            subs={20: [11]},
        )
        code, out = run(capsys, clone("a"), "next", "--tracking", "20")
        assert code == cli.OK
        assert out.out == "No sub-issue of #20 is free.\n"


class DescribeNextPlans:
    @pytest.mark.spec("next-cmd-names-tracking-issue", "command-splits-output-streams-without-json")
    def it_names_an_approved_plan_at_its_lowest_open_sub_issue(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "tracking"),
            make_issue(9, "approved", state="CLOSED"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            subs={20: [9, 12]},
        )
        code, out = run(capsys, clone("a"), "next")
        assert code == cli.OK
        assert (out.out, out.err) == ("#11 issue 11\n", "")

        github(
            make_issue(20, "approved", "tracking"),
            make_issue(10, "approved"),
            make_issue(11, "approved"),
            subs={20: [10]},
        )
        code, out = run(capsys, clone("b"), "next")
        assert code == cli.OK
        assert out.out == (
            "#20 issue 20 is an approved tracking issue.\n"
            "To take its next sub-issue, run: issues.py next --tracking 20\n"
        )

    @pytest.mark.spec("next-cmd-names-tracking-issue")
    def it_names_the_plan_apart_from_the_issue_to_work(self, capsys, clone, github):
        github(make_issue(20, "approved", "tracking"), make_issue(21, "approved"), subs={20: []})
        code, data = run_json(capsys, clone("a"), "next")
        assert code == cli.OK
        assert data["data"]["issue"] is None
        assert data["data"]["tracking"] == {"number": 20, "title": "issue 20"}

    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_never_offers_a_plan_or_an_approved_plans_sub_issue_as_work(self, capsys, clone, github):
        github(
            make_issue(20, "tracking"),
            make_issue(30, "approved", "tracking"),
            make_issue(10, "approved"),
            make_issue(31, "approved"),
            make_issue(32, "approved"),
            subs={20: [10], 30: [31]},
            blockers={10: [(1, "open")]},
        )
        code, data = run_json(capsys, clone("a"), "next")
        assert code == cli.OK
        # 10 belongs to a plan nobody approved, so it is offered on its own,
        # and blocked; 30 takes its place before 32.
        assert data["data"]["issue"] is None
        assert data["data"]["tracking"] == {"number": 30, "title": "issue 30"}
        assert [b["number"] for b in data["data"]["blocked"]] == [10]


class DescribeRelease:
    @pytest.mark.spec("release-cmd-frees-unused-claim")
    def it_deletes_an_empty_branch_and_the_label(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        gh = github(make_issue(12, "approved", "in-progress"))
        code, out = run(capsys, a, "release", "12", "--reason", "blocked on #9")
        assert code == cli.OK
        assert remote_branches(remote) == {cli.BASE}
        assert ("issue", "edit", "12", "--remove-label", cli.IN_PROGRESS) in gh.calls
        assert ("issue", "comment", "12", "--body", "Released issue/12. blocked on #9") in gh.calls

    @pytest.mark.spec("release-cmd-keeps-work")
    def it_never_deletes_work(self, capsys, remote, clone, github):
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

    @pytest.mark.spec("release-cmd-requires-held-claim")
    def it_is_a_problem_on_an_unclaimed_issue(self, capsys, clone, github):
        github(make_issue(12, "approved"))
        code, out = run(capsys, clone("a"), "release", "12")
        assert code == cli.PROBLEMS
        assert "#12 is not claimed" in out.err

    @pytest.mark.spec("command-never-writes-in-preview")
    def it_changes_nothing_on_a_dry_run(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        gh = github(make_issue(12, "approved", "in-progress"))
        code, out = run(capsys, a, "release", "12", "--dry-run")
        assert code == cli.OK
        assert out.out == "Would release #12\n"
        assert "issue/12" in remote_branches(remote)
        assert gh.writes() == []

    @pytest.mark.spec("release-cmd-frees-unused-claim", "next-cmd-offers-free-issue")
    def it_leaves_the_issue_free_again(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        github(make_issue(12, "approved", "in-progress"))
        run(capsys, a, "release", "12")
        github(make_issue(12, "approved"))
        assert run_json(capsys, a, "next")[1]["data"]["issue"]["number"] == 12

    @pytest.mark.spec("release-cmd-keeps-work")
    def it_keeps_a_branch_pushed_to_while_releasing(
        self, capsys, remote, clone, github, monkeypatch
    ):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        gh = github(make_issue(12, "approved", "in-progress"))
        real = cli.git

        def pushed_meanwhile(repo, *args, **kwargs):
            if "push" in args and any(w.startswith("--force-with-lease") for w in args):
                git(a, "commit", "--quiet", "--allow-empty", "-m", "work")
                git(a, "push", "--quiet")
            return real(repo, *args, **kwargs)

        monkeypatch.setattr(cli, "git", pushed_meanwhile)
        code, out = run(capsys, clone("b"), "release", "12")
        assert code == cli.PROBLEMS
        assert "issue/12 changed while releasing" in out.err
        assert "issue/12" in remote_branches(remote)
        assert gh.writes() == []

    @pytest.mark.spec("release-cmd-frees-unused-claim")
    def it_frees_an_issue_whose_label_outlived_its_branch(self, capsys, remote, clone, github):
        gh = github(make_issue(12, "approved", "in-progress"))
        code, out = run(capsys, clone("a"), "release", "12")
        assert code == cli.OK
        assert ("issue", "edit", "12", "--remove-label", cli.IN_PROGRESS) in gh.calls
        assert ("issue", "comment", "12", "--body", "Released issue/12.") in gh.calls


def claim_comment(when):
    return {"body": "%s `issue/12`." % cli.CLAIM_MARK, "createdAt": when}


def claimed(capsys, clone, github):
    a = clone("a")
    github(make_issue(12, "approved"))
    run(capsys, a, "claim", "12")
    return a


class DescribeStale:
    def it_reports_an_idle_claim(self, capsys, clone, github):
        a = claimed(capsys, clone, github)
        github(
            make_issue(
                12, "approved", "in-progress", comments=[claim_comment("2026-02-01T00:00:00Z")]
            )
        )
        code, out = run(capsys, a, "stale")
        assert code == cli.PROBLEMS
        assert "#12: issue/12 idle for 28 days" in out.err

    def it_passes_a_recent_claim_on_an_old_main(self, capsys, clone, github):
        a = claimed(capsys, clone, github)
        github(
            make_issue(
                12, "approved", "in-progress", comments=[claim_comment("2026-02-28T00:00:00Z")]
            )
        )
        code, out = run(capsys, a, "stale")
        assert code == cli.OK
        assert out.out == "No stale claims.\n"

    def it_passes_a_claim_with_an_open_pull_request(self, capsys, clone, github):
        a = claimed(capsys, clone, github)
        github(make_issue(12, "approved", "in-progress"), pulls=["issue/12"])
        assert run(capsys, a, "stale")[0] == cli.OK

    @pytest.mark.spec("stale-cmd-reports-claims-left-behind")
    def it_reports_a_branch_left_after_the_issue_closed(self, capsys, clone, github):
        a = claimed(capsys, clone, github)
        github(make_issue(12, "approved", state="CLOSED"))
        code, out = run(capsys, a, "stale")
        assert code == cli.PROBLEMS
        assert "#12 is closed but issue/12 still exists; run release 12" in out.err

    @pytest.mark.spec("stale-cmd-reports-claims-left-behind")
    def it_reports_a_label_without_a_branch(self, capsys, clone, github):
        github(make_issue(12, "approved", "in-progress"))
        code, out = run(capsys, clone("a"), "stale")
        assert code == cli.PROBLEMS
        assert "#12 is labeled in-progress but issue/12 does not exist" in out.err

    @pytest.mark.spec("stale-cmd-reports-claims-left-behind")
    def it_reports_a_closed_issue_that_kept_the_label(self, capsys, clone, github):
        github(make_issue(12, "approved", "in-progress", state="CLOSED"))
        code, out = run(capsys, clone("a"), "stale")
        assert code == cli.PROBLEMS
        assert "#12 is closed but still labeled in-progress; run release 12" in out.err


def commit_file(repo, name, text, message=None):
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "--quiet", "-m", message or name)


def squash_merged(capsys, clone, github, remote):
    """A clone holding issue/12, whose work reached main as a new commit.

    Main then moves on, so the branch's tree matches no commit on main.
    """
    a = claimed(capsys, clone, github)
    commit_file(a, "work", "work\n")
    commit_file(a, "more", "more\n")
    git(a, "push", "--quiet")
    seed = remote.parent / "seed"
    git(seed, "pull", "--quiet", cli.REMOTE, cli.BASE)
    (seed / "work").write_text("work\n")
    (seed / "more").write_text("more\n")
    git(seed, "add", "work", "more")
    git(seed, "commit", "--quiet", "-m", "squashed")
    commit_file(seed, "later", "later\n")
    git(seed, "push", "--quiet", cli.REMOTE, "HEAD:" + cli.BASE)
    github(make_issue(12, "approved", state="CLOSED"))
    return a


def merged_then_edited(capsys, clone, github, remote):
    """A clone holding issue/12, squash-merged, whose line main has edited since.

    Replaying the branch onto main now conflicts, though main had all of it.
    """
    a = claimed(capsys, clone, github)
    commit_file(a, "README", "work\n")
    git(a, "push", "--quiet")
    seed = remote.parent / "seed"
    git(seed, "pull", "--quiet", cli.REMOTE, cli.BASE)
    # Its own message, or it would be the branch's commit byte for byte.
    commit_file(seed, "README", "work\n", "squashed")
    commit_file(seed, "README", "later\n")
    git(seed, "push", "--quiet", cli.REMOTE, "HEAD:" + cli.BASE)
    return a


def local_branches(repo):
    return set(git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split())


class DescribeClear:
    @pytest.mark.spec("clear-cmd-deletes-merged-branch")
    def it_deletes_a_branch_whose_work_main_has(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        code, out = run(capsys, a, "clear", "12")
        assert code == cli.OK
        assert out.out.startswith("Cleared issue/12\n")
        assert "issue/12" not in local_branches(a)
        assert git(a, "rev-parse", "HEAD") == git(remote, "rev-parse", cli.BASE)

    @pytest.mark.spec("clear-cmd-deletes-merged-branch")
    def it_deletes_a_branch_a_merged_pull_request_holds_after_main_moves_on(
        self, capsys, remote, clone, github
    ):
        a = merged_then_edited(capsys, clone, github, remote)
        tip = git(a, "rev-parse", "issue/12")
        github(make_issue(12, "approved", state="CLOSED"), merged=[(7, "issue/12", tip)])
        code, data = run_json(capsys, a, "clear", "12")
        assert code == cli.OK
        assert data["data"]["pull_request"] == 7
        assert "issue/12" not in local_branches(a)

    @pytest.mark.spec("clear-cmd-deletes-merged-branch")
    def it_fetches_a_pull_request_head_the_clone_lacks(self, capsys, remote, clone, github):
        """The clone's issue/12 is behind the head that merged, pushed from elsewhere."""
        a = merged_then_edited(capsys, clone, github, remote)
        b = clone("b")
        git(b, "switch", "--quiet", "issue/12")
        commit_file(b, "review", "review\n")
        head = git(b, "rev-parse", "HEAD")
        git(b, "push", "--quiet", cli.REMOTE, "HEAD:refs/pull/7/head")
        assert subprocess.run(["git", "cat-file", "-e", head], cwd=a).returncode != 0
        github(make_issue(12, "approved", state="CLOSED"), merged=[(7, "issue/12", head)])
        code, data = run_json(capsys, a, "clear", "12")
        assert code == cli.OK
        assert data["data"]["pull_request"] == 7
        assert "issue/12" not in local_branches(a)

    @pytest.mark.spec("clear-cmd-deletes-merged-branch")
    def it_moves_a_worktree_off_the_branch_and_keeps_it(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        git(a, "switch", "--quiet", "--detach")
        tree = a.parent / "tree"
        git(a, "worktree", "add", "--quiet", str(tree), "issue/12")
        code, data = run_json(capsys, a, "clear", "12")
        assert code == cli.OK
        assert data["data"]["worktrees"] == [git(tree, "rev-parse", "--show-toplevel")]
        assert tree.is_dir()
        assert git(tree, "branch", "--show-current") == ""
        assert git(tree, "rev-parse", "HEAD") == git(remote, "rev-parse", cli.BASE)
        assert "issue/12" not in local_branches(a)

    @pytest.mark.parametrize("change", ["new-file", "conflict"])
    @pytest.mark.spec("clear-cmd-keeps-unmerged-work")
    def it_keeps_a_branch_holding_work_main_lacks(self, capsys, remote, clone, github, change):
        a = squash_merged(capsys, clone, github, remote)
        if change == "new-file":
            commit_file(a, "unmerged", "unmerged\n")
        else:
            commit_file(a, "later", "a different later\n")
        tip = git(a, "rev-parse", "issue/12")
        code, out = run(capsys, a, "clear", "12")
        assert code == cli.PROBLEMS
        assert "and changes origin/main lacks" in out.err
        assert git(a, "rev-parse", "issue/12") == tip
        assert git(a, "branch", "--show-current") == "issue/12"

    @pytest.mark.parametrize("pull", ["no-pull", "earlier-pull"])
    @pytest.mark.spec("clear-cmd-keeps-unmerged-work")
    def it_keeps_a_commit_no_merged_pull_request_has_when_main_conflicts(
        self, capsys, remote, clone, github, pull
    ):
        a = merged_then_edited(capsys, clone, github, remote)
        merged = (
            [(7, "issue/12", git(a, "rev-parse", "issue/12"))] if pull == "earlier-pull" else []
        )
        commit_file(a, "after", "after\n")
        tip = git(a, "rev-parse", "issue/12")
        github(make_issue(12, "approved", state="CLOSED"), merged=merged)
        code, out = run(capsys, a, "clear", "12")
        assert code == cli.PROBLEMS
        assert "issue/12 holds commits no merged pull request from it has" in out.err
        assert git(a, "rev-parse", "issue/12") == tip

    @pytest.mark.parametrize("dry_run", [False, True], ids=["run", "dry-run"])
    @pytest.mark.spec("clear-cmd-keeps-uncommitted-changes")
    def it_keeps_a_worktree_with_uncommitted_changes(self, capsys, remote, clone, github, dry_run):
        a = squash_merged(capsys, clone, github, remote)
        git(a, "switch", "--quiet", "--detach")
        tree = a.parent / "tree"
        git(a, "worktree", "add", "--quiet", str(tree), "issue/12")
        (tree / "README").write_text("unsaved\n")
        code, out = run(capsys, a, "clear", "12", *(["--dry-run"] if dry_run else []))
        assert code == cli.PROBLEMS
        assert "has issue/12 checked out and uncommitted changes" in out.err
        assert "run clear 12 again" in out.err
        assert git(tree, "branch", "--show-current") == "issue/12"
        assert (tree / "README").read_text() == "unsaved\n"
        assert "issue/12" in local_branches(a)

    @pytest.mark.spec("clear-cmd-keeps-unmerged-work")
    def it_keeps_the_branch_of_an_open_issue(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        github(make_issue(12, "approved", "in-progress"))
        code, out = run(capsys, a, "clear", "12")
        assert code == cli.PROBLEMS
        assert "#12 is still open" in out.err
        assert "issue/12" in local_branches(a)

    @pytest.mark.spec("clear-cmd-keeps-unmerged-work")
    def it_is_a_problem_when_there_is_no_local_branch(self, capsys, clone, github):
        github(make_issue(12, "approved", state="CLOSED"))
        code, out = run(capsys, clone("a"), "clear", "12")
        assert code == cli.PROBLEMS
        assert "there is no local issue/12 to clear" in out.err

    @pytest.mark.spec("command-never-writes-in-preview")
    def it_changes_nothing_on_a_dry_run(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        code, out = run(capsys, a, "clear", "12", "--dry-run")
        assert code == cli.OK
        assert out.out.startswith("Would clear issue/12\n")
        assert "issue/12" in local_branches(a)
        assert git(a, "branch", "--show-current") == "issue/12"


def gone_from_origin(remote, name):
    """GitHub deletes a pull request's branch when it merges."""
    git(remote, "branch", "-D", name)


class DescribeSweep:
    @pytest.mark.spec("sweep-cmd-deletes-merged-branches")
    def it_deletes_every_branch_whose_work_is_on_main(self, capsys, remote, clone, github):
        a = merged_then_edited(capsys, clone, github, remote)
        tip = git(a, "rev-parse", "issue/12")
        gone_from_origin(remote, "issue/12")
        git(a, "branch", "claude/fresh-session", "origin/main")
        git(a, "switch", "--quiet", "-c", "claude/squashed", "origin/main")
        commit_file(a, "squash-me", "squash-me\n")
        seed = remote.parent / "seed"
        git(seed, "pull", "--quiet", cli.REMOTE, cli.BASE)
        commit_file(seed, "squash-me", "squash-me\n", "squashed as a new commit")
        git(seed, "push", "--quiet", cli.REMOTE, "HEAD:" + cli.BASE)
        git(a, "switch", "--quiet", "--detach")
        github(merged=[(7, "issue/12", tip)])
        code, data = run_json(capsys, a, "sweep")
        assert code == cli.OK
        assert sorted(data["data"]["deleted"]) == [
            "claude/fresh-session",
            "claude/squashed",
            "issue/12",
        ]
        assert data["data"]["kept"] == []
        assert local_branches(a) == {cli.BASE}

    @pytest.mark.spec("sweep-cmd-keeps-live-branches")
    def it_keeps_each_branch_that_may_still_be_in_use_and_says_why(
        self, capsys, remote, clone, github
    ):
        a = claimed(capsys, clone, github)
        git(a, "switch", "--quiet", "-c", "claude/unmerged")
        commit_file(a, "unmerged", "unmerged\n")
        git(a, "switch", "--quiet", "--detach")
        git(a, "branch", "claude/in-a-worktree", cli.BASE)
        tree = a.parent / "tree"
        git(a, "worktree", "add", "--quiet", str(tree), "claude/in-a-worktree")
        github()
        code, out = run(capsys, a, "sweep")
        assert code == cli.OK
        assert out.out.splitlines() == [
            "Kept claude/in-a-worktree: checked out in %s"
            % git(tree, "rev-parse", "--show-toplevel"),
            "Kept claude/unmerged: holds work origin/main lacks",
            "Kept issue/12: still on origin, where someone may be working on it",
        ]
        assert local_branches(a) == {
            cli.BASE,
            "claude/in-a-worktree",
            "claude/unmerged",
            "issue/12",
        }

    @pytest.mark.spec("command-never-writes-in-preview")
    def it_changes_nothing_on_a_dry_run(self, capsys, clone, github):
        a = clone("a")
        git(a, "branch", "claude/fresh-session")
        github()
        code, out = run(capsys, a, "sweep", "--dry-run")
        assert code == cli.OK
        assert out.out == "Would delete claude/fresh-session\n"
        assert "claude/fresh-session" in local_branches(a)


class DescribeMain:
    @pytest.mark.parametrize(
        "argv",
        [
            ["next"],
            ["claim", "12", "--dry-run"],
            ["release", "12"],
            ["stale"],
            ["clear", "12"],
            ["sweep", "--dry-run"],
        ],
    )
    @pytest.mark.spec("command-prints-json-envelope")
    def it_prints_the_same_envelope_for_every_command(self, capsys, clone, github, argv):
        github(make_issue(12, "approved"))
        _, data = run_json(capsys, clone("a"), *argv)
        assert set(data) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert data["version"] == cli.ENVELOPE_VERSION
        assert data["command"] == argv[0]

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_when_gh_fails(self, capsys, clone, github):
        github(fail=("view",))
        code, out = run(capsys, clone("a"), "claim", "12")
        assert code == cli.CANNOT_RUN
        assert out.out == ""
        assert out.err == "issues.py: gh view failed\n"

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_outside_a_clone(self, capsys, tmp_path, github):
        github()
        code, out = run(capsys, tmp_path, "next")
        assert code == cli.CANNOT_RUN
        assert out.err.startswith("issues.py: ")

    @pytest.mark.spec("script-ignores-closed-pipe")
    def it_exits_ok_when_its_reader_closes_the_pipe(self, capsys, clone, github, closed_pipe):
        github(make_issue(13, "approved"))
        closed_pipe()
        assert cli.main(["next", "-C", str(clone("a"))]) == cli.OK
        assert capsys.readouterr().err == ""

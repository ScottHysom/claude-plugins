"""The queue and the claim lock: what keeps two agents off the same issue.

The claim has to be atomic - two agents claiming at once, one wins - and
neither release nor clear may throw away work. Every test runs against real
git, with a bare repository standing in for GitHub's; only gh is faked.
"""

import json
import shutil
import subprocess

import pytest

import flywheel

MAIN_DATE = "2026-01-01T00:00:00+00:00"


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


def seeded(world):
    """Build the bare repository the remote fixture starts from.

    Beside it sits `seed`, the clone that made its first commit, which a test
    uses to move main. Its origin is a relative path, so it still names the
    bare repository beside it once the two are copied.
    """
    world.mkdir()
    bare = world / "remote.git"
    git(world, "init", "--quiet", "--bare", "-b", flywheel.BASE, str(bare))
    seed = world / "seed"
    git(world, "clone", "--quiet", str(bare), str(seed))
    git(seed, "remote", "set-url", flywheel.REMOTE, "../remote.git")
    (seed / "README").write_text("seed\n")
    git(seed, "add", "README")
    git(seed, "commit", "--quiet", "-m", "seed")
    git(seed, "push", "--quiet", flywheel.REMOTE, "HEAD:" + flywheel.BASE)


@pytest.fixture
def remote(tmp_path, repo_copy):
    return repo_copy(seeded, tmp_path / "world") / "remote.git"


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

    def __init__(self, issues=None, merged=(), fail=(), blockers=None, subs=None, graphql=None):
        self.issues = issues or {}
        self.graphql = graphql
        self.blockers = blockers or {}
        self.subs = subs or {}
        self.merged = merged
        self.fail = fail
        self.calls = []

    def __call__(self, repo, *args):
        self.calls.append(args)
        if any(word in args for word in self.fail):
            raise flywheel.Fatal("gh %s failed" % args[1])
        kind, verb = args[0], args[1]
        if kind == "api" and verb == "graphql":
            return json.dumps(self.graphql)
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
        if kind == "pr":
            head = args[args.index("--head") + 1] if "--head" in args else None
            return json.dumps(
                [
                    {"number": n, "headRefName": b, "headRefOid": sha}
                    for n, b, sha in self.merged
                    if head in (None, b)
                ]
            )
        if verb == "view":
            return json.dumps(self.issues[int(args[2])])
        if verb == "list":
            # gh filters by label without case, as GitHub reads label names.
            label = args[args.index("--label") + 1].lower()
            state = args[args.index("--state") + 1].upper()
            return json.dumps(
                [
                    i
                    for _, i in sorted(self.issues.items())
                    if state in ("ALL", i["state"]) and label in [n.lower() for n in names(i)]
                ]
            )
        return ""

    def writes(self):
        return [c for c in self.calls if c[1] in ("edit", "comment", "close")]


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
        monkeypatch.setattr(flywheel, "gh", fake)
        return fake

    return install


def run(capsys, repo, *argv):
    code = flywheel.main([*argv, "-C", str(repo)])
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
        assert code == flywheel.OK
        assert out.out == "Claimed #12 on branch issue/12\n"
        assert "issue/12" in remote_branches(remote)
        assert git(a, "branch", "--show-current") == "issue/12"
        assert git(a, "rev-parse", "HEAD") == git(remote, "rev-parse", flywheel.BASE)
        assert ("issue", "edit", "12", "--add-label", "claimed") in gh.calls
        assert any(c[1] == "comment" and flywheel.CLAIM_MARK in c[-1] for c in gh.calls)

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
        assert run(capsys, a, "claim", "12")[0] == flywheel.OK
        before = git(remote, "rev-parse", "issue/12")
        if main_moved:
            seed = remote.parent / "seed"
            git(seed, "commit", "--quiet", "--allow-empty", "-m", "later")
            git(seed, "push", "--quiet", flywheel.REMOTE, "HEAD:" + flywheel.BASE)

        real, calls = flywheel.claims, []

        def stale_first_view(repo):
            calls.append(repo)
            return {} if len(calls) == 1 else real(repo)

        monkeypatch.setattr(flywheel, "claims", stale_first_view)
        gh = github(make_issue(12, "approved"))
        code, out = run(capsys, b, "claim", "12")

        assert code == flywheel.PROBLEMS
        assert "#12 is held" in out.err
        assert git(remote, "rev-parse", "issue/12") == before
        assert gh.writes() == []

    @pytest.mark.spec("claim-cmd-picks-one-winner", "next-cmd-moves-past-lost-claim")
    def it_refuses_a_held_issue_before_pushing(self, capsys, remote, clone, github):
        a, b = clone("a"), clone("b")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        gh = github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, b, "claim", "12")
        assert code == flywheel.PROBLEMS
        assert "#12 is held: branch issue/12 already exists" in out.err
        assert out.out == ""
        assert gh.writes() == []
        assert git(b, "branch", "--show-current") == flywheel.BASE

    @pytest.mark.parametrize(
        ("item", "message"),
        [
            (make_issue(12), "#12 is not labeled approved"),
            (make_issue(12, "approved", state="CLOSED"), "#12 is closed"),
        ],
    )
    @pytest.mark.spec("repo:claim-cmd-refuses-unapproved-issues")
    def it_refuses_an_issue_that_may_not_be_worked_on(
        self, capsys, remote, clone, github, item, message
    ):
        gh = github(item)
        code, out = run(capsys, clone("a"), "claim", "12")
        assert code == flywheel.PROBLEMS
        assert message in out.err
        assert remote_branches(remote) == {flywheel.BASE}
        assert gh.writes() == []

    @pytest.mark.spec("repo:claim-cmd-ignores-label-case")
    def it_claims_an_issue_whose_label_differs_only_in_case(self, capsys, remote, clone, github):
        github(make_issue(12, "Approved"))
        code, out = run(capsys, clone("a"), "claim", "12")
        assert code == flywheel.OK, out.err
        assert "issue/12" in remote_branches(remote)

    @pytest.mark.spec("repo:command-never-writes-in-preview")
    def it_changes_nothing_on_a_dry_run(self, capsys, remote, clone, github):
        a = clone("a")
        gh = github(make_issue(12, "approved"))
        code, out = run(capsys, a, "claim", "12", "--dry-run")
        assert code == flywheel.OK
        assert out.out == "Would claim #12 on branch issue/12\n"
        assert remote_branches(remote) == {flywheel.BASE}
        assert gh.writes() == []

    @pytest.mark.spec(
        "claim-cmd-adds-in-progress-label", "repo:command-splits-output-streams-without-json"
    )
    def it_warns_when_the_label_fails_after_the_push(self, capsys, remote, clone, github):
        github(make_issue(12, "approved"), fail=("--add-label",))
        code, out = run(capsys, clone("a"), "claim", "12")
        assert code == flywheel.OK
        assert "warning: claimed, but could not add the claimed label" in out.err
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
        assert code == flywheel.CANNOT_RUN
        assert out.err.startswith("flywheel.py: could not push issue/12")
        assert gh.writes() == []

    @pytest.mark.spec(
        "claim-cmd-switches-to-issue-branch", "repo:command-splits-output-streams-without-json"
    )
    def it_warns_when_it_cannot_switch_to_the_branch(self, capsys, remote, clone, github):
        a = clone("a")
        git(a, "branch", "issue/12")
        github(make_issue(12, "approved"))
        code, out = run(capsys, a, "claim", "12")
        assert code == flywheel.OK
        assert "warning: claimed, but could not switch to issue/12" in out.err
        assert "issue/12" in remote_branches(remote)


def stale_views(monkeypatch, count):
    """Have claims() miss every claim for its first `count` calls.

    Another agent's claim lands after this agent read the branch list, so the
    queue offers it an issue it is about to lose.
    """
    real, calls = flywheel.claims, []

    def view(repo):
        calls.append(repo)
        return {} if len(calls) <= count else real(repo)

    monkeypatch.setattr(flywheel, "claims", view)


@pytest.mark.spec("next-cmd-moves-past-lost-claim")
class DescribeClaimNext:
    @pytest.mark.parametrize("stale", [1, 2], ids=["lost-before-push", "lost-at-push"])
    def it_claims_the_next_free_issue_when_another_agent_wins_the_offered_one(
        self, capsys, remote, clone, github, monkeypatch, stale
    ):
        a, b = clone("a"), clone("b")
        github(make_issue(12, "approved"), make_issue(13, "approved"))
        assert run(capsys, a, "claim", "12")[0] == flywheel.OK
        stale_views(monkeypatch, stale)
        gh = github(make_issue(12, "approved"), make_issue(13, "approved"))
        code, out = run(capsys, b, "claim", "--next")
        assert code == flywheel.OK, out.err
        assert out.out == "Claimed #13 on branch issue/13\n"
        assert "#12 is held by another agent, so the next free issue was taken" in out.err
        assert git(b, "branch", "--show-current") == "issue/13"
        assert {c[2] for c in gh.writes()} == {"13"}

    def it_reports_the_issues_it_lost_in_json(self, capsys, remote, clone, github, monkeypatch):
        a, b = clone("a"), clone("b")
        github(make_issue(12, "approved"), make_issue(13, "approved"))
        run(capsys, a, "claim", "12")
        stale_views(monkeypatch, 1)
        code, data = run_json(capsys, b, "claim", "--next")
        assert code == flywheel.OK
        assert data["data"] == {"number": 13, "branch": "issue/13", "lost": [12]}

    def it_stops_without_claiming_when_no_other_issue_is_free(
        self, capsys, remote, clone, github, monkeypatch
    ):
        a, b = clone("a"), clone("b")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        stale_views(monkeypatch, 1)
        gh = github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, b, "claim", "--next")
        assert code == flywheel.PROBLEMS
        assert out.out == ""
        assert "No other approved issue is free to claim" in out.err
        assert gh.writes() == []
        assert git(b, "branch", "--show-current") == flywheel.BASE

    def it_claims_the_issue_queue_offers_when_nobody_holds_it(self, capsys, remote, clone, github):
        github(make_issue(12, "approved"), make_issue(13, "approved"))
        code, out = run(capsys, clone("a"), "claim", "--next")
        assert code == flywheel.OK
        assert out.out == "Claimed #12 on branch issue/12\n"
        assert out.err == ""

    def it_changes_nothing_on_a_dry_run(self, capsys, remote, clone, github):
        gh = github(make_issue(12, "approved"))
        code, out = run(capsys, clone("a"), "claim", "--next", "--dry-run")
        assert code == flywheel.OK
        assert out.out == "Would claim #12 on branch issue/12\n"
        assert remote_branches(remote) == {flywheel.BASE}
        assert gh.writes() == []

    def it_claims_a_plans_next_sub_issue_when_another_agent_wins_the_offered_one(
        self, capsys, remote, clone, github, monkeypatch
    ):
        a, b = clone("a"), clone("b")
        issues = (
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            make_issue(13, "approved"),
        )
        github(*issues, subs={20: [13, 11, 12]})
        run(capsys, a, "claim", "13")
        stale_views(monkeypatch, 1)
        code, out = run(capsys, b, "claim", "--next", "--tracking", "20")
        assert code == flywheel.OK, out.err
        assert out.out == "Claimed #11 on branch issue/11\n"
        assert "#13 is held by another agent" in out.err

    def it_still_stops_at_a_plans_unapproved_sub_issue(
        self, capsys, remote, clone, github, monkeypatch
    ):
        a, b = clone("a"), clone("b")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        stale_views(monkeypatch, 1)
        gh = github(
            make_issue(20, "approved", "plan"),
            make_issue(12, "approved"),
            make_issue(13),
            make_issue(14, "approved"),
            subs={20: [12, 13, 14]},
        )
        code, out = run(capsys, b, "claim", "--next", "--tracking", "20")
        assert code == flywheel.PROBLEMS
        assert "#13 issue 13 is next in #20's order and is not labeled approved" in out.err
        assert gh.writes() == []
        assert remote_branches(remote) == {flywheel.BASE, "issue/12"}

    def it_stops_on_a_plan_that_may_not_be_worked(self, capsys, remote, clone, github):
        github(make_issue(20, "plan"), make_issue(12, "approved"), subs={20: [12]})
        code, out = run(capsys, clone("a"), "claim", "--next", "--tracking", "20")
        assert code == flywheel.PROBLEMS
        assert "#20 is not labeled approved" in out.err
        assert remote_branches(remote) == {flywheel.BASE}

    def it_names_the_plan_that_comes_first_and_how_to_start_it(self, capsys, remote, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved"),
            make_issue(30, "approved"),
            subs={20: [11]},
        )
        code, out = run(capsys, clone("a"), "claim", "--next")
        assert code == flywheel.PROBLEMS
        assert "#20 issue 20 is an approved tracking issue" in out.err
        assert "flywheel.py claim --next --tracking 20" in out.err
        assert remote_branches(remote) == {flywheel.BASE}

    def it_says_a_plan_is_finished(self, capsys, remote, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved", state="CLOSED"),
            subs={20: [11]},
        )
        code, out = run(capsys, clone("a"), "claim", "--next", "--tracking", "20")
        assert code == flywheel.PROBLEMS
        assert "plan is finished. To close it, run: flywheel.py plan close 20" in out.err

    @pytest.mark.parametrize(
        ("argv", "says"),
        [
            ((), "Every free approved issue is blocked by an open issue: #12 by #99"),
            (("--tracking", "20"), "Every free sub-issue of #20 is blocked"),
        ],
        ids=["queue", "plan"],
    )
    def it_names_each_blocker_when_every_free_issue_is_blocked(
        self, capsys, remote, clone, github, argv, says
    ):
        if argv:
            github(
                make_issue(20, "approved", "plan"),
                make_issue(12, "approved"),
                subs={20: [12]},
                blockers={12: [(99, "open")]},
            )
        else:
            github(make_issue(12, "approved"), blockers={12: [(99, "open")]})
        code, out = run(capsys, clone("a"), "claim", "--next", *argv)
        assert code == flywheel.PROBLEMS
        assert says in out.err

    def it_stops_on_an_offered_issue_that_closed_before_the_claim(
        self, capsys, remote, clone, github, monkeypatch
    ):
        github(make_issue(12, "approved"))
        real = flywheel.issue
        monkeypatch.setattr(flywheel, "issue", lambda root, n: dict(real(root, n), state="CLOSED"))
        code, out = run(capsys, clone("a"), "claim", "--next")
        assert code == flywheel.PROBLEMS
        assert "#12 is closed" in out.err
        assert remote_branches(remote) == {flywheel.BASE}

    @pytest.mark.parametrize(
        "argv", [("claim", "12", "--next"), ("claim",)], ids=["both", "neither"]
    )
    def it_takes_either_a_number_or_next(self, capsys, clone, argv):
        with pytest.raises(SystemExit) as exc:
            flywheel.main([*argv, "-C", str(clone("a"))])
        assert exc.value.code == flywheel.CANNOT_RUN

    def it_cannot_run_with_tracking_but_without_next(self, capsys, clone, github):
        github(make_issue(12, "approved"))
        code, out = run(capsys, clone("a"), "claim", "12", "--tracking", "20")
        assert code == flywheel.CANNOT_RUN
        assert "--tracking works only with --next" in out.err


class DescribeQueue:
    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_skips_branch_held_issues_whatever_their_labels(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(10, "approved"), make_issue(11, "approved"))
        run(capsys, a, "claim", "10")
        run(capsys, a, "claim", "11")
        github(
            make_issue(10, "approved"),  # held by branch, label not added yet
            make_issue(11, "approved", "claimed"),
            make_issue(12),
            make_issue(14, "approved"),
            make_issue(13, "approved"),
        )
        code, data = run_json(capsys, a, "queue")
        assert code == flywheel.OK
        assert data["data"]["issues"] == [{"number": 13}]

    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_reads_only_a_numbered_issue_branch_as_a_claim(self, capsys, clone, github):
        a = clone("a")
        git(a, "push", "--quiet", flywheel.REMOTE, "HEAD:refs/heads/issue/notes")
        github(make_issue(12, "approved"))
        assert run_json(capsys, a, "queue")[1]["data"]["issues"] == [{"number": 12}]

    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_offers_a_labeled_issue_that_no_branch_holds(self, capsys, clone, github):
        github(make_issue(11, "approved", "claimed"), make_issue(12, "approved"))
        code, data = run_json(capsys, clone("a"), "queue")
        assert code == flywheel.OK
        assert data["data"]["issues"] == [{"number": 11}]

    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_never_offers_a_closed_issue(self, capsys, clone, github):
        github(make_issue(12, "approved", state="CLOSED"))
        assert run_json(capsys, clone("a"), "queue")[1]["data"]["issues"] == []

    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_is_not_a_problem_when_nothing_is_free(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(11, "approved", "claimed"))
        run(capsys, a, "claim", "11")
        code, out = run(capsys, a, "queue")
        assert code == flywheel.OK
        assert out.out == "No approved issue is free.\n"

    @pytest.mark.spec(
        "next-cmd-offers-free-issue", "repo:command-splits-output-streams-without-json"
    )
    def it_names_the_free_issue_on_stdout(self, capsys, clone, github):
        github(make_issue(13, "approved"))
        code, out = run(capsys, clone("a"), "queue")
        assert code == flywheel.OK
        assert (out.out, out.err) == ("#13 issue 13\n", "")


class DescribeQueueBlockers:
    @pytest.mark.spec("next-cmd-skips-blocked-issues")
    def it_skips_an_issue_whose_blocker_is_open(self, capsys, clone, github):
        github(
            make_issue(10, "approved"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            blockers={10: [(9, "open")], 11: [(8, "closed")]},
        )
        code, data = run_json(capsys, clone("a"), "queue")
        assert code == flywheel.OK
        assert data["data"]["issues"] == [{"number": 11}]

    @pytest.mark.spec("next-cmd-skips-blocked-issues")
    def it_names_each_blocked_issue_with_its_open_blockers_when_all_are_blocked(
        self, capsys, clone, github
    ):
        github(
            make_issue(10, "approved"),
            make_issue(11, "approved"),
            blockers={10: [(9, "open"), (8, "open"), (7, "closed")], 11: [(10, "open")]},
        )
        code, out = run(capsys, clone("a"), "queue")
        assert code == flywheel.OK
        assert out.out == (
            "Every free approved issue is blocked by an open issue:\n"
            "#10 issue 10, blocked by #8, #9\n"
            "#11 issue 11, blocked by #10\n"
        )

    @pytest.mark.spec("next-cmd-skips-blocked-issues")
    def it_leaves_claim_unchanged_for_a_blocked_issue(self, capsys, remote, clone, github):
        gh = github(make_issue(10, "approved"), blockers={10: [(9, "open")]})
        code, _ = run(capsys, clone("a"), "claim", "10")
        assert code == flywheel.OK
        assert not any(c[0] == "api" for c in gh.calls)


class DescribeQueueTracking:
    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    def it_offers_sub_issues_in_the_order_the_tracking_issue_lists_them(
        self, capsys, clone, github
    ):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            subs={20: [12, 11]},
        )
        code, data = run_json(capsys, clone("a"), "queue", "--tracking", "20")
        assert code == flywheel.OK
        assert data["data"]["issues"] == [{"number": 12}]
        assert data["data"]["tracking"] == {"number": 20}

    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    def it_passes_over_closed_held_and_blocked_sub_issues(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(11, "approved"), make_issue(13, "approved"))
        run(capsys, a, "claim", "11")
        run(capsys, a, "claim", "13")
        github(
            make_issue(20, "approved", "plan"),
            make_issue(10, "approved", state="CLOSED"),
            make_issue(11, "approved", "claimed"),
            make_issue(13, "approved"),
            make_issue(14, "approved"),
            make_issue(15, "approved"),
            make_issue(16, "approved"),
            subs={20: [10, 11, 13, 14, 16, 15]},
            blockers={14: [(99, "open")]},
        )
        code, data = run_json(capsys, a, "queue", "--tracking", "20")
        assert code == flywheel.OK
        assert data["data"]["issues"] == [{"number": 16}]
        assert data["data"]["blocked"] == [{"number": 14, "blocked_by": [99]}]

    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    def it_offers_a_labeled_sub_issue_that_no_branch_holds(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved", "claimed"),
            make_issue(12, "approved"),
            subs={20: [11, 12]},
        )
        code, data = run_json(capsys, clone("a"), "queue", "--tracking", "20")
        assert code == flywheel.OK
        assert data["data"]["issues"] == [{"number": 11}]

    @pytest.mark.spec(
        "next-cmd-follows-tracking-issue", "repo:command-splits-output-streams-without-json"
    )
    def it_fails_on_an_unapproved_sub_issue_rather_than_skip_it(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11),
            make_issue(12, "approved"),
            subs={20: [11, 12]},
        )
        code, out = run(capsys, clone("a"), "queue", "--tracking", "20")
        assert code == flywheel.PROBLEMS
        assert out.out == ""
        assert "#11 issue 11 is next in #20's order" in out.err

    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    @pytest.mark.parametrize(
        ("labels", "state", "says"),
        [
            (("plan",), "OPEN", "not labeled approved"),
            (("approved",), "OPEN", "not labeled plan"),
            (("approved", "plan"), "CLOSED", "is closed"),
        ],
    )
    def it_refuses_an_issue_that_is_not_an_open_approved_plan(
        self, capsys, clone, github, labels, state, says
    ):
        gh = github(make_issue(20, *labels, state=state), subs={20: []})
        code, out = run(capsys, clone("a"), "queue", "--tracking", "20")
        assert code == flywheel.PROBLEMS
        assert says in out.err
        assert not any(c[0] == "api" for c in gh.calls)

    @pytest.mark.spec("next-cmd-follows-tracking-issue")
    def it_names_each_blocked_sub_issue_when_all_are_blocked(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved"),
            make_issue(12),
            subs={20: [11, 12]},
            blockers={11: [(9, "open")], 12: [(11, "open")]},
        )
        code, out = run(capsys, clone("a"), "queue", "--tracking", "20")
        assert code == flywheel.OK
        assert out.out == (
            "Every free sub-issue of #20 is blocked by an open issue:\n"
            "#11 issue 11, blocked by #9\n"
            "#12 issue 12, blocked by #11\n"
        )

    @pytest.mark.spec("next-cmd-reports-finished-plan")
    def it_says_the_plan_is_finished_when_every_sub_issue_is_closed(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved", state="CLOSED"),
            make_issue(12, "approved", state="CLOSED"),
            subs={20: [11, 12]},
        )
        code, out = run(capsys, clone("a"), "queue", "--tracking", "20")
        assert code == flywheel.OK
        assert out.out == (
            "Every sub-issue of #20 is closed, so its plan is finished.\n"
            "To close #20, run: flywheel.py plan close 20\n"
        )
        code, data = run_json(capsys, clone("b"), "queue", "--tracking", "20")
        assert data["data"]["finished"] is True
        assert data["data"]["issues"] == []

    @pytest.mark.spec("next-cmd-reports-finished-plan")
    def it_does_not_call_a_plan_finished_while_a_held_sub_issue_is_open(
        self, capsys, remote, clone, github
    ):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved", state="CLOSED"),
            make_issue(12, "approved", "claimed"),
            subs={20: [11, 12]},
        )
        code, out = run(capsys, a, "queue", "--tracking", "20")
        assert code == flywheel.OK
        assert out.out == "No sub-issue of #20 is free.\n"
        assert run_json(capsys, a, "queue", "--tracking", "20")[1]["data"]["finished"] is False

    @pytest.mark.spec("next-cmd-reports-finished-plan")
    def it_does_not_call_a_plan_without_sub_issues_finished(self, capsys, clone, github):
        github(make_issue(20, "approved", "plan"), subs={20: []})
        code, data = run_json(capsys, clone("a"), "queue", "--tracking", "20")
        assert code == flywheel.OK
        assert data["data"]["finished"] is False


class DescribeQueuePlans:
    @pytest.mark.spec(
        "next-cmd-names-tracking-issue", "repo:command-splits-output-streams-without-json"
    )
    def it_names_an_approved_plan_at_its_lowest_open_sub_issue(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(9, "approved", state="CLOSED"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            subs={20: [9, 12]},
        )
        code, out = run(capsys, clone("a"), "queue")
        assert code == flywheel.OK
        assert (out.out, out.err) == ("#11 issue 11\n", "")

        github(
            make_issue(20, "approved", "plan"),
            make_issue(10, "approved"),
            make_issue(11, "approved"),
            subs={20: [10]},
        )
        code, out = run(capsys, clone("b"), "queue")
        assert code == flywheel.OK
        assert out.out == (
            "#20 issue 20 is an approved tracking issue.\n"
            "To take its next sub-issue, run: flywheel.py queue --tracking 20\n"
        )

    @pytest.mark.spec("next-cmd-names-tracking-issue")
    def it_names_the_plan_apart_from_the_issue_to_work(self, capsys, clone, github):
        github(make_issue(20, "approved", "plan"), make_issue(21, "approved"), subs={20: []})
        code, data = run_json(capsys, clone("a"), "queue")
        assert code == flywheel.OK
        assert data["data"]["issues"] == []
        assert data["data"]["tracking"] == {"number": 20}

    @pytest.mark.spec("next-cmd-offers-free-issue")
    def it_never_offers_a_plan_or_an_approved_plans_sub_issue_as_work(self, capsys, clone, github):
        github(
            make_issue(20, "plan"),
            make_issue(30, "approved", "plan"),
            make_issue(10, "approved"),
            make_issue(31, "approved"),
            make_issue(32, "approved"),
            subs={20: [10], 30: [31]},
            blockers={10: [(1, "open")]},
        )
        code, data = run_json(capsys, clone("a"), "queue")
        assert code == flywheel.OK
        # 10 belongs to a plan nobody approved, so it is offered on its own,
        # and blocked; 30 takes its place before 32.
        assert data["data"]["issues"] == []
        assert data["data"]["tracking"] == {"number": 30}
        assert [b["number"] for b in data["data"]["blocked"]] == [10]


@pytest.mark.spec("queue-cmd-offers-up-to-count")
class DescribeQueueCount:
    def it_offers_up_to_count_free_issues_oldest_first(self, capsys, clone, github):
        github(
            *(make_issue(n, "approved") for n in (14, 13, 12, 11, 10)),
            blockers={11: [(9, "open")]},
        )
        code, out = run(capsys, clone("a"), "queue", "--count", "3")
        assert code == flywheel.OK
        assert (out.out, out.err) == ("#10 issue 10\n#12 issue 12\n#13 issue 13\n", "")
        code, data = run_json(capsys, clone("b"), "queue", "--count", "3")
        assert data["data"]["issues"] == [{"number": 10}, {"number": 12}, {"number": 13}]
        assert data["data"]["blocked"] == [{"number": 11, "blocked_by": [9]}]

    def it_says_when_fewer_are_free(self, capsys, clone, github):
        github(make_issue(10, "approved"), make_issue(12, "approved"), blockers={12: [(9, "open")]})
        code, out = run(capsys, clone("a"), "queue", "--count", "3")
        assert code == flywheel.OK
        assert out.out == (
            "#10 issue 10\n"
            "Every other free approved issue is blocked by an open issue:\n"
            "#12 issue 12, blocked by #9\n"
        )
        github(make_issue(10, "approved"))
        code, out = run(capsys, clone("b"), "queue", "--count", "2")
        assert code == flywheel.OK
        assert out.out == "#10 issue 10\nNo other approved issue is free.\n"

    def it_offers_no_issue_after_an_approved_plan(self, capsys, clone, github):
        github(
            make_issue(10, "approved"),
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            subs={20: [11]},
        )
        code, out = run(capsys, clone("a"), "queue", "--count", "3")
        assert code == flywheel.OK
        assert out.out == (
            "#10 issue 10\n"
            "#20 issue 20 is an approved tracking issue.\n"
            "To take its next sub-issue, run: flywheel.py queue --tracking 20\n"
        )

    def it_offers_up_to_count_of_a_plans_sub_issues_in_its_order(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            *(make_issue(n, "approved") for n in (11, 12, 13)),
            subs={20: [13, 11, 12]},
        )
        code, out = run(capsys, clone("a"), "queue", "--tracking", "20", "--count", "2")
        assert code == flywheel.OK
        assert out.out == "#13 issue 13\n#11 issue 11\n"

    def it_says_when_fewer_of_a_plans_sub_issues_are_free(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved"),
            subs={20: [11]},
        )
        code, out = run(capsys, clone("a"), "queue", "--tracking", "20", "--count", "2")
        assert code == flywheel.OK
        assert out.out == "#11 issue 11\nNo other sub-issue of #20 is free.\n"

    def it_stops_before_an_unapproved_sub_issue_and_warns(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved"),
            make_issue(12),
            make_issue(13, "approved"),
            subs={20: [11, 12, 13]},
        )
        code, out = run(capsys, clone("a"), "queue", "--tracking", "20", "--count", "3")
        assert code == flywheel.OK
        assert out.out == "#11 issue 11\n"
        assert out.err == (
            "warning: #12 issue 12 is next in #20's order and is not labeled approved; "
            "ask the owner to approve it\n"
        )

    @pytest.mark.parametrize("count", ["0", "-1", "two"])
    def it_refuses_a_count_below_one(self, capsys, count):
        with pytest.raises(SystemExit) as exc:
            flywheel.main(["queue", "--count", count])
        assert exc.value.code == flywheel.CANNOT_RUN
        assert "is not a whole number of 1 or more" in capsys.readouterr().err


@pytest.mark.spec("queue-cmd-checks-named-issues")
class DescribeQueueNamed:
    def it_offers_each_named_issue_that_can_start_in_the_order_named(self, capsys, clone, github):
        github(make_issue(14, "approved"), make_issue(12, "approved"), make_issue(10, "approved"))
        code, out = run(capsys, clone("a"), "queue", "14", "12", "14")
        assert code == flywheel.OK
        assert (out.out, out.err) == ("#14 issue 14\n#12 issue 12\n", "")
        code, data = run_json(capsys, clone("b"), "queue", "14", "12")
        assert data["data"]["issues"] == [{"number": 14}, {"number": 12}]

    def it_offers_a_named_sub_issue_of_an_approved_plan(self, capsys, clone, github):
        github(
            make_issue(20, "approved", "plan"),
            make_issue(11, "approved"),
            make_issue(12, "approved"),
            subs={20: [11, 12]},
        )
        code, data = run_json(capsys, clone("a"), "queue", "12")
        assert code == flywheel.OK
        assert data["data"]["issues"] == [{"number": 12}]

    def it_names_the_reason_each_other_issue_cannot_start(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(13, "approved"))
        run(capsys, a, "claim", "13")
        github(
            make_issue(10, "approved"),
            make_issue(11, "approved", state="CLOSED"),
            make_issue(12),
            make_issue(13, "approved", "claimed"),
            make_issue(14, "approved"),
            make_issue(15),
            blockers={14: [(9, "open"), (8, "closed")], 15: [(9, "open")]},
        )
        code, out = run(capsys, a, "queue", "10", "11", "12", "13", "14", "15")
        assert code == flywheel.PROBLEMS
        assert out.out == "#10 issue 10\n"
        assert out.err == (
            "#11 issue 11 cannot start: it is closed\n"
            "#12 issue 12 cannot start: it is not labeled approved; "
            "ask the owner to approve it\n"
            "#13 issue 13 cannot start: another session holds its claim on issue/13\n"
            "#14 issue 14 cannot start: it is blocked by #9\n"
            "#15 issue 15 cannot start: it is not labeled approved; "
            "ask the owner to approve it; it is blocked by #9\n"
        )
        code, data = run_json(capsys, a, "queue", "10", "14")
        assert code == flywheel.PROBLEMS
        assert data["data"]["issues"] == [{"number": 10}]
        assert data["data"]["blocked"] == [{"number": 14, "blocked_by": [9]}]
        assert data["errors"] == ["#14 issue 14 cannot start: it is blocked by #9"]

    def it_names_a_tracking_issue_and_the_command_that_runs_its_plan(self, capsys, clone, github):
        gh = github(make_issue(20, "approved", "plan"), subs={20: [11]})
        code, out = run(capsys, clone("a"), "queue", "20")
        assert code == flywheel.OK
        assert out.out == (
            "#20 issue 20 is a tracking issue.\n"
            "To run its plan, run: flywheel.py queue --tracking 20\n"
        )
        code, data = run_json(capsys, clone("b"), "queue", "20")
        assert data["data"]["issues"] == []
        assert data["data"]["tracking"] == {"number": 20}
        assert not any(c[0] == "api" for c in gh.calls)

    def it_refuses_a_tracking_issue_named_beside_other_issues(self, capsys, clone, github):
        github(make_issue(20, "approved", "plan"), make_issue(12, "approved"))
        code, data = run_json(capsys, clone("a"), "queue", "12", "20")
        assert code == flywheel.PROBLEMS
        assert data["data"]["issues"] == [{"number": 12}]
        assert data["data"]["tracking"] is None
        assert data["errors"] == [
            "#20 issue 20 cannot start: it is a tracking issue; to run its plan, name it on its own"
        ]

    def it_cannot_run_with_tracking_too(self, capsys, clone):
        with pytest.raises(SystemExit) as exc:
            flywheel.main(["queue", "12", "--tracking", "20", "-C", str(clone("a"))])
        assert exc.value.code == flywheel.CANNOT_RUN
        assert "not allowed with argument" in capsys.readouterr().err


class DescribeRelease:
    @pytest.mark.spec("release-cmd-frees-unused-claim")
    def it_deletes_an_empty_branch_and_the_label(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        gh = github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, a, "release", "12")
        assert code == flywheel.OK
        assert remote_branches(remote) == {flywheel.BASE}
        assert ("issue", "edit", "12", "--remove-label", "claimed") in gh.calls
        assert ("issue", "comment", "12", "--body", "Released issue/12.") in gh.calls

    @pytest.mark.spec("release-cmd-keeps-work")
    def it_never_deletes_work(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        (a / "work").write_text("work\n")
        git(a, "add", "work")
        git(a, "commit", "--quiet", "-m", "work")
        git(a, "push", "--quiet")
        gh = github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, clone("b"), "release", "12")
        assert code == flywheel.PROBLEMS
        assert "issue/12 has 1 commit(s) not on main" in out.err
        assert "issue/12" in remote_branches(remote)
        assert gh.writes() == []

    @pytest.mark.spec("release-cmd-requires-held-claim")
    def it_is_a_problem_on_an_unclaimed_issue(self, capsys, clone, github):
        github(make_issue(12, "approved"))
        code, out = run(capsys, clone("a"), "release", "12")
        assert code == flywheel.PROBLEMS
        assert "#12 is not claimed" in out.err

    @pytest.mark.spec("repo:command-never-writes-in-preview")
    def it_changes_nothing_on_a_dry_run(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        gh = github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, a, "release", "12", "--dry-run")
        assert code == flywheel.OK
        assert out.out == "Would release #12\n"
        assert "issue/12" in remote_branches(remote)
        assert gh.writes() == []

    @pytest.mark.spec("release-cmd-frees-unused-claim", "next-cmd-offers-free-issue")
    def it_leaves_the_issue_free_again(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        github(make_issue(12, "approved", "claimed"))
        run(capsys, a, "release", "12")
        github(make_issue(12, "approved"))
        assert run_json(capsys, a, "queue")[1]["data"]["issues"] == [{"number": 12}]

    @pytest.mark.spec("release-cmd-keeps-work")
    def it_keeps_a_branch_pushed_to_while_releasing(
        self, capsys, remote, clone, github, monkeypatch
    ):
        a = clone("a")
        github(make_issue(12, "approved"))
        run(capsys, a, "claim", "12")
        gh = github(make_issue(12, "approved", "claimed"))
        real = flywheel.git

        def pushed_meanwhile(repo, *args, **kwargs):
            if "push" in args and any(w.startswith("--force-with-lease") for w in args):
                git(a, "commit", "--quiet", "--allow-empty", "-m", "work")
                git(a, "push", "--quiet")
            return real(repo, *args, **kwargs)

        monkeypatch.setattr(flywheel, "git", pushed_meanwhile)
        code, out = run(capsys, clone("b"), "release", "12")
        assert code == flywheel.PROBLEMS
        assert "issue/12 changed while releasing" in out.err
        assert "issue/12" in remote_branches(remote)
        assert gh.writes() == []

    @pytest.mark.spec("release-cmd-frees-unused-claim")
    def it_frees_an_issue_whose_label_outlived_its_branch(self, capsys, remote, clone, github):
        gh = github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, clone("a"), "release", "12")
        assert code == flywheel.OK
        assert ("issue", "edit", "12", "--remove-label", "claimed") in gh.calls
        assert ("issue", "comment", "12", "--body", "Released issue/12.") in gh.calls

    @pytest.mark.spec("release-cmd-frees-unused-claim")
    def it_frees_a_claim_whose_label_was_never_added(self, capsys, remote, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"), fail=("--add-label",))
        run(capsys, a, "claim", "12")
        gh = github(make_issue(12, "approved"))
        code, out = run(capsys, a, "release", "12")
        assert code == flywheel.OK
        assert "issue/12" not in remote_branches(remote)
        assert gh.writes() == [("issue", "comment", "12", "--body", "Released issue/12.")]


def claimed(capsys, clone, github):
    a = clone("a")
    github(make_issue(12, "approved"))
    run(capsys, a, "claim", "12")
    return a


class DescribeStale:
    @pytest.mark.spec("stale-cmd-reports-claims-left-behind")
    def it_reports_a_branch_left_after_the_issue_closed(self, capsys, clone, github):
        a = claimed(capsys, clone, github)
        github(make_issue(12, "approved", state="CLOSED"))
        code, out = run(capsys, a, "stale")
        assert code == flywheel.PROBLEMS
        assert "#12 is closed but issue/12 still exists; run release 12" in out.err

    @pytest.mark.spec("stale-cmd-reports-claims-left-behind")
    def it_reports_a_label_without_a_branch(self, capsys, clone, github):
        github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, clone("a"), "stale")
        assert code == flywheel.PROBLEMS
        assert "#12 is labeled claimed but issue/12 does not exist" in out.err

    @pytest.mark.spec("stale-cmd-reports-claims-left-behind")
    def it_reports_a_closed_issue_that_kept_the_label(self, capsys, clone, github):
        github(make_issue(12, "approved", "claimed", state="CLOSED"))
        code, out = run(capsys, clone("a"), "stale")
        assert code == flywheel.PROBLEMS
        assert "#12 is closed but still labeled claimed; run release 12" in out.err

    @pytest.mark.spec("stale-cmd-reports-claims-left-behind")
    def it_reports_a_claim_that_lacks_the_label(self, capsys, clone, github):
        a = claimed(capsys, clone, github)
        github(make_issue(12, "approved"))
        code, out = run(capsys, a, "stale")
        assert code == flywheel.PROBLEMS
        assert (
            "#12 has issue/12 but is not labeled claimed; "
            "run gh issue edit 12 --add-label claimed" in out.err
        )

    @pytest.mark.spec("stale-cmd-reports-claims-left-behind")
    def it_says_so_when_every_claim_agrees(self, capsys, clone, github):
        a = claimed(capsys, clone, github)
        github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, a, "stale")
        assert code == flywheel.OK
        assert (out.out, out.err) == ("No stale claims.\n", "")


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
    git(seed, "pull", "--quiet", flywheel.REMOTE, flywheel.BASE)
    (seed / "work").write_text("work\n")
    (seed / "more").write_text("more\n")
    git(seed, "add", "work", "more")
    git(seed, "commit", "--quiet", "-m", "squashed")
    commit_file(seed, "later", "later\n")
    git(seed, "push", "--quiet", flywheel.REMOTE, "HEAD:" + flywheel.BASE)
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
    git(seed, "pull", "--quiet", flywheel.REMOTE, flywheel.BASE)
    # Its own message, or it would be the branch's commit byte for byte.
    commit_file(seed, "README", "work\n", "squashed")
    commit_file(seed, "README", "later\n")
    git(seed, "push", "--quiet", flywheel.REMOTE, "HEAD:" + flywheel.BASE)
    return a


def local_branches(repo):
    return set(git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split())


class DescribeClear:
    @pytest.mark.spec("clear-cmd-deletes-merged-branch")
    def it_deletes_a_branch_whose_work_main_has(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        code, out = run(capsys, a, "clear", "12")
        assert code == flywheel.OK
        assert out.out.startswith("Cleared issue/12\n")
        assert "issue/12" not in local_branches(a)
        assert git(a, "rev-parse", "HEAD") == git(remote, "rev-parse", flywheel.BASE)

    @pytest.mark.spec("clear-cmd-deletes-merged-branch")
    def it_deletes_a_branch_a_merged_pull_request_holds_after_main_moves_on(
        self, capsys, remote, clone, github
    ):
        a = merged_then_edited(capsys, clone, github, remote)
        tip = git(a, "rev-parse", "issue/12")
        github(make_issue(12, "approved", state="CLOSED"), merged=[(7, "issue/12", tip)])
        code, data = run_json(capsys, a, "clear", "12")
        assert code == flywheel.OK
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
        git(b, "push", "--quiet", flywheel.REMOTE, "HEAD:refs/pull/7/head")
        assert subprocess.run(["git", "cat-file", "-e", head], cwd=a).returncode != 0
        github(make_issue(12, "approved", state="CLOSED"), merged=[(7, "issue/12", head)])
        code, data = run_json(capsys, a, "clear", "12")
        assert code == flywheel.OK
        assert data["data"]["pull_request"] == 7
        assert "issue/12" not in local_branches(a)

    @pytest.mark.spec("clear-cmd-deletes-merged-branch")
    def it_moves_a_worktree_off_the_branch_and_keeps_it(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        git(a, "switch", "--quiet", "--detach")
        tree = a.parent / "tree"
        git(a, "worktree", "add", "--quiet", str(tree), "issue/12")
        code, data = run_json(capsys, a, "clear", "12")
        assert code == flywheel.OK
        assert data["data"]["worktrees"] == [git(tree, "rev-parse", "--show-toplevel")]
        assert tree.is_dir()
        assert git(tree, "branch", "--show-current") == ""
        assert git(tree, "rev-parse", "HEAD") == git(remote, "rev-parse", flywheel.BASE)
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
        assert code == flywheel.PROBLEMS
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
        assert code == flywheel.PROBLEMS
        assert "issue/12 holds commits that every merged pull request from it lacks" in out.err
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
        assert code == flywheel.PROBLEMS
        assert "has issue/12 checked out and uncommitted changes" in out.err
        assert "run clear 12 again" in out.err
        assert git(tree, "branch", "--show-current") == "issue/12"
        assert (tree / "README").read_text() == "unsaved\n"
        assert "issue/12" in local_branches(a)

    @pytest.mark.spec("clear-cmd-keeps-unmerged-work")
    def it_keeps_the_branch_of_an_open_issue(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        github(make_issue(12, "approved", "claimed"))
        code, out = run(capsys, a, "clear", "12")
        assert code == flywheel.PROBLEMS
        assert "#12 is still open" in out.err
        assert "issue/12" in local_branches(a)

    @pytest.mark.spec("clear-cmd-keeps-unmerged-work")
    def it_is_a_problem_when_there_is_no_local_branch(self, capsys, clone, github):
        github(make_issue(12, "approved", state="CLOSED"))
        code, out = run(capsys, clone("a"), "clear", "12")
        assert code == flywheel.PROBLEMS
        assert "there is no local issue/12 to clear" in out.err

    @pytest.mark.spec("repo:command-never-writes-in-preview")
    def it_changes_nothing_on_a_dry_run(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        code, out = run(capsys, a, "clear", "12", "--dry-run")
        assert code == flywheel.OK
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
        git(seed, "pull", "--quiet", flywheel.REMOTE, flywheel.BASE)
        commit_file(seed, "squash-me", "squash-me\n", "squashed as a new commit")
        git(seed, "push", "--quiet", flywheel.REMOTE, "HEAD:" + flywheel.BASE)
        git(a, "switch", "--quiet", "--detach")
        github(merged=[(7, "issue/12", tip)])
        code, data = run_json(capsys, a, "sweep")
        assert code == flywheel.OK
        assert sorted(data["data"]["deleted"]) == [
            "claude/fresh-session",
            "claude/squashed",
            "issue/12",
        ]
        assert data["data"]["kept"] == []
        assert local_branches(a) == {flywheel.BASE}

    @pytest.mark.spec("sweep-cmd-keeps-live-branches")
    def it_keeps_each_branch_that_may_still_be_in_use_and_says_why(
        self, capsys, remote, clone, github
    ):
        a = claimed(capsys, clone, github)
        git(a, "switch", "--quiet", "-c", "claude/unmerged")
        commit_file(a, "unmerged", "unmerged\n")
        git(a, "switch", "--quiet", "--detach")
        git(a, "branch", "claude/in-a-worktree", flywheel.BASE)
        tree = a.parent / "tree"
        git(a, "worktree", "add", "--quiet", str(tree), "claude/in-a-worktree")
        github()
        code, out = run(capsys, a, "sweep")
        assert code == flywheel.OK
        assert out.out.splitlines() == [
            "Kept claude/in-a-worktree: checked out in %s"
            % git(tree, "rev-parse", "--show-toplevel"),
            "Kept claude/unmerged: holds work origin/main lacks",
            "Kept issue/12: still on origin, where someone may be working on it",
        ]
        assert local_branches(a) == {
            flywheel.BASE,
            "claude/in-a-worktree",
            "claude/unmerged",
            "issue/12",
        }

    @pytest.mark.spec("repo:command-never-writes-in-preview")
    def it_changes_nothing_on_a_dry_run(self, capsys, clone, github):
        a = clone("a")
        git(a, "branch", "claude/fresh-session")
        github()
        code, out = run(capsys, a, "sweep", "--dry-run")
        assert code == flywheel.OK
        assert out.out == "Would delete claude/fresh-session\n"
        assert "claude/fresh-session" in local_branches(a)


class DescribeMain:
    @pytest.mark.parametrize(
        "argv",
        [
            ["queue"],
            ["claim", "12", "--dry-run"],
            ["release", "12"],
            ["stale"],
            ["clear", "12"],
            ["sweep", "--dry-run"],
        ],
    )
    @pytest.mark.spec("repo:command-prints-json-envelope")
    def it_prints_the_same_envelope_for_every_command(self, capsys, clone, github, argv):
        github(make_issue(12, "approved"))
        _, data = run_json(capsys, clone("a"), *argv)
        assert set(data) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert data["version"] == flywheel.ENVELOPE_VERSION
        assert data["command"] == argv[0]

    @pytest.mark.spec("repo:command-prints-json-envelope")
    def it_names_only_the_issue_and_branch_for_claim_release_and_stale(self, capsys, clone, github):
        a = clone("a")
        github(make_issue(12, "approved"))
        claim = run_json(capsys, a, "claim", "12")[1]["data"]
        github(make_issue(12, "approved", "claimed"))
        stale = run_json(capsys, a, "stale")[1]["data"]
        release = run_json(capsys, a, "release", "12")[1]["data"]
        row = {"number": 12, "branch": "issue/12"}
        assert (claim, stale, release) == (row, {"claims": [row]}, row)

    @pytest.mark.spec("repo:command-prints-json-envelope")
    def it_leaves_whether_clear_cleared_to_the_exit_code(self, capsys, remote, clone, github):
        a = squash_merged(capsys, clone, github, remote)
        code, data = run_json(capsys, a, "clear", "12")
        assert code == flywheel.OK
        assert set(data["data"]) == {"number", "branch", "pull_request", "worktrees"}

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    def it_cannot_run_when_gh_fails(self, capsys, clone, github):
        github(fail=("view",))
        code, out = run(capsys, clone("a"), "claim", "12")
        assert code == flywheel.CANNOT_RUN
        assert out.out == ""
        assert out.err == "flywheel.py: gh view failed\n"

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    def it_cannot_run_outside_a_clone(self, capsys, tmp_path, github):
        github()
        code, out = run(capsys, tmp_path, "queue")
        assert code == flywheel.CANNOT_RUN
        assert out.err.startswith("flywheel.py: ")


APPROVED_AT = "2026-10-15T10:00:00Z"


def answer(*events, edited=None, labels=("approved",), comments=(), body="Fix it.\n"):
    """GitHub's GraphQL answer for issue 12, labeled at each (time, label) event."""
    return {
        "data": {
            "repository": {
                "nameWithOwner": "owner/project",
                "owner": {"login": "owner"},
                "issue": {
                    "number": 12,
                    "title": "issue 12",
                    "body": body,
                    "url": "https://github.com/owner/project/issues/12",
                    "lastEditedAt": edited,
                    "labels": {"nodes": [{"name": n} for n in labels]},
                    "timelineItems": {
                        "nodes": [{"createdAt": t, "label": {"name": n}} for t, n in events]
                    },
                    "comments": {
                        "nodes": [
                            {"author": {"login": who}, "body": text, "createdAt": t}
                            for who, text, t in comments
                        ]
                    },
                },
            }
        }
    }


def configure(root, roles=True, gates=True):
    """Write the roles and gates files brief reads, as the owner would."""
    if roles:
        (root / ".flywheel").mkdir(exist_ok=True)
        (root / flywheel.ROLES_FILE).write_text(
            json.dumps({"roles": {"implementer": {"tier": 3, "model": "m", "effort": "high"}}})
        )
    if gates:
        (root / ".flywheel").mkdir(exist_ok=True)
        (root / flywheel.GATES_FILE).write_text(
            json.dumps({"gates": {"check": "make check", "verify": "make verify"}})
        )


class DescribeBriefMappedApproval:
    @pytest.mark.spec("labelsfile-maps-roles", "brief-cmd-prints-issue-as-approved")
    def it_reads_the_approval_from_the_mapped_approval_label(self, capsys, clone, github):
        a = mapped(clone("a"))
        configure(a)
        github(
            graphql=answer(
                ("2026-10-15T08:00:00Z", "ready"), (APPROVED_AT, "approved"), labels=("ready",)
            )
        )
        code, env = run_json(capsys, a, "brief", "12")
        assert code == flywheel.OK, env["errors"]
        assert env["data"]["approved_at"] == "2026-10-15T08:00:00Z"

        github(graphql=answer((APPROVED_AT, "approved")))
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.PROBLEMS
        assert "#12 is not labeled ready" in out.err


@pytest.mark.spec("brief-cmd-prints-issue-as-approved")
class DescribeBrief:
    def it_prints_the_issue_the_owners_comments_the_role_and_the_gates(self, capsys, clone, github):
        a = clone("a")
        configure(a)
        github(
            graphql=answer(
                ("2026-10-15T09:00:00Z", "enhancement"),
                (APPROVED_AT, "approved"),
                body="## What's wrong\n\nIt breaks.\n",
                comments=[
                    ("owner", "Before approval.", "2026-10-15T09:30:00Z"),
                    ("owner", "Keep the old name.", "2026-10-15T11:00:00Z"),
                    ("someone", "Me too.", "2026-10-15T11:10:00Z"),
                    ("owner", "**Claude:** Done.", "2026-10-15T11:20:00Z"),
                    ("owner", "Claimed on branch `issue/12`.", "2026-10-15T11:30:00Z"),
                ],
            )
        )
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.OK
        assert out.err == ""
        assert out.out == (
            "Work issue #12 in owner/project, as the implementer, with the work-issue skill.\n"
            "\n"
            "The implementer is tier 3 in .flywheel/roles.json.\n"
            "\n"
            "The gate commands, from .flywheel/gates.json:\n"
            "- check: `make check`\n"
            "- verify: `make verify`\n"
            "\n"
            "The issue, as the owner approved it at 2026-10-15T10:00:00Z:\n"
            "\n"
            "> # issue 12\n"
            ">\n"
            "> ## What's wrong\n"
            ">\n"
            "> It breaks.\n"
            "\n"
            "The owner's comments since approval:\n"
            "\n"
            "> **2026-10-15T11:00:00Z**\n"
            ">\n"
            "> Keep the old name.\n"
        )

    def it_gives_the_same_brief_in_its_envelope(self, capsys, clone, github):
        a = clone("a")
        configure(a)
        github(graphql=answer((APPROVED_AT, "approved")))
        _, plain = run(capsys, a, "brief", "12")
        code, env = run_json(capsys, a, "brief", "12")
        assert code == flywheel.OK
        assert env["command"] == "brief"
        assert env["data"]["prompt"] == plain.out
        assert env["data"]["role"] == {"name": "implementer", "tier": 3}
        assert env["data"]["approved_at"] == APPROVED_AT
        assert env["data"]["comments"] == []

    def it_names_the_skill_that_works_the_issue_in_its_first_line(self, capsys, clone, github):
        a = clone("a")
        configure(a)
        github(graphql=answer((APPROVED_AT, "approved")))
        _, out = run(capsys, a, "brief", "12")
        assert out.out.split("\n")[0].endswith(", with the work-issue skill.")

    def it_says_when_the_owner_has_not_commented(self, capsys, clone, github):
        a = clone("a")
        configure(a)
        github(graphql=answer((APPROVED_AT, "approved")))
        _, out = run(capsys, a, "brief", "12")
        assert out.out.endswith("> Fix it.\n\nThe owner has not commented since approval.\n")

    def it_refuses_an_issue_edited_after_approval(self, capsys, clone, github):
        a = clone("a")
        configure(a)
        github(graphql=answer((APPROVED_AT, "approved"), edited="2026-10-15T12:00:00Z"))
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.PROBLEMS
        assert out.out == ""
        assert out.err == (
            "#12 was edited at 2026-10-15T12:00:00Z, after `approved` was added at "
            "2026-10-15T10:00:00Z. The owner reads the edit and re-approves it by removing the "
            "label and adding it again.\n"
        )
        assert run_json(capsys, a, "brief", "12")[1]["data"]["prompt"] is None

    def it_reads_the_last_approval_as_the_one_that_counts(self, capsys, clone, github):
        a = clone("a")
        configure(a)
        github(
            graphql=answer(
                ("2026-10-15T08:00:00Z", "Approved"),
                (APPROVED_AT, "approved"),
                edited="2026-10-15T09:00:00Z",
            )
        )
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.OK
        assert "approved it at 2026-10-15T10:00:00Z" in out.out

    def it_refuses_an_issue_that_is_not_labeled_approved(self, capsys, clone, github):
        a = clone("a")
        configure(a)
        github(graphql=answer((APPROVED_AT, "approved"), labels=("bug",)))
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.PROBLEMS
        assert out.out == ""
        assert "#12 is not labeled approved" in out.err

    def it_takes_every_owners_comment_when_the_approval_is_out_of_reach(
        self, capsys, clone, github
    ):
        a = clone("a")
        configure(a)
        github(
            graphql=answer(
                edited="2026-10-15T12:00:00Z",
                comments=[("owner", "Early.", "2026-10-15T09:30:00Z")],
            )
        )
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.OK
        assert "The issue, as the owner approved it:\n" in out.out
        assert "> Early.\n" in out.out

    def it_leaves_out_each_gate_the_owner_has_not_set(self, capsys, clone, github):
        a = clone("a")
        configure(a)
        (a / flywheel.GATES_FILE).write_text(
            json.dumps({"gates": {"build": None, "check": "make check", "verify": None}})
        )
        github(graphql=answer((APPROVED_AT, "approved")))
        _, out = run(capsys, a, "brief", "12")
        assert "The gate commands, from .flywheel/gates.json:\n- check: `make check`\n\n" in out.out
        assert "None" not in out.out

    def it_warns_without_a_roles_or_a_gates_file(self, capsys, clone, github):
        a = clone("a")
        github(graphql=answer((APPROVED_AT, "approved")))
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.OK
        assert out.out.startswith(
            "Work issue #12 in owner/project, as the implementer, with the work-issue skill.\n\nThe issue, as the owner"
        )
        assert out.err == (
            "warning: .flywheel/roles.json does not name the implementer role, so the brief"
            " leaves out its tier. Run config init to write it.\n"
            "warning: .flywheel/gates.json is missing, so the brief names no gate commands."
            ' Write it with a "gates" object that maps each gate to its command.\n'
        )

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
    @pytest.mark.parametrize(
        ("text", "says"),
        [
            ("{", "is not valid JSON"),
            ('{"gates": ["make check"]}', 'does not hold a "gates" object'),
        ],
    )
    def it_stops_on_a_gates_file_it_cannot_read(self, capsys, clone, github, text, says):
        a = clone("a")
        configure(a, gates=False)
        (a / flywheel.GATES_FILE).write_text(text)
        github(graphql=answer((APPROVED_AT, "approved")))
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.CANNOT_RUN
        assert out.err.startswith("flywheel.py: .flywheel/gates.json %s" % says)
        assert out.err.endswith("Fix it, then run again.\n")

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
    def it_stops_on_a_number_that_is_not_an_issue(self, capsys, clone, github):
        github(graphql={"data": {"repository": {"issue": None}}})
        code, out = run(capsys, clone("a"), "brief", "12")
        assert code == flywheel.CANNOT_RUN
        assert out.err == (
            "flywheel.py: #12 is not an issue in this repository. Name an issue's number.\n"
        )


@pytest.fixture
def path_with(tmp_path, monkeypatch):
    """A PATH holding git and, when `gh` is given, a gh that runs that shell body."""

    def make(gh=None):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").symlink_to(shutil.which("git"))
        if gh is not None:
            (bin_dir / "gh").write_text("#!/bin/sh\n" + gh)
            (bin_dir / "gh").chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir))

    return make


@pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
class DescribeTheGitHubCli:
    def it_stops_when_gh_is_not_installed(self, capsys, clone, path_with):
        a = clone("a")
        path_with()
        code, out = run(capsys, a, "queue")
        assert code == flywheel.CANNOT_RUN
        assert out.err.startswith("flywheel.py: cannot run gh: ")
        assert out.err.endswith("Install it, or put it on PATH, then run again.\n")

    def it_stops_when_gh_fails_and_leaves_a_query_out_of_the_message(
        self, capsys, clone, path_with
    ):
        a = clone("a")
        path_with("echo 'gh: not signed in' >&2\nexit 1\n")
        code, out = run(capsys, a, "brief", "12")
        assert code == flywheel.CANNOT_RUN
        assert out.err == (
            "flywheel.py: `gh api graphql -F owner={owner} -F name={repo} -F number=12 -f ...`"
            " failed: gh: not signed in\n"
        )

    def it_stops_when_gh_does_not_answer_in_json(self, capsys, clone, path_with):
        a = clone("a")
        path_with("echo 'not json'\n")
        code, out = run(capsys, a, "queue")
        assert code == flywheel.CANNOT_RUN
        assert out.err.startswith("flywheel.py: gh issue did not return JSON: ")


# A repository whose own labels play the loop's roles.
MAPPED = {"approval": "ready", "plan": "epic", "claim": "flywheel-claim"}


def mapped(path):
    """The clone at path, with .flywheel/labels.json giving MAPPED."""
    (path / ".flywheel").mkdir(exist_ok=True)
    (path / ".flywheel" / "labels.json").write_text(json.dumps({"roles": MAPPED}))
    return path


class DescribeMappedLabels:
    @pytest.mark.spec("labelsfile-maps-roles", "next-cmd-offers-free-issue")
    def it_offers_only_an_issue_carrying_the_mapped_approval_label(self, capsys, clone, github):
        github(make_issue(12, "approved"), make_issue(13, "ready"))
        code, data = run_json(capsys, mapped(clone("a")), "queue")
        assert code == flywheel.OK
        assert data["data"]["issues"] == [{"number": 13}]

    @pytest.mark.spec("labelsfile-maps-roles", "next-cmd-names-tracking-issue")
    def it_names_a_plan_by_the_mapped_plan_label(self, capsys, clone, github):
        github(
            make_issue(20, "ready", "epic"),
            make_issue(21, "ready", "plan"),
            make_issue(10, "ready"),
            subs={20: [10], 21: []},
        )
        code, data = run_json(capsys, mapped(clone("a")), "queue", "--count", "2")
        assert code == flywheel.OK
        assert data["data"]["tracking"] == {"number": 20}

    @pytest.mark.spec("labelsfile-maps-roles", "next-cmd-follows-tracking-issue")
    def it_follows_a_plan_that_carries_the_mapped_labels(self, capsys, clone, github):
        github(make_issue(20, "ready", "epic"), make_issue(11, "ready"), subs={20: [11]})
        code, data = run_json(capsys, mapped(clone("a")), "queue", "--tracking", "20")
        assert code == flywheel.OK, data["errors"]
        assert data["data"]["issues"] == [{"number": 11}]

        github(make_issue(20, "approved", "plan"), make_issue(11, "ready"), subs={20: [11]})
        code, data = run_json(capsys, mapped(clone("b")), "queue", "--tracking", "20")
        assert code == flywheel.PROBLEMS
        assert "#20 is not labeled epic" in data["errors"][0]
        assert "#20 is not labeled ready" in data["errors"][1]

    @pytest.mark.spec("labelsfile-maps-roles", "claim-cmd-adds-in-progress-label")
    def it_claims_by_the_mapped_approval_label_and_adds_the_mapped_claim_label(
        self, capsys, remote, clone, github
    ):
        a = mapped(clone("a"))
        gh = github(make_issue(12, "approved"))
        code, out = run(capsys, a, "claim", "12")
        assert code == flywheel.PROBLEMS
        assert "#12 is not labeled ready" in out.err

        gh = github(make_issue(12, "ready"))
        code, out = run(capsys, a, "claim", "12")
        assert code == flywheel.OK, out.err
        assert ("issue", "edit", "12", "--add-label", "flywheel-claim") in gh.calls

    @pytest.mark.spec("labelsfile-maps-roles", "release-cmd-frees-unused-claim")
    def it_releases_by_removing_the_mapped_claim_label(self, capsys, remote, clone, github):
        a = mapped(clone("a"))
        gh = github(make_issue(12, "ready", "flywheel-claim"))
        code, out = run(capsys, a, "release", "12")
        assert code == flywheel.OK, out.err
        assert ("issue", "edit", "12", "--remove-label", "flywheel-claim") in gh.calls

        gh = github(make_issue(12, "ready", "claimed"))
        code, out = run(capsys, a, "release", "12")
        assert code == flywheel.PROBLEMS
        assert gh.writes() == []

    @pytest.mark.spec("labelsfile-maps-roles", "stale-cmd-reports-claims-left-behind")
    def it_reports_the_mapped_claim_label_left_without_a_branch(self, capsys, clone, github):
        github(make_issue(12, "ready", "flywheel-claim"), make_issue(13, "claimed"))
        code, out = run(capsys, mapped(clone("a")), "stale")
        assert code == flywheel.PROBLEMS
        assert out.err == (
            "#12 is labeled flywheel-claim but issue/12 does not exist; run release 12\n"
        )

    @pytest.mark.spec("labelsfile-maps-roles", "planclose-cmd-closes-finished-plan")
    def it_closes_only_a_plan_carrying_the_mapped_labels(self, capsys, clone, github):
        gh = github(make_issue(20, "approved", "plan"), subs={20: []})
        code, data = run_json(capsys, mapped(clone("a")), "plan", "close", "20")
        assert code == flywheel.PROBLEMS
        assert data["errors"] == [
            "#20 is not labeled epic; plan close closes only a plan",
            "#20 is not labeled ready; ask the owner to approve the plan or close it",
        ]
        assert gh.writes() == []

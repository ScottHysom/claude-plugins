"""issues.py's `plan close`, and what every issues.py command shares. The plan
commands' other suite is test_issues_plan.py. Each test runs in a real clone;
only gh is faked.
"""

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
    git(world, "init", "--quiet", "--bare", "-b", "main", str(bare))
    seed = world / "seed"
    git(world, "clone", "--quiet", str(bare), str(seed))
    git(seed, "remote", "set-url", "origin", "../remote.git")
    (seed / "README").write_text("seed\n")
    git(seed, "add", "README")
    git(seed, "commit", "--quiet", "-m", "seed")
    git(seed, "push", "--quiet", "origin", "HEAD:" + "main")


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


class FakeGitHub:
    """gh, answering from a dict of issues. Records every call."""

    def __init__(self, issues=None, merged=(), fail=(), blockers=None, subs=None):
        self.issues = issues or {}
        self.blockers = blockers or {}
        self.subs = subs or {}
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
        monkeypatch.setattr(cli, "gh", fake)
        return fake

    return install


def run(capsys, repo, *argv):
    code = cli.main([*argv, "-C", str(repo)])
    return code, capsys.readouterr()


def run_json(capsys, repo, *argv):
    code, out = run(capsys, repo, *argv, "--json")
    return code, json.loads(out.out)


class DescribePlanClose:
    @pytest.mark.spec("planclose-cmd-closes-finished-plan")
    def it_closes_a_plan_whose_sub_issues_are_all_closed(self, capsys, clone, github):
        gh = github(
            make_issue(20, "approved", "tracking"),
            make_issue(11, "approved", state="CLOSED"),
            make_issue(12, "approved", state="CLOSED"),
            subs={20: [12, 11]},
        )
        code, out = run(capsys, clone("a"), "plan", "close", "20")
        assert code == cli.OK
        assert (out.out, out.err) == (
            "Closed #20. Every sub-issue is closed: #12, #11.\n",
            "",
        )
        assert gh.writes() == [
            (
                "issue",
                "close",
                "20",
                "--reason",
                "completed",
                "--comment",
                "Every sub-issue is closed: #12, #11.",
            )
        ]

    @pytest.mark.spec("planclose-cmd-closes-finished-plan")
    def it_refuses_while_any_sub_issue_is_open(self, capsys, clone, github):
        gh = github(
            make_issue(20, "approved", "tracking"),
            make_issue(11, "approved", state="CLOSED"),
            make_issue(12, "approved", "in-progress"),
            make_issue(13),
            subs={20: [11, 12, 13]},
        )
        code, data = run_json(capsys, clone("a"), "plan", "close", "20")
        assert code == cli.PROBLEMS
        assert "#20 still has open sub-issues: #12, #13" in data["errors"][0]
        assert data["data"]["closed"] is False
        assert gh.writes() == []

    @pytest.mark.spec("planclose-cmd-closes-finished-plan")
    @pytest.mark.parametrize(
        ("labels", "state", "says"),
        [
            (("tracking",), "OPEN", "not labeled approved"),
            (("approved",), "OPEN", "not labeled tracking"),
            (("approved", "tracking"), "CLOSED", "is closed already"),
        ],
    )
    def it_refuses_an_issue_that_is_not_an_open_approved_plan(
        self, capsys, clone, github, labels, state, says
    ):
        gh = github(make_issue(20, *labels, state=state), subs={20: []})
        code, out = run(capsys, clone("a"), "plan", "close", "20")
        assert code == cli.PROBLEMS
        assert says in out.err
        assert gh.writes() == []
        assert not any(c[0] == "api" for c in gh.calls)

    @pytest.mark.spec("planclose-cmd-closes-finished-plan")
    def it_refuses_a_plan_without_sub_issues(self, capsys, clone, github):
        gh = github(make_issue(20, "approved", "tracking"), subs={20: []})
        code, out = run(capsys, clone("a"), "plan", "close", "20")
        assert code == cli.PROBLEMS
        assert "#20 has no sub-issues" in out.err
        assert gh.writes() == []


class DescribeMain:
    @pytest.mark.spec("command-prints-json-envelope")
    def it_prints_the_same_envelope_for_plan_close(self, capsys, clone, github):
        github(make_issue(20, "approved", "tracking"), subs={20: []})
        _, data = run_json(capsys, clone("a"), "plan", "close", "20")
        assert set(data) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert data["version"] == cli.ENVELOPE_VERSION
        assert data["command"] == "plan close"

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_when_gh_fails(self, capsys, clone, github):
        github(fail=("view",))
        code, out = run(capsys, clone("a"), "plan", "close", "12")
        assert code == cli.CANNOT_RUN
        assert out.out == ""
        assert out.err == "issues.py: gh view failed\n"

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_outside_a_clone(self, capsys, tmp_path, github):
        github()
        code, out = run(capsys, tmp_path, "plan", "close", "12")
        assert code == cli.CANNOT_RUN
        assert out.err.startswith("issues.py: ")

    @pytest.mark.spec("script-ignores-closed-pipe")
    def it_exits_ok_when_its_reader_closes_the_pipe(self, capsys, clone, github, closed_pipe):
        github(
            make_issue(20, "approved", "tracking"),
            make_issue(11, "approved", state="CLOSED"),
            subs={20: [11]},
        )
        closed_pipe()
        assert cli.main(["plan", "close", "20", "-C", str(clone("a"))]) == cli.OK
        assert capsys.readouterr().err == ""

    # Every other command asks GitHub, which only the test process can fake.
    @pytest.mark.spec("script-ignores-closed-pipe")
    @pytest.mark.parametrize(
        "command", [["--help"], ["plan", "--help"], ["plan", "close", "--help"]]
    )
    def it_exits_ok_without_a_traceback_when_its_reader_has_gone(self, closed_pipe_child, command):
        assert closed_pipe_child(_PATH, *command) == (cli.OK, "")


_CLAUDE_MD = _PATH.parents[2] / "CLAUDE.md"


def issues_section():
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    return text.split("\n## Issues\n", 1)[1].split("\n## ", 1)[0]


@pytest.mark.spec("claudemd-reports-claim-first")
class DescribeTheClaimRuleInClaudeMd:
    def it_tells_the_agent_to_report_the_claim_before_other_work(self):
        rule = next(item for item in issues_section().split("\n- ") if "how the claim went" in item)
        assert "before any other work" in rule
        assert "`claim N`" in rule
        assert "#N" in rule
        assert "`issue/N`" in rule
        assert "exit 1" in rule

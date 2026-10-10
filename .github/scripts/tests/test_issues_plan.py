"""issues.py plan turns one approved plan into issues, links and a tracking
issue. A filed issue cannot be counted on to come back, so the plan is checked
whole before the first call, filed only with the token of the report the owner
read, and read back once filed. gh is faked by a small GitHub that keeps the
issues, links and sub-issues it is given.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "issues.py"
_spec = importlib.util.spec_from_file_location("issues_plan", _PATH)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

LABELS = ("bug", "enhancement", "docs", "repo", "plugin:todos", "approved", "tracking")
BODY = (
    "**Claude:**\n\n## What's wrong\n\nIt breaks.\n\n## Evidence\n\nissues.py:1\n\n"
    "## Done when\n\nIt works.\n\n## Requirements\n\nNone.\n"
)
FIRST = 100
# The body of an issue filed before the plan. It keeps neither the headings
# a draft needs nor its {KEY}, which only a draft's body has filled in.
OLD_BODY = "Filed by hand. See #{A}.\n"


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "clone"
    path.mkdir()
    subprocess.run(["git", "init", "--quiet", str(path)], check=True)
    return path


class Hub:
    """gh, as a repository that keeps what it is sent. Records every call.

    `fail_create` makes the create call with that index, counting from 0,
    fail; `drop_link` takes a link to that issue and keeps none of it.
    """

    def __init__(self, labels=LABELS, outside=(), fail_create=None, drop_link=None):
        self.labels = list(labels)
        self.issues = {}
        for number, state in outside:
            self.issues[number] = {
                "number": number,
                "title": "old #%d" % number,
                "state": state,
                "labels": [{"name": "bug"}, {"name": "repo"}],
                "body": OLD_BODY,
                "url": "https://github.com/o/r/issues/%d" % number,
            }
        self.blocked, self.subs, self.calls = {}, {}, []
        self.next = FIRST
        self.creates = 0
        self.fail_create = fail_create
        self.drop_link = drop_link

    def __call__(self, repo, *args, stdin=None):
        self.calls.append(args)
        if args[:2] == ("repo", "view"):
            return json.dumps({"nameWithOwner": "o/r", "url": "https://github.com/o/r"})
        if args[:2] == ("label", "list"):
            return json.dumps([{"name": n} for n in self.labels])
        if args[:2] == ("issue", "view"):
            number = int(args[2])
            if number not in self.issues:
                raise cli.Fatal("no issue #%d" % number)
            return json.dumps(self.issues[number])
        if args[:2] == ("issue", "create"):
            index, self.creates = self.creates, self.creates + 1
            if index == self.fail_create:
                raise cli.Fatal("gh issue create failed")
            number, self.next = self.next, self.next + 1
            labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
            self.issues[number] = {
                "number": number,
                "title": args[args.index("--title") + 1],
                "state": "OPEN",
                "labels": labels,
                "body": stdin,
            }
            return "https://github.com/o/r/issues/%d\n" % number
        if args[:3] == ("api", "-X", "POST"):
            path, field = args[3], args[5]
            target = field.split("=")[1]
            number = int(target) - 1000
            if path.endswith("/blocked_by"):
                issue = int(path.split("/")[-3])
                if issue != self.drop_link:
                    self.blocked.setdefault(issue, []).append(number)
            else:
                self.subs.setdefault(int(path.split("/")[-2]), []).append(number)
            return "{}"
        path = args[1]
        if "/sub_issues" in path:
            listed = self.subs.get(int(path.split("/")[-2]), [])
            return json.dumps([{"number": n, "state": "open"} for n in listed])
        if path.endswith("/blocked_by"):
            listed = self.blocked.get(int(path.split("/")[-3]), [])
            return json.dumps([{"number": n, "state": "open"} for n in listed])
        number = int(path.split("/")[-1])
        return json.dumps({"id": 1000 + number, "number": number})

    def filed(self):
        """{number: issue} for every issue this repository was sent."""
        return {n: i for n, i in self.issues.items() if n >= FIRST}

    def writes(self):
        return [
            c for c in self.calls if c[:2] == ("issue", "create") or c[:3] == ("api", "-X", "POST")
        ]


@pytest.fixture
def hub(monkeypatch):
    def install(**kwargs):
        fake = Hub(**kwargs)
        monkeypatch.setattr(cli, "gh", fake)
        return fake

    return install


def issue(key, *blocked_by, labels=("enhancement", "repo"), body=BODY, title=None):
    out = {"key": key, "title": title or "issue %s" % key, "labels": list(labels), "body": body}
    if blocked_by:
        out["blocked_by"] = list(blocked_by)
    return out


def write_plan(tmp_path, *issues, plan="Do the plan.", **extra):
    path = tmp_path / "plan.json"
    data = {"issues": list(issues), "tracking": {"title": "The plan", "plan": plan}}
    data.update(extra)
    path.write_text(json.dumps(data))
    return path


def run(capsys, repo, *argv):
    code = cli.main([*argv, "-C", str(repo)])
    return code, capsys.readouterr()


def run_json(capsys, repo, *argv):
    code, out = run(capsys, repo, *argv, "--json")
    return code, json.loads(out.out)


def report(capsys, repo, plan):
    return run_json(capsys, repo, "plan", "report", "--drafts", str(plan))


def token_for(capsys, repo, plan):
    code, data = report(capsys, repo, plan)
    assert code == cli.OK, data["errors"]
    return data["data"]["token"]


def file_plan(capsys, repo, plan, token, *more):
    return run_json(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token, *more)


class DescribePlanReportDrafts:
    @pytest.mark.parametrize(
        ("draft", "says"),
        [
            (
                issue("A", body=BODY.replace("**Claude:**", "Claude")),
                "does not open with **Claude:**",
            ),
            (
                issue("A", body=BODY.replace("## Evidence", "## Proof")),
                "lacks the heading `## Evidence`",
            ),
            (issue("A", labels=("bug", "docs", "repo")), "carries 2 kind labels (bug, docs)"),
            (issue("A", labels=("bug",)), "carries 0 area labels"),
            (
                issue("A", labels=("bug", "repo", "approved")),
                "`approved`, which only the owner adds",
            ),
            (
                issue("A", labels=("bug", "repo", "tracking")),
                "which only the tracking issue carries",
            ),
            (issue("A", labels=("bug", "repo", "wontfix")), "a label the repository does not have"),
            (issue("A", labels=("bug", "plugin:nope")), "`plugin:nope`, a label the repository"),
        ],
        ids=[
            "opening",
            "heading",
            "two-kinds",
            "no-area",
            "approved",
            "tracking",
            "unknown",
            "area",
        ],
    )
    @pytest.mark.spec("planreport-cmd-checks-each-draft")
    def it_refuses_a_draft_that_breaks_the_issue_rules(
        self, capsys, tmp_path, repo, hub, draft, says
    ):
        gh = hub()
        code, data = report(capsys, repo, write_plan(tmp_path, draft, issue("B")))
        assert code == cli.PROBLEMS
        assert any(says in e and e.startswith("`A`") for e in data["errors"]), data["errors"]
        assert not any(e.startswith("`B`") for e in data["errors"])
        assert data["data"]["token"] is None
        assert gh.writes() == []

    @pytest.mark.spec("planreport-cmd-checks-each-draft", "script-checks-every-answer")
    def it_names_every_fault_in_one_run(self, capsys, tmp_path, repo, hub):
        hub()
        plan = write_plan(
            tmp_path,
            issue("A", labels=("approved",), body="no opening"),
            {"key": "B", "title": "", "body": BODY, "labels": ["bug", "repo"], "color": "red"},
            "not an issue",
        )
        code, data = report(capsys, repo, plan)
        assert code == cli.PROBLEMS
        errors = "\n".join(data["errors"])
        for says in (
            "`A`'s body does not open with",
            "`A`'s body lacks the headings",
            "`A` carries 0 kind labels",
            "`A` carries `approved`",
            "`B` has no title",
            "`B` has 'color'",
            "issue 3 is not a JSON object",
        ):
            assert says in errors

    @pytest.mark.spec("planreport-cmd-checks-each-draft")
    def it_passes_a_plan_that_keeps_the_rules(self, capsys, tmp_path, repo, hub):
        hub()
        plan = write_plan(tmp_path, issue("A", labels=("Bug", "plugin:todos")))
        code, data = report(capsys, repo, plan)
        assert code == cli.OK
        assert data["errors"] == []
        assert data["data"]["issues"][0]["labels"] == ["bug", "plugin:todos"]
        assert len(data["data"]["token"]) == cli.TOKEN_LENGTH


class DescribePlanReportLinks:
    @pytest.mark.parametrize(
        ("issues", "says"),
        [
            ((issue("A"), issue("A")), "the key `A` names more than one issue"),
            ((issue("A", body=BODY + "See #{Z}."),), "`A`'s body names {Z}, and no issue"),
            ((issue("A", "Z"),), "`A` is blocked by `Z`, and no issue in the plan has that key"),
            ((issue("A", 7),), "`A` is blocked by #7, which is closed"),
            ((issue("A", 9),), "`A` is blocked by #9, which cannot be read"),
            (
                (issue("A", "C"), issue("B", "A"), issue("C", "B")),
                "the links form a cycle: `A` is blocked by `C`, `C` is blocked by `B`, "
                "`B` is blocked by `A`",
            ),
            ((issue("A", "A"),), "the links form a cycle: `A` is blocked by `A`"),
            (
                (issue("A", body=BODY + "Then #{B}."), issue("B")),
                "`A`'s body names {B}, which is filed after it",
            ),
        ],
        ids=["repeat", "reference", "blocker", "closed", "missing", "cycle", "self", "forward"],
    )
    @pytest.mark.spec("planreport-cmd-checks-plan-links")
    def it_refuses_a_link_that_names_nothing_it_can_file(
        self, capsys, tmp_path, repo, hub, issues, says
    ):
        gh = hub(outside=[(7, "CLOSED")])
        code, data = report(capsys, repo, write_plan(tmp_path, *issues))
        assert code == cli.PROBLEMS
        assert any(says in e for e in data["errors"]), data["errors"]
        assert data["data"]["token"] is None
        assert gh.writes() == []

    @pytest.mark.spec("planreport-cmd-checks-plan-links")
    def it_refuses_a_reference_in_the_tracking_plan_to_nothing(self, capsys, tmp_path, repo, hub):
        hub()
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A"), plan="Start at {X}."))
        assert code == cli.PROBLEMS
        assert "the tracking issue's plan names {X}" in data["errors"][0]

    @pytest.mark.spec("planreport-cmd-checks-plan-links")
    def it_leaves_a_key_in_code_alone(self, capsys, tmp_path, repo, hub):
        hub()
        body = BODY + "Write `{KEY}` for an issue.\n\n```text\n{OTHER}\n```\n"
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A", body=body)))
        assert code == cli.OK, data["errors"]

    @pytest.mark.spec("planreport-cmd-checks-plan-links")
    def it_accepts_an_open_blocker_outside_the_plan(self, capsys, tmp_path, repo, hub):
        hub(outside=[(8, "OPEN")])
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A", 8)))
        assert code == cli.OK, data["errors"]


class DescribePlanReportOrder:
    @pytest.mark.spec("planreport-cmd-orders-by-links")
    def it_puts_each_issue_after_its_blockers_and_keeps_ties_in_listed_order(
        self, capsys, tmp_path, repo, hub
    ):
        hub(outside=[(8, "OPEN")])
        plan = write_plan(
            tmp_path,
            issue("D", "B"),
            issue("A"),
            issue("B", "C", 8, body=BODY + "After #{C}."),
            issue("C"),
            issue("E"),
        )
        code, data = report(capsys, repo, plan)
        assert code == cli.OK, data["errors"]
        assert data["data"]["order"] == ["A", "C", "B", "D", "E"]
        body = data["data"]["tracking"]["body"]
        assert body.startswith("**Claude:**\n\nDo the plan.\n\n## Order\n\n")
        assert body.endswith(
            "1. #{A} issue A\n"
            "2. #{C} issue C\n"
            "3. #{B} issue B, blocked by #{C}, #8\n"
            "4. #{D} issue D, blocked by #{B}\n"
            "5. #{E} issue E\n"
        )


class DescribePlanReportFile:
    @pytest.mark.spec(
        "planreport-cmd-writes-report-file", "command-splits-output-streams-without-json"
    )
    def it_writes_the_report_it_prints_and_ends_it_with_the_token(
        self, capsys, tmp_path, repo, hub
    ):
        hub()
        plan = write_plan(tmp_path, issue("A"), issue("B", "A", body=BODY + "After #{A}."))
        code, out = run(capsys, repo, "plan", "report", "--drafts", str(plan))
        assert code == cli.OK
        assert out.err == ""
        written = (repo / cli.PLAN_REPORT).read_text()
        assert written == out.out
        token = cli.approval_token(plan.read_bytes(), "o/r", sorted(LABELS))
        assert written.endswith("Approval token: `%s`\n" % token)
        assert "> After #{A}." in written
        assert "## 2. `B`: issue B" in written
        assert "- **Blocked by:** `A`" in written
        assert "> 1. #{A} issue A" in written

    @pytest.mark.spec(
        "planreport-cmd-writes-report-file", "command-splits-output-streams-without-json"
    )
    def it_writes_a_refused_report_with_its_faults_and_no_token(self, capsys, tmp_path, repo, hub):
        hub()
        plan = write_plan(tmp_path, issue("A", labels=("bug",)))
        code, out = run(capsys, repo, "plan", "report", "--drafts", str(plan))
        assert code == cli.PROBLEMS
        written = (repo / cli.PLAN_REPORT).read_text()
        assert written == out.out
        assert "## Refused" in written
        assert "token" not in written.lower()
        assert "carries 0 area labels" in out.err


def filed_plan(tmp_path):
    return write_plan(
        tmp_path,
        issue("B", "A", 8, body=BODY + "After #{A}, not `{A}`."),
        issue("A"),
        issue("C", labels=("docs", "plugin:todos")),
        plan="Start with {A}.",
    )


class DescribePlanFile:
    @pytest.mark.spec("planfile-cmd-files-in-order")
    def it_files_links_and_groups_the_plan_as_the_report_showed_it(
        self, capsys, tmp_path, repo, hub
    ):
        gh = hub(outside=[(8, "OPEN")])
        plan = filed_plan(tmp_path)
        token = token_for(capsys, repo, plan)
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.OK, data["errors"]
        a, b, c, t = 100, 101, 102, 103
        assert [(i["key"], i["number"]) for i in data["data"]["issues"]] == [
            ("A", a),
            ("B", b),
            ("C", c),
        ]
        assert gh.issues[b]["body"] == BODY + "After #100, not `{A}`."
        assert gh.issues[c]["labels"] == ["docs", "plugin:todos"]
        assert gh.blocked == {b: [8, a]}
        assert gh.issues[t]["labels"] == ["tracking"]
        assert gh.issues[t]["body"].startswith("**Claude:**\n\nStart with 100.\n\n## Order\n")
        assert "2. #101 issue B, blocked by #100, #8\n" in gh.issues[t]["body"]
        assert gh.subs == {t: [a, b, c]}
        assert data["data"]["tracking"]["url"] == "https://github.com/o/r/issues/103"

    @pytest.mark.spec("planfile-cmd-files-in-order", "command-splits-output-streams-without-json")
    def it_names_each_number_and_address_on_stdout(self, capsys, tmp_path, repo, hub):
        hub()
        plan = write_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == cli.OK
        assert out.err == ""
        assert out.out.splitlines() == [
            "filed #100 issue A  https://github.com/o/r/issues/100",
            "filed tracking issue #101 The plan  https://github.com/o/r/issues/101",
            "added #100 to #101",
        ]


class DescribePlanFiledIssue:
    @pytest.mark.spec("planreport-cmd-shows-filed-issue")
    def it_shows_an_issue_named_by_number_as_github_holds_it(self, capsys, tmp_path, repo, hub):
        gh = hub(outside=[(40, "OPEN")])
        plan = write_plan(tmp_path, issue("A"), {"key": "B", "number": 40, "blocked_by": ["A"]})
        code, data = report(capsys, repo, plan)
        assert code == cli.OK, data["errors"]
        shown = data["data"]["issues"][1]
        assert shown["number"] == 40
        assert shown["title"] == "old #40"
        assert shown["labels"] == ["bug", "repo"]
        assert shown["body"] == OLD_BODY
        assert data["data"]["numbers"] == {"B": 40}
        assert "2. #40 old #40, blocked by #{A}\n" in data["data"]["tracking"]["body"]
        written = (repo / cli.PLAN_REPORT).read_text()
        assert "## 2. `B`: old #40" in written
        assert "- **Filed already** as #40, before this plan." in written
        assert "> Filed by hand. See #{A}." in written
        assert "by an earlier run" not in written
        assert gh.writes() == []

    @pytest.mark.spec("planreport-cmd-shows-filed-issue")
    def it_lets_a_draft_name_a_filed_issue_listed_after_it(self, capsys, tmp_path, repo, hub):
        hub(outside=[(40, "OPEN")])
        plan = write_plan(
            tmp_path, issue("A", body=BODY + "Before #{B}."), {"key": "B", "number": 40}
        )
        code, data = report(capsys, repo, plan)
        assert code == cli.OK, data["errors"]
        assert "> Before #40." in (repo / cli.PLAN_REPORT).read_text()

    @pytest.mark.parametrize(
        ("issues", "says"),
        [
            (({"key": "A", "number": 7},), "`A` names #7, which is closed"),
            (({"key": "A", "number": 9},), "`A` names #9, which cannot be read"),
            (
                ({"key": "A", "number": 40}, {"key": "B", "number": 40}),
                "`A` and `B` both name #40",
            ),
            (
                ({"key": "A", "number": 40, "title": "new"},),
                "`A` names an issue filed already, so it takes only key, number, blocked_by, "
                "and has 'title'",
            ),
            (({"key": "A", "number": "40"},), "`A`'s number is not an issue number"),
            (({"key": "A", "number": 40, "blocked_by": "B"},), "`A`'s blocked_by is not a list"),
        ],
        ids=["closed", "missing", "twice", "draft-field", "not-a-number", "blockers"],
    )
    @pytest.mark.spec("planreport-cmd-shows-filed-issue")
    def it_refuses_a_number_it_cannot_group(self, capsys, tmp_path, repo, hub, issues, says):
        hub(outside=[(7, "CLOSED"), (40, "OPEN")])
        code, data = report(capsys, repo, write_plan(tmp_path, *issues))
        assert code == cli.PROBLEMS
        assert any(says in e for e in data["errors"]), data["errors"]
        assert data["data"]["token"] is None

    @pytest.mark.spec("planfile-cmd-groups-filed-issue")
    def it_links_and_groups_a_filed_issue_without_filing_it(self, capsys, tmp_path, repo, hub):
        gh = hub(outside=[(40, "OPEN")])
        plan = write_plan(
            tmp_path,
            {"key": "B", "number": 40, "blocked_by": ["A"]},
            issue("A"),
            issue("C", "B", body=BODY + "After #{B}."),
        )
        token = token_for(capsys, repo, plan)
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.OK, data["errors"]
        a, c, t = 100, 101, 102
        assert [(i["key"], i["number"], i["filed"]) for i in data["data"]["issues"]] == [
            ("A", a, True),
            ("B", 40, False),
            ("C", c, True),
        ]
        assert gh.issues[40]["body"] == OLD_BODY
        assert gh.issues[c]["body"] == BODY + "After #40."
        assert gh.blocked == {40: [a], c: [40]}
        assert gh.subs == {t: [a, 40, c]}
        assert "2. #40 old #40, blocked by #100\n" in gh.issues[t]["body"]
        ledger = json.loads((repo / cli.PLAN_LEDGER).read_text())
        assert sorted(ledger["issues"]) == ["A", "C"]
        assert ledger["complete"] is True

    @pytest.mark.spec("planfile-cmd-groups-filed-issue")
    def it_names_a_filed_issue_as_already_filed(self, capsys, tmp_path, repo, hub):
        hub(outside=[(40, "OPEN")])
        plan = write_plan(tmp_path, {"key": "A", "number": 40})
        token = token_for(capsys, repo, plan)
        code, dry = file_plan(capsys, repo, plan, token, "--dry-run")
        assert code == cli.OK, dry["errors"]
        assert dry["data"]["issues"][0]["number"] == 40
        assert dry["data"]["issues"][0]["filed"] is False
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == cli.OK
        assert out.out.splitlines() == [
            "already filed #40 old #40",
            "filed tracking issue #100 The plan  https://github.com/o/r/issues/100",
            "added #40 to #100",
        ]

    @pytest.mark.spec("planfile-cmd-groups-filed-issue")
    def it_names_a_filed_issue_github_lists_out_of_order(self, capsys, tmp_path, repo, hub):
        gh = hub(outside=[(40, "OPEN")])
        plan = write_plan(tmp_path, issue("A"), {"key": "B", "number": 40})
        token = token_for(capsys, repo, plan)
        gh.subs[101] = [40]
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.PROBLEMS
        assert (
            "#101 lists its sub-issues as #40, #100, and the plan's order is #100, #40"
            in (data["errors"][0])
        )


class DescribePlanFileToken:
    @pytest.mark.spec("planfile-cmd-requires-token")
    def it_files_nothing_with_a_token_that_does_not_match(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        code, data = file_plan(capsys, repo, plan, "0" * cli.TOKEN_LENGTH)
        assert code == cli.PROBLEMS
        assert data["errors"] == [cli.TOKEN_STALE]
        assert gh.writes() == []

    @pytest.mark.parametrize("change", ["plan", "labels"])
    @pytest.mark.spec("planfile-cmd-requires-token")
    def it_refuses_the_token_once_the_plan_or_the_repository_changes(
        self, capsys, tmp_path, repo, hub, change
    ):
        hub()
        plan = write_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        if change == "plan":
            write_plan(tmp_path, issue("A", title="another title"))
            gh = hub()
        else:
            gh = hub(labels=(*LABELS, "new"))
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.PROBLEMS
        assert data["errors"] == [cli.TOKEN_STALE]
        assert gh.writes() == []

    @pytest.mark.spec("planfile-cmd-requires-token")
    def it_checks_the_plan_again_before_filing(self, capsys, tmp_path, repo, hub):
        hub(outside=[(8, "OPEN")])
        plan = write_plan(tmp_path, issue("A", 8))
        token = token_for(capsys, repo, plan)
        gh = hub(outside=[(8, "CLOSED")])
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.PROBLEMS
        assert "`A` is blocked by #8, which is closed" in data["errors"]
        assert "nothing was filed" in data["errors"]
        assert gh.writes() == []

    @pytest.mark.spec("command-never-writes-in-preview")
    def it_files_nothing_on_a_dry_run(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        code, out = run(
            capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token, "--dry-run"
        )
        assert code == cli.OK
        assert out.out.splitlines() == [
            "would file issue A",
            "would file tracking issue The plan",
        ]
        assert gh.writes() == []
        assert not (repo / cli.PLAN_LEDGER).exists()


class DescribePlanFileReadBack:
    @pytest.mark.spec("planfile-cmd-verifies-links")
    def it_names_a_link_github_does_not_hold(self, capsys, tmp_path, repo, hub):
        hub(drop_link=101)
        plan = write_plan(tmp_path, issue("A"), issue("B", "A"))
        token = token_for(capsys, repo, plan)
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.PROBLEMS
        assert data["errors"] == ["#101 is blocked by nothing on GitHub, and the plan says #100"]

    @pytest.mark.spec("planfile-cmd-verifies-links")
    def it_names_sub_issues_out_of_the_plans_order(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"), issue("B"))
        token = token_for(capsys, repo, plan)
        real = gh.__call__

        def reordered(repo_, *args, stdin=None):
            out = real(repo_, *args, stdin=stdin)
            if args[:3] == ("api", "-X", "POST") and "sub_issues" in args[3]:
                gh.subs[102].sort(reverse=True)
            return out

        cli.gh = reordered
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.PROBLEMS
        assert data["errors"] == [
            "#102 lists its sub-issues as #101, #100, and the plan's order is #100, #101"
        ]


class DescribePlanFileResume:
    @pytest.mark.spec("planfile-cmd-resumes-after-failed-call")
    def it_stops_at_a_failed_call_and_files_only_the_rest_when_run_again(
        self, capsys, tmp_path, repo, hub
    ):
        gh = hub(outside=[(8, "OPEN")], fail_create=1)
        plan = filed_plan(tmp_path)
        token = token_for(capsys, repo, plan)
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == cli.PROBLEMS
        assert out.out == "filed #100 issue A  https://github.com/o/r/issues/100\n"
        assert "gh issue create failed. plan file stopped there" in out.err
        assert "run plan file again with the same plan and token to file the rest" in out.err
        assert list(gh.filed()) == [100]

        code, out = run(capsys, repo, "plan", "report", "--drafts", str(plan))
        assert code == cli.OK
        assert "- **Filed already** as #100" in out.out
        assert "> After #100, not `{A}`." in out.out

        gh.fail_create = None
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.OK, data["errors"]
        assert [i["filed"] for i in data["data"]["issues"]] == [False, True, True]
        assert sorted(gh.filed()) == [100, 101, 102, 103]
        assert gh.blocked == {101: [8, 100]}
        assert gh.subs == {103: [100, 101, 102]}

    @pytest.mark.spec("script-names-remedy-on-stop")
    def it_says_to_check_the_repository_when_it_cannot_read_an_address(
        self, capsys, tmp_path, repo, hub
    ):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"), issue("B"))
        token = token_for(capsys, repo, plan)
        real = gh.__call__

        def garbled(repo_, *args, stdin=None):
            out = real(repo_, *args, stdin=stdin)
            if args[:2] == ("issue", "create") and gh.creates == 2:
                return "Creating issue in o/r\n"
            return out

        cli.gh = garbled
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == cli.PROBLEMS
        assert sorted(gh.filed()) == [100, 101]
        assert "not an issue's address. plan file stopped there" in out.err
        assert "check the repository for it before running plan file again" in out.err
        assert "to file the rest" not in out.err

    @pytest.mark.spec("planfile-cmd-resumes-after-failed-call")
    def it_adds_only_the_links_and_sub_issues_github_lacks(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"), issue("B", "A"))
        token = token_for(capsys, repo, plan)
        real = gh.__call__
        failing = {"on": True}

        def fails_second_sub(repo_, *args, stdin=None):
            if failing["on"] and args[:3] == ("api", "-X", "POST") and gh.subs.get(102):
                raise cli.Fatal("gh api failed")
            return real(repo_, *args, stdin=stdin)

        cli.gh = fails_second_sub
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.PROBLEMS
        failing["on"] = False
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.OK, data["errors"]
        assert data["data"]["links"] == []
        assert data["data"]["sub_issues"] == [{"issue": 101, "tracking": 102}]
        assert gh.blocked == {101: [100]}
        assert gh.subs == {102: [100, 101]}

    @pytest.mark.spec("planfile-cmd-resumes-after-failed-call")
    def it_never_files_a_finished_plan_twice(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        assert file_plan(capsys, repo, plan, token)[0] == cli.OK
        before = len(gh.writes())
        code, data = file_plan(capsys, repo, plan, token)
        assert code == cli.PROBLEMS
        assert "this plan was filed already, under tracking issue #101" in data["errors"][0]
        assert len(gh.writes()) == before

    @pytest.mark.spec("planfile-cmd-resumes-after-failed-call")
    def it_warns_of_an_issue_filed_earlier_that_the_plan_dropped(self, capsys, tmp_path, repo, hub):
        gh = hub(fail_create=1)
        plan = write_plan(tmp_path, issue("A"), issue("B"))
        token = token_for(capsys, repo, plan)
        assert file_plan(capsys, repo, plan, token)[0] == cli.PROBLEMS
        plan = write_plan(tmp_path, issue("B"))
        gh.fail_create = None
        code, data = report(capsys, repo, plan)
        assert code == cli.OK
        assert data["warnings"] == [
            "`A` was filed as #100 by an earlier run of plan file and is not in this plan; "
            "it stays as it is, outside the tracking issue"
        ]

    @pytest.mark.spec("planfile-cmd-resumes-after-failed-call")
    def it_starts_a_new_plan_afresh_once_the_last_one_is_finished(
        self, capsys, tmp_path, repo, hub
    ):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        assert file_plan(capsys, repo, plan, token_for(capsys, repo, plan))[0] == cli.OK
        plan = write_plan(tmp_path, issue("A", title="a new plan"))
        code, data = file_plan(capsys, repo, plan, token_for(capsys, repo, plan))
        assert code == cli.OK, data["errors"]
        assert sorted(gh.filed()) == [100, 101, 102, 103]


class DescribePlanMain:
    @pytest.mark.parametrize("command", ["report", "file"])
    @pytest.mark.spec("command-prints-json-envelope")
    def it_prints_the_same_envelope_as_every_command(self, capsys, tmp_path, repo, hub, command):
        hub()
        plan = write_plan(tmp_path, issue("A"))
        _, data = run_json(
            capsys,
            repo,
            "plan",
            command,
            "--drafts",
            str(plan),
            *(["--token", "x"] if command == "file" else []),
        )
        assert set(data) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert data["command"] == "plan " + command

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_on_a_plan_that_is_not_json(self, capsys, tmp_path, repo, hub):
        hub()
        plan = tmp_path / "plan.json"
        plan.write_text("{not json")
        code, out = run(capsys, repo, "plan", "report", "--drafts", str(plan))
        assert code == cli.CANNOT_RUN
        assert out.err.startswith("issues.py: %s is not JSON" % plan)

"""flywheel.py plan turns one approved plan into issues, links and a tracking
issue. A filed issue cannot be counted on to come back, so the plan is checked
whole before the first call, filed only with the token of the report the owner
read, and read back once filed. gh is faked by a small GitHub that keeps the
issues, links and sub-issues it is given.
"""

import json
import subprocess
from pathlib import Path

import pytest

import flywheel

LABELS = (
    "bug",
    "enhancement",
    "documentation",
    "docs",
    "repo",
    "plugin:todos",
    "approved",
    "tracking",
)
BODY = (
    "**Claude:**\n\n## What's wrong\n\nIt breaks.\n\n## Evidence\n\nflywheel.py:1\n\n"
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
def repo(tmp_path, git_init):
    return git_init(tmp_path / "clone")


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
                raise flywheel.Fatal("no issue #%d" % number)
            return json.dumps(self.issues[number])
        if args[:2] == ("issue", "create"):
            index, self.creates = self.creates, self.creates + 1
            if index == self.fail_create:
                raise flywheel.Fatal("gh issue create failed")
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
        if args[:2] == ("issue", "close"):
            self.issues[int(args[2])]["state"] = "CLOSED"
            return ""
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
            # The REST API spells state in lower case, unlike gh issue view.
            return json.dumps(
                [
                    {"number": n, "state": self.issues.get(n, {}).get("state", "open").lower()}
                    for n in listed
                ]
            )
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
            c
            for c in self.calls
            if c[:2] in (("issue", "create"), ("issue", "close")) or c[:3] == ("api", "-X", "POST")
        ]


@pytest.fixture
def hub(monkeypatch):
    def install(**kwargs):
        fake = Hub(**kwargs)
        monkeypatch.setattr(flywheel, "gh", fake)
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
    code = flywheel.main([*argv, "-C", str(repo)])
    return code, capsys.readouterr()


def run_json(capsys, repo, *argv):
    code, out = run(capsys, repo, *argv, "--json")
    return code, json.loads(out.out)


def report(capsys, repo, plan):
    return run_json(capsys, repo, "plan", "report", "--drafts", str(plan))


def token_for(capsys, repo, plan):
    code, data = report(capsys, repo, plan)
    assert code == flywheel.OK, data["errors"]
    return data["data"]["token"]


def file_plan(capsys, repo, plan, token, *more):
    return run_json(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token, *more)


class DescribePlanDraft:
    @pytest.mark.spec("plandraft-cmd-makes-own-file")
    def it_makes_an_empty_file_in_the_temporary_directory(
        self, capsys, repo, monkeypatch, tmp_path
    ):
        temp = tmp_path / "temp"
        temp.mkdir()
        monkeypatch.setattr(flywheel.tempfile, "tempdir", str(temp))
        code, data = run_json(capsys, repo, "plan", "draft")
        assert code == flywheel.OK
        path = Path(data["data"]["path"])
        assert path.parent == temp
        assert path.name.startswith("plan-")
        assert path.suffix == ".json"
        assert path.read_bytes() == b""

    @pytest.mark.spec("plandraft-cmd-makes-own-file")
    def it_gives_each_run_a_file_of_its_own(self, capsys, repo, monkeypatch, tmp_path):
        monkeypatch.setattr(flywheel.tempfile, "tempdir", str(tmp_path))
        paths = {run(capsys, repo, "plan", "draft")[1].out.strip() for _ in range(5)}
        assert len(paths) == 5
        assert all(Path(p).is_file() for p in paths)

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
    def it_stops_when_the_temporary_directory_cannot_take_a_file(
        self, capsys, repo, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(flywheel.tempfile, "tempdir", str(tmp_path / "missing"))
        code, out = run(capsys, repo, "plan", "draft")
        assert code == flywheel.CANNOT_RUN
        assert out.out == ""
        assert out.err.startswith("flywheel.py: cannot make a file for the plan in ")
        assert "Set TMPDIR" in out.err


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
            (
                issue("A", labels=("bug", "documentation", "repo")),
                "carries 2 kind labels (bug, documentation)",
            ),
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
        assert code == flywheel.PROBLEMS
        assert any(says in e and e.startswith("`A`") for e in data["errors"]), data["errors"]
        assert not any(e.startswith("`B`") for e in data["errors"])
        assert data["data"]["token"] is None
        assert gh.writes() == []

    @pytest.mark.spec("planreport-cmd-checks-each-draft", "repo:script-checks-every-answer")
    def it_names_every_fault_in_one_run(self, capsys, tmp_path, repo, hub):
        hub()
        plan = write_plan(
            tmp_path,
            issue("A", labels=("approved",), body="no opening"),
            {"key": "B", "title": "", "body": BODY, "labels": ["bug", "repo"], "color": "red"},
            "not an issue",
        )
        code, data = report(capsys, repo, plan)
        assert code == flywheel.PROBLEMS
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
        assert code == flywheel.OK
        assert data["errors"] == []
        assert data["data"]["issues"][0]["labels"] == ["bug", "plugin:todos"]
        assert len(data["data"]["token"]) == flywheel.TOKEN_LENGTH


class DescribePlanReportSplitLines:
    @pytest.mark.spec("repo:planreport-cmd-refuses-split-lines")
    def it_names_each_line_that_continues_a_paragraph(self, capsys, tmp_path, repo, hub):
        hub()
        body = BODY.replace("It breaks.", "It\nbreaks\nbadly.")
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A", body=body), issue("B")))
        assert code == flywheel.PROBLEMS
        assert data["data"]["token"] is None
        lines = body.splitlines()
        named = [int(e.split("line ")[1].split()[0]) for e in data["errors"]]
        assert [lines[n - 1] for n in named] == ["breaks", "badly."]
        assert all(e.startswith("`A`'s body: line") for e in data["errors"])
        assert "join the line to the one above" in data["errors"][0]

    @pytest.mark.spec("repo:planreport-cmd-refuses-split-lines")
    def it_names_a_line_that_continues_a_list_item_of_the_plan(self, capsys, tmp_path, repo, hub):
        hub()
        plan = "Fix it.\n\n- first\n  still first\n- second\n"
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A"), plan=plan))
        assert code == flywheel.PROBLEMS
        assert data["errors"] == [
            "the tracking issue's plan: line 4 continues the paragraph or list item above it. "
            "GitHub renders the newline as a line break, so join the line to the one above"
        ]

    @pytest.mark.spec("repo:planreport-cmd-refuses-split-lines")
    @pytest.mark.parametrize(
        "block",
        [
            "- one\n- two\n  - nested\n1. three\n2) four\n",
            "| a | b |\n|---|---|\n| 1 | 2 |\n",
            "> quoted\n> still quoted\n",
            "<details>\n<summary>more</summary>\n</details>\n",
            "Text\n---\n",
            "Text\n===\n",
            "```sh\npython3 x.py\n  --json\n```\n",
            "<!--\nnote\nmore note\n-->\n",
            "Text\n\n    code line\n    more code\n\n    still code\n",
            "Text\n<!-- spec: x -->\n",
            "Text\n### Heading\nText\n",
        ],
    )
    def it_passes_lines_that_github_does_not_join(self, capsys, tmp_path, repo, hub, block):
        hub()
        body = BODY + "\n" + block
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A", body=body), plan=block))
        assert code == flywheel.OK, data["errors"]

    @pytest.mark.spec("repo:planreport-cmd-refuses-split-lines")
    def it_names_the_line_the_author_wrote_after_a_long_comment(self, capsys, tmp_path, repo, hub):
        hub()
        body = BODY.replace("It breaks.", "<!--\none\ntwo\n-->\nIt\nbreaks.")
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A", body=body)))
        assert code == flywheel.PROBLEMS
        assert body.splitlines()[9] == "breaks."
        assert "line 10 continues" in data["errors"][0]

    @pytest.mark.spec("repo:planreport-cmd-refuses-split-lines")
    def it_does_not_check_an_issue_filed_already(self, capsys, tmp_path, repo, hub):
        gh = hub(outside=[(40, "OPEN")])
        gh.issues[40]["body"] = "Filed\nby hand.\n"
        plan = write_plan(tmp_path, {"key": "A", "number": 40})
        code, data = report(capsys, repo, plan)
        assert code == flywheel.OK, data["errors"]


class DescribePlanReportLinks:
    @pytest.mark.parametrize(
        ("issues", "says"),
        [
            ((issue("A"), issue("A")), "the key `A` names more than one issue"),
            ((issue("A", body=BODY + "\nSee #{Z}."),), "`A`'s body names {Z}, and no issue"),
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
                (issue("A", body=BODY + "\nThen #{B}."), issue("B")),
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
        assert code == flywheel.PROBLEMS
        assert any(says in e for e in data["errors"]), data["errors"]
        assert data["data"]["token"] is None
        assert gh.writes() == []

    @pytest.mark.spec("planreport-cmd-checks-plan-links")
    def it_refuses_a_reference_in_the_tracking_plan_to_nothing(self, capsys, tmp_path, repo, hub):
        hub()
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A"), plan="Start at {X}."))
        assert code == flywheel.PROBLEMS
        assert "the tracking issue's plan names {X}" in data["errors"][0]

    @pytest.mark.spec("planreport-cmd-checks-plan-links")
    def it_leaves_a_key_in_code_alone(self, capsys, tmp_path, repo, hub):
        hub()
        body = BODY + "\nWrite `{KEY}` for an issue.\n\n```text\n{OTHER}\n```\n"
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A", body=body)))
        assert code == flywheel.OK, data["errors"]

    @pytest.mark.spec("planreport-cmd-checks-plan-links")
    def it_accepts_an_open_blocker_outside_the_plan(self, capsys, tmp_path, repo, hub):
        hub(outside=[(8, "OPEN")])
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A", 8)))
        assert code == flywheel.OK, data["errors"]


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
            issue("B", "C", 8, body=BODY + "\nAfter #{C}."),
            issue("C"),
            issue("E"),
        )
        code, data = report(capsys, repo, plan)
        assert code == flywheel.OK, data["errors"]
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
        "repo:planreport-cmd-writes-report-file", "repo:command-splits-output-streams-without-json"
    )
    def it_writes_the_report_it_prints_and_ends_it_with_the_token(
        self, capsys, tmp_path, repo, hub
    ):
        hub()
        plan = write_plan(tmp_path, issue("A"), issue("B", "A", body=BODY + "\nAfter #{A}."))
        code, out = run(capsys, repo, "plan", "report", "--drafts", str(plan))
        assert code == flywheel.OK
        assert out.err == ""
        written = (repo / flywheel.PLAN_REPORT).read_text()
        assert written == out.out
        token = flywheel.approval_token(plan.read_bytes(), "o/r", sorted(LABELS))
        assert written.endswith("Approval token: `%s`\n" % token)
        assert "> After #{A}." in written
        assert "## 2. `B`: issue B" in written
        assert "- **Blocked by:** `A`" in written
        assert "> 1. #{A} issue A" in written

    @pytest.mark.spec(
        "repo:planreport-cmd-writes-report-file", "repo:command-splits-output-streams-without-json"
    )
    def it_writes_a_refused_report_with_its_faults_and_no_token(self, capsys, tmp_path, repo, hub):
        hub()
        plan = write_plan(tmp_path, issue("A", labels=("repo",)))
        code, out = run(capsys, repo, "plan", "report", "--drafts", str(plan))
        assert code == flywheel.PROBLEMS
        written = (repo / flywheel.PLAN_REPORT).read_text()
        assert written == out.out
        assert "## Refused" in written
        assert "token" not in written.lower()
        assert "carries 0 kind labels" in out.err


def filed_plan(tmp_path):
    return write_plan(
        tmp_path,
        issue("B", "A", 8, body=BODY + "\nAfter #{A}, not `{A}`."),
        issue("A"),
        issue("C", labels=("documentation", "plugin:todos")),
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
        assert code == flywheel.OK, data["errors"]
        a, b, c, t = 100, 101, 102, 103
        assert [(i["key"], i["number"]) for i in data["data"]["issues"]] == [
            ("A", a),
            ("B", b),
            ("C", c),
        ]
        assert gh.issues[b]["body"] == BODY + "\nAfter #100, not `{A}`."
        assert gh.issues[c]["labels"] == ["documentation", "plugin:todos"]
        assert gh.blocked == {b: [8, a]}
        assert gh.issues[t]["labels"] == ["tracking"]
        assert gh.issues[t]["body"].startswith("**Claude:**\n\nStart with 100.\n\n## Order\n")
        assert "2. #101 issue B, blocked by #100, #8\n" in gh.issues[t]["body"]
        assert gh.subs == {t: [a, b, c]}
        assert data["data"]["tracking"]["url"] == "https://github.com/o/r/issues/103"

    @pytest.mark.spec(
        "planfile-cmd-files-in-order", "repo:command-splits-output-streams-without-json"
    )
    def it_names_each_number_and_address_on_stdout(self, capsys, tmp_path, repo, hub):
        hub()
        plan = write_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == flywheel.OK
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
        assert code == flywheel.OK, data["errors"]
        shown = data["data"]["issues"][1]
        assert shown["number"] == 40
        assert shown["title"] == "old #40"
        assert shown["labels"] == ["bug", "repo"]
        assert shown["body"] == OLD_BODY
        assert data["data"]["numbers"] == {"B": 40}
        assert "2. #40 old #40, blocked by #{A}\n" in data["data"]["tracking"]["body"]
        written = (repo / flywheel.PLAN_REPORT).read_text()
        assert "## 2. `B`: old #40" in written
        assert "- **Filed already** as #40, before this plan." in written
        assert "> Filed by hand. See #{A}." in written
        assert "by an earlier run" not in written
        assert gh.writes() == []

    @pytest.mark.spec("planreport-cmd-shows-filed-issue")
    def it_lets_a_draft_name_a_filed_issue_listed_after_it(self, capsys, tmp_path, repo, hub):
        hub(outside=[(40, "OPEN")])
        plan = write_plan(
            tmp_path, issue("A", body=BODY + "\nBefore #{B}."), {"key": "B", "number": 40}
        )
        code, data = report(capsys, repo, plan)
        assert code == flywheel.OK, data["errors"]
        assert "> Before #40." in (repo / flywheel.PLAN_REPORT).read_text()

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
        assert code == flywheel.PROBLEMS
        assert any(says in e for e in data["errors"]), data["errors"]
        assert data["data"]["token"] is None

    @pytest.mark.spec("planfile-cmd-groups-filed-issue")
    def it_links_and_groups_a_filed_issue_without_filing_it(self, capsys, tmp_path, repo, hub):
        gh = hub(outside=[(40, "OPEN")])
        plan = write_plan(
            tmp_path,
            {"key": "B", "number": 40, "blocked_by": ["A"]},
            issue("A"),
            issue("C", "B", body=BODY + "\nAfter #{B}."),
        )
        token = token_for(capsys, repo, plan)
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.OK, data["errors"]
        a, c, t = 100, 101, 102
        assert [(i["key"], i["number"], i["filed"]) for i in data["data"]["issues"]] == [
            ("A", a, True),
            ("B", 40, False),
            ("C", c, True),
        ]
        assert gh.issues[40]["body"] == OLD_BODY
        assert gh.issues[c]["body"] == BODY + "\nAfter #40."
        assert gh.blocked == {40: [a], c: [40]}
        assert gh.subs == {t: [a, 40, c]}
        assert "2. #40 old #40, blocked by #100\n" in gh.issues[t]["body"]
        ledger = json.loads((repo / flywheel.PLAN_LEDGER).read_text())
        assert sorted(ledger["issues"]) == ["A", "C"]
        assert ledger["complete"] is True

    @pytest.mark.spec("planfile-cmd-groups-filed-issue")
    def it_names_a_filed_issue_as_already_filed(self, capsys, tmp_path, repo, hub):
        hub(outside=[(40, "OPEN")])
        plan = write_plan(tmp_path, {"key": "A", "number": 40})
        token = token_for(capsys, repo, plan)
        code, dry = file_plan(capsys, repo, plan, token, "--dry-run")
        assert code == flywheel.OK, dry["errors"]
        assert dry["data"]["issues"][0]["number"] == 40
        assert dry["data"]["issues"][0]["filed"] is False
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == flywheel.OK
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
        assert code == flywheel.PROBLEMS
        assert (
            "#101 lists its sub-issues as #40, #100, and the plan's order is #100, #40"
            in (data["errors"][0])
        )


class DescribePlanFileToken:
    @pytest.mark.spec("planfile-cmd-requires-token")
    def it_files_nothing_with_a_token_that_does_not_match(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        code, data = file_plan(capsys, repo, plan, "0" * flywheel.TOKEN_LENGTH)
        assert code == flywheel.PROBLEMS
        assert data["errors"] == [flywheel.TOKEN_STALE]
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
        assert code == flywheel.PROBLEMS
        assert data["errors"] == [flywheel.TOKEN_STALE]
        assert gh.writes() == []

    @pytest.mark.spec("planfile-cmd-requires-token")
    def it_checks_the_plan_again_before_filing(self, capsys, tmp_path, repo, hub):
        hub(outside=[(8, "OPEN")])
        plan = write_plan(tmp_path, issue("A", 8))
        token = token_for(capsys, repo, plan)
        gh = hub(outside=[(8, "CLOSED")])
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.PROBLEMS
        assert "`A` is blocked by #8, which is closed" in data["errors"]
        assert "nothing was filed" in data["errors"]
        assert gh.writes() == []

    @pytest.mark.spec("repo:command-never-writes-in-preview")
    def it_files_nothing_on_a_dry_run(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        code, out = run(
            capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token, "--dry-run"
        )
        assert code == flywheel.OK
        assert out.out.splitlines() == [
            "would file issue A",
            "would file tracking issue The plan",
        ]
        assert gh.writes() == []
        assert not (repo / flywheel.PLAN_LEDGER).exists()


class DescribePlanFileReadBack:
    @pytest.mark.spec("planfile-cmd-verifies-links")
    def it_names_a_link_github_does_not_hold(self, capsys, tmp_path, repo, hub):
        hub(drop_link=101)
        plan = write_plan(tmp_path, issue("A"), issue("B", "A"))
        token = token_for(capsys, repo, plan)
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.PROBLEMS
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

        flywheel.gh = reordered
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.PROBLEMS
        assert data["errors"] == [
            "#102 lists its sub-issues as #101, #100, and the plan's order is #100, #101"
        ]


class DescribePlanFileResume:
    @pytest.mark.spec("repo:planfile-cmd-resumes-after-failed-call")
    def it_stops_at_a_failed_call_and_files_only_the_rest_when_run_again(
        self, capsys, tmp_path, repo, hub
    ):
        gh = hub(outside=[(8, "OPEN")], fail_create=1)
        plan = filed_plan(tmp_path)
        token = token_for(capsys, repo, plan)
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == flywheel.PROBLEMS
        assert out.out == "filed #100 issue A  https://github.com/o/r/issues/100\n"
        assert "gh issue create failed. plan file stopped there" in out.err
        assert "run plan file again with the same plan and token to file the rest" in out.err
        assert list(gh.filed()) == [100]

        code, out = run(capsys, repo, "plan", "report", "--drafts", str(plan))
        assert code == flywheel.OK
        assert "- **Filed already** as #100" in out.out
        assert "> After #100, not `{A}`." in out.out

        gh.fail_create = None
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.OK, data["errors"]
        assert [i["filed"] for i in data["data"]["issues"]] == [False, True, True]
        assert sorted(gh.filed()) == [100, 101, 102, 103]
        assert gh.blocked == {101: [8, 100]}
        assert gh.subs == {103: [100, 101, 102]}

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
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

        flywheel.gh = garbled
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == flywheel.PROBLEMS
        assert sorted(gh.filed()) == [100, 101]
        assert "not an issue's address. plan file stopped there" in out.err
        assert "check the repository for it before running plan file again" in out.err
        assert "to file the rest" not in out.err

    @pytest.mark.spec("repo:planfile-cmd-resumes-after-failed-call")
    def it_adds_only_the_links_and_sub_issues_github_lacks(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"), issue("B", "A"))
        token = token_for(capsys, repo, plan)
        real = gh.__call__
        failing = {"on": True}

        def fails_second_sub(repo_, *args, stdin=None):
            if failing["on"] and args[:3] == ("api", "-X", "POST") and gh.subs.get(102):
                raise flywheel.Fatal("gh api failed")
            return real(repo_, *args, stdin=stdin)

        flywheel.gh = fails_second_sub
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.PROBLEMS
        failing["on"] = False
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.OK, data["errors"]
        assert data["data"]["links"] == []
        assert data["data"]["sub_issues"] == [{"issue": 101, "tracking": 102}]
        assert gh.blocked == {101: [100]}
        assert gh.subs == {102: [100, 101]}

    @pytest.mark.spec("repo:planfile-cmd-resumes-after-failed-call")
    def it_never_files_a_finished_plan_twice(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        assert file_plan(capsys, repo, plan, token)[0] == flywheel.OK
        before = len(gh.writes())
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.PROBLEMS
        assert "this plan was filed already, under tracking issue #101" in data["errors"][0]
        assert len(gh.writes()) == before

    @pytest.mark.spec("repo:planfile-cmd-resumes-after-failed-call")
    def it_warns_of_an_issue_filed_earlier_that_the_plan_dropped(self, capsys, tmp_path, repo, hub):
        gh = hub(fail_create=1)
        plan = write_plan(tmp_path, issue("A"), issue("B"))
        token = token_for(capsys, repo, plan)
        assert file_plan(capsys, repo, plan, token)[0] == flywheel.PROBLEMS
        plan = write_plan(tmp_path, issue("B"))
        gh.fail_create = None
        code, data = report(capsys, repo, plan)
        assert code == flywheel.OK
        assert data["warnings"] == [
            "`A` was filed as #100 by an earlier run of plan file and is not in this plan; "
            "it stays as it is, outside the tracking issue"
        ]

    @pytest.mark.spec("repo:planfile-cmd-resumes-after-failed-call")
    def it_starts_a_new_plan_afresh_once_the_last_one_is_finished(
        self, capsys, tmp_path, repo, hub
    ):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        assert file_plan(capsys, repo, plan, token_for(capsys, repo, plan))[0] == flywheel.OK
        plan = write_plan(tmp_path, issue("A", title="a new plan"))
        code, data = file_plan(capsys, repo, plan, token_for(capsys, repo, plan))
        assert code == flywheel.OK, data["errors"]
        assert sorted(gh.filed()) == [100, 101, 102, 103]


class DescribePlanMain:
    @pytest.mark.parametrize("command", ["report", "file"])
    @pytest.mark.spec("repo:command-prints-json-envelope")
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

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    def it_cannot_run_on_a_plan_that_is_not_json(self, capsys, tmp_path, repo, hub):
        hub()
        plan = tmp_path / "plan.json"
        plan.write_text("{not json")
        code, out = run(capsys, repo, "plan", "report", "--drafts", str(plan))
        assert code == flywheel.CANNOT_RUN
        assert out.err.startswith("flywheel.py: %s is not JSON" % plan)


def tracking_issue(hub_, number, *labels, state="OPEN", subs=()):
    """Put tracking issue #number, and each sub-issue as (number, state), in hub_."""
    hub_.issues[number] = {
        "number": number,
        "title": "plan %d" % number,
        "state": state,
        "labels": [{"name": n} for n in labels],
        "comments": [],
    }
    for n, st in subs:
        hub_.issues[n] = {"number": n, "title": "issue %d" % n, "state": st, "labels": []}
    hub_.subs[number] = [n for n, _ in subs]


class DescribePlanClose:
    @pytest.mark.spec("planclose-cmd-closes-finished-plan")
    def it_closes_a_plan_whose_sub_issues_are_all_closed(self, capsys, repo, hub):
        gh = hub()
        tracking_issue(gh, 20, "approved", "tracking", subs=[(12, "CLOSED"), (11, "CLOSED")])
        code, out = run(capsys, repo, "plan", "close", "20")
        assert code == flywheel.OK
        assert (out.out, out.err) == ("Closed #20. Every sub-issue is closed: #12, #11.\n", "")
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
    def it_refuses_while_any_sub_issue_is_open(self, capsys, repo, hub):
        gh = hub()
        tracking_issue(
            gh, 20, "approved", "tracking", subs=[(11, "CLOSED"), (12, "OPEN"), (13, "OPEN")]
        )
        code, data = run_json(capsys, repo, "plan", "close", "20")
        assert code == flywheel.PROBLEMS
        assert "#20 still has open sub-issues: #12, #13" in data["errors"][0]
        assert "flywheel.py claim --next --tracking 20" in data["errors"][0]
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
        self, capsys, repo, hub, labels, state, says
    ):
        gh = hub()
        tracking_issue(gh, 20, *labels, state=state)
        code, out = run(capsys, repo, "plan", "close", "20")
        assert code == flywheel.PROBLEMS
        assert says in out.err
        assert gh.writes() == []
        assert not any(c[0] == "api" for c in gh.calls)

    @pytest.mark.spec("planclose-cmd-closes-finished-plan")
    def it_refuses_a_plan_without_sub_issues(self, capsys, repo, hub):
        gh = hub()
        tracking_issue(gh, 20, "approved", "tracking")
        code, out = run(capsys, repo, "plan", "close", "20")
        assert code == flywheel.PROBLEMS
        assert "#20 has no sub-issues" in out.err
        assert gh.writes() == []


def one_issue_plan(tmp_path, *issues):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"issues": list(issues)}))
    return path


@pytest.mark.spec("planreport-cmd-accepts-one-issue")
class DescribeOneIssuePlan:
    def it_reports_the_issue_alone(self, capsys, tmp_path, repo, hub):
        gh = hub()
        code, data = report(capsys, repo, one_issue_plan(tmp_path, issue("A")))
        assert code == flywheel.OK, data["errors"]
        assert data["data"]["order"] == ["A"]
        assert data["data"]["tracking"] is None
        written = (repo / flywheel.PLAN_REPORT).read_text()
        assert "## 1. `A`: issue A" in written
        assert "Tracking issue" not in written
        assert "1 issue(s), without a tracking issue." in written
        assert gh.writes() == []

    def it_files_the_issue_without_a_tracking_issue(self, capsys, tmp_path, repo, hub):
        gh = hub(outside=[(8, "OPEN")])
        plan = one_issue_plan(tmp_path, issue("A", 8))
        token = token_for(capsys, repo, plan)
        code, out = run(capsys, repo, "plan", "file", "--drafts", str(plan), "--token", token)
        assert code == flywheel.OK, out.err
        assert out.out.splitlines() == [
            "filed #100 issue A  https://github.com/o/r/issues/100",
            "linked #100, blocked by #8",
        ]
        assert list(gh.filed()) == [100]
        assert gh.blocked == {100: [8]}
        assert gh.subs == {}
        ledger = json.loads((repo / flywheel.PLAN_LEDGER).read_text())
        assert (ledger["tracking"], ledger["complete"]) == (None, True)

    def it_says_on_a_dry_run_that_it_files_no_tracking_issue(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = one_issue_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        code, data = file_plan(capsys, repo, plan, token, "--dry-run")
        assert code == flywheel.OK, data["errors"]
        assert data["data"]["tracking"] is None
        assert [i["key"] for i in data["data"]["issues"]] == ["A"]
        assert gh.writes() == []

    def it_never_files_the_issue_twice(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = one_issue_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        assert file_plan(capsys, repo, plan, token)[0] == flywheel.OK
        code, data = file_plan(capsys, repo, plan, token)
        assert code == flywheel.PROBLEMS
        assert data["errors"][0].startswith("this plan was filed already; nothing is left")
        assert list(gh.filed()) == [100]

    def it_refuses_a_plan_of_several_issues_without_a_tracking_issue(
        self, capsys, tmp_path, repo, hub
    ):
        hub()
        code, data = report(capsys, repo, one_issue_plan(tmp_path, issue("A"), issue("B")))
        assert code == flywheel.PROBLEMS
        assert (
            'the plan\'s "tracking" is not an object with a "title" and a "plan"'
            in (data["errors"])
        )
        assert data["data"]["token"] is None


class DescribePlanFolder:
    @pytest.mark.spec("repo:planreport-cmd-writes-report-file")
    def it_keeps_what_it_writes_out_of_every_commit(self, capsys, tmp_path, repo, hub):
        hub()
        report(capsys, repo, write_plan(tmp_path, issue("A")))
        assert (repo / flywheel.PLAN_IGNORE).read_text() == "*\n"
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert status == ""


class DescribePlanReportShape:
    @pytest.mark.spec("planreport-cmd-checks-each-draft")
    @pytest.mark.parametrize(
        ("plan", "says"),
        [
            (["not", "an", "object"], "the plan is not a JSON object"),
            (
                {"issues": [issue("A")], "extra": 1},
                "the plan has 'extra', which is not one of issues, tracking",
            ),
            ({"issues": []}, 'the plan\'s "issues" is not a list holding at least one issue'),
            (
                {"issues": [issue("A")], "tracking": {"title": "T", "plan": "P", "x": 1}},
                "the tracking issue has 'x', which is not one of title, plan",
            ),
            (
                {"issues": [{"title": "t", "body": BODY, "labels": ["bug", "repo"]}]},
                "issue 1 has no key, or one that is not a letter",
            ),
            (
                {"issues": [{"key": "A", "title": "t", "body": 7, "labels": ["bug", "repo"]}]},
                "`A` has no body",
            ),
            (
                {"issues": [{"key": "A", "title": "t", "body": BODY, "labels": "bug"}]},
                "`A`'s labels are not a list of names",
            ),
        ],
        ids=[
            "not-object",
            "extra-key",
            "no-issues",
            "tracking-field",
            "no-key",
            "no-body",
            "labels",
        ],
    )
    def it_refuses_a_plan_of_the_wrong_shape(self, capsys, tmp_path, repo, hub, plan, says):
        hub()
        path = tmp_path / "plan.json"
        path.write_text(json.dumps(plan))
        code, data = report(capsys, repo, path)
        assert code == flywheel.PROBLEMS
        assert any(says in e for e in data["errors"]), data["errors"]
        assert data["data"]["token"] is None

    @pytest.mark.spec("planreport-cmd-orders-by-links")
    def it_names_a_blocker_once_however_often_the_plan_repeats_it(
        self, capsys, tmp_path, repo, hub
    ):
        hub()
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A"), issue("B", "A", "A")))
        assert code == flywheel.OK, data["errors"]
        assert data["data"]["issues"][1]["blocked_by"] == ["A"]

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
    def it_cannot_run_on_a_plan_file_it_cannot_read(self, capsys, tmp_path, repo, hub):
        hub()
        code, out = run(capsys, repo, "plan", "report", "--drafts", str(tmp_path / "gone.json"))
        assert code == flywheel.CANNOT_RUN
        assert out.err.startswith("flywheel.py: cannot read %s" % (tmp_path / "gone.json"))


class DescribePlanRecord:
    @pytest.mark.spec("repo:planfile-cmd-resumes-after-failed-call")
    def it_shows_a_tracking_issue_an_earlier_run_filed(self, capsys, tmp_path, repo, hub):
        gh = hub()
        plan = write_plan(tmp_path, issue("A"))
        token = token_for(capsys, repo, plan)
        real = gh.__call__

        def fails_sub_issue(repo_, *args, stdin=None):
            if args[:3] == ("api", "-X", "POST") and "sub_issues" in args[3]:
                raise flywheel.Fatal("gh api failed")
            return real(repo_, *args, stdin=stdin)

        flywheel.gh = fails_sub_issue
        assert file_plan(capsys, repo, plan, token)[0] == flywheel.PROBLEMS
        code, data = report(capsys, repo, plan)
        assert code == flywheel.OK, data["errors"]
        assert data["data"]["tracking"]["number"] == 101
        written = (repo / flywheel.PLAN_REPORT).read_text()
        assert "- **Filed already** as #101, by an earlier run." in written

    @pytest.mark.spec("repo:planfile-cmd-resumes-after-failed-call")
    def it_starts_afresh_on_a_record_for_another_repository(self, capsys, tmp_path, repo, hub):
        hub()
        ledger = flywheel.empty_ledger("other/repo")
        ledger["issues"]["A"] = {"number": 5, "title": "issue A", "url": "u"}
        (repo / flywheel.PLAN_DIR).mkdir(parents=True)
        (repo / flywheel.PLAN_LEDGER).write_text(json.dumps(ledger))
        code, data = report(capsys, repo, write_plan(tmp_path, issue("A")))
        assert code == flywheel.OK, data["errors"]
        assert data["data"]["numbers"] == {}

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
    def it_stops_on_a_record_it_cannot_read(self, capsys, tmp_path, repo, hub):
        hub()
        (repo / flywheel.PLAN_DIR).mkdir(parents=True)
        (repo / flywheel.PLAN_LEDGER).write_text("{not json")
        code, out = run(
            capsys, repo, "plan", "report", "--drafts", str(write_plan(tmp_path, issue("A")))
        )
        assert code == flywheel.CANNOT_RUN
        assert "cannot read %s" % flywheel.PLAN_LEDGER in out.err
        assert "ask the owner before removing it" in out.err


def mapped(repo):
    """The clone at repo, whose own labels play the loop's roles."""
    (repo / ".flywheel").mkdir(exist_ok=True)
    roles = {"approval": "ready", "plan": "epic", "claim": "flywheel-claim", "repo-area": "general"}
    (repo / ".flywheel" / "labels.json").write_text(
        json.dumps({"roles": roles, "areas": {"plugin:*": "One plugin"}})
    )
    return repo


class DescribeMappedPlanLabels:
    @pytest.mark.spec("labelsfile-maps-roles", "planreport-cmd-checks-each-draft")
    def it_checks_each_draft_against_the_mapped_labels(self, capsys, tmp_path, repo, hub):
        hub(labels=(*LABELS, "ready", "epic", "general"))
        plan = write_plan(
            tmp_path,
            issue("A", labels=("bug", "general", "ready")),
            issue("B", labels=("bug", "general", "epic")),
            issue("C", labels=("bug", "repo")),
            issue("D", labels=("bug", "general", "approved", "tracking")),
        )
        code, data = report(capsys, mapped(repo), plan)
        assert code == flywheel.PROBLEMS
        assert data["data"]["token"] is None
        assert data["errors"] == [
            "`A` carries `ready`, which only the owner adds",
            "`B` carries `epic`, which only the tracking issue carries",
            "`C` carries 0 area labels; it takes exactly one, from `plugin:*` or `general`",
        ]

    @pytest.mark.spec("labelsfile-maps-roles", "planfile-cmd-files-in-order")
    def it_files_the_tracking_issue_with_the_mapped_plan_label(self, capsys, tmp_path, repo, hub):
        gh = hub(labels=(*LABELS, "ready", "epic", "general"))
        repo = mapped(repo)
        plan = write_plan(
            tmp_path,
            issue("A", labels=("bug", "general")),
            issue("B", labels=("documentation", "general")),
        )
        code, data = report(capsys, repo, plan)
        assert code == flywheel.OK, data["errors"]
        assert data["data"]["tracking"]["labels"] == ["epic"]
        assert "- **Labels:** epic\n" in (repo / flywheel.PLAN_REPORT).read_text()
        code, data = file_plan(capsys, repo, plan, data["data"]["token"])
        assert code == flywheel.OK, data["errors"]
        assert gh.issues[102]["labels"] == ["epic"]


def ruled(repo, labels=None, template=None):
    """The clone at repo, with labels as its .flywheel/labels.json and template
    as its .flywheel/issue-template.md."""
    (repo / ".flywheel").mkdir(exist_ok=True)
    if labels is not None:
        (repo / flywheel.LABELS_FILE).write_text(json.dumps(labels))
    if template is not None:
        (repo / flywheel.TEMPLATE_FILE).write_text(template)
    return repo


AREAS = {"plugin:*": "One plugin", "web": "The web app"}


class DescribeIssueRules:
    @pytest.mark.spec("labelsfile-sets-kinds-areas", "planreport-cmd-checks-each-draft")
    def it_takes_githubs_kinds_and_needs_no_area_without_the_labels_file(
        self, capsys, tmp_path, repo, hub
    ):
        hub()
        plan = write_plan(
            tmp_path,
            issue("A", labels=("documentation",)),
            issue("B", labels=("bug", "repo")),
            issue("C", labels=("docs",)),
        )
        code, data = report(capsys, repo, plan)
        assert code == flywheel.PROBLEMS
        assert data["errors"] == [
            "`C` carries 0 kind labels; it takes exactly one, from bug, enhancement or"
            " documentation"
        ]

    @pytest.mark.spec("labelsfile-sets-kinds-areas", "planreport-cmd-checks-each-draft")
    def it_checks_each_draft_against_the_kinds_and_areas_the_file_gives(
        self, capsys, tmp_path, repo, hub
    ):
        hub(labels=(*LABELS, "web"))
        ruled(repo, {"kinds": {"bug": "", "docs": ""}, "areas": AREAS})
        plan = write_plan(
            tmp_path,
            issue("A", labels=("docs", "Plugin:Todos")),
            issue("B", labels=("bug", "web")),
            issue("C", labels=("bug", "repo")),
            issue("D", labels=("enhancement", "web")),
            issue("E", labels=("bug",)),
            issue("F", labels=("bug", "web", "plugin:todos")),
        )
        code, data = report(capsys, repo, plan)
        assert code == flywheel.PROBLEMS
        assert data["errors"] == [
            "`D` carries 0 kind labels; it takes exactly one, from bug or docs",
            "`E` carries 0 area labels; it takes exactly one, from `plugin:*`, `web` or `repo`",
            "`F` carries 2 area labels (web, plugin:todos); it takes exactly one, from"
            " `plugin:*`, `web` or `repo`",
        ]

    @pytest.mark.spec("issuetemplate-sets-headings", "planreport-cmd-checks-each-draft")
    def it_checks_each_draft_against_the_templates_headings(self, capsys, tmp_path, repo, hub):
        hub()
        ruled(repo, template="Filed by the loop.\n\n## Problem\n\nWhat breaks.\n\n## Fix\n")
        plan = write_plan(
            tmp_path,
            issue("A", body="**Claude:**\n\n## Problem\n\nIt breaks.\n\n## Fix\n\nMend it.\n"),
            issue("B"),
        )
        code, data = report(capsys, repo, plan)
        assert code == flywheel.PROBLEMS
        assert data["errors"] == ["`B`'s body lacks the headings `## Problem`, `## Fix`"]

    @pytest.mark.spec("issuetemplate-sets-headings")
    def it_reads_each_heading_with_the_guidance_under_it(self, repo):
        ruled(repo, template="Filed by the loop.\n\n## Problem\n\nWhat breaks.\n\n## Fix\n")
        assert flywheel.issue_headings(str(repo)) == (("Problem", "What breaks."), ("Fix", ""))

    @pytest.mark.spec("issuetemplate-sets-headings")
    def it_gives_the_house_headings_without_a_template(self, repo):
        assert [h for h, _ in flywheel.issue_headings(str(repo))] == [
            "What's wrong",
            "Evidence",
            "Done when",
            "Requirements",
        ]

    @pytest.mark.spec("issuetemplate-sets-headings", "repo:script-exits-2-when-unrunnable")
    def it_stops_on_a_template_without_a_heading(self, capsys, tmp_path, repo, hub):
        hub()
        ruled(repo, template="Say what is wrong.\n### Not a section\n")
        code, out = run(capsys, repo, "plan", "report", "--drafts", str(write_plan(tmp_path)))
        assert code == flywheel.CANNOT_RUN
        assert out.out == ""
        assert "%s holds no `##` heading" % flywheel.TEMPLATE_FILE in out.err

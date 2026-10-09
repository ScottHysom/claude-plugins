"""What `todos.py file` files on GitHub, what it marks, and when it refuses."""

import os

import pytest

import todos


@pytest.fixture
def three(repo):
    """A clone with three pending TODOs in two files."""
    repo.write("a.py", "x = 1\ny = 2\n")
    repo.write("b.sh", "echo hi\n")
    repo.commit()
    repo.write("a.py", "# TODO(bug): one\n# detail\nx = 1\n# TODO: two\ny = 2\n")
    repo.write("b.sh", "echo hi\n# TODO: three\n")
    return repo


def creates(github):
    return [c for c in github.calls if c[:2] == ("issue", "create")]


@pytest.mark.spec("file-cmd-creates-issues")
class DescribeFiling:
    def it_creates_one_issue_for_each_draft(self, three, github):
        found, _ = three.scan()
        drafts = three.drafts(
            [
                three.draft(found[0], title="One", body="Line one.\nLine two.", labels=["bug"]),
                three.draft(found[2], title="Three", labels=["bug", "plugin:todos"]),
            ]
        )
        code, env = three.file(drafts)
        assert code == todos.OK, three.err
        assert sorted(github.issues, key=lambda i: i["title"]) == [
            {
                "title": "One",
                "body": "Line one.\nLine two.",
                "labels": ["bug"],
                "repo": "owner/project",
            },
            {
                "title": "Three",
                "body": "",
                "labels": ["bug", "plugin:todos"],
                "repo": "owner/project",
            },
        ]

    def it_sends_the_body_on_stdin(self, three, github):
        three.file(three.draft_all())
        for call in creates(github):
            assert call[call.index("--body-file") + 1] == "-"

    def it_prints_each_issues_number_and_address(self, three):
        drafts = three.draft_all()
        token = three.token(drafts)
        code, out, err = three.human("file", "--drafts", drafts, "--token", token)
        assert code == todos.OK, err
        assert out == (
            "filed #1 https://github.com/owner/project/issues/1\n"
            "  and marked a.py:4 as TODO-HANDLED(#1)\n"
            "filed #2 https://github.com/owner/project/issues/2\n"
            "  and marked a.py:1-2 as TODO-HANDLED(#2)\n"
            "filed #3 https://github.com/owner/project/issues/3\n"
            "  and marked b.sh:2 as TODO-HANDLED(#3)\n"
        )

    def it_gives_each_number_and_address_in_json(self, three):
        code, env = three.file(three.draft_all())
        assert code == todos.OK
        assert [(f["number"], f["url"], f["first"]) for f in env["data"]["filed"]] == [
            (1, "https://github.com/owner/project/issues/1", 4),
            (2, "https://github.com/owner/project/issues/2", 1),
            (3, "https://github.com/owner/project/issues/3", 2),
        ]

    def it_works_from_the_last_todo_in_each_file_to_the_first(self, three, github):
        three.file(three.draft_all())
        assert [i["title"] for i in github.issues] == ["two", "one", "three"]


@pytest.mark.spec("file-cmd-files-in-reported-repo")
class DescribeTheRepository:
    def it_passes_the_reported_repository_to_every_later_call(self, three, github):
        github.repository = "someone/fork"
        three.file(three.draft_all())
        later = [c for c in github.calls if c[:2] not in (("repo", "view"), ("api", "graphql"))]
        assert later
        for call in later:
            assert call[call.index("--repo") + 1] == "someone/fork"
        assert github.queries
        for query in github.queries:
            assert "repo:someone/fork " in query

    @pytest.mark.spec("file-cmd-requires-token")
    def it_refuses_once_the_repository_changes(self, three, github):
        drafts = three.draft_all()
        token = three.token(drafts)
        github.repository = "upstream/project"
        code, _ = three.run("file", "--drafts", drafts, "--token", token)
        assert code == todos.PROBLEMS
        assert creates(github) == []


@pytest.mark.spec("file-cmd-requires-token")
class DescribeTheToken:
    def it_refuses_a_token_report_did_not_print(self, three, github):
        before = (three.read("a.py"), three.read("b.sh"))
        code, env = three.run("file", "--drafts", three.draft_all(), "--token", "0" * 16)
        assert code == todos.PROBLEMS
        assert env["errors"] == [todos.TOKEN_STALE]
        assert creates(github) == []
        assert (three.read("a.py"), three.read("b.sh")) == before

    def it_refuses_once_a_named_file_changes(self, three, github):
        drafts = three.draft_all()
        token = three.token(drafts)
        three.write("b.sh", three.read("b.sh") + b"echo bye\n")
        code, _ = three.run("file", "--drafts", drafts, "--token", token)
        assert code == todos.PROBLEMS
        assert creates(github) == []

    def it_refuses_once_a_named_file_is_gone(self, three, github):
        drafts = three.draft_all()
        token = three.token(drafts)
        (three.root / "b.sh").unlink()
        code, env = three.run("file", "--drafts", drafts, "--token", token)
        assert code == todos.PROBLEMS
        assert env["errors"] == [todos.TOKEN_STALE]
        assert creates(github) == []

    def it_refuses_once_the_drafts_change(self, three, github):
        drafts = three.draft_all()
        token = three.token(drafts)
        found, _ = three.scan()
        three.drafts([three.draft(found[0], title="Something else")])
        code, _ = three.run("file", "--drafts", drafts, "--token", token)
        assert code == todos.PROBLEMS
        assert creates(github) == []


@pytest.mark.spec("file-cmd-checks-before-filing", "repo:script-checks-every-answer")
class DescribeCheckingFirst:
    @pytest.mark.spec("report-cmd-refuses-unknown-labels")
    def it_files_nothing_when_a_label_has_gone_since_the_report(self, three, github):
        found, _ = three.scan()
        drafts = three.drafts([three.draft(found[0]), three.draft(found[1], labels=["bug"])])
        token = three.token(drafts)
        github.labels = [x for x in github.labels if x["name"] != "bug"]
        before = three.read("a.py")
        code, env = three.run("file", "--drafts", drafts, "--token", token)
        assert code == todos.PROBLEMS
        assert env["errors"] == [
            "draft 2 names the label `bug`, which owner/project does not have. Use one scan lists",
            "nothing was filed, posted or written",
        ]
        assert creates(github) == []
        assert three.read("a.py") == before

    @pytest.mark.spec("report-cmd-refuses-stale-drafts")
    def it_refuses_a_stale_draft_whatever_the_token(self, three, github, monkeypatch):
        found, _ = three.scan()
        drafts = three.drafts([three.draft(found[0], line=3)])
        monkeypatch.setattr(todos, "approval_token", lambda *a: "t")
        code, env = three.run("file", "--drafts", drafts, "--token", "t")
        assert code == todos.PROBLEMS
        assert env["errors"][0].startswith("draft 1: a.py:3 does not hold a pending TODO")
        assert creates(github) == []

    @pytest.mark.spec("report-cmd-refuses-drafts-sharing-todo")
    def it_refuses_a_repeated_todo_whatever_the_token(self, three, github, monkeypatch):
        found, _ = three.scan()
        drafts = three.drafts([three.draft(found[0]), three.draft(found[0])])
        monkeypatch.setattr(todos, "approval_token", lambda *a: "t")
        code, env = three.run("file", "--drafts", drafts, "--token", "t")
        assert code == todos.PROBLEMS
        assert env["errors"][0] == "drafts 1, 2 name one TODO, a.py:1. Keep one of them"
        assert creates(github) == []

    @pytest.mark.spec("report-cmd-refuses-approved-label")
    def it_refuses_the_owners_label_whatever_the_token(self, three, github, monkeypatch):
        found, _ = three.scan()
        drafts = three.drafts([three.draft(found[0], labels=["APPROVED"])])
        monkeypatch.setattr(todos, "approval_token", lambda *a: "t")
        code, env = three.run("file", "--drafts", drafts, "--token", "t")
        assert code == todos.PROBLEMS
        assert "which only the owner adds" in env["errors"][0]
        assert creates(github) == []


@pytest.mark.spec("file-cmd-checks-writes-first", "repo:script-names-remedy-on-stop")
class DescribeWritableFiles:
    @pytest.mark.skipif(os.geteuid() == 0, reason="root can write a read-only file")
    def it_names_a_file_it_cannot_write_and_files_nothing(self, three, github):
        drafts = three.draft_all()
        token = three.token(drafts)
        (three.root / "b.sh").chmod(0o444)
        try:
            code, env = three.run("file", "--drafts", drafts, "--token", token)
        finally:
            (three.root / "b.sh").chmod(0o644)
        assert (code, env) == (todos.CANNOT_RUN, None)
        assert three.err == (
            "todos.py: cannot open b.sh for writing: Permission denied. Make it writable, then"
            " run file again; nothing was filed or posted\n"
        )
        assert creates(github) == []


@pytest.mark.spec("file-cmd-stops-at-failed-call")
class DescribeAFailedCall:
    def it_stops_and_leaves_the_todos_not_filed(self, three, github):
        github.fail = (2,)
        code, env = three.file(three.draft_all())
        assert code == todos.PROBLEMS
        assert len(creates(github)) == 2
        assert [i["title"] for i in github.issues] == ["two"]
        assert three.read("a.py") == (
            b"# TODO(bug): one\n# detail\nx = 1\n# TODO-HANDLED(#1): two\ny = 2\n"
        )
        assert three.read("b.sh") == b"echo hi\n# TODO: three\n"
        assert [(r["file"], r["first"]) for r in env["data"]["left"]] == [
            ("a.py", 1),
            ("b.sh", 2),
        ]
        assert env["errors"] == [
            "draft 1 (a.py:1-2): `gh issue create` failed: HTTP 502. Filing stopped there, and"
            " the TODOs of the drafts not filed or posted are still in their files"
        ]

    def it_lists_the_todos_left_in_text(self, three, github):
        github.fail = (1,)
        drafts = three.draft_all()
        token = three.token(drafts)
        code, out, err = three.human("file", "--drafts", drafts, "--token", token)
        assert code == todos.PROBLEMS
        assert out == (
            "not filed: draft 2, a.py:4, left in place\n"
            "not filed: draft 1, a.py:1-2, left in place\n"
            "not filed: draft 3, b.sh:2, left in place\n"
        )
        assert err.startswith("draft 2 (a.py:4): `gh issue create` failed")

    def it_stops_when_gh_prints_no_address(self, three, github):
        github.printed = "Creating issue\n"
        code, env = three.file(three.draft_all())
        assert code == todos.PROBLEMS
        assert len(creates(github)) == 1
        assert env["errors"][0].startswith(
            "draft 2 (a.py:4): `gh issue create` did not print an issue's address, but printed"
            " 'Creating issue'. Look in https://github.com/owner/project for the issue"
        )
        assert three.read("a.py").count(b"TODO-HANDLED") == 0

    def it_stops_when_gh_prints_nothing(self, three, github):
        github.printed = ""
        code, env = three.file(three.draft_all())
        assert code == todos.PROBLEMS
        assert "but printed ''" in env["errors"][0]


@pytest.mark.spec("file-cmd-never-posts-in-preview", "repo:command-never-writes-in-preview")
class DescribeDryRun:
    def it_says_what_it_would_file_and_mark(self, three, github):
        found, _ = three.scan()
        drafts = three.drafts(
            [three.draft(found[0], labels=["bug", "plugin:todos"]), three.draft(found[2])]
        )
        before = (three.read("a.py"), three.read("b.sh"))
        token = three.token(drafts)
        code, out, _ = three.human("file", "--drafts", drafts, "--token", token, "--dry-run")
        assert code == todos.OK
        assert out == (
            "would file in owner/project: one  [bug, plugin:todos]\n"
            "  and mark a.py:1-2 with the new issue's number\n"
            "would file in owner/project: three  [no labels]\n"
            "  and mark b.sh:2 with the new issue's number\n"
        )
        assert creates(github) == []
        assert (three.read("a.py"), three.read("b.sh")) == before

    def it_gives_no_number_in_json(self, three, github):
        code, env = three.file(three.draft_all(), "--dry-run")
        assert code == todos.OK
        assert env["data"]["dry_run"] is True
        assert [(f["number"], f["url"], f["handled"]) for f in env["data"]["filed"]] == [
            (None, None, None)
        ] * 3
        assert creates(github) == []

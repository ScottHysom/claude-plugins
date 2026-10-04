"""Drafts routed to `comment`: what `report` checks and shows, and what
`file` posts."""

import json

import pytest

import todos
from test_todos_github import VIEW, gh_script

ISSUE_URL = "https://github.com/owner/project/issues/7"


@pytest.fixture
def two(repo, github):
    """A clone with two pending TODOs in run.py, and open issue #7."""
    repo.write("run.py", "def run():\n    pass\n")
    repo.commit()
    repo.write(
        "run.py", "# TODO(bug): run hangs\n# no timeout\ndef run():\n    pass\n# TODO: tidy up\n"
    )
    github.add_issue(7, "run() hangs on a stalled gh")
    return repo


def comments(github):
    return [c for c in github.calls if c[:2] == ("issue", "comment")]


def lookups(github):
    return [q for q in github.queries if "issue(number:" in q]


@pytest.mark.spec("report-cmd-shows-each-draft")
class DescribeTheReport:
    def it_prints_a_comment_draft_whole(self, two):
        found, _ = two.scan()
        drafts = two.drafts([two.comment(found[0], 7, body="No timeout.\n\nAt all.")])
        code, out, _ = two.human("report", "--drafts", drafts)
        assert code == todos.OK, out
        assert (
            "draft 1  run.py:1-2  comment\n"
            "  on      #7  run() hangs on a stalled gh\n"
            "  body\n"
            "    | No timeout.\n"
            "    |\n"
            "    | At all.\n"
            "\n"
        ) in out

    def it_gives_the_issue_in_json(self, two):
        found, _ = two.scan()
        _, env = two.run("report", "--drafts", two.drafts([two.comment(found[1], 7, body="b")]))
        assert env["data"]["drafts"] == [
            {
                "draft": 1,
                "file": "run.py",
                "first": 5,
                "last": 5,
                "route": "comment",
                "body": "b",
                "issue": {"number": 7, "title": "run() hangs on a stalled gh", "url": ISSUE_URL},
            }
        ]


@pytest.mark.spec("report-cmd-checks-comment-targets", "repo:script-checks-every-answer")
class DescribeTheTargetIssue:
    def refused(self, repo, drafts):
        code, env = repo.run("report", "--drafts", repo.drafts(drafts))
        assert code == todos.PROBLEMS
        assert env["data"]["token"] is None
        return env["errors"]

    def it_refuses_an_issue_the_repository_does_not_have(self, two):
        found, _ = two.scan()
        assert self.refused(two, [two.comment(found[0], 8)]) == [
            "draft 1 names issue #8, which owner/project does not have. Name an open issue scan"
            " lists, or route the draft to `issue`"
        ]

    def it_refuses_a_closed_issue(self, two, github):
        github.add_issue(3, "Old", state="CLOSED")
        found, _ = two.scan()
        assert self.refused(two, [two.comment(found[0], 3)]) == [
            "draft 1 names issue #3, which is closed. Name an open issue scan lists, or route"
            " the draft to `issue`"
        ]

    def it_looks_up_every_issue_in_one_query(self, two, github):
        github.add_issue(9, "Tidy")
        found, _ = two.scan()
        drafts = [two.comment(found[0], 9), two.comment(found[1], 7)]
        code, _ = two.run("report", "--drafts", two.drafts(drafts))
        assert code == todos.OK
        (query,) = lookups(github)
        assert 'repository(owner: "owner", name: "project")' in query
        assert "i7: issue(number: 7)" in query
        assert "i9: issue(number: 9)" in query

    def it_does_not_look_up_an_issue_when_no_draft_comments(self, two, github):
        code, _ = two.run("report", "--drafts", two.draft_all())
        assert code == todos.OK
        assert lookups(github) == []

    @pytest.mark.parametrize("number", ["7", 0, True, None])
    def it_refuses_an_issue_that_is_not_a_number(self, two, number):
        found, _ = two.scan()
        assert self.refused(two, [two.comment(found[0], number)]) == [
            "draft 1 has an `issue` that is not an issue number"
        ]

    @pytest.mark.parametrize("body", ["", " \n"])
    def it_refuses_a_comment_without_words(self, two, body):
        found, _ = two.scan()
        assert self.refused(two, [two.comment(found[0], 7, body=body)]) == [
            "draft 1 has a `body` with no words in it, which a comment needs"
        ]

    def it_refuses_the_keys_of_an_issue_draft(self, two):
        found, _ = two.scan()
        assert self.refused(two, [two.comment(found[0], 7, labels=["bug"])]) == [
            "draft 1 has `labels`, which a draft does not take"
        ]

    def it_refuses_in_file_once_the_issue_has_closed(self, two, github):
        found, _ = two.scan()
        drafts = two.drafts([two.comment(found[0], 7)])
        token = two.token(drafts)
        github.existing[7]["state"] = "CLOSED"
        before = two.read("run.py")
        code, env = two.run("file", "--drafts", drafts, "--token", token)
        assert code == todos.PROBLEMS
        assert env["errors"] == [
            "draft 1 names issue #7, which is closed. Name an open issue scan lists, or route"
            " the draft to `issue`",
            "nothing was filed, posted or written",
        ]
        assert comments(github) == []
        assert two.read("run.py") == before


@pytest.mark.spec("report-cmd-checks-comment-targets")
class DescribeTheRealLookup:
    def lookup(self, repo, gh_on_path, graphql, graphql_exit):
        gh_on_path(gh_script(view=VIEW, graphql=json.dumps(graphql), graphql_exit=graphql_exit))
        repo.write("a.py", "# TODO: one\n")
        draft = {
            "file": "a.py",
            "line": 1,
            "text": "# TODO: one",
            "route": "comment",
            "issue": 8,
            "body": "b",
        }
        return repo.run("report", "--drafts", repo.drafts([draft, dict(draft, issue=7)]))

    def it_reads_a_missing_issue_from_what_gh_prints_as_it_fails(self, repo, gh_on_path):
        found = {"number": 7, "title": "T", "state": "OPEN", "url": ISSUE_URL}
        graphql = {
            "data": {"repository": {"i7": found, "i8": None}},
            "errors": [{"type": "NOT_FOUND", "path": ["repository", "i8"]}],
        }
        code, env = self.lookup(repo, gh_on_path, graphql, 1)
        assert code == todos.PROBLEMS, repo.err
        assert env["errors"] == [
            "draft 1 names issue #8, which owner/project does not have. Name an open issue scan"
            " lists, or route the draft to `issue`",
        ]

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
    @pytest.mark.parametrize(
        "graphql",
        [
            {"data": {"repository": None}, "errors": [{"type": "FORBIDDEN"}]},
            {"data": None, "errors": [{"type": "NOT_FOUND"}]},
            {"data": {"repository": None}},
        ],
    )
    def it_stops_when_the_lookup_fails_for_another_reason(self, repo, gh_on_path, graphql):
        code, env = self.lookup(repo, gh_on_path, graphql, 1)
        assert (code, env) == (todos.CANNOT_RUN, None)
        assert repo.err == (
            "todos.py: `gh api graphql` failed: gh: Could not resolve. Run it yourself to see"
            " what gh reports.\n"
        )

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    def it_stops_when_a_failed_lookup_prints_nothing(self, repo, gh_on_path):
        gh_on_path(gh_script(view=VIEW, graphql=None))
        repo.write("a.py", "# TODO: one\n")
        draft = {
            "file": "a.py",
            "line": 1,
            "text": "# TODO: one",
            "route": "comment",
            "issue": 8,
            "body": "b",
        }
        code, _ = repo.run("report", "--drafts", repo.drafts([draft]))
        assert code == todos.CANNOT_RUN
        assert "`gh api graphql` failed: gh: request failed" in repo.err


@pytest.mark.spec("file-cmd-posts-comments")
class DescribePosting:
    def it_posts_the_body_on_the_issue(self, two, github):
        found, _ = two.scan()
        drafts = two.drafts([two.comment(found[0], 7, body="Seen again in run.py.")])
        code, _ = two.file(drafts)
        assert code == todos.OK, two.err
        assert github.comments == [
            {"issue": 7, "body": "Seen again in run.py.", "repo": "owner/project"}
        ]
        assert github.issues == []
        (comment,) = comments(github)
        assert comment == (
            "issue",
            "comment",
            "7",
            "--repo",
            "owner/project",
            "--body-file",
            "-",
        )

    @pytest.mark.spec("file-cmd-removes-handled-todos")
    def it_removes_the_todo_once_the_comment_exists(self, two):
        found, _ = two.scan()
        code, _ = two.file(two.drafts([two.comment(found[0], 7)]))
        assert code == todos.OK
        assert two.read("run.py") == b"def run():\n    pass\n# TODO: tidy up\n"

    def it_prints_the_comments_address(self, two):
        found, _ = two.scan()
        drafts = two.drafts([two.comment(found[0], 7), two.draft(found[1])])
        token = two.token(drafts)
        code, out, err = two.human("file", "--drafts", drafts, "--token", token)
        assert code == todos.OK, err
        assert out == (
            "filed #1 https://github.com/owner/project/issues/1\n"
            "  and removed run.py:5\n"
            "commented on #7 %s#issuecomment-101\n"
            "  and removed run.py:1-2\n" % ISSUE_URL
        )

    def it_gives_the_address_in_json(self, two):
        found, _ = two.scan()
        code, env = two.file(two.drafts([two.comment(found[0], 7)]))
        assert code == todos.OK
        assert [(f["route"], f["number"], f["url"]) for f in env["data"]["filed"]] == [
            ("comment", 7, ISSUE_URL + "#issuecomment-101")
        ]

    @pytest.mark.spec("file-cmd-stops-at-failed-call")
    def it_stops_when_gh_prints_no_address(self, two, github):
        github.printed = "posted\n"
        found, _ = two.scan()
        code, env = two.file(two.drafts([two.comment(found[0], 7)]))
        assert code == todos.PROBLEMS
        assert env["errors"] == [
            "draft 1 (run.py:1-2): `gh issue comment` did not print a comment's address, but"
            " printed 'posted'. Look on %s for the comment before posting again. Filing stopped"
            " there, and the TODOs of the drafts not filed or posted are still in their files"
            % ISSUE_URL
        ]
        assert two.read("run.py").count(b"TODO") == 2

    @pytest.mark.spec("file-cmd-stops-at-failed-call")
    def it_stops_at_a_comment_that_fails(self, two, github):
        # The issue for run.py:5 is filed first, from the last TODO up.
        github.fail = (2,)
        found, _ = two.scan()
        drafts = two.drafts([two.comment(found[0], 7), two.draft(found[1])])
        code, env = two.file(drafts)
        assert code == todos.PROBLEMS
        assert [i["title"] for i in github.issues] == ["tidy up"]
        assert github.comments == []
        assert two.read("run.py") == b"# TODO(bug): run hangs\n# no timeout\ndef run():\n    pass\n"
        assert env["errors"][0].startswith("draft 1 (run.py:1-2): `gh issue comment` failed")

    def it_posts_through_gh_with_the_body_on_stdin(self, repo, gh_on_path, tmp_path):
        found = {"number": 7, "title": "T", "state": "OPEN", "url": ISSUE_URL}
        gh_on_path(
            gh_script(
                view=VIEW,
                graphql=json.dumps({"data": {"repository": {"i7": found}, "s0": {"nodes": []}}}),
                comment=ISSUE_URL + "#issuecomment-55",
            )
        )
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: one\nx = 1\n")
        found_todos, _ = repo.scan()
        drafts = repo.drafts([repo.comment(found_todos[0], 7, body="It's 'quoted'.\n")])
        code, env = repo.file(drafts)
        assert code == todos.OK, repo.err
        assert env["data"]["filed"][0]["url"] == ISSUE_URL + "#issuecomment-55"
        assert (tmp_path / "gh-bin" / "gh.body").read_text() == "It's 'quoted'.\n"
        assert repo.read("a.py") == b"x = 1\n"


@pytest.mark.spec("file-cmd-never-posts-in-preview", "repo:command-never-writes-in-preview")
class DescribeDryRun:
    def it_says_what_it_would_post_and_remove(self, two, github):
        found, _ = two.scan()
        drafts = two.drafts([two.comment(found[0], 7)])
        before = two.read("run.py")
        token = two.token(drafts)
        code, out, _ = two.human("file", "--drafts", drafts, "--token", token, "--dry-run")
        assert code == todos.OK
        assert out == (
            "would comment on owner/project#7: run() hangs on a stalled gh\n"
            "  and remove run.py:1-2\n"
        )
        assert comments(github) == []
        assert two.read("run.py") == before

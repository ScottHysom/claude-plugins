"""TODOs left as review comments on a pull request: how `--pr` reads them,
places them on the lines of the head branch's worktree, files them and hands
them off without writing any file."""

import os
from pathlib import Path

import pytest

import todos

PR = 527


def branch_of(tree):
    return tree.git("branch", "--show-current").decode().strip()


def real(path):
    return os.path.realpath(str(path))


class Comments:
    """Review comments as GitHub's REST API gives them, numbered from 1."""

    def __init__(self):
        self.made = []

    def add(self, path, line, commit, body, start=None, reply_to=None, side="RIGHT"):
        n = len(self.made) + 1
        self.made.append(
            {
                "id": n,
                "in_reply_to_id": reply_to,
                "body": body,
                "path": path,
                "original_line": line,
                "original_start_line": start,
                "original_commit_id": commit,
                "side": side,
                "html_url": "https://github.com/owner/project/pull/%d#discussion_r%d" % (PR, n),
            }
        )
        return self.made[-1]


@pytest.fixture
def comments():
    return Comments()


@pytest.fixture
def review(repo, github, comments):
    """The repo's branch as the head of PR, whose review comments are
    `comments`. Returns the pull request."""
    pull = github.add_pull(PR, branch_of(repo))
    github.reviews[PR] = comments.made
    return pull


DOC = "# Title\n\nFirst paragraph.\n\n- one\n- two\n- three\n"


def scan_pr(tree):
    code, env = tree.run("scan", "--pr", str(PR))
    assert code == todos.OK, tree.err
    return env


def pr_token(tree, drafts):
    """The token report --pr prints for a drafts file, which must pass."""
    code, env = tree.run("report", "--pr", str(PR), "--drafts", drafts)
    assert code == todos.OK, tree.err
    return env["data"]["token"]


@pytest.mark.spec("scan-cmd-reads-review-todos")
class DescribeReviewTodos:
    def it_reads_the_title_detail_kind_and_lines_of_a_review_comment(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        body = "TODO(prose): too long\nSplit it.\n\n- at the comma\n"
        made = comments.add("doc.md", 3, repo.head(), body)
        env = scan_pr(repo)
        [todo] = env["data"]["todos"]
        assert todo["file"] == "doc.md"
        assert (todo["first"], todo["last"]) == (3, 3)
        assert todo["text"] == "TODO(prose): too long"
        assert todo["kind"] == "prose"
        assert todo["title"] == "too long"
        assert todo["detail"] == "Split it.\n\n- at the comma"
        assert todo["above"] is None
        assert todo["comment"] == {"id": made["id"], "url": made["html_url"]}
        assert env["data"]["pull_request"] == {
            "number": PR,
            "url": review["url"],
            "branch": review["headRefName"],
        }

    def it_gives_the_lines_a_comment_on_a_range_covers(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 7, repo.head(), "TODO: three items", start=5)
        [todo] = scan_pr(repo)["data"]["todos"]
        assert (todo["first"], todo["last"]) == (5, 7)

    def it_skips_replies_and_comments_that_do_not_open_with_a_todo(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        top = comments.add("doc.md", 3, repo.head(), "Looks fine. TODO: later")
        comments.add("doc.md", 3, repo.head(), "TODO: in a reply", reply_to=top["id"])
        comments.add("doc.md", 3, repo.head(), "  TODO: read past the leading space")
        [todo] = scan_pr(repo)["data"]["todos"]
        assert todo["title"] == "read past the leading space"

    def it_warns_about_a_word_that_is_not_a_kind(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO(someday): later")
        env = scan_pr(repo)
        assert env["data"]["todos"][0]["kind"] is None
        [warning] = env["warnings"]
        assert warning.startswith(made["html_url"])
        assert "`someday` is not a kind" in warning

    def it_does_not_read_the_trees_pending_todos(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        repo.write("a.py", "# TODO: pending in the tree\n")
        comments.add("doc.md", 3, repo.head(), "TODO: from the review")
        assert [t["title"] for t in scan_pr(repo)["data"]["todos"]] == ["from the review"]

    def it_does_not_name_other_worktrees_when_the_review_holds_no_todo(
        self, repo, worktree, review
    ):
        worktree.write("a.py", "# TODO: pending in the other checkout\n")
        env = scan_pr(repo)
        assert env["data"]["other_worktrees"] == []

    def it_lists_the_todos_in_file_and_line_order(self, repo, review, comments):
        repo.write("b.md", DOC)
        repo.write("a.md", DOC)
        repo.commit()
        head = repo.head()
        comments.add("b.md", 3, head, "TODO: b3")
        comments.add("a.md", 5, head, "TODO: a5")
        comments.add("a.md", 3, head, "TODO: a3")
        titles = [t["title"] for t in scan_pr(repo)["data"]["todos"]]
        assert titles == ["a3", "a5", "b3"]

    def it_warns_about_a_comment_that_is_not_on_lines_of_the_head(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        whole = comments.add("doc.md", None, repo.head(), "TODO: on the whole file")
        removed = comments.add("doc.md", 3, repo.head(), "TODO: on a removed line", side="LEFT")
        env = scan_pr(repo)
        assert env["data"]["todos"] == []
        assert [w.split(": ")[0] for w in env["warnings"]] == [
            whole["html_url"],
            removed["html_url"],
        ]
        assert all("Leave it on the lines it is about" in w for w in env["warnings"])

    def it_warns_about_a_comment_on_a_file_the_tree_does_not_hold(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        head = repo.head()
        repo.git("rm", "-q", "doc.md")
        repo.commit("gone")
        made = comments.add("doc.md", 3, head, "TODO: on a file since deleted")
        env = scan_pr(repo)
        assert env["data"]["todos"] == []
        [warning] = env["warnings"]
        assert warning.startswith(made["html_url"])
        assert "doc.md is not a file with lines" in warning

    def it_says_when_no_review_comment_holds_a_todo(self, repo, review):
        code, out, _ = repo.human("scan", "--pr", str(PR))
        assert code == todos.OK
        assert "No review comment on #%d opens with a TODO." % PR in out

    def it_names_each_todos_comment_in_human_output(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO: too long")
        code, out, _ = repo.human("scan", "--pr", str(PR))
        assert code == todos.OK
        assert "TODOs in the review of #%d" % PR in out
        assert "doc.md:3: too long" in out
        assert "review comment %s" % made["html_url"] in out


@pytest.mark.spec("scan-cmd-finds-moved-review-lines")
class DescribeMovedReviewLines:
    def it_follows_lines_a_later_commit_moved(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 6, repo.head(), "TODO: two", start=5)
        repo.write("doc.md", "# Title\n\nNew paragraph.\n\n" + DOC[len("# Title\n\n") :])
        repo.commit("moved")
        env = scan_pr(repo)
        [todo] = env["data"]["todos"]
        assert (todo["first"], todo["last"]) == (7, 8)
        assert env["warnings"] == []

    def it_reads_the_tree_as_it_stands_with_its_uncommitted_lines(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: first paragraph")
        repo.write("doc.md", "Above.\n" + DOC)
        [todo] = scan_pr(repo)["data"]["todos"]
        assert todo["first"] == 4

    def it_warns_and_names_the_comment_when_its_lines_changed(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 7, repo.head(), "TODO: the list", start=5)
        repo.write("doc.md", DOC.replace("- two\n", "- deux\n"))
        repo.commit("changed")
        env = scan_pr(repo)
        [todo] = env["data"]["todos"]
        assert (todo["first"], todo["last"]) == (5, 7)
        [warning] = env["warnings"]
        assert warning.startswith(made["html_url"])
        assert "doc.md:5-7 at %s" % made["original_commit_id"][: todos.ABBREV] in warning
        assert "placed at doc.md:5-7" in warning

    def it_places_a_todo_whose_lines_are_gone_after_the_line_before_them(
        self, repo, review, comments
    ):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 6, repo.head(), "TODO: two")
        repo.write("doc.md", DOC.replace("- two\n", ""))
        repo.commit("removed")
        env = scan_pr(repo)
        assert env["data"]["todos"][0]["first"] == 6
        assert "placed at doc.md:6." in env["warnings"][0]

    def it_places_a_todo_whose_lines_are_gone_from_the_top_on_the_first_line(
        self, repo, review, comments
    ):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 1, repo.head(), "TODO: the title")
        repo.write("doc.md", DOC.replace("# Title\n", "# Heading\n"))
        repo.commit("retitled")
        env = scan_pr(repo)
        assert env["data"]["todos"][0]["first"] == 1
        assert "placed at doc.md:1." in env["warnings"][0]

    def it_stops_when_the_clone_does_not_hold_the_comments_commit(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, "0" * 40, "TODO: from an unfetched commit")
        code, _ = repo.run("scan", "--pr", str(PR))
        assert code == todos.CANNOT_RUN
        assert made["html_url"] in repo.err
        assert "`git fetch`" in repo.err


@pytest.mark.spec("command-reads-review-with-pr")
class DescribePrOption:
    def it_reads_the_passages_from_the_worktree_on_the_head_branch(
        self, repo, worktree, github, comments
    ):
        worktree.write("doc.md", DOC)
        worktree.commit()
        comments.add("doc.md", 3, worktree.head(), "TODO: from the review")
        github.add_pull(PR, branch_of(worktree), comments.made)
        [todo] = scan_pr(repo)["data"]["todos"]
        assert todo["file"] == "doc.md"
        drafts = repo.drafts([repo.draft(todo)])
        code, env = repo.run("report", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        assert [r["first"] for r in env["data"]["drafts"]] == [3]
        token = env["data"]["token"]
        code, env = repo.run(
            "file", "--pr", str(PR), "--drafts", drafts, "--token", token, "--dry-run"
        )
        assert code == todos.OK, repo.err
        assert [r["first"] for r in env["data"]["filed"]] == [3]

    def it_answers_questions_about_review_todos(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: one")
        comments.add("doc.md", 3, repo.head(), "TODO: two")
        batch = repo.drafts(
            [
                {
                    "question": "Same thing?",
                    "options": [{"label": "Yes"}],
                    "todos": [{"file": "doc.md", "line": 3}],
                }
            ]
        )
        code, env = repo.run("questions", "--pr", str(PR), "--batch", batch)
        assert code == todos.OK, repo.err
        page = Path(env["data"]["page"]).read_text()
        assert "- `doc.md:3` one" in page
        assert "- `doc.md:3` two" in page

    def it_stops_when_no_worktree_has_the_head_branch_checked_out(self, repo, github):
        github.add_pull(PR, "feature/elsewhere")
        for command in ("scan", "report", "file", "questions"):
            extra = {"report": ["--drafts", "x"], "file": ["--drafts", "x"]}
            extra["questions"] = ["--batch", "x"]
            code, _ = repo.run(command, "--pr", str(PR), *extra.get(command, []))
            assert code == todos.CANNOT_RUN
            assert "feature/elsewhere, the head branch of #%d" % PR in repo.err

    def it_stops_when_the_number_is_not_a_pull_request(self, repo):
        code, _ = repo.run("scan", "--pr", "9")
        assert code == todos.CANNOT_RUN
        assert "Check that #9 is a pull request of owner/project" in repo.err

    def it_stops_when_gh_cannot_read_the_review_comments(self, repo, review, github):
        del github.reviews[PR]
        code, _ = repo.run("scan", "--pr", str(PR))
        assert code == todos.CANNOT_RUN
        assert "HTTP 404. Run it yourself" in repo.err

    def it_refuses_pr_beside_from(self, repo, capsys):
        with pytest.raises(SystemExit) as exc:
            todos.main(["scan", "--pr", "1", "--from", "x", "-C", str(repo.root)])
        assert exc.value.code == todos.CANNOT_RUN
        assert "not allowed with argument" in capsys.readouterr().err


@pytest.mark.spec("file-cmd-leaves-review-todos-unmarked")
class DescribeFilingReviewTodos:
    def it_files_a_review_todo_and_writes_no_file(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO(bug): broken\nIt fails.")
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.draft(todo, labels=["bug"])])
        before = repo.read("doc.md")
        token = pr_token(repo, drafts)
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts, "--token", token)
        assert code == todos.OK, repo.err
        assert repo.read("doc.md") == before
        assert repo.git("status", "--porcelain").decode().strip() == ""
        [filed] = env["data"]["filed"]
        assert filed["number"] == 1
        assert filed["handled"] is None
        assert filed["comment"]["url"] == made["html_url"]
        assert github.issues[0]["body"] == "It fails."

    def it_names_the_review_comment_rather_than_a_mark(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO: later")
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.draft(todo)])
        token = pr_token(repo, drafts)
        code, out, _ = repo.human(
            "file", "--pr", str(PR), "--drafts", drafts, "--token", token, "--dry-run"
        )
        assert code == todos.OK
        assert "from the review comment %s" % made["html_url"] in out
        assert "mark" not in out

    def it_keeps_apart_two_comments_on_one_line(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: one")
        comments.add("doc.md", 3, repo.head(), "TODO: two")
        found = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.draft(t) for t in found])
        code, env = repo.run("report", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        assert [r["title"] for r in env["data"]["drafts"]] == ["one", "two"]


@pytest.mark.spec("file-cmd-requires-token")
class DescribeReviewToken:
    def it_goes_stale_when_a_named_review_comment_changes(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO: later\nSome detail.")
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.draft(todo)])
        token = pr_token(repo, drafts)
        made["body"] = "TODO: later\nOther detail."
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts, "--token", token)
        assert code == todos.PROBLEMS
        assert env["errors"] == [todos.TOKEN_STALE]

    def it_refuses_a_token_beside_a_malformed_draft(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: later")
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts(
            [repo.draft(todo), {"file": 3, "line": [], "text": None, "route": "issue"}]
        )
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts, "--token", "x")
        assert code == todos.PROBLEMS
        assert env["errors"] == [todos.TOKEN_STALE]


@pytest.mark.spec("file-cmd-prints-handoffs")
class DescribeReviewHandoffs:
    def it_hands_off_the_passage_the_comments_lines_sit_in(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 6, repo.head(), "TODO(prose): wordy", start=5)
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(todo)])
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        [handoff] = env["data"]["handoffs"]
        [item] = handoff["todos"]
        assert item["comment"] == {
            "id": made["id"],
            "url": made["html_url"],
            "first": 5,
            "last": 6,
        }
        passage = item["passage"]
        assert (passage["first"], passage["last"]) == (5, 6)
        assert passage["text"] == "- one\n- two"
        assert passage["line"] is None
        assert passage["trailing"] is False

    def it_names_the_comment_in_human_output(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO(prose): wordy")
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(todo)])
        code, out, _ = repo.human("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK
        assert "in the review comment %s, on lines 3-3" % made["html_url"] in out

    def it_names_the_worktree_it_read_in(self, repo, worktree, github, comments):
        worktree.write("doc.md", DOC)
        worktree.commit()
        comments.add("doc.md", 3, worktree.head(), "TODO(prose): wordy")
        github.add_pull(PR, branch_of(worktree), comments.made)
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(todo)])
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        checkout = env["data"]["handoffs"][0]["checkout"]
        assert real(checkout["root"]) == real(worktree.root)
        assert checkout["branch"] == branch_of(worktree)

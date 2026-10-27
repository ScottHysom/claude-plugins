"""TODOs left as review comments on a pull request: how `--pr` reads them,
places them on the lines of the head branch's worktree, files them and hands
them off without writing any file, and marks each by a reply in its thread."""

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

    def add(self, path, line, commit, body, start=None, reply_to=None, side="RIGHT", pending=False):
        n = len(self.made) + 1
        self.made.append(
            {
                "id": n,
                "pending": pending,
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


# A file whose change makes a pull request about prose, so that a prose TODO
# in its review may go to a skill.
PROSE_RULES = ".claude/rules/prose-style.md"


@pytest.fixture
def review(repo, github, comments):
    """The repo's branch as the head of PR, a pull request about prose,
    whose review comments are `comments`. Returns the pull request."""
    pull = github.add_pull(PR, branch_of(repo), files=("README.md", PROSE_RULES))
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
        assert todo["comment"] == {"id": made["id"], "url": made["html_url"], "pending": False}
        assert env["data"]["pull_request"] == {
            "number": PR,
            "url": review["url"],
            "branch": review["headRefName"],
            "prose": True,
        }

    def it_reads_threads_past_the_first_page(self, repo, review, comments, monkeypatch):
        monkeypatch.setattr(todos, "THREAD_PAGE", 1)
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: first")
        comments.add("doc.md", 5, repo.head(), "TODO: second")
        found = scan_pr(repo)["data"]["todos"]
        assert [t["title"] for t in found] == ["first", "second"]

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
        assert (
            "Could not resolve to a PullRequest with the number of %d. Run it yourself" % PR
            in repo.err
        )

    def it_refuses_pr_beside_from(self, repo, capsys):
        with pytest.raises(SystemExit) as exc:
            todos.main(["scan", "--pr", "1", "--from", "x", "-C", str(repo.root)])
        assert exc.value.code == todos.CANNOT_RUN
        assert "not allowed with argument" in capsys.readouterr().err


@pytest.mark.spec("file-cmd-leaves-tree-for-review-todos")
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
        assert filed["comment"]["url"] == made["html_url"]
        assert github.issues[0]["body"] == "It fails."

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
        github.add_pull(PR, branch_of(worktree), comments.made, files=(PROSE_RULES,))
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(todo)])
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        checkout = env["data"]["handoffs"][0]["checkout"]
        assert real(checkout["root"]) == real(worktree.root)
        assert checkout["branch"] == branch_of(worktree)


def file_pr(tree, drafts, *extra):
    """Run file --pr with the token report --pr prints."""
    token = pr_token(tree, drafts)
    return tree.run("file", "--pr", str(PR), "--drafts", drafts, "--token", token, *extra)


def thread(github, made):
    """The bodies of the replies in the thread of review comment made."""
    return [r["body"] for r in github.replies if r["in_reply_to_id"] == made["id"]]


@pytest.mark.spec("file-cmd-replies-to-review-todos")
class DescribeReviewReplies:
    def it_replies_in_the_thread_naming_the_issue(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO(bug): broken")
        [todo] = scan_pr(repo)["data"]["todos"]
        code, env = file_pr(repo, repo.drafts([repo.draft(todo)]))
        assert code == todos.OK, repo.err
        assert thread(github, made) == ["TODO-HANDLED(#1): Filed as #1."]
        [filed] = env["data"]["filed"]
        assert filed["handled"] == "TODO-HANDLED(#1)"
        assert filed["reply_url"] == github.replies[0]["html_url"]

    def it_names_the_issue_a_comment_went_to_and_the_skill_a_hand_off_went_to(
        self, repo, review, comments, github
    ):
        repo.write("doc.md", DOC)
        repo.commit()
        github.add_issue(7, "Lists run long")
        on_issue = comments.add("doc.md", 3, repo.head(), "TODO: also here")
        on_skill = comments.add("doc.md", 5, repo.head(), "TODO(prose): wordy")
        first, second = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.comment(first, 7), repo.skill(second)])
        code, _ = file_pr(repo, drafts)
        assert code == todos.OK, repo.err
        assert thread(github, on_issue) == ["TODO-HANDLED(#7 comment): Added to #7 as a comment."]
        assert thread(github, on_skill) == [
            "TODO-HANDLED(example:learn-prose-rules): Handed to the skill"
            " `example:learn-prose-rules`."
        ]

    def it_opens_each_reply_with_the_lead_it_is_given(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO(prose): wordy")
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(todo)])
        code, _ = repo.run(
            "file", "--pr", str(PR), "--drafts", drafts, "--reply-lead", "**Claude:** "
        )
        assert code == todos.OK, repo.err
        assert thread(github, made)[0].startswith("**Claude:** TODO-HANDLED(")

    @pytest.mark.spec("file-cmd-never-posts-in-preview")
    def it_does_not_reply_in_a_dry_run(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO(prose): wordy")
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(todo)])
        code, out, _ = repo.human("file", "--pr", str(PR), "--drafts", drafts, "--dry-run")
        assert code == todos.OK
        assert github.replies == []
        assert "and reply in %s: TODO-HANDLED(" % made["html_url"] in out

    @pytest.mark.spec("file-cmd-never-posts-in-preview")
    def it_says_a_dry_run_replies_with_the_new_issues_number(self, repo, review, comments):
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
        assert "and reply in %s with the new issue's number" % made["html_url"] in out

    def it_names_each_reply_in_human_output(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO: later")
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.draft(todo)])
        token = pr_token(repo, drafts)
        code, out, _ = repo.human("file", "--pr", str(PR), "--drafts", drafts, "--token", token)
        assert code == todos.OK
        assert "and replied in %s: TODO-HANDLED(#1): Filed as #1." % made["html_url"] in out

    def it_stops_and_gives_the_reply_when_a_reply_fails(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: first")
        made = comments.add("doc.md", 5, repo.head(), "TODO: second")
        found = scan_pr(repo)["data"]["todos"]
        github.fail_replies = (1,)
        code, env = file_pr(repo, repo.drafts([repo.draft(t) for t in found]))
        assert code == todos.PROBLEMS
        assert len(github.issues) == 1
        [error] = env["errors"]
        assert made["html_url"] in error
        assert '"TODO-HANDLED(#1): Filed as #1."' in error
        assert [r["first"] for r in env["data"]["left"]] == [3]

    def it_stops_when_a_reply_does_not_print_its_address(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO(prose): wordy")
        [todo] = scan_pr(repo)["data"]["todos"]
        github.reply_gives = {"addPullRequestReviewThreadReply": None}
        code, env = repo.run("file", "--pr", str(PR), "--drafts", repo.drafts([repo.skill(todo)]))
        assert code == todos.PROBLEMS
        assert "did not give the reply's address, but gave" in env["errors"][0]

    def it_does_not_reply_twice_when_a_stopped_run_runs_again(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        first = comments.add("doc.md", 3, repo.head(), "TODO: first")
        second = comments.add("doc.md", 5, repo.head(), "TODO: second")
        github.fail = (2,)
        found = scan_pr(repo)["data"]["todos"]
        code, _ = file_pr(repo, repo.drafts([repo.draft(t) for t in found]))
        assert code == todos.PROBLEMS
        github.fail = ()
        [left] = scan_pr(repo)["data"]["todos"]
        assert left["title"] == "first"
        code, _ = file_pr(repo, repo.drafts([repo.draft(left)]))
        assert code == todos.OK, repo.err
        assert len(thread(github, first)) == 1
        assert len(thread(github, second)) == 1


@pytest.mark.spec("scan-cmd-skips-answered-review-todos")
class DescribeAnsweredReviewTodos:
    def it_skips_a_thread_that_holds_a_reply_with_a_mark(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        top = comments.add("doc.md", 3, repo.head(), "TODO: done already")
        reply = "**Claude:** TODO-HANDLED(#4): Filed as #4."
        comments.add("doc.md", 3, repo.head(), reply, reply_to=top["id"])
        assert scan_pr(repo)["data"]["todos"] == []

    def it_reads_a_thread_whose_replies_do_not_hold_a_mark(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        top = comments.add("doc.md", 3, repo.head(), "TODO: still open")
        comments.add("doc.md", 3, repo.head(), "Agreed, TODO-HANDLED later", reply_to=top["id"])
        [todo] = scan_pr(repo)["data"]["todos"]
        assert todo["title"] == "still open"

    def it_skips_a_thread_whose_mark_waits_in_a_pending_review(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        top = comments.add("doc.md", 3, repo.head(), "TODO: done already")
        reply = "TODO-HANDLED(#4): Filed as #4."
        comments.add("doc.md", 3, repo.head(), reply, reply_to=top["id"], pending=True)
        assert scan_pr(repo)["data"]["todos"] == []


PENDING = "PRR_pending"


@pytest.fixture
def pending(review, github):
    """The signed-in user has a pending review on PR."""
    github.pending_reviews[PR] = PENDING
    return PENDING


@pytest.mark.spec("scan-cmd-reads-pending-review-todos")
class DescribePendingReviewTodos:
    def it_reads_a_todo_in_the_pending_review_and_says_so(self, repo, pending, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: submitted")
        comments.add("doc.md", 5, repo.head(), "TODO: not yet", pending=True)
        found = scan_pr(repo)["data"]["todos"]
        assert [(t["title"], t["comment"]["pending"]) for t in found] == [
            ("submitted", False),
            ("not yet", True),
        ]

    def it_names_the_pending_review_in_human_output(self, repo, pending, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), "TODO: not yet", pending=True)
        code, out, _ = repo.human("scan", "--pr", str(PR))
        assert code == todos.OK
        assert "    review comment in your pending review %s" % made["html_url"] in out


@pytest.mark.spec("file-cmd-replies-into-pending-review")
class DescribeRepliesInPendingReview:
    def it_adds_each_reply_to_the_pending_review(self, repo, pending, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        submitted = comments.add("doc.md", 3, repo.head(), "TODO(prose): submitted")
        waiting = comments.add("doc.md", 5, repo.head(), "TODO(prose): not yet", pending=True)
        found = scan_pr(repo)["data"]["todos"]
        code, env = repo.run(
            "file", "--pr", str(PR), "--drafts", repo.drafts([repo.skill(t) for t in found])
        )
        assert code == todos.OK, repo.err
        assert len(thread(github, submitted)) == 1
        assert len(thread(github, waiting)) == 1
        assert all(r["pending"] for r in github.replies)
        assert [f["reply_pending"] for f in env["data"]["filed"]] == [True, True]

    def it_posts_each_reply_at_once_when_no_review_is_pending(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO(prose): wordy")
        [todo] = scan_pr(repo)["data"]["todos"]
        code, env = repo.run("file", "--pr", str(PR), "--drafts", repo.drafts([repo.skill(todo)]))
        assert code == todos.OK, repo.err
        assert [r["pending"] for r in github.replies] == [False]
        assert env["data"]["filed"][0]["reply_pending"] is False

    def it_says_each_reply_appears_when_the_review_is_submitted(self, repo, pending, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO(prose): not yet", pending=True)
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(todo)])
        code, out, _ = repo.human("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK
        assert "The reply is in your pending review, and appears when you submit it." in out


def suggesting(title, *lines, fence="```"):
    """A review comment's body: a TODO, then a suggestion block of lines."""
    return "\n".join(["TODO(prose): %s" % title, fence + "suggestion", *lines, fence])


def hand_off(tree, *drafts_of, dry_run=False):
    """Run file --pr on skill drafts for the TODOs scan gives, in order.
    Returns the envelope."""
    found = scan_pr(tree)["data"]["todos"]
    drafts = tree.drafts([tree.skill(t) for t in found])
    extra = ["--dry-run"] if dry_run else []
    code, env = tree.run("file", "--pr", str(PR), "--drafts", drafts, *extra)
    assert code == todos.OK, tree.err
    return env


@pytest.mark.spec("scan-cmd-reads-review-todos")
class DescribeReviewSuggestions:
    def it_gives_the_lines_of_a_comments_suggestion_block(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One.", "Two."))
        [todo] = scan_pr(repo)["data"]["todos"]
        assert todo["suggestion"] == {"lines": ["One.", "Two."], "current": True}

    def it_runs_a_block_that_is_not_closed_to_the_end(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: wordy\n~~~~ suggestion\nOne.")
        [todo] = scan_pr(repo)["data"]["todos"]
        assert todo["suggestion"]["lines"] == ["One."]

    def it_gives_no_suggestion_for_a_comment_without_one(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), "TODO: wordy\n```text\nOne.\n```")
        [todo] = scan_pr(repo)["data"]["todos"]
        assert todo["suggestion"] is None

    def it_says_the_suggestion_is_not_current_when_its_lines_changed(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One."))
        repo.write("doc.md", DOC.replace("First", "Opening"))
        [todo] = scan_pr(repo)["data"]["todos"]
        assert todo["suggestion"]["current"] is False


@pytest.mark.spec("file-cmd-writes-review-suggestions")
class DescribeWritingSuggestions:
    def it_writes_the_suggestion_over_the_lines_the_comment_covers(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One paragraph."))
        env = hand_off(repo)
        assert repo.read("doc.md") == DOC.replace("First paragraph.", "One paragraph.").encode()
        assert env["data"]["suggested"] == [
            {"file": "doc.md", "first": 3, "last": 3, "comment": made["html_url"]}
        ]

    def it_hands_off_the_suggested_lines_as_the_changed_lines(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        body = suggesting("wordy", "- one", "- two and", "  more") + "\nToo long."
        comments.add("doc.md", 6, repo.head(), body, start=5)
        [handoff] = hand_off(repo)["data"]["handoffs"]
        [item] = handoff["todos"]
        passage = item["passage"]
        assert passage["text"] == "- one\n- two and\n  more"
        assert (passage["first"], passage["last"]) == (5, 7)
        assert passage["changed"] == [6, 7]
        assert (item["comment"]["first"], item["comment"]["last"]) == (5, 7)
        assert item["detail"] == "Too long."
        assert "suggestion" not in handoff["arguments"]

    def it_moves_the_todos_below_a_suggestion_that_adds_lines(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        head = repo.head()
        comments.add("doc.md", 3, head, suggesting("split", "First.", "Paragraph."))
        comments.add("doc.md", 6, head, suggesting("number", "- 2"))
        comments.add("doc.md", 7, head, "TODO(prose): plain note")
        env = hand_off(repo)
        assert repo.read("doc.md") == (b"# Title\n\nFirst.\nParagraph.\n\n- one\n- 2\n- three\n")
        items = env["data"]["handoffs"][0]["todos"]
        assert [i["passage"]["text"] for i in items] == ["First.\nParagraph.", "- 2", "- three"]
        assert [i["comment"]["first"] for i in items] == [3, 7, 8]

    def it_keeps_the_todos_above_a_suggestion_where_they_are(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        head = repo.head()
        comments.add("doc.md", 1, head, "TODO(prose): the title")
        comments.add("doc.md", 5, head, suggesting("split", "- a", "- b"))
        items = hand_off(repo)["data"]["handoffs"][0]["todos"]
        assert [i["comment"]["first"] for i in items] == [1, 5]
        assert items[0]["passage"]["text"] == "# Title"

    def it_removes_the_lines_of_an_empty_suggestion(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 6, repo.head(), suggesting("cut"))
        env = hand_off(repo)
        assert repo.read("doc.md") == DOC.replace("- two\n", "").encode()
        [item] = env["data"]["handoffs"][0]["todos"]
        assert (item["comment"]["first"], item["comment"]["last"]) == (6, 6)
        assert item["passage"]["text"] == "- three"

    def it_keeps_the_files_line_endings(self, repo, review, comments):
        repo.write("doc.md", DOC.replace("\n", "\r\n").rstrip("\r\n"))
        repo.commit()
        comments.add("doc.md", 7, repo.head(), suggesting("split", "- 3", "- 4"))
        hand_off(repo)
        assert repo.read("doc.md").endswith(b"- two\r\n- 3\r\n- 4")

    def it_ends_lines_with_a_newline_in_a_one_line_file_without_an_ending(
        self, repo, review, comments
    ):
        repo.write("doc.md", "two")
        repo.commit()
        comments.add("doc.md", 1, repo.head(), suggesting("split", "2", "3"))
        hand_off(repo)
        assert repo.read("doc.md") == b"2\n3"

    def it_writes_nothing_in_a_dry_run(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One."))
        found = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(t) for t in found])
        code, out, _ = repo.human("file", "--pr", str(PR), "--drafts", drafts, "--dry-run")
        assert code == todos.OK
        assert repo.read("doc.md") == DOC.encode()
        assert "would write the suggestion of %s at doc.md:3" % made["html_url"] in out
        assert "One." in out

    def it_names_what_it_wrote_in_human_output(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One."))
        found = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(t) for t in found])
        code, out, _ = repo.human("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK
        assert "wrote the suggestion of %s at doc.md:3" % made["html_url"] in out

    def it_leaves_lines_that_changed_since_the_comment_and_warns(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One."))
        repo.write("doc.md", DOC.replace("First", "Opening"))
        repo.commit("reworded")
        env = hand_off(repo)
        assert repo.read("doc.md") == DOC.replace("First", "Opening").encode()
        assert env["data"]["suggested"] == []
        assert any(
            w.startswith(made["html_url"]) and "suggestion was not written" in w
            for w in env["warnings"]
        )
        [item] = env["data"]["handoffs"][0]["todos"]
        assert "One." in item["detail"]

    def it_writes_only_the_first_of_two_overlapping_suggestions(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        head = repo.head()
        first = comments.add("doc.md", 6, head, suggesting("both", "- 1", "- 2"), start=5)
        second = comments.add("doc.md", 6, head, suggesting("two", "- deux"))
        env = hand_off(repo)
        assert repo.read("doc.md") == DOC.replace("- one\n- two", "- 1\n- 2").encode()
        [warning] = env["warnings"]
        assert warning.startswith(second["html_url"])
        assert "overlap those of %s" % first["html_url"] in warning

    def it_does_not_write_a_suggestion_that_empties_the_file(self, repo, review, comments):
        repo.write("doc.md", "only\n")
        repo.commit()
        made = comments.add("doc.md", 1, repo.head(), suggesting("cut"))
        env = hand_off(repo)
        assert repo.read("doc.md") == b"only\n"
        [warning] = env["warnings"]
        assert warning.startswith(made["html_url"])
        assert "would leave doc.md empty" in warning

    def it_stops_before_filing_when_it_cannot_write_the_file(self, repo, review, comments, github):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One."))
        comments.add("doc.md", 5, repo.head(), "TODO(bug): broken")
        found = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.skill(found[0]), repo.draft(found[1])])
        token = pr_token(repo, drafts)
        os.chmod(str(repo.root / "doc.md"), 0o444)
        code, _ = repo.run("file", "--pr", str(PR), "--drafts", drafts, "--token", token)
        assert code == todos.CANNOT_RUN
        assert "cannot open doc.md for writing" in repo.err
        assert github.posts() == 0


@pytest.mark.spec("report-cmd-keeps-review-suggestions")
class DescribeSuggestionsInDrafts:
    def it_refuses_an_issue_draft_that_leaves_out_the_suggestion(self, repo, review, comments):
        repo.write("doc.md", DOC)
        repo.commit()
        made = comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One."))
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.draft(todo, body="Too wordy.")])
        code, env = repo.run("report", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.PROBLEMS
        [error] = env["errors"]
        assert error.startswith("draft 1: its body leaves out the wording")
        assert made["html_url"] in error

    def it_files_an_issue_that_keeps_the_suggestion_and_writes_no_file(
        self, repo, review, comments, github
    ):
        repo.write("doc.md", DOC)
        repo.commit()
        comments.add("doc.md", 3, repo.head(), suggesting("wordy", "One."))
        [todo] = scan_pr(repo)["data"]["todos"]
        drafts = repo.drafts([repo.draft(todo)])
        token = pr_token(repo, drafts)
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts, "--token", token)
        assert code == todos.OK, repo.err
        assert repo.read("doc.md") == DOC.encode()
        assert env["data"]["suggested"] == []
        assert "```suggestion\nOne.\n```" in github.issues[0]["body"]


@pytest.fixture
def other_review(repo, github, comments):
    """The repo's branch as the head of PR, a pull request whose diff does
    not change any prose-style.md. Returns the pull request."""
    files = ("README.md", "docs/prose-style.md.orig", "prose-style.txt")
    pull = github.add_pull(PR, branch_of(repo), files=files)
    github.reviews[PR] = comments.made
    return pull


@pytest.mark.spec("scan-cmd-tells-prose-pr")
class DescribeProsePullRequest:
    def it_says_a_pull_request_that_changes_a_prose_style_file_is_about_prose(
        self, repo, github, comments
    ):
        github.add_pull(PR, branch_of(repo), comments.made, files=("a/b/prose-style.md",))
        assert scan_pr(repo)["data"]["pull_request"]["prose"] is True

    def it_says_a_pull_request_that_changes_no_prose_style_file_is_not(self, repo, other_review):
        assert scan_pr(repo)["data"]["pull_request"]["prose"] is False

    def it_says_so_in_human_output(self, repo, other_review):
        code, out, _ = repo.human("scan", "--pr", str(PR))
        assert code == todos.OK
        assert "#%d does not change a prose-style.md" % PR in out


def review_doc(repo, comments, body="TODO(prose): wordy"):
    """Commit DOC and leave one review comment on its line 3. Returns the
    TODO scan gives for it."""
    repo.write("doc.md", DOC)
    repo.commit()
    comments.add("doc.md", 3, repo.head(), body)
    [todo] = scan_pr(repo)["data"]["todos"]
    return todo


@pytest.mark.spec("report-cmd-holds-prose-from-pr")
class DescribeProseFromOtherPullRequest:
    def it_refuses_a_prose_todo_routed_to_a_skill(self, repo, other_review, comments):
        todo = review_doc(repo, comments)
        drafts = repo.drafts([repo.skill(todo)])
        code, env = repo.run("report", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.PROBLEMS
        [error] = env["errors"]
        assert error.startswith("draft 1:")
        assert "does not change a prose-style.md" in error
        assert "Route it to `issue`, with `skill`" in error

    def it_refuses_it_in_file_and_hands_off_nothing(self, repo, other_review, comments, github):
        todo = review_doc(repo, comments)
        drafts = repo.drafts([repo.skill(todo)])
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.PROBLEMS
        assert env["data"]["handoffs"] == []
        assert github.replies == []

    def it_hands_off_a_todo_of_another_kind(self, repo, other_review, comments):
        todo = review_doc(repo, comments, "TODO(change): split the step")
        drafts = repo.drafts([repo.skill(todo)])
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        assert [h["skill"] for h in env["data"]["handoffs"]] == ["example:learn-prose-rules"]

    def it_hands_off_a_prose_todo_from_a_pull_request_about_prose(self, repo, review, comments):
        todo = review_doc(repo, comments)
        drafts = repo.drafts([repo.skill(todo)])
        code, env = repo.run("file", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        assert len(env["data"]["handoffs"]) == 1


SKILL = "example:learn-prose-rules"


@pytest.mark.spec("file-cmd-files-handoff-issue")
class DescribeHandoffIssues:
    def it_adds_the_handoff_to_the_body_the_report_shows(self, repo, other_review, comments):
        todo = review_doc(repo, comments, "TODO(prose): wordy\nSay it once.")
        drafts = repo.drafts(
            [repo.draft(todo, body="For a skill that learns prose rules.", skill=SKILL)]
        )
        code, env = repo.run("report", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        [row] = env["data"]["drafts"]
        body = row["body"]
        assert body.startswith("For a skill that learns prose rules.\n\n")
        assert "Hand-off to `%s`" % SKILL in body
        assert "branch `%s`" % branch_of(repo) in body
        assert "commit `%s`" % repo.head() in body
        assert todos.HANDOFF_LEAD in body
        assert "## Note: wordy" in body
        assert "> Say it once." in body
        assert "- **File:** `doc.md`" in body
        assert "- **Lines:** 3-3" in body
        assert "- **Lines changed since the last commit:** none" in body
        assert comments.made[0]["html_url"] in body
        assert "First paragraph." in body
        report = Path(env["data"]["report"]).read_text()
        assert "Hand-off to `%s`" % SKILL in report

    def it_files_the_body_the_report_showed_and_names_the_issue_in_the_reply(
        self, repo, other_review, comments, github
    ):
        todo = review_doc(repo, comments)
        drafts = repo.drafts([repo.draft(todo, body="Later.", skill=SKILL)])
        code, env = repo.run("report", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.OK, repo.err
        shown = env["data"]["drafts"][0]["body"]
        code, env = file_pr(repo, drafts, "--reply-lead", "**Claude:**")
        assert code == todos.OK, repo.err
        assert github.issues[0]["body"] == shown
        assert env["data"]["handoffs"] == []
        [reply] = thread(github, comments.made[0])
        assert reply.startswith("**Claude:** TODO-HANDLED(#1):")

    def it_leaves_a_suggestion_in_the_body_and_unwritten(
        self, repo, other_review, comments, github
    ):
        todo = review_doc(repo, comments, suggesting("wordy", "One."))
        drafts = repo.drafts([repo.draft(todo, skill=SKILL)])
        code, env = file_pr(repo, drafts)
        assert code == todos.OK, repo.err
        assert repo.read("doc.md") == DOC.encode()
        assert env["data"]["suggested"] == []
        assert "```suggestion\nOne.\n```" in github.issues[0]["body"]

    def it_refuses_a_skill_without_words(self, repo, other_review, comments):
        todo = review_doc(repo, comments)
        drafts = repo.drafts([repo.draft(todo, skill=" ")])
        code, env = repo.run("report", "--pr", str(PR), "--drafts", drafts)
        assert code == todos.PROBLEMS
        assert env["errors"] == ["draft 1 has a `skill` that is not a string with words in it"]

"""TODOs left in another worktree of the repository: how `scan` names the
worktree, and how `--from` reads it and marks the TODOs there."""

import json
import os
import shlex
import shutil
import subprocess

import pytest

import todos

# The branch conftest's worktree fixture checks out.
BRANCH = "review"


def real(path):
    return os.path.realpath(str(path))


def branch_of(tree):
    return tree.git("branch", "--show-current").decode().strip()


@pytest.mark.spec("scan-cmd-names-worktrees-with-todos")
class DescribeOtherWorktrees:
    def it_names_a_worktree_holding_todos_and_exits_with_problems(self, repo, worktree):
        worktree.write("a.py", "# TODO: left in the other checkout\n")
        worktree.write("b.md", "TODO: and here\n")
        code, env = repo.run("scan")
        assert code == todos.PROBLEMS
        [tree] = env["data"]["other_worktrees"]
        assert real(tree["root"]) == real(worktree.root)
        assert tree["branch"] == BRANCH
        assert tree["files"] == ["a.py", "b.md"]
        [error] = env["errors"]
        assert "on %s" % BRANCH in error
        assert "a.py, b.md" in error
        assert "`scan --from %s`" % shlex.quote(tree["root"]) in error

    def it_says_so_on_stderr_in_human_output(self, repo, worktree):
        worktree.write("a.py", "# TODO: left in the other checkout\n")
        code, out, err = repo.human("scan")
        assert code == todos.PROBLEMS
        assert "No pending TODOs" in out
        assert "scan --from" in err
        assert "scan --from" not in out

    def it_leaves_out_a_worktree_without_a_todo(self, repo, worktree):
        worktree.write("a.py", "x = 1\n")
        code, env = repo.run("scan")
        assert code == todos.OK
        assert env["data"]["other_worktrees"] == []

    def it_does_not_look_elsewhere_when_this_tree_holds_a_todo(self, repo, worktree):
        repo.write("here.py", "# TODO: here\n")
        worktree.write("a.py", "# TODO: there\n")
        code, env = repo.run("scan")
        assert code == todos.OK
        assert env["data"]["other_worktrees"] == []

    def it_names_a_detached_worktree_without_a_branch(self, repo, tmp_path):
        root = tmp_path / "detached"
        repo.git("worktree", "add", "-q", "--detach", str(root))
        (root / "a.py").write_text("# TODO: detached\n")
        code, env = repo.run("scan")
        assert code == todos.PROBLEMS
        assert env["data"]["other_worktrees"][0]["branch"] is None
        assert ", on " not in env["errors"][0]

    def it_skips_a_worktree_whose_folder_is_gone(self, repo, worktree):
        worktree.write("a.py", "# TODO: there\n")
        shutil.rmtree(str(worktree.root))
        code, env = repo.run("scan")
        assert code == todos.OK
        assert env["data"]["other_worktrees"] == []

    def it_skips_the_bare_repository_its_worktrees_share(self, repo, tmp_path, todo_repo):
        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "-q", "--bare", str(repo.root), str(bare)],
            check=True,
            capture_output=True,
        )
        here, there = tmp_path / "here", tmp_path / "there"
        for root in (here, there):
            subprocess.run(
                ["git", "-C", str(bare), "worktree", "add", "-q", "--detach", str(root)],
                check=True,
                capture_output=True,
            )
        (there / "a.py").write_text("# TODO: there\n")
        code, env = todo_repo(here).run("scan")
        assert code == todos.PROBLEMS
        assert [real(t["root"]) for t in env["data"]["other_worktrees"]] == [real(there)]


@pytest.mark.spec("scan-cmd-reports-nothing-pending")
class DescribeNothingPendingAnywhere:
    def it_exits_ok_when_no_worktree_holds_a_todo(self, repo, worktree):
        code, out, err = repo.human("scan")
        assert code == todos.OK
        assert "No pending TODOs" in out
        assert err == ""


@pytest.mark.spec("command-reads-other-worktree-with-from")
class DescribeFrom:
    def it_scans_the_worktree_named(self, repo, worktree):
        worktree.write("a.py", "# TODO: there\n")
        code, env = repo.run("scan", "--from", str(worktree.root))
        assert code == todos.OK
        assert [(t["file"], t["title"]) for t in env["data"]["todos"]] == [("a.py", "there")]
        assert env["data"]["other_worktrees"] == []

    def it_does_not_name_other_worktrees_when_the_one_named_is_empty(self, repo, worktree):
        repo.write("here.py", "# TODO: here\n")
        code, env = repo.run("scan", "--from", str(worktree.root))
        assert code == todos.OK
        assert env["data"]["todos"] == []
        assert env["data"]["other_worktrees"] == []

    def it_scans_the_worktree_whose_branch_is_named(self, repo, worktree):
        worktree.write("a.py", "# TODO: there\n")
        code, env = repo.run("scan", "--from", BRANCH)
        assert code == todos.OK, repo.err
        assert [t["title"] for t in env["data"]["todos"]] == ["there"]

    @pytest.mark.parametrize("by", ["folder", "branch"])
    def it_reads_this_tree_as_with_no_from_when_named(self, repo, worktree, by):
        worktree.write("a.py", "# TODO: there\n")
        name = str(repo.root) if by == "folder" else branch_of(repo)
        code, env = repo.run("scan", "--from", name)
        assert code == todos.PROBLEMS
        assert env["data"]["todos"] == []
        assert [real(t["root"]) for t in env["data"]["other_worktrees"]] == [real(worktree.root)]

    def it_reports_drafts_against_the_worktree_named(self, repo, worktree):
        worktree.write("a.py", "# TODO: there\n")
        [todo] = worktree.scan()[0]
        drafts = repo.drafts([repo.draft(todo)])
        code, env = repo.run("report", "--drafts", drafts, "--from", str(worktree.root))
        assert code == todos.OK, repo.err
        assert [r["file"] for r in env["data"]["drafts"]] == ["a.py"]
        assert env["data"]["token"]

    def it_asks_about_the_todos_of_the_worktree_named(self, repo, worktree):
        worktree.write("a.py", "# TODO: there\n")
        batch = repo.root.parent / "questions.json"
        q = {
            "question": "Bug?",
            "options": [{"label": "Yes"}],
            "todos": [{"file": "a.py", "line": 1}],
        }
        batch.write_text(json.dumps([q]))
        code, env = repo.run("questions", "--batch", str(batch), "--from", str(worktree.root))
        assert code == todos.OK, repo.err
        assert env["data"]["page"] == str(repo.root / todos.QUESTIONS_FILE)
        assert "- `a.py:1` there\n" in (repo.root / todos.QUESTIONS_FILE).read_text(
            encoding="utf-8"
        )
        assert not (worktree.root / todos.QUESTIONS_FILE).exists()

    def it_refuses_a_draft_for_this_tree_when_reading_another(self, repo, worktree):
        repo.write("here.py", "# TODO: here\n")
        drafts = repo.draft_all()
        code, env = repo.run("report", "--drafts", drafts, "--from", str(worktree.root))
        assert code == todos.PROBLEMS
        assert "here.py:1 does not hold a pending TODO" in env["errors"][0]


@pytest.mark.spec("file-cmd-marks-other-worktree-with-from")
class DescribeFileFrom:
    def it_marks_the_todo_in_the_worktree_named(self, repo, worktree, github):
        worktree.write("a.py", "x = 1\n")
        worktree.commit()
        worktree.write("a.py", "# TODO: there\nx = 1\n")
        [todo] = worktree.scan()[0]
        drafts = repo.drafts([repo.draft(todo)])
        source = ("--from", str(worktree.root))
        code, env = repo.run("report", "--drafts", drafts, *source)
        assert code == todos.OK, repo.err
        code, env = repo.run("file", "--drafts", drafts, "--token", env["data"]["token"], *source)
        assert code == todos.OK, repo.err
        assert [i["title"] for i in github.issues] == ["there"]
        assert worktree.read("a.py") == b"# TODO-HANDLED(#1): there\nx = 1\n"
        assert repo.git("status", "--porcelain") == b""


@pytest.mark.spec("command-refuses-unknown-from-worktree")
class DescribeUnknownWorktree:
    @pytest.mark.parametrize("command", ["scan", "report", "file"])
    def it_names_a_folder_that_is_not_a_worktree_and_cannot_run(
        self, repo, tmp_path, command, github, git_init
    ):
        elsewhere = tmp_path / "elsewhere"
        git_init(elsewhere)
        argv = [command, "--from", str(elsewhere)]
        if command != "scan":
            argv += ["--drafts", repo.drafts([])]
        if command == "file":
            argv += ["--token", "0" * todos.TOKEN_LENGTH]
        code, env = repo.run(*argv)
        assert code == todos.CANNOT_RUN
        assert env is None
        assert str(elsewhere) in repo.err
        assert "is neither a worktree of this repository" in repo.err
        assert github.posts() == 0

    def it_lists_the_worktrees_with_their_branches(self, repo, worktree):
        code, _ = repo.run("scan", "--from", "reveiw")
        assert code == todos.CANNOT_RUN
        assert "reveiw is neither" in repo.err
        assert "%s on %s (this tree);" % (repo.root, branch_of(repo)) in repo.err
        assert "%s on %s" % (worktree.root, BRANCH) in repo.err

    def it_says_a_worktree_is_detached(self, repo, tmp_path):
        root = tmp_path / "detached"
        repo.git("worktree", "add", "-q", "--detach", str(root))
        code, _ = repo.run("scan", "--from", "nowhere")
        assert code == todos.CANNOT_RUN
        assert "%s (detached)" % root in repo.err


@pytest.mark.spec("file-cmd-prints-handoffs")
class DescribeTheHandoffFrom:
    @staticmethod
    def approved(repo, tree, name):
        """`file`'s arguments for a prose TODO in tree, routed to a skill and
        read with --from name."""
        tree.write("a.md", "<!-- TODO(prose): too long -->\nSome text.\n")
        [todo] = tree.scan()[0]
        drafts = repo.drafts([repo.skill(todo)])
        code, env = repo.run("report", "--drafts", drafts, "--from", name)
        assert code == todos.OK, repo.err
        return ("file", "--drafts", drafts, "--token", env["data"]["token"], "--from", name)

    def it_names_the_checkout_the_passage_was_read_in(self, repo, worktree):
        code, env = repo.run(*self.approved(repo, worktree, BRANCH))
        assert code == todos.OK, repo.err
        [handoff] = env["data"]["handoffs"]
        assert real(handoff["checkout"]["root"]) == real(worktree.root)
        assert handoff["checkout"]["branch"] == BRANCH

    def it_names_the_checkout_in_text(self, repo, worktree):
        code, out, err = repo.human(*self.approved(repo, worktree, BRANCH))
        assert code == todos.OK, err
        expected = "hand-off to example:learn-prose-rules\n  read in %s, on %s\n"
        assert expected % (worktree.root, BRANCH) in out

    def it_names_a_detached_checkout_without_a_branch_in_text(self, repo, tmp_path, todo_repo):
        root = tmp_path / "detached"
        repo.git("worktree", "add", "-q", "--detach", str(root))
        code, out, err = repo.human(*self.approved(repo, todo_repo(root), str(root)))
        assert code == todos.OK, err
        assert "  read in %s\n" % root in out


@pytest.mark.spec("report-cmd-writes-report-file")
class DescribeTheReportFileUnderFrom:
    def it_writes_the_report_in_this_tree(self, repo, worktree):
        worktree.write("a.py", "# TODO: there\n")
        [todo] = worktree.scan()[0]
        drafts = repo.drafts([repo.draft(todo)])
        code, env = repo.run("report", "--drafts", drafts, "--from", str(worktree.root))
        assert code == todos.OK, repo.err
        assert env["data"]["report"] == str(repo.root / todos.REPORT_FILE)
        assert "`a.py:1`" in (repo.root / todos.REPORT_FILE).read_text(encoding="utf-8")
        assert not (worktree.root / todos.REPORT_FILE).exists()

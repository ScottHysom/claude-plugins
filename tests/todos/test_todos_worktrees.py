"""TODOs left in another worktree of the repository: how `scan` names the
worktree, and how `--from` reads it and removes the TODOs there."""

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


@pytest.mark.spec("scan-cmd-names-other-worktrees")
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


@pytest.mark.spec("command-reads-other-worktree")
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

    def it_reports_drafts_against_the_worktree_named(self, repo, worktree):
        worktree.write("a.py", "# TODO: there\n")
        [todo] = worktree.scan()[0]
        drafts = repo.drafts([repo.draft(todo)])
        code, env = repo.run("report", "--drafts", drafts, "--from", str(worktree.root))
        assert code == todos.OK, repo.err
        assert [r["file"] for r in env["data"]["drafts"]] == ["a.py"]
        assert env["data"]["token"]

    def it_refuses_a_draft_for_this_tree_when_reading_another(self, repo, worktree):
        repo.write("here.py", "# TODO: here\n")
        drafts = repo.draft_all()
        code, env = repo.run("report", "--drafts", drafts, "--from", str(worktree.root))
        assert code == todos.PROBLEMS
        assert "here.py:1 does not hold a pending TODO" in env["errors"][0]


@pytest.mark.spec("file-cmd-removes-from-other-worktree")
class DescribeFileFrom:
    def it_removes_the_todo_from_the_worktree_named(self, repo, worktree, github):
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
        assert worktree.read("a.py") == b"x = 1\n"
        assert worktree.git("status", "--porcelain") == b""
        assert repo.git("status", "--porcelain") == b""


@pytest.mark.spec("command-refuses-unknown-worktree")
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
        assert "is not another worktree of this repository" in repo.err
        assert github.posts() == 0

    def it_refuses_this_tree_itself(self, repo, worktree):
        code, _ = repo.run("scan", "--from", str(repo.root))
        assert code == todos.CANNOT_RUN
        assert "is not another worktree" in repo.err

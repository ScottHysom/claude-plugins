"""Learning from edits that sit in another checkout of the same repository.

The Claude Code desktop app opens a session in a fresh worktree, while the
author's edits sit uncommitted in the main checkout. evidence names that
checkout, and carry copies its pending files into the session's tree, so the
run finishes where the session can write.
"""

import os
import subprocess

import pytest

import prose

MAIN_BRANCH = "prose-changes"
SESSION_BRANCH = "session"


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def snapshot(root):
    """{relative path: bytes} for every file under root but .git."""
    out = {}
    for folder, dirs, files in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, str(root))] = fh.read()
    return out


@pytest.fixture
def checkouts(prose_repo, tmp_path, capsys):
    """(main, session): the author's checkout, and a worktree opened from it.

    main is the prose_repo, committed and on its own branch. session is a
    linked worktree on a branch of its own, made from the same commit, as the
    desktop app makes one.
    """
    prose_repo.commit()
    git(prose_repo.root, "checkout", "-q", "-b", MAIN_BRANCH)
    root = tmp_path / "session"
    git(prose_repo.root, "worktree", "add", "-q", "-b", SESSION_BRANCH, str(root))
    # The fixture's own class, so the session runs commands the same way.
    return prose_repo, type(prose_repo)(root, capsys)


def edit(tree, rel="target.md", text="Rewritten by the author.\n"):
    """Write an uncommitted edit into tree, a checkout's root folder."""
    path = tree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


class DescribeWorktrees:
    """Repo.worktrees, which evidence and carry both read."""

    @pytest.mark.spec("evidence-cmd-names-other-worktrees")
    def it_lists_every_other_worktree_with_its_branch(self, checkouts, tmp_path):
        main, session = checkouts
        detached = tmp_path / "detached"
        git(main.root, "worktree", "add", "-q", "--detach", str(detached))
        trees = prose.Repo(str(session.root)).worktrees()
        assert sorted((os.path.realpath(r), b) for r, b in trees) == sorted(
            [
                (os.path.realpath(str(main.root)), MAIN_BRANCH),
                (os.path.realpath(str(detached)), None),
            ]
        )

    @pytest.mark.spec("evidence-cmd-names-other-worktrees")
    def it_leaves_out_a_worktree_whose_folder_is_gone(self, checkouts, tmp_path):
        main, session = checkouts
        gone = tmp_path / "gone"
        git(main.root, "worktree", "add", "-q", "--detach", str(gone))
        subprocess.run(["rm", "-rf", str(gone)], check=True)
        roots = [os.path.realpath(r) for r, _ in prose.Repo(str(session.root)).worktrees()]
        assert roots == [os.path.realpath(str(main.root))]

    @pytest.mark.spec("evidence-cmd-names-other-worktrees")
    def it_leaves_out_a_bare_repository(self, checkouts, tmp_path):
        main, _ = checkouts
        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "-q", "--bare", str(main.root), str(bare)],
            check=True,
            capture_output=True,
        )
        tree = tmp_path / "from-bare"
        git(bare, "worktree", "add", "-q", "--detach", str(tree))
        assert prose.Repo(str(tree)).worktrees() == []


class DescribeEvidenceAcrossWorktrees:
    @pytest.mark.spec("evidence-cmd-names-other-worktrees")
    def it_names_the_worktree_that_holds_the_edits_when_this_tree_holds_none(self, checkouts):
        main, session = checkouts
        edit(main.root)
        code, env = session.run("evidence")
        assert code == prose.PROBLEMS
        [tree] = env["data"]["other_worktrees"]
        assert os.path.realpath(tree["root"]) == os.path.realpath(str(main.root))
        assert (tree["branch"], tree["files"]) == (MAIN_BRANCH, ["target.md"])
        [error] = env["errors"]
        assert "on %s," % MAIN_BRANCH in error
        assert "`carry --from %s`" % tree["root"] in error

    @pytest.mark.spec("evidence-cmd-names-other-worktrees")
    def it_names_a_detached_worktree_without_a_branch(self, checkouts, tmp_path):
        main, session = checkouts
        detached = tmp_path / "detached"
        git(main.root, "worktree", "add", "-q", "--detach", str(detached))
        edit(detached)
        code, env = session.run("evidence")
        assert code == prose.PROBLEMS
        [error] = env["errors"]
        assert " on " not in error.split(" holds them ")[0]

    @pytest.mark.spec("evidence-cmd-names-other-worktrees")
    def it_looks_no_further_when_this_tree_holds_edits(self, checkouts):
        main, session = checkouts
        edit(main.root)
        edit(session.root, text="The session's own edit.\n")
        code, env = session.run("evidence")
        assert code == prose.OK, env["errors"]
        assert env["data"]["other_worktrees"] == []

    @pytest.mark.spec("evidence-cmd-names-other-worktrees")
    def it_passes_when_no_worktree_holds_edits(self, checkouts):
        _, session = checkouts
        code, env = session.run("evidence")
        assert code == prose.OK, env["errors"]
        assert env["data"]["other_worktrees"] == []


class DescribeCarry:
    @pytest.mark.spec("carry-cmd-copies-pending-files")
    def it_copies_each_pending_file_byte_for_byte(self, checkouts):
        main, session = checkouts
        edit(main.root, text="Line one.\r\nLine two, with no newline at the end")
        edit(main.root, rel="notes/new.md", text="A document the author started.\n")
        edit(main.root, rel="README.md", text="Out of scope, so it stays behind.\n")
        code, env = session.run("carry", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert sorted(env["data"]["files"]) == ["notes/new.md", "target.md"]
        assert env["data"]["branch"] == MAIN_BRANCH
        assert env["data"]["written"] is True
        for rel in ("target.md", "notes/new.md"):
            assert (session.root / rel).read_bytes() == (main.root / rel).read_bytes()
        assert not (session.root / "README.md").exists()

    @pytest.mark.spec("carry-cmd-copies-pending-files")
    def it_copies_prose_style_md_when_the_author_edited_it(self, checkouts):
        main, session = checkouts
        rules = main.read(prose.CONFIG_PATH) + "\nA note the author added.\n"
        edit(main.root, rel=prose.CONFIG_PATH, text=rules)
        code, env = session.run("carry", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert env["data"]["files"] == [prose.CONFIG_PATH]
        assert session.read(prose.CONFIG_PATH) == rules

    @pytest.mark.spec("carry-cmd-copies-pending-files")
    def it_names_a_worktree_with_nothing_to_carry(self, checkouts):
        main, session = checkouts
        code, env = session.run("carry", "--from", str(main.root))
        assert code == prose.PROBLEMS
        assert "does not hold any pending edits to carry" in env["errors"][0]

    @pytest.mark.spec("carry-cmd-copies-pending-files")
    def it_tells_a_person_where_the_originals_stay(self, checkouts, capsys):
        main, session = checkouts
        edit(main.root)
        capsys.readouterr()
        code = prose.main(["carry", "--from", str(main.root), "-C", str(session.root)])
        out = capsys.readouterr().out
        assert code == prose.OK
        assert "carried target.md" in out
        assert (
            "the originals stay in %s, on %s" % (os.path.realpath(str(main.root)), MAIN_BRANCH)
            in out
        )

    @pytest.mark.spec("carry-cmd-refuses-different-base")
    def it_refuses_a_file_that_differs_between_the_last_commits(self, checkouts):
        main, session = checkouts
        edit(session.root, text="Committed on the session's branch.\n")
        session.commit()
        edit(main.root)
        before = snapshot(session.root)
        code, env = session.run("carry", "--from", str(main.root))
        assert code == prose.PROBLEMS
        assert "target.md differs between the two trees' last commits" in env["errors"][0]
        assert env["data"]["written"] is False
        assert snapshot(session.root) == before

    @pytest.mark.spec("carry-cmd-refuses-dirty-target")
    def it_writes_nothing_when_a_file_has_changes_here(self, checkouts):
        main, session = checkouts
        edit(main.root)
        edit(main.root, rel="notes/new.md", text="A document the author started.\n")
        edit(session.root, text="The session's own edit.\n")
        before = snapshot(session.root)
        code, env = session.run("carry", "--from", str(main.root))
        assert code == prose.PROBLEMS
        [error] = env["errors"]
        assert error.startswith("target.md has uncommitted changes here")
        assert snapshot(session.root) == before

    @pytest.mark.spec("carry-cmd-refuses-unknown-worktree")
    def it_refuses_a_folder_that_is_not_another_worktree(self, checkouts, tmp_path):
        _, session = checkouts
        stranger = tmp_path / "stranger"
        subprocess.run(["git", "init", "-q", str(stranger)], check=True, capture_output=True)
        for source in (stranger, session.root):
            code, env = session.run("carry", "--from", str(source))
            assert (code, env) == (prose.CANNOT_RUN, None)
            assert "is not another worktree of this repository" in session.err

    @pytest.mark.spec("carry-cmd-honors-dry-run")
    def it_lists_what_it_would_copy_and_writes_nothing(self, checkouts, capsys):
        main, session = checkouts
        edit(main.root)
        before = snapshot(session.root)
        code, env = session.run("carry", "--from", str(main.root), "--dry-run")
        assert code == prose.OK, env["errors"]
        assert (env["data"]["files"], env["data"]["written"]) == (["target.md"], False)
        assert snapshot(session.root) == before
        prose.main(["carry", "--from", str(main.root), "--dry-run", "-C", str(session.root)])
        assert "would carry target.md" in capsys.readouterr().out

    @pytest.mark.spec("carry-cmd-writes-only-this-tree")
    def it_leaves_the_other_worktree_as_it_was(self, checkouts):
        main, session = checkouts
        edit(main.root)
        edit(main.root, rel="notes/new.md", text="A document the author started.\n")
        before, status = snapshot(main.root), git(main.root, "status", "--porcelain")
        code, env = session.run("carry", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert snapshot(main.root) == before
        assert git(main.root, "status", "--porcelain") == status

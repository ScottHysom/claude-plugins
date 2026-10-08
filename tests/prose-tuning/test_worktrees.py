"""Learning from edits that sit in another checkout of the same repository.

The Claude Code desktop app opens a session in a fresh worktree, while the
author's edits sit uncommitted in the main checkout. evidence names that
checkout, and evidence and reproduce read its edits in place with --from,
against the session's prose-style.md, so the rules land where the session can
write and the author's checkout is left as it was.
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


def open_checkouts(prose_repo, tmp_path, capsys):
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


@pytest.fixture
def checkouts(prose_repo, tmp_path, capsys):
    return open_checkouts(prose_repo, tmp_path, capsys)


def edit(tree, rel="target.md", text="Rewritten by the author.\n"):
    """Write an uncommitted edit into tree, a checkout's root folder."""
    path = tree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


class DescribeWorktrees:
    """Repo.worktrees, which evidence reads to name the other checkouts."""

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
        assert "`evidence --from %s`" % tree["root"] in error

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


# A rule with a pattern, and a document it rewrites, so reproduce has an edit
# to find. STYLE stands in for the session's rules.
STYLE = """---
name: Probe
---

## Register

### register-plain-words: Say it plainly

**Pattern.** `(?i)in order to`

> **Before.** In order to run it.
> **After.** To run it.
"""

RULE = "register-plain-words"

BEFORE = """# Notes

We run it in order to check the build.

It keeps the notes short, and the lists shorter.
"""

REPRODUCED = BEFORE.replace("in order to", "to")
UNREPRODUCED = REPRODUCED.replace("It keeps", "The rule keeps")


@pytest.fixture
def notes(prose_repo, tmp_path, capsys):
    """(main, session) as checkouts gives them, with BEFORE committed under STYLE."""
    (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
    (prose_repo.root / "notes.md").write_text(BEFORE)
    return open_checkouts(prose_repo, tmp_path, capsys)


def tree_state(root):
    """Every byte under root but .git, and what git reports as changed there."""
    return snapshot(root), git(root, "status", "--porcelain")


class DescribeEvidenceFrom:
    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_reads_the_edits_of_the_worktree_from_names(self, checkouts):
        main, session = checkouts
        edit(main.root)
        code, env = session.run("evidence", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        [rec] = env["data"]["inferred"]
        assert (rec["file"], rec["new_lines"]) == ("target.md", ["Rewritten by the author."])
        checkout = env["data"]["checkout"]
        assert os.path.realpath(checkout["root"]) == os.path.realpath(str(main.root))
        assert checkout["branch"] == MAIN_BRANCH
        assert env["data"]["other_worktrees"] == []

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_diffs_against_the_other_worktrees_last_commit(self, checkouts):
        main, session = checkouts
        edit(session.root, text="Committed on the session's branch.\n")
        session.commit()
        edit(main.root)
        code, env = session.run("evidence", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        [rec] = env["data"]["inferred"]
        assert "Committed on the session's branch." not in rec["old_lines"]

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_takes_the_branch_the_worktree_has_checked_out(self, checkouts):
        main, session = checkouts
        edit(main.root)
        code, env = session.run("evidence", "--from", MAIN_BRANCH)
        assert code == prose.OK, env["errors"]
        assert [r["file"] for r in env["data"]["inferred"]] == ["target.md"]

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_reads_the_explicit_markup_there(self, checkouts):
        main, session = checkouts
        edit(main.root, text="Kept <del>and cut</del> text.\n")
        code, env = session.run("evidence", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert [r["kind"] for r in env["data"]["explicit"]] == ["del"]

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_takes_the_scope_from_this_trees_rules(self, checkouts):
        main, session = checkouts
        scoped = session.read(prose.CONFIG_PATH).replace(
            "---\n", "---\nscope:\n  include:\n    - notes/**\n", 1
        )
        edit(session.root, rel=prose.CONFIG_PATH, text=scoped)
        edit(main.root)
        edit(main.root, rel="notes/new.md", text="A document the author started.\n")
        code, env = session.run("evidence", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert env["data"]["inferred"] == []
        assert env["data"]["new_files"] == ["notes/new.md"]

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_names_a_pending_prose_style_md_there_and_does_not_read_it(self, checkouts):
        main, session = checkouts
        edit(main.root)
        rules = main.read(prose.CONFIG_PATH) + "\nA note the author added.\n"
        edit(main.root, rel=prose.CONFIG_PATH, text=rules)
        code, env = session.run("evidence", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert [r["file"] for r in env["data"]["inferred"]] == ["target.md"]
        [warning] = env["warnings"]
        assert warning.startswith("%s has uncommitted changes in " % prose.CONFIG_PATH)
        assert "this run does not read them" in warning

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_keeps_the_other_worktrees_prose_style_md_out_of_scope(self, checkouts):
        main, session = checkouts
        scoped = session.read(prose.CONFIG_PATH).replace(
            "---\n", "---\nscope:\n  exclude:\n    - drafts/**\n", 1
        )
        edit(session.root, rel=prose.CONFIG_PATH, text=scoped)
        edit(main.root, rel=prose.CONFIG_PATH, text=main.read(prose.CONFIG_PATH) + "\nMore.\n")
        code, env = session.run("evidence", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert env["data"]["inferred"] == []

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_reads_this_tree_as_with_no_from(self, checkouts):
        main, session = checkouts
        edit(main.root)
        edit(session.root, text="The session's own edit.\n")
        for source in (str(session.root), SESSION_BRANCH):
            _, plain = session.run("evidence")
            code, env = session.run("evidence", "--from", source)
            assert code == prose.OK, env["errors"]
            assert env == plain
            assert env["data"]["checkout"] is None

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_tells_a_person_which_checkout_it_read(self, checkouts, capsys):
        main, session = checkouts
        edit(main.root)
        capsys.readouterr()
        prose.main(["evidence", "--from", str(main.root), "-C", str(session.root)])
        out = capsys.readouterr().out
        assert out.startswith("reading %s, on %s\n" % (main.root, MAIN_BRANCH))

    @pytest.mark.spec("evidence-cmd-reads-other-worktree")
    def it_names_a_detached_checkout_by_its_folder_alone(self, checkouts, tmp_path, capsys):
        main, session = checkouts
        detached = tmp_path / "detached"
        git(main.root, "worktree", "add", "-q", "--detach", str(detached))
        edit(detached)
        capsys.readouterr()
        prose.main(["evidence", "--from", str(detached), "-C", str(session.root)])
        assert capsys.readouterr().out.startswith("reading %s\nbase " % detached)


class DescribeReproduceFrom:
    @pytest.mark.spec("reproduce-cmd-reads-other-worktree")
    def it_checks_the_other_worktrees_edits_against_this_trees_rules(self, notes):
        main, session = notes
        edit(main.root, rel="notes.md", text=UNREPRODUCED)
        code, env = session.run("reproduce", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert [(e["file"], e["start"], e["reproduced"]) for e in env["data"]["edits"]] == [
            ("notes.md", 3, True),
            ("notes.md", 5, False),
        ]
        assert env["data"]["edits"][0]["matches"][0]["rule"] == RULE
        assert env["data"]["checkout"]["branch"] == MAIN_BRANCH

    @pytest.mark.spec("reproduce-cmd-reads-other-worktree")
    def it_diffs_against_the_other_worktrees_last_commit(self, notes):
        main, session = notes
        edit(session.root, rel="notes.md", text=UNREPRODUCED)
        session.commit()
        edit(main.root, rel="notes.md", text=REPRODUCED)
        code, env = session.run("reproduce", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert [(e["start"], e["reproduced"]) for e in env["data"]["edits"]] == [(3, True)]

    @pytest.mark.spec("reproduce-cmd-reads-other-worktree")
    def it_reads_this_trees_rules_not_the_other_worktrees(self, notes):
        main, session = notes
        edit(main.root, rel="notes.md", text=REPRODUCED)
        edit(main.root, rel=prose.CONFIG_PATH, text=STYLE.split("### register")[0])
        code, env = session.run("reproduce", "--from", str(main.root))
        assert code == prose.OK, env["errors"]
        assert [e["reproduced"] for e in env["data"]["edits"]] == [True]

    @pytest.mark.spec("reproduce-cmd-reads-other-worktree")
    def it_reads_this_tree_as_with_no_from(self, notes):
        main, session = notes
        edit(main.root, rel="notes.md", text=UNREPRODUCED)
        edit(session.root, rel="notes.md", text=REPRODUCED)
        _, plain = session.run("reproduce")
        code, env = session.run("reproduce", "--from", str(session.root))
        assert code == prose.OK, env["errors"]
        assert env == plain

    @pytest.mark.spec("reproduce-cmd-reads-other-worktree")
    def it_tells_a_person_which_checkout_it_read(self, notes, capsys):
        main, session = notes
        edit(main.root, rel="notes.md", text=REPRODUCED)
        capsys.readouterr()
        prose.main(["reproduce", "--from", MAIN_BRANCH, "-C", str(session.root)])
        out = capsys.readouterr().out
        assert out.startswith("reading %s, on %s\n" % (main.root, MAIN_BRANCH))


class DescribeUnknownWorktree:
    @pytest.mark.spec("command-refuses-unknown-worktree")
    @pytest.mark.parametrize("command", ["evidence", "reproduce"])
    def it_refuses_a_folder_or_branch_that_no_worktree_has(self, checkouts, tmp_path, command):
        main, session = checkouts
        stranger = tmp_path / "stranger"
        subprocess.run(["git", "init", "-q", str(stranger)], check=True, capture_output=True)
        for source in (str(stranger), "no-such-branch"):
            code, env = session.run(command, "--from", source)
            assert (code, env) == (prose.CANNOT_RUN, None)
            assert "is neither a worktree of this repository nor a branch" in session.err
            assert "%s on %s" % (main.root, MAIN_BRANCH) in session.err
            assert "(this tree)" in session.err

    @pytest.mark.spec("command-refuses-unknown-worktree")
    def it_lists_a_detached_worktree_as_detached(self, checkouts, tmp_path):
        main, session = checkouts
        detached = tmp_path / "detached"
        git(main.root, "worktree", "add", "-q", "--detach", str(detached))
        code, _ = session.run("evidence", "--from", "no-such-branch")
        assert code == prose.CANNOT_RUN
        assert "%s (detached)" % detached in session.err


class DescribeSourceCheckout:
    @pytest.mark.spec("command-never-writes-other-worktree")
    def it_leaves_the_other_worktree_as_it_was(self, notes):
        main, session = notes
        edit(main.root, rel="notes.md", text="We run it <del>in order </del>to check.\n")
        edit(main.root, rel="drafts/new.md", text="A document the author started.\n")
        before = tree_state(main.root)
        for command in ("evidence", "reproduce"):
            code, env = session.run(command, "--from", str(main.root))
            assert code == prose.OK, env["errors"]
            assert tree_state(main.root) == before

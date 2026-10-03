"""What `todos.py scan` reads, and how it locates each TODO it finds."""

import os
import subprocess

import pytest

import todos

# A file long enough that git still pairs it with its old path after a rename
# that adds a line.
LONG = "".join("line %d\n" % n for n in range(1, 21))


# What scan prints first, from the fake gh's labels.
LABELS_TEXT = (
    "Labels in owner/project:\n"
    "  bug  Something is broken\n"
    "  enhancement  New behavior\n"
    "  plugin:todos\n"
    "\n"
)


def titles(found):
    return [t["title"] for t in found]


@pytest.mark.spec("scan-cmd-reads-pending-lines")
class DescribePendingLines:
    def it_reads_a_line_added_to_a_tracked_file(self, repo):
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: new one\nx = 1\n")
        assert titles(repo.scan()[0]) == ["new one"]

    def it_does_not_read_a_todo_already_committed(self, repo):
        repo.write("a.py", "# TODO: old one\nx = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: old one\nx = 2\n")
        assert repo.scan() == ([], [])

    def it_reads_a_staged_change_and_a_staged_new_file(self, repo):
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "x = 1\n# TODO: staged\n")
        repo.write("b.py", "# TODO: added\n")
        repo.git("add", "-A")
        assert titles(repo.scan()[0]) == ["staged", "added"]

    def it_compares_a_renamed_file_with_its_old_path(self, repo):
        repo.write("old.txt", "TODO: committed\n" + LONG)
        repo.commit()
        repo.git("mv", "old.txt", "new.txt")
        repo.write("new.txt", "TODO: committed\n" + LONG + "TODO: after the rename\n")
        found, _ = repo.scan()
        assert [(t["file"], t["title"]) for t in found] == [("new.txt", "after the rename")]

    def it_does_not_read_a_removed_line_as_added(self, repo):
        repo.write("a.py", "x = 1\ny = 2\nz = 3\n")
        repo.commit()
        repo.write("a.py", "# TODO: one\nx = 1\nz = 3")
        (todo,), _ = repo.scan()
        assert todo["above"] == {"line": 2, "text": "x = 1", "base_line": 1}

    def it_reads_every_line_of_an_untracked_file(self, repo):
        repo.write("notes/new.txt", "TODO: first\nplain\nTODO: second\n")
        assert titles(repo.scan()[0]) == ["first", "second"]

    def it_skips_a_file_git_ignores(self, repo):
        repo.write(".gitignore", "build/\n")
        repo.commit()
        repo.write("build/out.txt", "TODO: ignored\n")
        assert repo.scan() == ([], [])

    def it_skips_a_deleted_file(self, repo):
        repo.write("a.py", "x = 1\n")
        repo.commit()
        os.remove(str(repo.root / "a.py"))
        assert repo.scan() == ([], [])

    def it_skips_a_symlink(self, repo):
        target = repo.root.parent / "outside.txt"
        target.write_text("TODO: through a link\n")
        os.symlink(str(target), str(repo.root / "link.txt"))
        assert repo.scan() == ([], [])

    def it_skips_a_repository_nested_inside(self, repo, git_init):
        git_init(repo.root / "sub")
        (repo.root / "sub" / "f.txt").write_text("TODO: in the nested repo\n")
        assert repo.scan() == ([], [])

    def it_does_not_read_line_endings_as_changes(self, repo):
        repo.write(".gitattributes", "*.txt eol=crlf\n")
        repo.write("a.txt", "TODO: committed\nx\n")
        repo.commit()
        os.remove(str(repo.root / "a.txt"))
        repo.git("checkout", "--", "a.txt")
        assert (repo.root / "a.txt").read_bytes() == b"TODO: committed\r\nx\r\n"
        repo.write("a.txt", b"TODO: committed\r\nx\r\nTODO: new\r\n")
        assert titles(repo.scan()[0]) == ["new"]

    def it_reads_the_last_commit_as_checkout_writes_it(self, repo):
        repo.write(".gitattributes", "*.txt ident\n")
        repo.write("a.txt", "TODO: committed $Id$\n")
        repo.commit()
        os.remove(str(repo.root / "a.txt"))
        repo.git("checkout", "--", "a.txt")
        expanded = (repo.root / "a.txt").read_text()
        assert expanded.startswith("TODO: committed $Id: ")
        repo.write("a.txt", expanded + "a new line\n")
        assert repo.scan() == ([], [])

    def it_does_not_read_a_line_whose_ending_alone_changed(self, repo):
        repo.write("a.txt", b"TODO: committed\nx\n")
        repo.commit()
        repo.write("a.txt", b"TODO: committed\r\nx\r\n")
        assert repo.scan() == ([], [])

    @pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
    def it_warns_and_skips_a_file_it_cannot_read(self, repo):
        path = repo.write("secret.txt", "TODO: unreadable\n")
        path.chmod(0)
        try:
            found, warnings = repo.scan()
        finally:
            path.chmod(0o644)
        assert found == []
        assert len(warnings) == 1
        assert warnings[0].startswith("secret.txt: cannot read")


@pytest.mark.spec("scan-cmd-skips-binary-files")
class DescribeBinaryFiles:
    def it_skips_an_untracked_file_git_reads_as_binary(self, repo):
        repo.write("blob.bin", b"TODO: in a binary\n\0\n")
        assert repo.scan() == ([], [])

    def it_skips_a_changed_tracked_binary_file(self, repo):
        repo.write("blob.bin", b"\0\n")
        repo.commit()
        repo.write("blob.bin", b"\0\nTODO: in a binary\n")
        assert repo.scan() == ([], [])

    def it_skips_a_text_file_marked_binary_by_attributes(self, repo):
        repo.write(".gitattributes", "*.dat binary\n")
        repo.commit()
        repo.write("x.dat", "TODO: marked binary\n")
        assert repo.scan() == ([], [])


@pytest.mark.spec("scan-cmd-reports-nothing-pending")
class DescribeNothingPending:
    def it_says_so_and_exits_ok(self, repo):
        code, out, err = repo.human("scan")
        assert code == todos.OK
        assert out == LABELS_TEXT + "No pending TODOs in the changes since %s.\n" % repo.head()[:7]
        assert err == ""

    def it_gives_an_empty_list_in_json(self, repo):
        repo.write("a.txt", "no notes here\n")
        code, env = repo.run("scan")
        assert code == todos.OK
        assert env["ok"] is True
        assert env["data"]["todos"] == []


@pytest.mark.spec("scan-cmd-locates-each-todo")
class DescribeLocation:
    def it_gives_the_file_lines_and_the_line_below(self, repo):
        repo.write("run.py", "import os\n\ndef run(repo):\n    pass\n")
        repo.commit()
        repo.write(
            "run.py",
            "import os\n\n# TODO(bug): run() waits forever\n# no timeout\ndef run(repo):\n"
            "    pass\n",
        )
        (todo,), _ = repo.scan()
        assert (todo["file"], todo["first"], todo["last"]) == ("run.py", 3, 4)
        assert todo["above"] == {"line": 5, "text": "def run(repo):", "base_line": 3}

    def it_gives_no_old_number_for_a_line_below_that_is_new(self, repo):
        repo.write("a.py", "# TODO: first\nx = 1\n")
        (todo,), _ = repo.scan()
        assert todo["above"] == {"line": 2, "text": "x = 1", "base_line": None}

    def it_looks_past_blank_lines_and_other_todos(self, repo):
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: one\n\n# TODO: two\n\nx = 1\n")
        found, _ = repo.scan()
        assert [t["above"] for t in found] == [{"line": 5, "text": "x = 1", "base_line": 1}] * 2

    def it_gives_nothing_below_a_todo_at_the_end_of_a_file(self, repo):
        repo.write("a.py", "x = 1\n# TODO: last\n\n")
        (todo,), _ = repo.scan()
        assert todo["above"] is None

    def it_gives_the_last_commit_and_that_no_remote_holds_it(self, repo):
        code, env = repo.run("scan")
        assert code == todos.OK
        assert env["data"]["commit"] == {"hash": repo.head(), "on_remote": False}

    def it_says_when_a_remote_branch_holds_the_last_commit(self, repo, tmp_path):
        remote = tmp_path / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        repo.git("remote", "add", "origin", str(remote))
        repo.git("push", "-q", "origin", "HEAD:refs/heads/main")
        _, env = repo.run("scan")
        assert env["data"]["commit"]["on_remote"] is True

    @pytest.mark.spec("repo:command-splits-output-streams")
    def it_prints_each_todo_on_stdout_and_warnings_on_stderr(self, repo):
        repo.write("run.py", "def run():\n    pass\n")
        repo.commit()
        repo.write(
            "run.py",
            "# TODO(bug): hangs\n# no timeout\n#\n# at all\ndef run():\n    pass\n# TODO: last\n"
            "x = 1  # TODO: trailing\n",
        )
        code, out, err = repo.human("scan")
        short = repo.head()[:7]
        assert code == todos.OK
        assert out == LABELS_TEXT + (
            "run.py:1-4: (bug) hangs\n"
            "    no timeout\n"
            "\n"
            "    at all\n"
            "    above line 5 (line 1 at %s): def run():\n"
            "run.py:7: last\n"
            "    above line 8 (new): x = 1  # TODO: trailing\n"
            "Last commit %s, not on any remote branch.\n" % (short, short)
        )
        assert err.startswith("warning: run.py:8: ")

    def it_says_in_text_when_a_remote_holds_the_commit(self, repo, tmp_path):
        remote = tmp_path / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        repo.git("remote", "add", "origin", str(remote))
        repo.git("push", "-q", "origin", "HEAD:refs/heads/main")
        repo.write("a.py", "# TODO: one\n")
        _, out, _ = repo.human("scan")
        assert out.endswith("on a remote branch.\n")
        assert "above" not in out

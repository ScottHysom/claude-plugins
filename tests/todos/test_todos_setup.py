"""What `todos.py setup` puts in the project, and what scan then leaves out."""

import hashlib

import pytest

import todos


@pytest.mark.spec("setup-cmd-copies-locally")
class DescribeTheCopy:
    def it_copies_the_script_byte_for_byte(self, repo, script_path):
        code, env = repo.run("setup")
        assert code == todos.OK
        with open(script_path, "rb") as fh:
            assert repo.read(".todos/todos.py") == fh.read()

    def it_gives_the_prefix_that_reaches_the_copy(self, repo):
        code, env = repo.run("setup")
        assert code == todos.OK
        assert env["data"]["prefix"] == "TODOS=.todos/todos.py"
        assert env["data"]["repo"] == str(repo.root.resolve())
        assert (repo.root / env["data"]["prefix"].split("=", 1)[1]).is_file()

    def it_gives_the_prefix_in_text(self, repo):
        code, out, err = repo.human("setup")
        assert code == todos.OK
        assert out == (
            "wrote .todos/todos.py\nwrote .todos/.gitignore\n"
            "\nfrom %s, start every command with:\nTODOS=.todos/todos.py && \n"
            % repo.root.resolve()
        )
        assert err == ""

    def it_overwrites_an_earlier_copy(self, repo, script_path):
        repo.write(".todos/todos.py", "old\n")
        code, _ = repo.run("setup")
        assert code == todos.OK
        with open(script_path, "rb") as fh:
            assert repo.read(".todos/todos.py") == fh.read()

    def it_gives_each_files_checksum(self, repo):
        _, env = repo.run("setup")
        for f in env["data"]["files"]:
            assert f["sha256"] == hashlib.sha256(repo.read(f["file"])).hexdigest()


@pytest.mark.spec("setup-cmd-ignores-its-copy")
class DescribeIgnoringTheCopy:
    def it_writes_a_gitignore_of_star_beside_it(self, repo):
        repo.run("setup")
        assert repo.read(".todos/.gitignore") == b"*\n"

    def it_leaves_nothing_for_git_to_commit(self, repo):
        repo.run("setup")
        assert repo.git("status", "--porcelain") == b""


@pytest.mark.spec("repo:command-never-writes-in-preview")
class DescribeSetupDryRun:
    def it_writes_nothing(self, repo):
        code, env = repo.run("setup", "--dry-run")
        assert code == todos.OK
        assert env["data"]["dry_run"] is True
        assert [f["file"] for f in env["data"]["files"]] == [
            ".todos/todos.py",
            ".todos/.gitignore",
        ]
        assert not (repo.root / ".todos").exists()

    def it_says_what_it_would_write(self, repo):
        _, out, _ = repo.human("setup", "--dry-run")
        assert out.startswith("would write .todos/todos.py\nwould write .todos/.gitignore\n")


@pytest.mark.spec("scan-cmd-skips-its-copy")
class DescribeScanningBesideTheCopy:
    def it_does_not_read_the_copy(self, repo):
        repo.run("setup")
        assert repo.scan() == ([], [])

    def it_does_not_read_the_copy_when_git_does_not_ignore_it(self, repo):
        repo.run("setup")
        (repo.root / ".todos" / ".gitignore").unlink()
        repo.write(".todos/notes.txt", "TODO: inside the copy\n")
        assert repo.scan() == ([], [])

    def it_reads_a_folder_whose_name_only_starts_the_same(self, repo):
        repo.write(".todos-old/notes.txt", "TODO: kept\n")
        assert [t["title"] for t in repo.scan()[0]] == ["kept"]

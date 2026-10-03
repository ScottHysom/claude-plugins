"""What `todos.py file` leaves in a file once it has filed a TODO from it."""

import pytest

import todos


def file_all(repo, rel, base, now):
    """Commit `base` at rel, write `now` over it, file every TODO, and
    return the file's bytes."""
    repo.write(rel, base)
    repo.commit()
    repo.write(rel, now)
    code, _ = repo.file(repo.draft_all())
    assert code == todos.OK, repo.err
    return repo.read(rel)


@pytest.mark.spec("file-cmd-removes-handled-todos")
class DescribeRemovingATodo:
    def it_removes_every_line_of_a_block_todo(self, repo):
        base = "<p>one</p>\n<p>two</p>\n"
        now = "<p>one</p>\n<!-- TODO(docs): say more\n  about this\n-->\n<p>two</p>\n"
        assert file_all(repo, "a.html", base, now) == base.encode()

    def it_removes_the_detail_of_a_line_todo(self, repo):
        base = "x = 1\n"
        now = "// TODO: one\n// more\n// and more\nx = 1\n"
        assert file_all(repo, "a.js", base, now) == base.encode()

    def it_leaves_every_other_byte_alone(self, repo):
        base = "a  \r\n\tb\r\n"
        now = "a  \r\n# TODO: one\r\n\tb\r\nnew line\r\n"
        assert file_all(repo, "a.txt", base, now) == b"a  \r\n\tb\r\nnew line\r\n"

    def it_removes_a_todo_before_it_files_the_next(self, repo, github, monkeypatch):
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: one\nx = 1\n# TODO: two\n")
        seen = []

        def spy(root, *args, stdin=None):
            if args[:2] == ("issue", "create"):
                seen.append(repo.read("a.py"))
            return github(root, *args, stdin=stdin)

        monkeypatch.setattr(todos, "gh", spy)
        code, _ = repo.file(repo.draft_all())
        assert code == todos.OK
        assert seen == [b"# TODO: one\nx = 1\n# TODO: two\n", b"# TODO: one\nx = 1\n"]
        assert repo.read("a.py") == b"x = 1\n"

    def it_leaves_a_todo_with_no_draft(self, repo):
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: one\nx = 1\n# TODO: two\n")
        found, _ = repo.scan()
        code, _ = repo.file(repo.drafts([repo.draft(found[1])]))
        assert code == todos.OK
        assert repo.read("a.py") == b"# TODO: one\nx = 1\n"

    def it_leaves_an_empty_file_where_a_new_file_held_only_a_todo(self, repo):
        repo.write("notes.txt", "TODO: one\n")
        code, _ = repo.file(repo.draft_all())
        assert code == todos.OK
        assert repo.read("notes.txt") == b""

    def it_keeps_a_byte_order_mark(self, repo):
        base = b"\xef\xbb\xbfx = 1\n"
        now = b"\xef\xbb\xbf# TODO: one\nx = 1\n"
        assert file_all(repo, "a.py", base, now) == base


@pytest.mark.spec("file-cmd-tidies-blank-lines")
class DescribeTidyingBlankLines:
    def it_removes_added_blank_lines_between_committed_lines(self, repo):
        base = "a\nb\n"
        now = "a\n\n# TODO: one\n\n\nb\n"
        assert file_all(repo, "a.txt", base, now) == b"a\nb\n"

    def it_keeps_a_committed_blank_line(self, repo):
        base = "a\n\nb\n"
        now = "a\n\n\n# TODO: one\n\nb\n"
        assert file_all(repo, "a.txt", base, now) == b"a\n\nb\n"

    def it_keeps_one_blank_line_beside_an_added_line(self, repo):
        base = "a\n"
        now = "a\n\n# TODO: one\n\nnew\n"
        assert file_all(repo, "a.txt", base, now) == b"a\n\nnew\n"

    def it_keeps_one_blank_line_below_an_added_line(self, repo):
        base = "a\n"
        now = "new\n\n# TODO: one\n\na\n"
        assert file_all(repo, "a.txt", base, now) == b"new\n\na\n"

    def it_keeps_the_first_of_the_run(self, repo):
        base = "a\n"
        now = "a\n  \n# TODO: one\n\t\nnew\n"
        assert file_all(repo, "a.txt", base, now) == b"a\n  \nnew\n"

    def it_removes_a_run_that_reaches_the_end_of_the_file(self, repo):
        base = "a\n"
        now = "a\nnew\n\n# TODO: one\n\n"
        assert file_all(repo, "a.txt", base, now) == b"a\nnew\n"

    def it_removes_a_run_that_reaches_the_start_of_the_file(self, repo):
        base = "a\n"
        now = "\n# TODO: one\n\nnew\na\n"
        assert file_all(repo, "a.txt", base, now) == b"new\na\n"

    def it_does_not_touch_a_blank_line_away_from_every_todo(self, repo):
        base = "a\nb\nc\n"
        now = "a\n# TODO: one\nb\n\nc\n"
        assert file_all(repo, "a.txt", base, now) == b"a\nb\n\nc\n"

    def it_tidies_between_two_todos_once_both_are_gone(self, repo):
        base = "a\nb\n"
        now = "a\n\n# TODO: one\n\n# TODO: two\n\nb\n"
        assert file_all(repo, "a.txt", base, now) == b"a\nb\n"

    def it_keeps_the_spacing_beside_a_todo_left_in_place(self, repo):
        repo.write("a.txt", "a\nb\n")
        repo.commit()
        repo.write("a.txt", "a\n\n# TODO: one\n\n# TODO: two\n\nb\n")
        found, _ = repo.scan()
        code, _ = repo.file(repo.drafts([repo.draft(found[1])]))
        assert code == todos.OK
        assert repo.read("a.txt") == b"a\n\n# TODO: one\n\nb\n"


@pytest.mark.spec("file-cmd-restores-todo-only-files")
class DescribeRestoringAFile:
    def it_restores_a_file_whose_last_line_had_no_ending(self, repo):
        assert file_all(repo, "a.txt", "a\nb", "a\nb\n# TODO: one\n") == b"a\nb"

    def it_restores_it_when_the_todo_has_no_ending_either(self, repo):
        assert file_all(repo, "a.txt", "a\nb", "a\nb\n\n# TODO: one") == b"a\nb"

    def it_restores_crlf_endings(self, repo):
        base = b"a\r\nb"
        assert file_all(repo, "a.txt", base, b"a\r\n# TODO: one\r\nb\r\n# TODO: two") == base

    def it_keeps_the_ending_of_a_last_line_that_had_one(self, repo):
        assert file_all(repo, "a.txt", "a\n", "a\n# TODO: one") == b"a\n"

    def it_keeps_the_ending_of_a_line_that_was_not_last(self, repo):
        assert file_all(repo, "a.txt", "a\nb", "a\n# TODO: one\nb") == b"a\nb"

    def it_leaves_the_ending_of_an_added_last_line(self, repo):
        assert file_all(repo, "a.txt", "a", "a\nnew\n# TODO: one\n") == b"a\nnew\n"

    def it_restores_every_kind_of_todo_together(self, repo):
        base = "<p>one</p>\n\n<p>two</p>"
        now = (
            "<!-- TODO: block\nmore -->\n<p>one</p>\n\n<!-- TODO(docs): line -->\n\n"
            "- TODO: a list one\n<p>two</p>\n\n<!-- TODO: last -->\n"
        )
        assert file_all(repo, "a.md", base, now) == base.encode()

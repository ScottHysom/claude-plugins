"""How `todos.py` reads a TODO at the end of a line of code, and how `file`
marks it once it is filed."""

import pytest

import todos


def changed(repo, rel, base, now):
    """Commit `base` at rel, write `now` over it, and scan."""
    repo.write(rel, base)
    repo.commit()
    repo.write(rel, now)
    return repo.scan()


def file_all(repo, rel, base, now):
    """Commit `base` at rel, write `now` over it, file every TODO, and
    return the file's bytes."""
    repo.write(rel, base)
    repo.commit()
    repo.write(rel, now)
    code, _ = repo.file(repo.draft_all())
    assert code == todos.OK, repo.err
    return repo.read(rel)


@pytest.mark.spec("scan-cmd-reads-trailing-todos")
class DescribeReadingATrailingTodo:
    def it_reads_the_title_and_kind_after_the_code(self, repo):
        (todo,), warnings = changed(
            repo, "a.py", "x = 3\n", "x = 3  # TODO(fix): the vendor allows 5 retries\n"
        )
        assert warnings == []
        assert (todo["first"], todo["last"], todo["kind"], todo["marker"]) == (1, 1, "fix", "#")
        assert todo["title"] == "the vendor allows 5 retries"
        assert todo["text"] == "x = 3  # TODO(fix): the vendor allows 5 retries"

    @pytest.mark.parametrize(
        ("rel", "base", "now", "marker"),
        [
            ("a.ts", "let x = 3;", "let x = 3; // TODO: the title", "//"),
            ("a.sql", "SELECT 1", "SELECT 1 -- TODO: the title", "--"),
            ("notes.txt", "Some sentence.", "Some sentence. TODO: the title", ""),
            ("a.md", "A paragraph.", "A paragraph. <!-- TODO(docs): the title -->", "<!--"),
            ("a.c", "int x = 3;", "int x = 3; /* TODO: the title */  ", "/*"),
            ("a.py", "f(a)", "f(a)# TODO: the title", "#"),
        ],
    )
    def it_reads_the_title_after_any_marker(self, repo, rel, base, now, marker):
        (todo,), warnings = changed(repo, rel, "top\n%s\nend\n" % base, "top\n%s\nend\n" % now)
        assert warnings == []
        assert (todo["title"], todo["marker"], todo["first"]) == ("the title", marker, 2)

    def it_gives_no_detail(self, repo):
        (todo,), warnings = changed(repo, "a.py", "x = 3\n", "x = 3  # TODO: one\n# more\n")
        assert (todo["last"], todo["detail"], warnings) == (1, "", [])

    def it_gives_its_own_line_as_the_last_commit_has_it(self, repo):
        (todo,), _ = changed(repo, "a.py", "a = 1\nx = 3\n", "a = 1\n\nx = 3  # TODO: one\n")
        assert todo["above"] == {"line": 3, "text": "x = 3", "base_line": 2}

    def it_gives_a_todo_above_the_line_as_the_last_commit_has_it(self, repo):
        found, _ = changed(repo, "a.py", "x = 3\n", "# TODO: one\nx = 3  # TODO: two\n")
        assert [t["above"]["text"] for t in found] == ["x = 3", "x = 3"]

    def it_says_in_text_that_it_sits_at_the_end_of_its_line(self, repo):
        changed(repo, "a.py", "x = 3\n", "x = 3  # TODO: one\n")
        _, out, _ = repo.human("scan")
        short = repo.head()[:7]
        assert "a.py:1: one\n    at the end of line 1 (line 1 at %s): x = 3\n" % short in out

    def it_keeps_space_the_last_commit_had_at_the_end_of_the_line(self, repo):
        (todo,), warnings = changed(repo, "a.py", "x = 3\nx = 3  \n", "x = 3\nx = 3  # TODO: one\n")
        assert (todo["above"]["text"], warnings) == ("x = 3  ", [])

    def it_reads_the_one_of_two_repeated_lines_that_the_commit_holds_once(self, repo):
        found, warnings = changed(
            repo, "a.py", "x = 3\n", "x = 3  # TODO: one\nx = 3  # TODO: two\n"
        )
        assert [t["title"] for t in found] == ["one"]
        assert warnings == ["a.py:2: " + todos.UNREAD_PART_WAY]


@pytest.mark.spec("scan-cmd-warns-on-unread-todos")
class DescribeWarningsOnATrailingTodo:
    def it_warns_when_the_code_changed_too(self, repo):
        found, warnings = changed(repo, "a.py", "x = 3\n", "x = 5  # TODO: one\n")
        assert found == []
        assert warnings == ["a.py:1: " + todos.UNREAD_PART_WAY]

    def it_warns_on_a_new_line(self, repo):
        found, warnings = changed(repo, "a.py", "x = 3\n", "x = 3\ny = 4  # TODO: one\n")
        assert found == []
        assert warnings == ["a.py:2: " + todos.UNREAD_PART_WAY]

    @pytest.mark.parametrize("now", ["<p>x</p> <!-- TODO: one", "<p>x</p> <!-- TODO: one --> <b>"])
    def it_warns_when_its_comment_does_not_end_the_line(self, repo, now):
        found, warnings = changed(repo, "a.html", "<p>x</p>\n", now + "\n")
        assert found == []
        assert warnings == ["a.html:1: a comment holding a TODO at the end of a line has to end it"]

    def it_neither_reads_nor_warns_in_a_code_fence(self, repo):
        base = "```\nx = 3\n```\n"
        assert changed(repo, "a.md", base, "```\nx = 3  # TODO: one\n```\n") == ([], [])


@pytest.mark.spec("file-cmd-marks-trailing-todos")
class DescribeMarkingATrailingTodo:
    def it_marks_the_todo_and_leaves_the_code_before_it(self, repo):
        base = "a = 1\nx = 3\nb = 2\n"
        now = "a = 1\nx = 3  # TODO(fix): the vendor allows 5 retries\nb = 2\n"
        assert file_all(repo, "a.py", base, now) == (
            b"a = 1\nx = 3  # TODO-HANDLED(#1): the vendor allows 5 retries\nb = 2\n"
        )

    def it_keeps_the_line_ending(self, repo):
        base = b"a\r\nx = 3\r\nb"
        now = b"a\r\nx = 3  # TODO: one\r\nb  # TODO: two"
        assert file_all(repo, "a.py", base, now) == (
            b"a\r\nx = 3  # TODO-HANDLED(#2): one\r\nb  # TODO-HANDLED(#1): two"
        )

    def it_marks_a_todo_above_the_line_too(self, repo):
        base = "x = 3\n"
        now = "# TODO: one\n# more\nx = 3  /* TODO: two */\n"
        assert file_all(repo, "a.c", base, now) == (
            b"# TODO-HANDLED(#2): one\n# more\nx = 3  /* TODO-HANDLED(#1): two */\n"
        )

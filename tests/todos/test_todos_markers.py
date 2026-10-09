"""How `todos.py scan` reads a TODO's marker, title, detail and kind, and
what it warns about."""

import pytest


def one(repo, rel, text):
    """The single TODO scan finds in a new file holding text."""
    repo.write(rel, text)
    found, warnings = repo.scan()
    assert len(found) == 1, (found, warnings)
    return found[0]


@pytest.mark.spec("scan-cmd-reads-any-symbol-marker")
class DescribeMarkers:
    @pytest.mark.parametrize(
        ("rel", "line", "marker"),
        [
            ("a.py", "# TODO: the title", "#"),
            ("a.ts", "  // TODO: the title", "//"),
            ("a.sql", "-- TODO: the title", "--"),
            ("a.el", ";;TODO: the title", ";;"),
            ("a.tex", "% TODO: the title", "%"),
            ("notes.txt", "TODO: the title", ""),
            ("a.md", "- TODO: the title", "-"),
            ("a.md", "> TODO: the title", ">"),
            ("Makefile", "\t# TODO: the title", "#"),
        ],
    )
    def it_reads_the_title_after_any_marker(self, repo, rel, line, marker):
        todo = one(repo, rel, line + "\n")
        assert (todo["title"], todo["marker"], todo["first"]) == ("the title", marker, 1)

    def it_reads_a_file_whatever_its_extension(self, repo):
        todo = one(repo, "config.unknownext", "!! TODO: odd syntax\n")
        assert todo["marker"] == "!!"

    def it_reads_bytes_that_are_not_utf8(self, repo):
        todo = one(repo, "latin.txt", b"# TODO: caf\xe9\n")
        assert todo["title"] == "caf�"


@pytest.mark.spec("scan-cmd-reads-line-detail")
class DescribeLineDetail:
    def it_reads_the_lines_below_with_the_same_marker(self, repo):
        todo = one(repo, "a.py", "# TODO: title\n# first\n#\n# second\nx = 1\n")
        assert todo["detail"] == "first\n\nsecond"
        assert todo["last"] == 4

    def it_stops_at_a_blank_line(self, repo):
        todo = one(repo, "a.py", "# TODO: title\n# detail\n\n# a comment of the code\n")
        assert (todo["detail"], todo["last"]) == ("detail", 2)

    def it_stops_at_the_next_todo(self, repo):
        repo.write("a.py", "# TODO: one\n# detail\n# TODO: two\n# more\n")
        found, _ = repo.scan()
        assert [(t["title"], t["detail"]) for t in found] == [("one", "detail"), ("two", "more")]

    def it_stops_at_another_marker(self, repo):
        todo = one(repo, "a.py", "# TODO: title\n## heading\n")
        assert (todo["detail"], todo["last"]) == ("", 1)

    def it_stops_at_another_indent(self, repo):
        todo = one(repo, "a.py", "# TODO: title\n    # indented\n")
        assert (todo["detail"], todo["last"]) == ("", 1)

    def it_stops_at_a_line_already_committed(self, repo):
        repo.write("a.py", "# a committed comment\n")
        repo.commit()
        todo = one(repo, "a.py", "# TODO: title\n# a committed comment\n")
        assert (todo["detail"], todo["last"]) == ("", 1)

    @pytest.mark.parametrize("marker", ["", "- ", "* ", "+ ", "> ", "| "])
    def it_gives_a_title_only_behind_an_empty_or_list_marker(self, repo, marker):
        todo = one(repo, "a.md", "%sTODO: title\n%sthe author's own line\n" % (marker, marker))
        assert (todo["detail"], todo["last"]) == ("", 1)


@pytest.mark.spec("scan-cmd-reads-c-and-html-comments")
class DescribeBlockComments:
    def it_reads_a_comment_on_one_line(self, repo):
        todo = one(repo, "a.md", "<!-- TODO(docs): the layout leaves things out -->\n")
        assert (todo["title"], todo["detail"], todo["last"]) == (
            "the layout leaves things out",
            "",
            1,
        )

    def it_runs_to_the_closer_and_gives_the_rest_as_detail(self, repo):
        todo = one(repo, "a.html", "<!-- TODO: title\n  first\n  second -->\n<p>x</p>\n")
        assert (todo["detail"], todo["first"], todo["last"]) == ("first\nsecond", 1, 3)
        assert todo["above"]["text"] == "<p>x</p>"

    def it_strips_the_stars_of_a_c_comment(self, repo):
        todo = one(repo, "a.css", "/* TODO(design): title\n * first\n * second\n */\n")
        assert todo["detail"] == "first\nsecond"

    def it_reads_a_c_comment_on_one_line(self, repo):
        todo = one(repo, "a.c", "int x; /* not this */\n/* TODO: title */\n")
        assert (todo["title"], todo["first"]) == ("title", 2)

    def it_warns_when_the_comment_runs_into_a_committed_line(self, repo):
        repo.write("a.md", "text\n-->\n")
        repo.commit()
        repo.write("a.md", "<!-- TODO: title\ntext\n-->\n")
        found, warnings = repo.scan()
        assert found == []
        assert warnings == [
            "a.md:1: the comment runs on to line 2, which was there at the last commit"
        ]

    def it_warns_when_the_comment_does_not_close(self, repo):
        repo.write("a.md", "<!-- TODO: title\nmore\n")
        assert repo.scan() == ([], ["a.md:1: the comment does not close with `-->`"])

    def it_warns_when_text_follows_the_closer(self, repo):
        repo.write("a.c", "/* TODO: title\n */ int x;\n")
        assert repo.scan() == ([], ["a.c:2: text follows the comment's `*/`"])


@pytest.mark.spec("scan-cmd-skips-markdown-code-todos")
class DescribeTodosInMarkdownCode:
    @pytest.mark.parametrize("fence", ["```", "~~~", "````"])
    def it_skips_a_todo_in_a_markdown_fence(self, repo, fence):
        repo.write("a.md", "%s sh\nTODO: shown\n# TODO( shown\n%s\nTODO: real\n" % (fence, fence))
        found, warnings = repo.scan()
        assert ([t["first"] for t in found], warnings) == ([5], [])

    def it_reads_the_text_around_a_fence(self, repo):
        repo.write("a.md", "TODO: before\n\n```\nTODO: shown\n```\nTODO: after\n")
        found, _ = repo.scan()
        assert [t["first"] for t in found] == [1, 6]

    def it_keeps_a_fence_open_until_a_matching_closer(self, repo):
        repo.write("a.md", "````\n```\nTODO: shown\n~~~~\n````\nTODO: real\n")
        found, _ = repo.scan()
        assert [t["first"] for t in found] == [6]

    def it_runs_an_unclosed_fence_to_the_end(self, repo):
        repo.write("a.markdown", "```\nTODO: shown\n")
        assert repo.scan() == ([], [])

    def it_does_not_open_a_fence_whose_info_holds_a_backtick(self, repo):
        repo.write("a.md", "```not`a fence\nTODO: real\n")
        found, _ = repo.scan()
        assert [t["first"] for t in found] == [2]

    def it_skips_a_todo_in_a_code_span(self, repo):
        repo.write("a.md", "Write `TODO:` or ``TODO(kind):`` here, with a ` stray tick.\n")
        assert repo.scan() == ([], [])

    def it_keeps_a_code_span_in_a_title(self, repo):
        todo = one(repo, "a.md", "TODO: rename `run()`\n")
        assert todo["title"] == "rename `run()`"

    def it_reads_a_fence_as_text_outside_markdown(self, repo):
        repo.write("a.txt", "```\nTODO: real here\n```\n")
        found, _ = repo.scan()
        assert [t["first"] for t in found] == [2]


@pytest.mark.spec("scan-cmd-reads-kind-word")
class DescribeKind:
    @pytest.mark.parametrize("kind", ["bug", "fix", "change", "design", "docs", "prose"])
    def it_gives_each_kind(self, repo, kind):
        todo = one(repo, "a.py", "# TODO(%s): title\n" % kind)
        assert todo["kind"] == kind

    def it_gives_no_kind_without_one(self, repo):
        assert one(repo, "a.py", "# TODO: title\n")["kind"] is None

    @pytest.mark.parametrize("word", ["feature", "Bug", ""])
    def it_warns_on_any_other_word_and_gives_no_kind(self, repo, word):
        repo.write("a.py", "# TODO(%s): title\n" % word)
        (todo,), (warning,) = repo.scan()
        assert todo["kind"] is None
        assert warning.startswith("a.py:1: `%s` is not a kind" % word)


@pytest.mark.spec("scan-cmd-warns-on-unread-todos")
class DescribeWarnings:
    @pytest.mark.parametrize(
        ("line", "reason"),
        [
            ("x = 1  # TODO: later", "a TODO is read at the start of its line"),
            ("call(TODO(x))", "a TODO is read at the start of its line"),
            ("# TODO(bug) no colon", "the line opens with TODO but not with"),
            ("# TODO fix this", "the line opens with TODO but not with"),
            ("TODOs pile up", "the line opens with TODO but not with"),
        ],
    )
    def it_warns_with_the_file_line_and_reason(self, repo, line, reason):
        repo.write("a.py", "x = 0\n" + line + "\n")
        found, warnings = repo.scan()
        assert found == []
        assert len(warnings) == 1
        assert warnings[0].startswith("a.py:2: " + reason)

    def it_does_not_warn_about_a_committed_line(self, repo):
        repo.write("a.py", "x = 1  # TODO: later\n")
        repo.commit()
        repo.write("a.py", "x = 1  # TODO: later\ny = 2\n")
        assert repo.scan() == ([], [])

    def it_does_not_warn_about_lowercase_todo(self, repo):
        repo.write("a.py", "x = 1  # todo: later\n")
        assert repo.scan() == ([], [])

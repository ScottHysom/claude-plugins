"""How `todos.py file` marks a TODO handled once it has filed it, and how
`scan` reads a file that holds marked TODOs."""

import pytest

import todos


def file_all(repo, rel, base, now):
    """Commit `base` at rel, write `now` over it, file every TODO as an issue,
    and return the file's bytes."""
    repo.write(rel, base)
    repo.commit()
    repo.write(rel, now)
    code, _ = repo.file(repo.draft_all())
    assert code == todos.OK, repo.err
    return repo.read(rel)


def changed(repo, rel, base, now):
    """Commit `base` at rel, write `now` over it, and scan."""
    repo.write(rel, base)
    repo.commit()
    repo.write(rel, now)
    return repo.scan()


@pytest.mark.spec("file-cmd-marks-handled-todos")
class DescribeMarkingATodo:
    def it_puts_the_marker_in_place_of_the_word(self, repo):
        now = "# TODO: one\nx = 1\n"
        assert file_all(repo, "a.py", "x = 1\n", now) == b"# TODO-HANDLED(#1): one\nx = 1\n"

    def it_replaces_the_kind_with_the_marker(self, repo):
        now = "x = 1\n    // TODO(bug): one\n    // more\n"
        assert file_all(repo, "a.js", "x = 1\n", now) == (
            b"x = 1\n    // TODO-HANDLED(#1): one\n    // more\n"
        )

    def it_leaves_a_block_comment_as_it_is_around_the_marker(self, repo):
        now = "<p>one</p>\n<!-- TODO(docs): say more\n  about this\n-->\n"
        assert file_all(repo, "a.html", "<p>one</p>\n", now) == (
            b"<p>one</p>\n<!-- TODO-HANDLED(#1): say more\n  about this\n-->\n"
        )

    def it_leaves_every_other_byte_alone(self, repo):
        base = "a  \r\n\tb\r\n"
        now = "a  \r\n\n#  TODO: one\r\n\n\tb\r\nnew line"
        assert file_all(repo, "a.txt", base, now) == (
            b"a  \r\n\n#  TODO-HANDLED(#1): one\r\n\n\tb\r\nnew line"
        )

    def it_marks_each_todo_in_a_block_comment(self, repo):
        now = "/* TODO: a\n * more\n * TODO: b\n */\nint x;\n"
        assert file_all(repo, "a.c", "int x;\n", now) == (
            b"/* TODO-HANDLED(#2): a\n * more\n * TODO-HANDLED(#1): b\n */\nint x;\n"
        )

    def it_keeps_a_byte_order_mark(self, repo):
        base = b"\xef\xbb\xbfx = 1\n"
        now = b"\xef\xbb\xbf# TODO: one\nx = 1\n"
        assert file_all(repo, "a.py", base, now) == b"\xef\xbb\xbf# TODO-HANDLED(#1): one\nx = 1\n"

    def it_marks_a_todo_before_it_files_the_next(self, repo, github, monkeypatch):
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
        assert seen == [
            b"# TODO: one\nx = 1\n# TODO: two\n",
            b"# TODO: one\nx = 1\n# TODO-HANDLED(#1): two\n",
        ]
        assert repo.read("a.py") == b"# TODO-HANDLED(#2): one\nx = 1\n# TODO-HANDLED(#1): two\n"

    def it_leaves_a_todo_with_no_draft(self, repo):
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: one\nx = 1\n# TODO: two\n")
        found, _ = repo.scan()
        code, _ = repo.file(repo.drafts([repo.draft(found[1])]))
        assert code == todos.OK
        assert repo.read("a.py") == b"# TODO: one\nx = 1\n# TODO-HANDLED(#1): two\n"

    def it_gives_the_marker_in_json(self, repo):
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: one\nx = 1\n")
        code, env = repo.file(repo.draft_all())
        assert code == todos.OK
        assert [f["handled"] for f in env["data"]["filed"]] == ["TODO-HANDLED(#1)"]


@pytest.mark.spec("file-cmd-wraps-markdown-todos")
class DescribeWrappingInMarkdown:
    def it_wraps_a_todo_on_a_line_of_its_own(self, repo):
        now = "Text.\nTODO: one\n"
        assert file_all(repo, "a.md", "Text.\n", now) == (
            b"Text.\n<!-- TODO-HANDLED(#1): one -->\n"
        )

    def it_wraps_a_list_item_after_its_indent(self, repo):
        now = "- a\n  - TODO(docs): one\n"
        assert file_all(repo, "a.md", "- a\n", now) == (
            b"- a\n  <!-- - TODO-HANDLED(#1): one -->\n"
        )

    def it_wraps_the_detail_lines_too(self, repo):
        now = "Text.\n% TODO: one\n% more\n% and more\n"
        assert file_all(repo, "a.md", "Text.\n", now) == (
            b"Text.\n<!-- % TODO-HANDLED(#1): one\n% more\n% and more -->\n"
        )

    def it_wraps_a_trailing_todo_from_its_marker(self, repo):
        now = "Text.  > TODO(fix): one\n"
        assert file_all(repo, "a.md", "Text.\n", now) == (
            b"Text.  <!-- > TODO-HANDLED(#1): one -->\n"
        )

    def it_keeps_the_line_ending_after_the_wrap(self, repo):
        assert file_all(repo, "a.md", "Text.\r\n", "Text.\r\nTODO: one\r\n") == (
            b"Text.\r\n<!-- TODO-HANDLED(#1): one -->\r\n"
        )

    def it_does_not_wrap_a_todo_that_is_a_comment_already(self, repo):
        now = "Text.\n<!-- TODO: one\nmore -->\n"
        assert file_all(repo, "a.md", "Text.\n", now) == (
            b"Text.\n<!-- TODO-HANDLED(#1): one\nmore -->\n"
        )

    def it_does_not_wrap_a_todo_inside_a_comment(self, repo):
        now = "Text.\n<!--\nTODO: one\n-->\n"
        assert file_all(repo, "a.md", "Text.\n", now) == (
            b"Text.\n<!--\nTODO-HANDLED(#1): one\n-->\n"
        )

    def it_does_not_wrap_a_trailing_todo_inside_a_comment(self, repo):
        now = "<!-- Text. TODO: one -->\n"
        assert file_all(repo, "a.md", "<!-- Text.\n", now) == (
            b"<!-- Text. TODO-HANDLED(#1): one -->\n"
        )

    def it_wraps_a_todo_after_a_comment_has_closed(self, repo):
        now = "<!-- a\nb -->\nTODO: one\n"
        assert file_all(repo, "a.md", "<!-- a\nb -->\n", now) == (
            b"<!-- a\nb -->\n<!-- TODO-HANDLED(#1): one -->\n"
        )

    def it_ignores_a_comment_opener_in_a_fence_or_a_code_span(self, repo):
        base = "```\n<!--\n```\nSay `<!--` here.\n"
        assert (
            file_all(repo, "a.md", base, base + "TODO: one\n")
            == (base + "<!-- TODO-HANDLED(#1): one -->\n").encode()
        )

    def it_does_not_wrap_outside_markdown(self, repo):
        now = "Text.\n- TODO: one\n"
        assert file_all(repo, "a.txt", "Text.\n", now) == b"Text.\n- TODO-HANDLED(#1): one\n"


@pytest.mark.spec("scan-cmd-skips-handled-todos")
class DescribeScanningMarkedTodos:
    def it_finds_nothing_once_every_todo_is_marked(self, repo):
        now = (
            "Text.  TODO: a\n\n- TODO(docs): b\n\n% TODO: c\n% more\n\n<!-- TODO: d\n-->\n"
            "\n/* TODO: e\n * more */\n"
        )
        file_all(repo, "a.md", "Text.\n", now)
        assert repo.scan() == ([], [])

    def it_finds_nothing_in_a_marked_file_of_code(self, repo):
        now = "# TODO(bug): a\n# more\nx = 3  # TODO: b\n"
        file_all(repo, "a.py", "x = 3\n", now)
        assert repo.scan() == ([], [])

    def it_stops_a_todos_detail_at_a_marked_one(self, repo):
        found, warnings = changed(
            repo, "a.py", "x = 1\n", "# TODO: new\n# TODO-HANDLED(#3): old\nx = 1\n"
        )
        assert [(t["title"], t["detail"], t["last"]) for t in found] == [("new", "", 1)]
        assert warnings == []

    def it_points_a_todo_past_a_marked_one_and_its_detail(self, repo):
        found, _ = changed(
            repo,
            "a.py",
            "x = 1\n",
            "# TODO: new\n\n# TODO-HANDLED(#3): old\n# more\nx = 1\n",
        )
        assert found[0]["above"]["line"] == 5

    def it_points_a_todo_past_a_wrapped_one(self, repo):
        found, _ = changed(
            repo,
            "a.md",
            "Text.\n",
            "TODO: new\n\n<!-- % TODO-HANDLED(#3): old\n% more -->\nText.\n",
        )
        assert found[0]["above"]["line"] == 5

    def it_reads_a_marked_block_to_its_closer(self, repo):
        found, _ = changed(
            repo, "a.c", "x = 1\n", "// TODO: new\n/* TODO-HANDLED(#3): old\n   more */\nx = 1\n"
        )
        assert found[0]["above"]["line"] == 4

    @pytest.mark.spec("scan-cmd-reads-c-and-html-comments")
    def it_reads_a_todo_after_a_marked_one_in_its_comment(self, repo):
        found, warnings = changed(
            repo, "a.c", "x = 1\n", "/* TODO-HANDLED(#3): old\n   TODO: new\n   more */\nx = 1\n"
        )
        assert [(t["title"], t["detail"], t["first"]) for t in found] == [("new", "more", 2)]
        assert warnings == []

    def it_warns_about_an_unclosed_marked_block_holding_a_todo(self, repo):
        _, warnings = changed(repo, "a.c", "x = 1\n", "/* TODO-HANDLED(#3): old\n   TODO: new\n")
        assert warnings == ["a.c:1: the comment does not close with `*/`"]

    def it_reads_an_unclosed_marked_block_as_one_line(self, repo):
        found, warnings = changed(
            repo, "a.c", "x = 1\n", "// TODO: new\n/* TODO-HANDLED(#3): old\nx = 1\n"
        )
        assert found[0]["above"]["line"] == 3
        assert warnings == []

    @pytest.mark.spec("scan-cmd-warns-on-unread-todos")
    def it_still_warns_about_a_marker_without_a_target(self, repo):
        _, warnings = changed(repo, "a.py", "x = 1\n", "# TODO-HANDLED: old\nx = 1\n")
        assert warnings == [
            "a.py:1: the line opens with TODO but not with `TODO:` or `TODO(<kind>):`"
        ]

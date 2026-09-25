"""Accepting keeps the <ins> side and drops the <del> side; rejecting does the
reverse. Getting this backwards silently discards the author's text, so both
directions are asserted against the exact expected output rather than against
a property.
"""

import prose

MARKED = (
    "Keep <del>cut this</del><ins>keep this</ins> here.\n"
    '<repl why="noun phrase"><del>old</del><ins>new</ins></repl>\n'
)


class DescribeResolveText:
    def it_keeps_the_insertion_on_accept(self):
        got, scanner = prose.resolve_text(prose.Text(MARKED), prose.ACCEPT, None, "t.md")
        assert scanner.errors == []
        assert got == "Keep keep this here.\nnew\n"

    def it_restores_the_original_on_reject(self):
        got, scanner = prose.resolve_text(prose.Text(MARKED), prose.REJECT, None, "t.md")
        assert scanner.errors == []
        assert got == "Keep cut this here.\nold\n"


CUT_MIDDLE = "One.\n\n<del>\nTwo\nlines.\n</del>\n\nThree.\n"


def accept(source):
    got, scanner = prose.resolve_text(prose.Text(source), prose.ACCEPT, None, "t.md")
    assert scanner.errors == []
    return got


def reject(source):
    got, scanner = prose.resolve_text(prose.Text(source), prose.REJECT, None, "t.md")
    assert scanner.errors == []
    return got


class DescribeResolvingAWholeBlockCut:
    def it_leaves_one_blank_line_where_a_paragraph_was_cut(self):
        assert accept(CUT_MIDDLE) == "One.\n\nThree.\n"

    def it_treats_a_repl_with_an_empty_insertion_as_a_cut(self):
        source = "One.\n\n<repl>\n<del>\nTwo\n</del>\n<ins>\n</ins>\n</repl>\n\nThree.\n"
        assert accept(source) == "One.\n\nThree.\n"

    def it_leaves_no_blank_line_at_the_start_when_the_first_block_is_cut(self):
        assert accept("<del>\nTwo\n</del>\n\nThree.\n") == "Three.\n"

    def it_leaves_no_blank_line_at_the_end_when_the_last_block_is_cut(self):
        assert accept("One.\n\n<del>\nTwo\n</del>\n") == "One.\n"

    def it_adds_no_newline_to_a_file_that_ended_without_one(self):
        assert accept("One.\n\n<del>\nTwo\n</del>") == "One."

    def it_leaves_one_blank_line_where_adjacent_paragraphs_were_cut(self):
        source = "One.\n\n<del>\nTwo\n</del>\n\n<del>\nThree\n</del>\n\nFour.\n"
        assert accept(source) == "One.\n\nFour.\n"

    def it_keeps_the_blank_lines_around_an_inline_cut(self):
        assert accept("One <del>two</del>.\n\n\nThree.\n") == "One .\n\n\nThree.\n"

    def it_keeps_every_blank_line_on_strip(self):
        source = "One.\n\n<ins>\nTwo\n</ins>\n\nThree.\n"
        assert reject(source) == "One.\n\n\nThree.\n"


class DescribeTagsResolve:
    def it_leaves_one_blank_line_where_a_paragraph_was_cut(self, prose_repo):
        (prose_repo.root / "target.md").write_text(CUT_MIDDLE)
        code, envelope = prose_repo.run("tags", "resolve", "target.md")
        assert code == prose.OK, envelope
        assert prose_repo.read() == "One.\n\nThree.\n"

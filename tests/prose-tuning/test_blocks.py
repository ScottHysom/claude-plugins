"""Blocks decides what each line of a document is, and some of those kinds are
off limits to every rewrite the plugin makes.

This is the classifier the apply guard consults. Asserting it here means a
change to what counts as a fence fails against the classifier itself, rather
than surfacing as one confusing case in test_apply.py.
"""

import pytest

import prose

PROTECTED = ["frontmatter", "blockquote", "fence", "comment"]


class DescribeBlocks:
    def it_classifies_each_line_as_the_map_says(self, target, target_lines):
        """conftest's TARGET_LINES is load-bearing - other tests address spans in
        that document by kind. Editing the document without editing the map would
        otherwise leave them silently aimed at the wrong line.
        """
        blocks = prose.Blocks(prose.Text(target))
        named = dict(target_lines)
        last = named.pop("last-paragraph")
        got = {kind: blocks.kind(line) for kind, line in named.items()}
        assert got == {kind: kind for kind in named}
        assert blocks.kind(last) == "paragraph"

    @pytest.mark.parametrize("kind", PROTECTED)
    def it_protects_a_line_of_a_protected_kind(self, target, target_lines, kind):
        blocks = prose.Blocks(prose.Text(target))
        assert blocks.is_protected(target_lines[kind]) is True

    @pytest.mark.parametrize("kind", ["heading", "paragraph", "table"])
    def it_leaves_a_line_of_prose_unprotected(self, target, target_lines, kind):
        blocks = prose.Blocks(prose.Text(target))
        assert blocks.is_protected(target_lines[kind]) is False


def items(src):
    """The line of the list item each line belongs to, or None."""
    blocks = prose.Blocks(prose.Text(src))
    return [item[0] if item else None for item in blocks.items]


class DescribeListItems:
    """A paragraph line can carry on a list item without starting one.

    apply indents a new line to the item's text only if it knows the line
    belongs to one, and segments reports it as a list-continuation.
    """

    def it_gives_an_indented_continuation_line_to_its_item(self):
        assert items("- First\n  continues.\n- Second.\n") == [1, 1, 3]

    def it_gives_a_lazy_continuation_line_to_its_item(self):
        assert items("- First\ncontinues lazily.\n") == [1, 1]

    def it_gives_an_indented_paragraph_after_a_blank_line_to_its_item(self):
        assert items("- First.\n\n  A second paragraph.\n") == [1, None, 1]

    def it_ends_the_list_at_an_unindented_paragraph_after_a_blank_line(self):
        assert items("- First.\n\nNot in the list.\n") == [1, None, None]

    def it_ends_the_list_at_a_heading(self):
        assert items("- First.\n# Heading\nProse.\n") == [1, None, None]

    def it_gives_a_line_to_the_innermost_item_its_indent_reaches(self):
        src = "- Outer\n  - Inner\n    inner text.\n\n  outer text.\n"
        assert items(src) == [1, 2, 2, None, 1]

    def it_records_the_column_the_item_text_starts_at(self):
        blocks = prose.Blocks(prose.Text("10. Item\n    more.\n"))
        assert blocks.item(2) == (1, 4)

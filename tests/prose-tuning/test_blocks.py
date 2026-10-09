"""Blocks decides what each line of a document is, and some of those kinds are
off limits to every rewrite the plugin makes.

This is the classifier the apply guard consults. Asserting it here means a
change to what counts as a fence fails against the classifier itself, rather
than surfacing as one confusing case in test_apply.py.
"""

import pytest

import prose

PROTECTED = ["frontmatter", "blockquote", "fence", "comment", "code-block", "html-block"]


class DescribeBlocks:
    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
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

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    @pytest.mark.parametrize("kind", PROTECTED)
    def it_protects_a_line_of_a_protected_kind(self, target, target_lines, kind):
        blocks = prose.Blocks(prose.Text(target))
        assert blocks.is_protected(target_lines[kind]) is True

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    @pytest.mark.parametrize("kind", ["heading", "paragraph", "table"])
    def it_leaves_a_line_of_prose_unprotected(self, target, target_lines, kind):
        blocks = prose.Blocks(prose.Text(target))
        assert blocks.is_protected(target_lines[kind]) is False


def kinds(src):
    return prose.Blocks(prose.Text(src)).kinds


class DescribeCodeAndHtmlBlocks:
    """Indented code and HTML blocks as CommonMark finds them.

    The protected-kind tests above check that both are protected. These check
    where each starts and ends, which is what decides how much is protected.
    """

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    def it_takes_a_line_indented_four_columns_past_its_list_item_for_code(self):
        src = "- Item.\n\n    more of the item.\n\n      code\n"
        assert kinds(src) == ["list-item", "blank", "paragraph", "blank", "code-block"]

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    def it_takes_an_indented_list_marker_for_code(self):
        """Taken for a list item, it would open an item that the next line
        belonged to."""
        src = "Para.\n\n    - not an item\n    more code\n\nAfter.\n"
        assert kinds(src)[2:4] == ["code-block", "code-block"]
        assert prose.Blocks(prose.Text(src)).item(6) is None

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    def it_counts_a_tab_as_four_columns_of_indent(self):
        assert kinds("Para.\n\n\tcode\n")[2] == "code-block"

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    def it_ends_an_html_block_at_a_blank_line(self):
        src = "<div>\nraw\n\nProse.\n"
        assert kinds(src) == ["html-block", "html-block", "blank", "paragraph"]

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    @pytest.mark.parametrize(
        ("block", "end"),
        [
            pytest.param("<script>\n\nx\n</script>", 4, id="raw-tag"),
            pytest.param("<?php\n\n?>", 3, id="processing-instruction"),
            pytest.param("<!DOCTYPE\n\nhtml>", 3, id="declaration"),
            pytest.param("<![CDATA[\n\n]]>", 3, id="cdata"),
        ],
    )
    def it_ends_an_html_block_with_an_end_marker_on_that_line(self, block, end):
        got = kinds(block + "\nProse.\n")
        assert got == ["html-block"] * end + ["paragraph"]

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    def it_runs_an_html_block_without_its_end_marker_to_the_end_of_the_file(self):
        assert kinds("<pre>never closed\n\nProse.\n") == ["html-block"] * 3

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    def it_lets_a_block_tag_interrupt_a_paragraph(self):
        assert kinds("Para.\n<div>\n") == ["paragraph", "html-block"]

    @pytest.mark.spec("segments-cmd-skips-protected-blocks")
    def it_does_not_take_a_tag_and_more_for_a_lone_tag(self):
        assert kinds("<span>text</span>\n") == ["paragraph"]


def items(src):
    """The line of the list item each line belongs to, or None."""
    blocks = prose.Blocks(prose.Text(src))
    return [item[0] if item else None for item in blocks.items]


class DescribeListItems:
    """A paragraph line can carry on a list item without starting one.

    apply indents a new line to the item's text only if it knows the line
    belongs to one, and segments reports it as a list-continuation.
    """

    @pytest.mark.spec("segments-cmd-maps-list-items")
    def it_gives_an_indented_continuation_line_to_its_item(self):
        assert items("- First\n  continues.\n- Second.\n") == [1, 1, 3]

    @pytest.mark.spec("segments-cmd-maps-list-items")
    def it_gives_a_lazy_continuation_line_to_its_item(self):
        assert items("- First\ncontinues lazily.\n") == [1, 1]

    @pytest.mark.spec("segments-cmd-maps-list-items")
    def it_gives_an_indented_paragraph_after_a_blank_line_to_its_item(self):
        assert items("- First.\n\n  A second paragraph.\n") == [1, None, 1]

    @pytest.mark.spec("segments-cmd-maps-list-items")
    def it_ends_the_list_at_an_unindented_paragraph_after_a_blank_line(self):
        assert items("- First.\n\nNot in the list.\n") == [1, None, None]

    @pytest.mark.spec("segments-cmd-maps-list-items")
    def it_ends_the_list_at_a_heading(self):
        assert items("- First.\n# Heading\nProse.\n") == [1, None, None]

    @pytest.mark.spec("segments-cmd-maps-list-items")
    def it_gives_a_line_to_the_innermost_item_its_indent_reaches(self):
        src = "- Outer\n  - Inner\n    inner text.\n\n  outer text.\n"
        assert items(src) == [1, 2, 2, None, 1]

    @pytest.mark.spec("segments-cmd-maps-list-items")
    def it_records_the_column_the_item_text_starts_at(self):
        blocks = prose.Blocks(prose.Text("10. Item\n    more.\n"))
        assert blocks.item(2) == (1, 4)

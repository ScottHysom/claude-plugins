"""segments keeps HTML comments away from the model.

A comment is a note for people, a FILL marker in the shipped rules among
them, so a prose rule has nothing to say about it. segments leaves every line
of one out, `<!--` and `-->` included, and hands out the prose either side of
a comment that sits inside a paragraph. The apply guard that backs this up is
in test_apply.py.
"""

import prose


def segments(src):
    text = prose.Text(src)
    return prose.segments_for(text, prose.Blocks(text))


def lines_of(segs):
    return sorted({s["line"] for s in segs})


class DescribeSegments:
    def it_leaves_out_every_line_of_a_multi_line_comment(self):
        segs = segments("# T\n\n<!--\nA note for people.\n-->\n\nProse.\n")
        assert lines_of(segs) == [1, 7]

    def it_leaves_out_a_comment_on_a_line_of_its_own(self):
        segs = segments("Before.\n\n<!-- FILL: say what this is for -->\n\nAfter.\n")
        assert [s["text"] for s in segs] == ["Before.", "After."]

    def it_leaves_out_a_comment_that_interrupts_a_paragraph(self):
        segs = segments("One line.\n<!-- a note\nstill a note -->\nNext line.\n")
        assert [s["text"] for s in segs] == ["One line.", "Next line."]

    def it_keeps_the_prose_either_side_of_a_comment_inside_a_paragraph(self):
        segs = segments("Some text <!-- a note --> more text.\n")
        assert [(s["col_start"], s["col_end"], s["text"]) for s in segs] == [
            (0, 9, "Some text"),
            (26, 36, "more text."),
        ]
        assert {s["kind"] for s in segs} == {"paragraph"}

    def it_leaves_out_the_middle_lines_of_a_comment_that_spans_paragraph_lines(self):
        segs = segments("A line <!-- that\nspans\nlines --> and ends.\n")
        assert [(s["line"], s["text"]) for s in segs] == [(1, "A line"), (3, "and ends.")]

    def it_keeps_a_heading_whose_comment_is_inline(self):
        segs = segments("# Title <!-- note -->\n")
        assert [(s["kind"], s["text"]) for s in segs] == [("heading", "Title")]

    def it_does_not_take_a_heading_or_fence_inside_a_comment_for_one(self):
        """A fence opened inside a comment would otherwise swallow the rest of
        the document, and a heading would join the heading path.
        """
        src = "<!--\n# Not a heading\n```\n-->\n\nProse after.\n"
        blocks = prose.Blocks(prose.Text(src))
        assert blocks.headings == []
        assert [s["text"] for s in segments(src)] == ["Prose after."]

    def it_treats_an_unclosed_comment_in_a_paragraph_as_text(self):
        """CommonMark renders it literally, and protecting to the end of the
        file would hide every paragraph after one stray marker.
        """
        segs = segments("Open <!-- never closed.\n\nLater prose.\n")
        assert [s["text"] for s in segs] == ["Open <!-- never closed.", "Later prose."]

    def it_does_not_close_a_comment_in_a_later_paragraph(self):
        segs = segments("Open <!-- stray.\n\nNext --> text.\n")
        assert [s["text"] for s in segs] == ["Open <!-- stray.", "Next --> text."]

    def it_ignores_a_comment_marker_inside_a_code_span(self):
        segs = segments("Write `<!--` to open one -->.\n")
        assert [s["text"] for s in segs] == ["Write `<!--` to open one -->."]

    def it_counts_the_lines_of_a_comment_as_protected(self, prose_repo, target_lines):
        code, envelope = prose_repo.run("segments", "target.md")
        assert code == prose.OK
        got = envelope["data"]["target.md"]
        assert target_lines["comment"] not in [s["line"] for s in got["segments"]]
        blocks = prose.Blocks(prose.Text(prose_repo.read()))
        comment_lines = [i + 1 for i, k in enumerate(blocks.kinds) if k == "comment"]
        assert comment_lines == [22, 23, 24]
        # front matter 3, blockquote 1, fence 3, comment 3
        assert got["protected_lines"] == 10

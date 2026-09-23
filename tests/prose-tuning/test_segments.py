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


# One of each kind segments hands out, for the tests that read its output.
KINDS = """# Title

A paragraph that
wraps.

- A list item.

| Term | Meaning |
|---|---|
| model | numbers |
"""


def run_text(prose_repo, capsys, *argv):
    """Run segments without --json. Returns (exit code, stdout, stderr)."""
    capsys.readouterr()
    code = prose.main(["segments", *argv, "-C", str(prose_repo.root)])
    out, err = capsys.readouterr()
    return code, out, err


class DescribeTheSegmentsCommand:
    def it_prints_one_line_per_segment_with_its_address_kind_and_text(self, prose_repo, capsys):
        (prose_repo.root / "kinds.md").write_text(KINDS)
        code, out, err = run_text(prose_repo, capsys, "kinds.md")
        assert code == prose.OK
        assert err == ""
        assert out == (
            "kinds.md:1:2-7  heading  Title\n"
            "kinds.md:3:0-16  paragraph  A paragraph that\n"
            "kinds.md:4:0-6  paragraph  wraps.\n"
            "kinds.md:6:2-14  list-item  A list item.\n"
            "kinds.md:8:2-6  table-cell  Term\n"
            "kinds.md:8:9-16  table-cell  Meaning\n"
            "kinds.md:10:2-7  table-cell  model\n"
            "kinds.md:10:10-17  table-cell  numbers\n"
        )

    def it_reads_every_file_in_scope_when_given_no_path(self, prose_repo, capsys):
        (prose_repo.root / "kinds.md").write_text(KINDS)
        code, out, _ = run_text(prose_repo, capsys)
        assert code == prose.OK
        assert {line.split(":", 1)[0] for line in out.splitlines()} == {"kinds.md", "target.md"}

    def it_prints_one_summary_line_per_file_and_the_totals(self, prose_repo, capsys):
        (prose_repo.root / "target.md").write_text(KINDS)
        code, out, _ = run_text(prose_repo, capsys, "--summary")
        assert code == prose.OK
        chars = len("TitleA paragraph thatwraps.A list item.TermMeaningmodelnumbers")
        assert out == (
            "target.md  8 segment(s), %d character(s), 0 protected line(s) of 10\n"
            "\n"
            "1 file(s), 8 segment(s), %d character(s)\n" % (chars, chars)
        )

    def it_leaves_the_segments_out_of_the_json_summary(self, prose_repo):
        code, envelope = prose_repo.run("segments", "--summary", "target.md")
        assert code == prose.OK
        assert "segments" not in envelope["data"]["target.md"]
        assert envelope["data"]["target.md"]["segment_count"] > 0


class DescribeListContinuations:
    def it_reports_a_line_that_continues_a_list_item_with_its_item(self):
        segs = segments("- First item starts here and\n  continues on this line.\n- Second.\n")
        assert [(s["line"], s["kind"], s.get("item")) for s in segs] == [
            (1, "list-item", None),
            (2, "list-continuation", 1),
            (3, "list-item", None),
        ]

    def it_reports_a_paragraph_after_a_list_as_a_paragraph(self):
        segs = segments("- An item.\n\nA paragraph.\n")
        assert [(s["kind"], s.get("item")) for s in segs] == [
            ("list-item", None),
            ("paragraph", None),
        ]

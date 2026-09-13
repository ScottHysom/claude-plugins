"""Spans that cannot be tagged safely are refused rather than mangled.

A tag opened inside a code fence or across a table row does not survive a
round trip, so the planner turns those down at plan time with a reason the
author can act on.
"""

import pytest

import prose


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        pytest.param({"kind": "del", "start": 5}, "heading", id="heading"),
        pytest.param({"kind": "del", "start": 19}, "fence", id="inside-a-fence"),
        pytest.param({"kind": "del", "start": 14}, "table", id="table-row"),
        pytest.param(
            {"kind": "del", "start": 7, "col_start": 5, "end": 8, "col_end": 3},
            "straddles",
            id="straddles-two-lines",
        ),
    ],
)
def test_unsafe_spans_are_refused(sample, record, reason):
    text = prose.Text(sample)
    blocks = prose.Blocks(text)
    with pytest.raises(prose.InsertRefusal) as caught:
        prose.plan_one_insert(text, blocks, record, "sample.md", 1)
    assert reason in str(caught.value)


def test_segments_skip_protected_regions(sample):
    """Front matter and code are not prose. Offering them for review invites
    a rewrite of a config key or a variable name.
    """
    text = prose.Text(sample)
    segments = prose.segments_for(text, prose.Blocks(text))
    bodies = [s["text"] for s in segments]
    assert not any("x = 1" in b for b in bodies)
    assert not any("title: sample" in b for b in bodies)


def test_segments_include_table_cells_and_headings(sample):
    text = prose.Text(sample)
    kinds = {s["kind"] for s in prose.segments_for(text, prose.Blocks(text))}
    assert "table-cell" in kinds
    assert "heading" in kinds


class TestRefusalsTheRoundTripPropertyFound:
    """Records the planner used to accept that broke the round trip, and the
    cases each fix still has to allow.

    The property in test_properties_round_trip.py asserts that no record breaks
    the round trip, for every record it can build. These name the particular
    cases it has found, one test each, because a shrunk counterexample in a
    failure message is not a reason - and the reason is what stops someone
    relaxing the guard later. When the property finds another, it goes here.
    """

    def plan(self, sample, record):
        text = prose.Text(sample)
        with pytest.raises(prose.InsertRefusal) as caught:
            prose.plan_one_insert(text, prose.Blocks(text), record, "sample.md", 1)
        return str(caught.value)

    def test_a_question_inside_a_fence(self, sample):
        """A <q> goes in as a new line, so it skipped the span check that
        refuses a <del> on the same line. Inside a fence the scanner then
        shields it as code and no strip ever removes it - a tag the author
        cannot delete.
        """
        assert "fence" in self.plan(
            sample, {"kind": "q", "start": 19, "text": "does this belong here?"}
        )

    def test_a_question_above_a_heading_is_still_allowed(self, sample):
        """The other side of that fix. A new line above a heading leaves the
        heading alone, so refusing it would be over-correction.
        """
        text = prose.Text(sample)
        assert prose.plan_one_insert(
            text,
            prose.Blocks(text),
            {"kind": "q", "start": 5, "text": "is this the right title?"},
            "sample.md",
            1,
        )

    @pytest.mark.parametrize(
        "cols",
        [
            pytest.param((0, 900), id="past-the-end"),
            pytest.param((-2, 6), id="negative"),
            pytest.param((9, 3), id="inverted"),
        ],
    )
    def test_columns_outside_the_line(self, sample, cols):
        """col_end=900 on a 76-character line put the closing tag at the end of
        the document, so a one-line edit wrapped the whole file.
        """
        problem = self.plan(
            sample, {"kind": "del", "start": 7, "col_start": cols[0], "col_end": cols[1]}
        )
        assert "col_start" in problem or "col_end" in problem

    def test_a_zero_width_inline_span(self, sample):
        """Both tags land on one offset, and EditEngine applies them in the
        order they were added: Curat</del><del>ed, not collected.
        """
        assert "empty" in self.plan(
            sample, {"kind": "del", "start": 7, "col_start": 5, "col_end": 5}
        )

    def test_a_tag_over_a_blank_line(self, sample):
        """Line 9 is blank. Wrapping it produced text that does not parse -
        `stray </del> closing nothing`.

        A one-line span is inline, and on a blank line both columns default to
        0, so the empty-span guard is the one that turns this down.
        """
        assert "empty" in self.plan(sample, {"kind": "del", "start": 9, "end": 9})

    def test_a_block_tag_over_nothing_but_blank_lines(self):
        """The multi-line form of the same thing, which needs a document with
        two blank lines in a row - SAMPLE has none.
        """
        text = prose.Text("Alpha.\n\n\n\nOmega.\n")
        with pytest.raises(prose.InsertRefusal) as caught:
            prose.plan_one_insert(
                text, prose.Blocks(text), {"kind": "del", "start": 2, "end": 4}, "t.md", 1
            )
        assert "blank" in str(caught.value)

    def test_an_insertion_alone_on_a_blank_line(self, sample):
        """<ins>x</ins> as a line's whole content is indistinguishable from a
        block tag, and a block tag owns its line - so the strip took the
        author's blank line with it.
        """
        assert "blank" in self.plan(sample, {"kind": "ins", "start": 4, "text": "a new sentence"})

    @pytest.mark.parametrize(
        "record",
        [
            pytest.param({"kind": "del", "start": 23, "end": 23}, id="inline"),
            pytest.param({"kind": "del", "start": 22, "end": 23}, id="block"),
            pytest.param(
                {"kind": "repl", "start": 22, "end": 23, "with": "New ending."}, id="block-repl"
            ),
        ],
    )
    def test_the_last_line_of_a_file_with_no_trailing_newline(self, sample, record):
        """Not a refusal - a fix, and two of them, because a span ending on the
        last line reaches that line by two different routes.

        A one-line span is inline, and its tags only look like block form once
        they are in the file, so top_replacement was the one adding the newline
        the file never had. A multi-line span is block form in the planner, and
        there it was the closing tag's own line. Either way every resolve pass
        returned the file one byte longer than it was.
        """
        text = prose.Text(sample)
        blocks = prose.Blocks(text)
        edits = prose.plan_one_insert(text, blocks, record, "sample.md", 1)
        assert not edits[-1][2].endswith("\n")

        engine, refusals, _ = prose.apply_inserts(
            text, blocks, [dict(record, file="sample.md")], "sample.md", 1
        )
        assert not refusals
        back, _ = prose.resolve_text(prose.Text(engine.result()), prose.REJECT, None, "sample.md")
        assert back == sample

    def test_two_records_whose_edits_share_an_offset(self, sample):
        """A <q> on the first line of a block <del> is an ordinary thing to
        ask for. The two edits land on one offset, EditEngine reported no
        conflict, and the splice dropped whichever went first.
        """
        text = prose.Text(sample)
        engine, refusals, _ = prose.apply_inserts(
            text,
            prose.Blocks(text),
            [
                {"file": "sample.md", "kind": "q", "start": 10, "text": "why?"},
                {"file": "sample.md", "kind": "del", "start": 10, "end": 12},
            ],
            "sample.md",
            1,
        )
        assert not refusals
        assert engine.conflicts()
        with pytest.raises(prose.Fatal):
            engine.result()

    def test_an_insertion_inside_another_record_s_deletion(self, sample):
        """The one defect plan_one_insert cannot see, because it is handed one
        record at a time.

        An <ins> point falling inside another record's <del> span is a grammar
        the scanner rejects - <ins> is not allowed inside <del>, which is what
        <repl> is for. Both records are well formed on their own, so nothing
        refused them, and the file written was one this tool's own `tags check`
        turns down.
        """
        text = prose.Text(sample)
        _, refusals, _ = prose.apply_inserts(
            text,
            prose.Blocks(text),
            [
                {"file": "sample.md", "kind": "del", "start": 7, "col_start": 0, "col_end": 7},
                {
                    "file": "sample.md",
                    "kind": "ins",
                    "start": 7,
                    "col_start": 3,
                    "col_end": 3,
                    "text": "a word",
                },
            ],
            "sample.md",
            1,
        )
        assert len(refusals) == 1
        assert "overlaps record 1" in refusals[0]

    def test_records_marking_up_separate_passages_are_both_kept(self, sample):
        """The other side of that fix: disjoint regions still compose, which is
        the whole reason insertion takes a batch.
        """
        text = prose.Text(sample)
        engine, refusals, _ = prose.apply_inserts(
            text,
            prose.Blocks(text),
            [
                {"file": "sample.md", "kind": "del", "start": 7, "col_start": 0, "col_end": 7},
                {"file": "sample.md", "kind": "del", "start": 8, "col_start": 0, "col_end": 4},
            ],
            "sample.md",
            1,
        )
        assert not refusals
        assert engine.conflicts() == []

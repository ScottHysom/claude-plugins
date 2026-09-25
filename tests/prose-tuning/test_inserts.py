"""Spans that cannot be tagged safely are refused rather than mangled.

A tag opened inside a code fence or across a table row does not survive a
round trip, so the planner turns those down at plan time with a reason the
author can act on.
"""

import json

import pytest

import prose


class DescribePlanOneInsert:
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
    def it_refuses_an_unsafe_span(self, sample, record, reason):
        text = prose.Text(sample)
        blocks = prose.Blocks(text)
        with pytest.raises(prose.InsertRefusal) as caught:
            prose.plan_one_insert(text, blocks, record, "sample.md", 1)
        assert reason in str(caught.value)


class DescribeSegmentsFor:
    """Which spans of a document are offered up for review at all."""

    def it_skips_protected_regions(self, sample):
        """Front matter and code are not prose. Offering them for review invites
        a rewrite of a config key or a variable name.
        """
        text = prose.Text(sample)
        segments = prose.segments_for(text, prose.Blocks(text))
        bodies = [s["text"] for s in segments]
        assert not any("x = 1" in b for b in bodies)
        assert not any("title: sample" in b for b in bodies)

    def it_includes_table_cells_and_headings(self, sample):
        text = prose.Text(sample)
        kinds = {s["kind"] for s in prose.segments_for(text, prose.Blocks(text))}
        assert "table-cell" in kinds
        assert "heading" in kinds


class DescribeRefusalsTheRoundTripPropertyFound:
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

    def it_refuses_a_question_inside_a_fence(self, sample):
        """A <q> goes in as a new line, so it skipped the span check that
        refuses a <del> on the same line. Inside a fence the scanner then
        shields it as code and no strip ever removes it - a tag the author
        cannot delete.
        """
        assert "fence" in self.plan(
            sample, {"kind": "q", "start": 19, "text": "does this belong here?"}
        )

    def it_allows_a_question_above_a_heading(self, sample):
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
    def it_refuses_columns_outside_the_line(self, sample, cols):
        """col_end=900 on a 76-character line put the closing tag at the end of
        the document, so a one-line edit wrapped the whole file.
        """
        problem = self.plan(
            sample, {"kind": "del", "start": 7, "col_start": cols[0], "col_end": cols[1]}
        )
        assert "col_start" in problem or "col_end" in problem

    def it_refuses_a_zero_width_inline_span(self, sample):
        """Both tags land on one offset, and EditEngine applies them in the
        order they were added: Curat</del><del>ed, not collected.
        """
        assert "empty" in self.plan(
            sample, {"kind": "del", "start": 7, "col_start": 5, "col_end": 5}
        )

    def it_refuses_a_tag_over_a_blank_line(self, sample):
        """Line 9 is blank. Wrapping it produced text that does not parse -
        `stray </del> closing nothing`.

        A one-line span is inline, and on a blank line both columns default to
        0, so the empty-span guard is the one that turns this down.
        """
        assert "empty" in self.plan(sample, {"kind": "del", "start": 9, "end": 9})

    def it_refuses_a_block_tag_over_nothing_but_blank_lines(self):
        """The multi-line form of the same thing, which needs a document with
        two blank lines in a row - SAMPLE has none.
        """
        text = prose.Text("Alpha.\n\n\n\nOmega.\n")
        with pytest.raises(prose.InsertRefusal) as caught:
            prose.plan_one_insert(
                text, prose.Blocks(text), {"kind": "del", "start": 2, "end": 4}, "t.md", 1
            )
        assert "blank" in str(caught.value)

    def it_refuses_an_insertion_alone_on_a_blank_line(self, sample):
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
    def it_adds_no_newline_to_a_file_that_ends_without_one(self, sample, record):
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

    def it_reports_a_conflict_when_two_records_share_an_offset(self, sample):
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

    def it_refuses_an_insertion_inside_another_records_deletion(self, sample):
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

    def it_keeps_records_marking_up_separate_passages(self, sample):
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


class DescribeAnchoredRecords:
    """A record may name its text and leave the columns out.

    The model used to count a record's columns itself, which is the mistake
    #76 fixed for apply's findings: a column off by one and the script refused
    a good edit. These mirror test_apply.py's DescribeAnchoredFindings.
    """

    LIST = "- First item starts here and\n  continues on this line.\n- Second.\n"

    def tag(self, content, record):
        """The file with the record's tags in it, or the refusal as a string."""
        text = prose.Text(content)
        engine, refusals, _ = prose.apply_inserts(
            text, prose.Blocks(text), [dict(record, file="doc.md")], "doc.md", 1
        )
        return refusals[0] if refusals else engine.result()

    def it_finds_the_text_on_its_start_line(self):
        assert (
            self.tag("the cat sat.\n", {"kind": "del", "start": 1, "text": "cat"})
            == "the <del>cat</del> sat.\n"
        )

    def it_replaces_the_text_it_names(self):
        record = {"kind": "repl", "start": 1, "text": "cat", "with": "dog"}
        assert self.tag("the cat sat.\n", record) == "the <del>cat</del><ins>dog</ins> sat.\n"

    def it_refuses_text_that_does_not_start_on_its_line(self):
        record = {"kind": "del", "start": 1, "text": "Another line."}
        assert self.tag("One line.\nAnother line.\n", record) == (
            "doc.md:1  record 1 refused: text: 'Another line.' does not start on this "
            "line. Re-run evidence."
        )

    def it_refuses_text_that_starts_more_than_once_on_its_line(self):
        record = {"kind": "del", "start": 1, "text": "the"}
        assert self.tag("the cat and the dog\n", record) == (
            "doc.md:1  record 1 refused: text: 'the' starts at columns 0, 12 on this "
            "line; add col_start to say which"
        )

    def it_takes_col_start_to_say_which_match(self):
        record = {"kind": "del", "start": 1, "text": "the", "col_start": 12}
        assert self.tag("the cat and the dog\n", record) == "the cat and <del>the</del> dog\n"

    def it_refuses_a_col_start_past_the_end_of_the_line(self):
        """Text.offset adds the column blind, so col_start=11 on a short line
        would look for the text on a later line instead.
        """
        record = {"kind": "del", "start": 1, "text": "cat", "col_start": 11}
        assert self.tag("Short.\nThe cat sat.\n", record) == (
            "doc.md:1  record 1 refused: column 11 is outside the line (6 characters)"
        )

    def it_marks_whole_lines_named_by_a_wrapped_text(self):
        """A wrapped list item is one record, in block form."""
        record = {
            "kind": "del",
            "start": 1,
            "text": "- First item starts here and\n  continues on this line.",
        }
        assert self.tag(self.LIST, record) == (
            "<del>\n- First item starts here and\n  continues on this line.\n</del>\n- Second.\n"
        )

    def it_takes_a_wrapped_text_without_its_first_lines_indent(self):
        content = "  An indented paragraph\n  that wraps.\n"
        record = {"kind": "del", "start": 1, "text": "An indented paragraph\n  that wraps."}
        assert self.tag(content, record) == (
            "  <del>\n  An indented paragraph\n  that wraps.\n  </del>\n"
        )

    @pytest.mark.parametrize(
        "wrapped",
        [
            pytest.param("item starts here and\n  continues on this line.", id="starts-mid-line"),
            pytest.param("- First item starts here and\n  continues", id="ends-mid-line"),
        ],
    )
    def it_refuses_a_wrapped_text_that_covers_part_of_a_line(self, wrapped):
        """Block form marks whole lines, so a text naming part of one would
        quietly tag more than it said.
        """
        refusal = self.tag(self.LIST, {"kind": "del", "start": 1, "text": wrapped})
        assert refusal == (
            "doc.md:1  record 1 refused: a text that crosses lines marks them whole; copy "
            "each line from its start to its end, list marker included, or keep it inside "
            "one line"
        )

    def it_refuses_an_end_that_disagrees_with_the_text(self):
        record = {
            "kind": "del",
            "start": 1,
            "end": 1,
            "text": "- First item starts here and\n  continues on this line.",
        }
        assert self.tag(self.LIST, record) == (
            "doc.md:1  record 1 refused: end is line 1, but the text ends on line 2; leave end out"
        )

    def it_places_an_insertion_after_the_text_it_follows(self):
        record = {"kind": "ins", "start": 1, "after": "the cat", "text": " quietly"}
        assert self.tag("the cat sat.\n", record) == "the cat<ins> quietly</ins> sat.\n"

    def it_refuses_an_insertion_after_a_text_that_crosses_lines(self):
        record = {"kind": "ins", "start": 1, "after": "here and\n  ", "text": "x"}
        assert self.tag(self.LIST, record) == (
            "doc.md:1  record 1 refused: <ins> inserts at a point; give an after on one line"
        )

    def it_refuses_an_insertion_after_a_text_that_is_not_there(self):
        record = {"kind": "ins", "start": 1, "after": "the dog", "text": "x"}
        assert self.tag("the cat sat.\n", record) == (
            "doc.md:1  record 1 refused: after: 'the dog' does not start on this line. "
            "Re-run evidence."
        )


class DescribeInsertCommand:
    """`tags insert` driven the way the skills drive it, with the batch in a
    file. The planner tests above hand records straight to apply_inserts, so
    nothing there reads a batch, parses it, or writes the result back.
    """

    def insert(self, prose_repo, batch_text, *flags):
        batch = prose_repo.root / "batch.json"
        batch.write_text(batch_text)
        return prose_repo.run("tags", "insert", "--batch", str(batch), *flags)

    def it_reads_a_batch_file_and_writes_its_tags(self, prose_repo, target):
        record = {"file": "target.md", "kind": "q", "start": 8, "text": "earned?"}
        code, envelope = self.insert(prose_repo, json.dumps([record]))
        assert code == prose.OK, envelope["errors"]
        assert envelope["data"] == {"target.md": {"tags": [{"kind": "q", "line": 8}]}}
        lines = target.split("\n")
        lines.insert(7, '<q id="1">earned?</q>')
        assert prose_repo.read() == "\n".join(lines)

    def it_tags_a_record_addressed_by_its_text(self, prose_repo, target):
        record = {
            "file": "target.md",
            "kind": "del",
            "start": 7,
            "text": "Curated, not collected.",
            "why": "restates",
        }
        code, envelope = self.insert(prose_repo, json.dumps([record]))
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read() == target.replace(
            "Curated, not collected.", '<del why="restates">Curated, not collected.</del>'
        )

    def it_writes_nothing_when_a_records_text_is_not_on_its_line(self, prose_repo, target):
        record = {"file": "target.md", "kind": "del", "start": 7, "text": "Final paragraph."}
        code, envelope = self.insert(prose_repo, json.dumps([record]))
        assert code == prose.PROBLEMS
        assert envelope["errors"][0] == (
            "target.md:7  record 1 refused: text: 'Final paragraph.' does not start on "
            "this line. Re-run evidence."
        )
        assert prose_repo.read() == target

    def it_leaves_the_file_alone_on_a_dry_run(self, prose_repo, target):
        record = {"file": "target.md", "kind": "q", "start": 8, "text": "earned?"}
        code, _ = self.insert(prose_repo, json.dumps([record]), "--dry-run")
        assert code == prose.OK
        assert prose_repo.read() == target

    @pytest.mark.parametrize(
        ("batch_text", "problem"),
        [
            pytest.param("not json", "not valid JSON", id="not-json"),
            pytest.param('{"kind": "q"}', "must be a JSON array", id="not-an-array"),
        ],
    )
    def it_stops_the_run_on_a_batch_it_cannot_use(self, prose_repo, target, batch_text, problem):
        code, envelope = self.insert(prose_repo, batch_text)
        assert code == prose.CANNOT_RUN
        assert envelope is None
        assert problem in prose_repo.err
        assert prose_repo.read() == target

    def it_stops_the_run_with_a_message_on_a_missing_batch_file(self, prose_repo):
        """The skills write the batch and then name it, so a wrong path is a
        typo away. apply reports a missing findings file as a message and exit
        2; insert has to do the same rather than end in a traceback.
        """
        missing = prose_repo.root / "no-such-batch.json"
        code, envelope = prose_repo.run("tags", "insert", "--batch", str(missing))
        assert code == prose.CANNOT_RUN
        assert envelope is None
        assert "cannot read batch" in prose_repo.err

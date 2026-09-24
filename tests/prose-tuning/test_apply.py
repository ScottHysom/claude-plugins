"""apply is the one command that rewrites a file the user did not open.

Every other command reports. This one takes a list of approved rewrites and
writes them to disk, so each guard in its loop is the last thing between a
finding computed against a stale report and a corrupted document. The guards
were asserted by nothing until these tests: `is_protected` could be replaced
with `return False` and the whole suite stayed green.

The refusals in test_inserts.py are the mirror of these at insertion time.
Both exist because a refusal the author can read beats a rewrite they have to
find later.
"""

import io
import json

import pytest

import prose


def errors_of(envelope):
    """Rejections, minus the trailing advice line apply appends in whole-batch
    mode. That line is about the run, not about a finding.
    """
    return [e for e in envelope["errors"] if not e.startswith("nothing was")]


class DescribeApply:
    """The path everything else in this file is a refusal of."""

    def it_writes_a_clean_finding(self, prose_repo, target_lines):
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(
                    target_lines["last-paragraph"],
                    col_start=0,
                    col_end=16,
                    text="Final paragraph.",
                    replacement="The closing paragraph.",
                ),
            ]
        )
        assert code == prose.OK
        assert envelope["errors"] == []
        assert "The closing paragraph." in prose_repo.read()

    def it_reads_the_findings_from_stdin_given_a_dash(self, prose_repo, target_lines, monkeypatch):
        finding = prose_repo.finding(
            target_lines["last-paragraph"],
            col_start=0,
            col_end=16,
            text="Final paragraph.",
            replacement="The closing paragraph.",
        )
        path = prose_repo.findings_file([finding])
        token = prose_repo.token(path)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([finding])))
        code, _ = prose_repo.run("apply", "--findings", "-", "--token", token)
        assert code == prose.OK
        assert "The closing paragraph." in prose_repo.read()


class DescribeGuards:
    """One malformed finding, one named rejection, and nothing on disk."""

    @pytest.mark.parametrize("kind", ["frontmatter", "blockquote", "fence", "comment"])
    def it_refuses_a_protected_line(self, prose_repo, target_lines, kind):
        before = prose_repo.read()
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(target_lines[kind]),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  is a %s; prose rules do not apply there" % (target_lines[kind], kind)
        ]
        assert prose_repo.read() == before

    @pytest.mark.parametrize(
        "line",
        [
            pytest.param(0, id="before-the-first-line"),
            pytest.param(-1, id="negative"),
            pytest.param(999, id="past-the-last-line"),
        ],
    )
    def it_refuses_a_line_outside_the_file(self, prose_repo, line):
        before = prose_repo.read()
        code, envelope = prose_repo.apply([prose_repo.finding(line)])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["target.md:%d  line is outside the file" % line]
        assert prose_repo.read() == before

    def it_refuses_a_missing_file(self, prose_repo):
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(1, file="nowhere.md"),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["nowhere.md  no such file"]

    def it_refuses_a_rule_the_config_does_not_define(self, prose_repo, target_lines):
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(target_lines["paragraph"], rule="made-up-rule"),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "finding 1 names rule 'made-up-rule', which is not in .claude/rules/prose-style.md"
        ]

    def it_refuses_text_that_moved_since_the_report(self, prose_repo, target_lines):
        """The report and the rewrite are two runs. If the document changed
        between them the offsets still resolve, they just resolve onto the
        wrong words - so the finding carries the text it expects to find.
        """
        before = prose_repo.read()
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(
                    target_lines["last-paragraph"],
                    col_start=0,
                    col_end=16,
                    text="Something else entirely.",
                ),
            ]
        )
        assert code == prose.PROBLEMS
        assert "the text moved" in errors_of(envelope)[0]
        assert prose_repo.read() == before

    @pytest.mark.parametrize(
        "replacement",
        [
            pytest.param("a | b", id="pipe"),
            pytest.param("a\nb", id="newline"),
        ],
    )
    def it_refuses_a_replacement_that_would_break_a_table(
        self, prose_repo, target_lines, replacement
    ):
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(
                    target_lines["table"], col_start=2, col_end=7, replacement=replacement
                ),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  a table cell cannot contain | or a newline" % target_lines["table"]
        ]

    @pytest.mark.parametrize(
        "cols",
        [
            pytest.param((0, 900), id="past-the-end"),
            pytest.param((-4, 6), id="negative"),
            pytest.param((9, 3), id="inverted"),
        ],
    )
    def it_refuses_columns_outside_the_line(self, prose_repo, target_lines, cols):
        """Text.offset checks the line and then adds the column blind, so an
        out-of-range column lands somewhere else in the file. col_end=900 on a
        short line put a rewrite at the end of the document.
        """
        line = target_lines["paragraph"]
        before = prose_repo.read()
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(line, col_start=cols[0], col_end=cols[1]),
            ]
        )
        assert code == prose.PROBLEMS
        assert "are outside the line" in errors_of(envelope)[0]
        assert prose_repo.read() == before

    def it_refuses_a_multi_line_replacement_outside_a_paragraph(self, prose_repo, target_lines):
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(
                    target_lines["heading"], col_start=2, col_end=9, replacement="two\nlines"
                ),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  a heading replacement cannot span lines" % target_lines["heading"]
        ]

    @pytest.mark.parametrize(
        "cols",
        [
            pytest.param((10, 25), id="the-whole-comment"),
            pytest.param((0, 12), id="prose-and-the-opening-marker"),
            pytest.param((15, 15), id="an-insertion-inside-it"),
        ],
    )
    def it_refuses_a_finding_that_touches_an_inline_comment(self, prose_repo, cols):
        (prose_repo.root / "notes.md").write_text("Some text <!-- a note --> more text.\n")
        before = prose_repo.read("notes.md")
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(1, file="notes.md", col_start=cols[0], col_end=cols[1]),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "notes.md:1  columns %d-%d touch an HTML comment; prose rules do not apply there" % cols
        ]
        assert prose_repo.read("notes.md") == before

    @pytest.mark.parametrize(
        ("cols", "after"),
        [
            pytest.param((0, 9), "rewritten <!-- a note --> more text.\n", id="the-prose-before"),
            pytest.param(
                (10, 10), "Some text rewritten<!-- a note --> more text.\n", id="up-to-it"
            ),
            pytest.param(
                (25, 25), "Some text <!-- a note -->rewritten more text.\n", id="just-after"
            ),
        ],
    )
    def it_applies_a_finding_on_the_prose_beside_an_inline_comment(self, prose_repo, cols, after):
        (prose_repo.root / "notes.md").write_text("Some text <!-- a note --> more text.\n")
        code, _ = prose_repo.apply(
            [
                prose_repo.finding(1, file="notes.md", col_start=cols[0], col_end=cols[1]),
            ]
        )
        assert code == prose.OK
        assert prose_repo.read("notes.md") == after

    def it_refuses_two_edits_on_the_same_span_and_names_both(self, prose_repo, target_lines):
        """EditEngine applies a batch from one snapshot. Overlapping spans have
        no defined result, so the batch is turned down rather than resolved by
        whichever sorted first. The refusal names each finding by its place in
        the batch, its line and its rule, since byte offsets send the author
        nowhere.
        """
        line = target_lines["paragraph"]
        before = prose_repo.read()
        first = prose_repo.finding(line, col_start=0, col_end=10)
        code, envelope = prose_repo.apply(
            [first, prose_repo.finding(line, col_start=5, col_end=15)]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md  finding 1 (target.md:%d, %s) overlaps finding 2 (target.md:%d, %s)"
            % (line, first["rule"], line, first["rule"])
        ]
        assert prose_repo.read() == before


def cut(prose_repo, line, text, **overrides):
    """A finding that deletes `text`, which starts `line` of doc.md."""
    record = dict(file="doc.md", col_start=0, col_end=len(text), text=text, replacement="")
    record.update(overrides)
    return prose_repo.finding(line, **record)


class DescribeWholeLineCuts:
    """A finding cannot reach past its line's end, so cutting a line used to
    empty it and keep its newline. Cutting a passage left one blank line per
    line it had, and #73 needed them collapsed by hand.
    """

    def write(self, prose_repo, content):
        (prose_repo.root / "doc.md").write_text(content)

    def it_removes_a_cut_passage_and_keeps_one_blank_line(self, prose_repo):
        self.write(prose_repo, "Keep this.\n\nCut this line.\nAnd this one.\n\nKeep this too.\n")
        code, _ = prose_repo.apply(
            [cut(prose_repo, 3, "Cut this line."), cut(prose_repo, 4, "And this one.")]
        )
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "Keep this.\n\nKeep this too.\n"

    def it_joins_the_lines_around_one_cut_from_a_paragraph(self, prose_repo):
        self.write(prose_repo, "One.\nTwo.\nThree.\n")
        code, _ = prose_repo.apply([cut(prose_repo, 2, "Two.")])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "One.\nThree.\n"

    def it_removes_a_line_that_two_findings_empty_between_them(self, prose_repo):
        self.write(prose_repo, "One.\nFirst half, second half.\nThree.\n")
        code, _ = prose_repo.apply(
            [
                cut(prose_repo, 2, "First half,", col_end=11),
                cut(prose_repo, 2, " second half.", col_start=11, col_end=24),
            ]
        )
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "One.\nThree.\n"

    def it_leaves_the_rest_of_a_partly_cut_line_alone(self, prose_repo):
        self.write(prose_repo, "One.\nKeep, cut.\nThree.\n")
        code, _ = prose_repo.apply([cut(prose_repo, 2, " cut.", col_start=5, col_end=10)])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "One.\nKeep,\nThree.\n"

    def it_keeps_a_line_that_also_takes_a_replacement(self, prose_repo):
        self.write(prose_repo, "One.\nOld words.\nThree.\n")
        code, _ = prose_repo.apply(
            [
                cut(prose_repo, 2, "Old", col_end=3, replacement="New"),
                cut(prose_repo, 2, " words.", col_start=3, col_end=10),
            ]
        )
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "One.\nNew\nThree.\n"

    @pytest.mark.parametrize(
        ("content", "line", "text", "after"),
        [
            pytest.param("Cut.\n\nKeep.\n", 1, "Cut.", "Keep.\n", id="start-of-file"),
            pytest.param("Keep.\n\nCut.\n", 3, "Cut.", "Keep.\n", id="end-of-file"),
            pytest.param("Keep.\n\nCut.", 3, "Cut.", "Keep.", id="end-without-a-newline"),
            pytest.param("Keep.\nCut.", 2, "Cut.", "Keep.", id="last-paragraph-line"),
        ],
    )
    def it_leaves_no_blank_line_at_either_end_of_the_file(
        self, prose_repo, content, line, text, after
    ):
        self.write(prose_repo, content)
        code, _ = prose_repo.apply([cut(prose_repo, line, text)])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == after

    def it_still_rewrites_a_later_line_after_a_cut(self, prose_repo):
        """Every edit is planned against one snapshot, so removing lines does
        not shift the address of a finding below them.
        """
        self.write(prose_repo, "Keep.\n\nCut.\n\nOld.\n")
        code, _ = prose_repo.apply(
            [cut(prose_repo, 3, "Cut."), cut(prose_repo, 5, "Old.", replacement="New.")]
        )
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "Keep.\n\nNew.\n"


def anchored(prose_repo, line, text, replacement="", **overrides):
    """A finding on doc.md addressed by its line and text, with no columns."""
    return prose_repo.finding(line, file="doc.md", text=text, replacement=replacement, **overrides)


class DescribeAnchoredFindings:
    """A finding may leave its columns out and let apply find its text.

    The model used to count the columns itself. One off-by-one read as stale
    text, and the next run of apply-prose wrote a helper to do the counting.
    """

    def write(self, prose_repo, content):
        (prose_repo.root / "doc.md").write_text(content)

    def it_finds_the_text_on_its_line(self, prose_repo):
        self.write(prose_repo, "- First item starts here and\n  continues on this line.\n")
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 2, "continues on this line.", "goes on here.")]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "- First item starts here and\n  goes on here.\n"

    def it_refuses_text_that_does_not_start_on_its_line(self, prose_repo):
        self.write(prose_repo, "One line.\nAnother line.\n")
        before = prose_repo.read("doc.md")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "Another line.")])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1: 'Another line.' does not start on this line. Re-run the report."
        ]
        assert prose_repo.read("doc.md") == before

    def it_refuses_text_that_starts_more_than_once_on_its_line(self, prose_repo):
        self.write(prose_repo, "the cat and the dog\n")
        before = prose_repo.read("doc.md")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "the", "a")])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1: 'the' starts at columns 0, 12 on this line; "
            "add col_start to say which"
        ]
        assert prose_repo.read("doc.md") == before

    def it_takes_col_start_to_say_which_match(self, prose_repo):
        self.write(prose_repo, "the cat and the dog\n")
        code, _ = prose_repo.apply([anchored(prose_repo, 1, "the", "a", col_start=12)])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "the cat and a dog\n"

    def it_refuses_a_col_start_past_the_end_of_the_line(self, prose_repo):
        """Text.offset adds the column blind, so col_start=40 on a short line
        would look for the text on a later line instead.
        """
        self.write(prose_repo, "Short.\nThe cat sat.\n")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "cat", "dog", col_start=11)])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["doc.md:1  column 11 is outside the line (6 characters)"]

    def it_refuses_an_empty_text_without_col_start(self, prose_repo):
        self.write(prose_repo, "One line.\n")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "", "x")])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1: an empty text needs col_start to say where it goes"
        ]

    def it_names_each_finding_by_its_place_in_the_batch(self, prose_repo):
        self.write(prose_repo, "One line.\nAnother line.\n")
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 1, "One", "Single"), anchored(prose_repo, 2, "missing")]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope)[0].startswith("doc.md:2  finding 2: 'missing'")


class DescribeSpansAcrossLines:
    """A finding whose text holds a newline ends on a later line.

    A wrapped sentence used to take one finding per line, each with its own
    columns, and #73 needed three sentences split that way.
    """

    WRAPPED = "- First item starts here and\n  continues on this line.\n"

    def write(self, prose_repo, content):
        (prose_repo.root / "doc.md").write_text(content)

    def it_rewrites_a_wrapped_sentence_as_one_finding(self, prose_repo):
        self.write(prose_repo, self.WRAPPED)
        code, envelope = prose_repo.apply(
            [
                anchored(
                    prose_repo,
                    1,
                    "First item starts here and\n  continues on this line.",
                    "One item.",
                )
            ]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "- One item.\n"

    def it_keeps_a_newline_in_the_rewrite_of_a_span_that_crossed_one(self, prose_repo):
        """A list item may not take a newline it did not have. A span that
        already crossed a line in one may put one back.
        """
        self.write(prose_repo, self.WRAPPED)
        code, envelope = prose_repo.apply(
            [
                anchored(
                    prose_repo,
                    1,
                    "starts here and\n  continues on this line.",
                    "starts here\n  and goes on.",
                )
            ]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "- First item starts here\n  and goes on.\n"

    def it_refuses_a_span_that_crosses_a_blank_line(self, prose_repo):
        self.write(prose_repo, "One.\n\nTwo.\n")
        before = prose_repo.read("doc.md")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "One.\n\nTwo.")])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1 crosses line 2, which is blank; a finding can cross "
            "lines only within a paragraph or a list item"
        ]
        assert prose_repo.read("doc.md") == before

    def it_refuses_a_span_that_reaches_a_protected_line(self, prose_repo):
        self.write(prose_repo, "Some prose.\n> A quotation.\n")
        before = prose_repo.read("doc.md")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "prose.\n> A")])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["doc.md:2  is a blockquote; prose rules do not apply there"]
        assert prose_repo.read("doc.md") == before

    def it_removes_the_lines_a_span_cuts_whole(self, prose_repo):
        self.write(prose_repo, "Keep this.\n\nCut this line.\nAnd this one.\n\nKeep this too.\n")
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 3, "Cut this line.\nAnd this one.")]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "Keep this.\n\nKeep this too.\n"

    def it_joins_what_is_left_when_a_span_cuts_part_of_a_line(self, prose_repo):
        """The first line is covered whole, but the span goes on into the
        second, so the span's own edit removes the newline between them.
        """
        self.write(prose_repo, "Cut.\nKeep this.\n")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "Cut.\nKeep ")])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "this.\n"


class DescribeNewLinesInListItems:
    """A new line in a list item's rewrite is indented to the item's text.

    Written at column 0, it ended the item there, and a line starting with a
    `-`, a `#` or a number and a dot became a block of its own (#80).
    """

    WRAPPED = "- First item starts here and\n  continues on this line.\n- Second item.\n"

    def write(self, prose_repo, content):
        (prose_repo.root / "doc.md").write_text(content)

    @pytest.mark.parametrize("added", ["A new sentence.", "- A dash.", "# A hash.", "2. A number."])
    def it_indents_a_new_line_on_a_continuation_line(self, prose_repo, added):
        self.write(prose_repo, self.WRAPPED)
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 2, "continues on this line.", "continues here.\n" + added)]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == (
            "- First item starts here and\n  continues here.\n  %s\n- Second item.\n" % added
        )

    def it_indents_a_new_line_in_a_span_that_starts_on_the_item(self, prose_repo):
        self.write(prose_repo, self.WRAPPED)
        code, envelope = prose_repo.apply(
            [
                anchored(
                    prose_repo,
                    1,
                    "starts here and\n  continues on this line.",
                    "starts here.\nIt goes on.",
                )
            ]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == (
            "- First item starts here.\n  It goes on.\n- Second item.\n"
        )

    def it_leaves_a_new_line_indented_past_the_item_text_as_written(self, prose_repo):
        self.write(prose_repo, self.WRAPPED)
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 2, "continues on this line.", "continues:\n    - deeper.")]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == (
            "- First item starts here and\n  continues:\n    - deeper.\n- Second item.\n"
        )

    def it_leaves_a_new_line_in_a_paragraph_after_the_list_unindented(self, prose_repo):
        self.write(prose_repo, "- An item.\n\nA paragraph.\n")
        code, envelope = prose_repo.apply([anchored(prose_repo, 3, "A paragraph.", "One.\nTwo.")])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "- An item.\n\nOne.\nTwo.\n"


class DescribeHelp:
    def it_describes_every_field_of_a_finding(self, capsys):
        with pytest.raises(SystemExit) as exit:
            prose.main(["apply", "--help"])
        assert exit.value.code == prose.OK
        out = capsys.readouterr().out
        for field in ("file", "line", "rule", "text", "replacement", "col_start", "col_end"):
            assert "  %s " % field in out, field
        assert "newline" in out
        assert "apply what is valid" in out


class DescribePartial:
    """Whole-batch by default, --partial to take what is good.

    The default is the safe one: a batch containing a bad finding writes
    nothing, so the author fixes the report rather than reconciling a document
    that took half of it.
    """

    def records(self, prose_repo, target_lines):
        return [
            prose_repo.finding(
                target_lines["last-paragraph"],
                col_start=0,
                col_end=16,
                replacement="The closing paragraph.",
            ),
            prose_repo.finding(target_lines["fence"]),
        ]

    def it_writes_nothing_when_one_finding_is_bad(self, prose_repo, target_lines):
        before = prose_repo.read()
        code, envelope = prose_repo.apply(self.records(prose_repo, target_lines))
        assert code == prose.PROBLEMS
        assert envelope["data"]["applied"] == []
        assert envelope["errors"][-1] == "nothing was written; pass --partial to apply the rest"
        assert prose_repo.read() == before

    def it_writes_the_good_finding_with_partial(self, prose_repo, target_lines):
        code, envelope = prose_repo.apply(self.records(prose_repo, target_lines), "--partial")
        assert code == prose.PROBLEMS
        assert [a["line"] for a in envelope["data"]["applied"]] == [target_lines["last-paragraph"]]
        assert "The closing paragraph." in prose_repo.read()

    def it_still_leaves_the_protected_line_alone_with_partial(self, prose_repo, target_lines):
        prose_repo.apply(self.records(prose_repo, target_lines), "--partial")
        line = prose_repo.read().splitlines()[target_lines["fence"] - 1]
        assert line == "x = 1"


class DescribeDryRun:
    def it_reports_without_writing(self, prose_repo, target_lines):
        before = prose_repo.read()
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(
                    target_lines["last-paragraph"],
                    col_start=0,
                    col_end=16,
                    replacement="The closing paragraph.",
                ),
            ],
            "--dry-run",
        )
        assert code == prose.OK
        assert len(envelope["data"]["applied"]) == 1
        assert prose_repo.read() == before


# A second rule beside RULE_ID, so a filter by rule has something to leave out.
OTHER_RULE = "sentences-plain-verbs"
OTHER_RULE_TEXT = """
### sentences-plain-verbs: Uses plain verbs

A sentence says what happens in the plainest verb that fits.
"""


class DescribeFilters:
    """--only and --file carry an approval by rule or by file.

    Without them the model cut the findings file down by hand, and nothing
    checked the cut. Each test runs the same four findings - two rules in two
    files - and asserts which of them reached disk.
    """

    @pytest.fixture
    def four(self, prose_repo, target_lines):
        style = prose_repo.root / prose.CONFIG_PATH
        style.write_text(style.read_text() + OTHER_RULE_TEXT)
        (prose_repo.root / "other.md").write_text(prose_repo.read())
        findings = []
        for rel in ("target.md", "other.md"):
            findings.append(
                prose_repo.finding(
                    target_lines["last-paragraph"],
                    file=rel,
                    col_start=0,
                    col_end=16,
                    text="Final paragraph.",
                    replacement="The closing paragraph.",
                )
            )
            findings.append(
                prose_repo.finding(
                    target_lines["paragraph"],
                    file=rel,
                    rule=OTHER_RULE,
                    col_start=0,
                    col_end=4,
                    text="used",
                    replacement="put to use",
                )
            )
        return findings

    def written(self, prose_repo):
        """Which (file, rule) pairs reached disk."""
        pairs = set()
        for rel in ("target.md", "other.md"):
            text = prose_repo.read(rel)
            if "The closing paragraph." in text:
                pairs.add((rel, "sentences-own-subject"))
            if "put to use for something." in text:
                pairs.add((rel, OTHER_RULE))
        return pairs

    def it_writes_every_finding_given_no_filter(self, prose_repo, four):
        code, _ = prose_repo.apply(four)
        assert code == prose.OK
        assert len(self.written(prose_repo)) == 4

    def it_writes_only_the_named_rules(self, prose_repo, four):
        code, _ = prose_repo.apply(four, "--only", OTHER_RULE)
        assert code == prose.OK
        assert self.written(prose_repo) == {("target.md", OTHER_RULE), ("other.md", OTHER_RULE)}

    def it_writes_only_the_named_files(self, prose_repo, four):
        before = prose_repo.read("other.md")
        code, _ = prose_repo.apply(four, "--file", "target.md")
        assert code == prose.OK
        assert self.written(prose_repo) == {
            ("target.md", "sentences-own-subject"),
            ("target.md", OTHER_RULE),
        }
        assert prose_repo.read("other.md") == before

    def it_writes_every_file_named_by_a_repeated_flag(self, prose_repo, four):
        code, _ = prose_repo.apply(four, "--file", "target.md", "--file", "other.md")
        assert code == prose.OK
        assert len(self.written(prose_repo)) == 4

    def it_writes_only_findings_that_pass_both_filters(self, prose_repo, four):
        code, envelope = prose_repo.apply(four, "--only", OTHER_RULE, "--file", "other.md")
        assert code == prose.OK
        assert self.written(prose_repo) == {("other.md", OTHER_RULE)}
        assert len(envelope["data"]["applied"]) == 1

    def it_matches_a_file_given_with_a_leading_dot_slash(self, prose_repo, four):
        code, _ = prose_repo.apply(four, "--file", "./other.md")
        assert code == prose.OK
        assert {rel for rel, _ in self.written(prose_repo)} == {"other.md"}

    @pytest.mark.parametrize(
        ("flags", "error"),
        [
            pytest.param(
                ("--only", "no-such-rule"), "--only no-such-rule matches no finding", id="rule"
            ),
            pytest.param(
                ("--file", "nowhere.md"), "--file nowhere.md matches no finding", id="file"
            ),
        ],
    )
    def it_refuses_a_filter_that_matches_no_finding(self, prose_repo, four, flags, error):
        """A typo in a filter used to select nothing, write nothing and exit
        clean, which reads as a successful run.
        """
        code, envelope = prose_repo.apply(four, *flags)
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [error]
        assert self.written(prose_repo) == set()

    def it_refuses_filters_whose_combination_matches_no_finding(self, prose_repo, four):
        """Each value matches some finding, so neither is a typo, but no
        finding passes both. That is still a run that would write nothing.
        """
        target_first_rule, other_second_rule = four[0], four[3]
        code, envelope = prose_repo.apply(
            [target_first_rule, other_second_rule],
            "--only",
            "sentences-own-subject",
            "--file",
            "other.md",
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["--only and --file together match no finding"]

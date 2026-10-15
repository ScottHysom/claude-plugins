"""apply is the one command that rewrites a file the user did not open.

Every other command reports. This one takes a list of approved rewrites and
writes them to disk, so each guard in its loop is the last thing between a
finding computed against a stale report and a corrupted document. The guards
were asserted by nothing until these tests: `is_protected` could be replaced
with `return False` and the whole suite stayed green.

Each guard refuses rather than writes, because a refusal the author can read
beats a rewrite they have to find later.
"""

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

    @pytest.mark.spec("apply-cmd-writes-approved")
    def it_writes_a_clean_finding(self, prose_repo, target_lines):
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(
                    target_lines["last-paragraph"],
                    text="Final paragraph.",
                    replacement="The closing paragraph.",
                ),
            ]
        )
        assert code == prose.OK
        assert envelope["errors"] == []
        assert "The closing paragraph." in prose_repo.read()

    @pytest.mark.spec(
        "apply-cmd-writes-approved", "repo:command-splits-output-streams-without-json"
    )
    def it_prints_the_edits_per_file_and_per_rule(self, prose_repo, target_lines, capsys):
        finding = prose_repo.finding(
            target_lines["last-paragraph"],
            text="Final paragraph.",
            replacement="The closing paragraph.",
        )
        path = prose_repo.findings_file([finding])
        token = prose_repo.token(path)
        capsys.readouterr()
        code = prose.main(
            ["apply", "--findings", path, "--token", token, "-C", str(prose_repo.root)]
        )
        out, err = capsys.readouterr()
        assert code == prose.OK
        assert err == ""
        assert out == "target.md  1 edit(s)\n  %-16s 1\n\n1 edit(s) written\n" % finding["rule"]

    @pytest.mark.spec("report-cmd-stops-on-unreadable-findings")
    @pytest.mark.parametrize("command", ["report", "apply"])
    @pytest.mark.parametrize(
        ("content", "message"),
        [
            pytest.param(None, "cannot read findings", id="missing"),
            pytest.param("[{", "findings is not valid JSON", id="not-json"),
        ],
    )
    def it_stops_on_a_findings_file_it_cannot_read(self, prose_repo, command, content, message):
        path = prose_repo.root / "findings.json"
        if content is not None:
            path.write_text(content)
        flags = ["--token", "0" * prose.TOKEN_LENGTH] if command == "apply" else []
        code, envelope = prose_repo.run(command, "--findings", str(path), *flags)
        assert code == prose.CANNOT_RUN
        assert envelope is None
        assert message in prose_repo.err


class DescribeGuards:
    """One malformed finding, one named rejection, and nothing on disk."""

    @pytest.mark.spec("apply-cmd-refuses-protected-lines-and-comments")
    @pytest.mark.parametrize(
        "kind", ["frontmatter", "blockquote", "fence", "comment", "code-block", "html-block"]
    )
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

    @pytest.mark.spec("report-cmd-refuses-stale-findings")
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

    @pytest.mark.spec("report-cmd-refuses-stale-findings")
    @pytest.mark.parametrize("command", ["report", "apply"])
    @pytest.mark.parametrize(
        "line",
        [
            pytest.param("x", id="a-word"),
            pytest.param(None, id="null"),
            pytest.param("2", id="a-numeral-in-a-string"),
            pytest.param(1.5, id="a-fraction"),
            pytest.param(True, id="a-boolean"),
        ],
    )
    def it_refuses_a_line_that_is_not_a_whole_number(self, prose_repo, target_lines, command, line):
        """The findings are the model's JSON, so a line can arrive as any
        value. One that is not a whole number names no line, and the rest of
        the batch is checked as usual.
        """
        good = prose_repo.finding(target_lines["last-paragraph"], text="Final paragraph.")
        bad = dict(good, line=line)
        if command == "report":
            code, envelope = prose_repo.report([bad, good])
        else:
            code, envelope = prose_repo.apply([bad, good], "--partial")
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md  finding 1: line %s is not a whole number" % json.dumps(line)
        ]
        if command == "report":
            assert [r["finding"] for r in envelope["data"]["findings"]] == [2]
        else:
            assert "Final paragraph." not in prose_repo.read()

    @pytest.mark.spec("report-cmd-refuses-stale-findings")
    def it_refuses_a_missing_file(self, prose_repo):
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(1, file="nowhere.md"),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["nowhere.md  no such file"]

    @pytest.mark.spec("report-cmd-refuses-undefined-rules")
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

    @pytest.mark.spec("report-cmd-refuses-stale-findings")
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
                    text="Something else entirely.",
                ),
            ]
        )
        assert code == prose.PROBLEMS
        assert "the text moved" in errors_of(envelope)[0]
        assert prose_repo.read() == before

    @pytest.mark.spec("apply-cmd-never-splits-table-cells")
    @pytest.mark.parametrize(
        ("text", "replacement"),
        [
            pytest.param("model", "a | b", id="adds-a-pipe"),
            pytest.param("model", "a\nb", id="adds-a-newline"),
            pytest.param("model | a large", "model a large", id="removes-a-pipe"),
        ],
    )
    def it_refuses_a_rewrite_that_would_break_a_table(
        self, prose_repo, target_lines, text, replacement
    ):
        before = prose_repo.read()
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(target_lines["table"], text=text, replacement=replacement),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  a table rewrite cannot add or remove a | or add a newline"
            % target_lines["table"]
        ]
        assert prose_repo.read() == before

    @pytest.mark.spec("apply-cmd-never-splits-table-cells")
    def it_refuses_a_multi_line_replacement_outside_a_paragraph(self, prose_repo, target_lines):
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(
                    target_lines["heading"], text="Heading", replacement="two\nlines"
                ),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  a heading replacement cannot span lines" % target_lines["heading"]
        ]

    @pytest.mark.spec("apply-cmd-refuses-protected-lines-and-comments")
    @pytest.mark.parametrize(
        ("col_start", "text"),
        [
            pytest.param(10, "<!-- a note -->", id="the-whole-comment"),
            pytest.param(0, "Some text <!", id="prose-and-the-opening-marker"),
        ],
    )
    def it_refuses_a_finding_that_touches_an_inline_comment(self, prose_repo, col_start, text):
        (prose_repo.root / "notes.md").write_text("Some text <!-- a note --> more text.\n")
        before = prose_repo.read("notes.md")
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(1, file="notes.md", col_start=col_start, text=text),
            ]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "notes.md:1  columns %d-%d touch an HTML comment; prose rules do not apply there"
            % (col_start, col_start + len(text))
        ]
        assert prose_repo.read("notes.md") == before

    @pytest.mark.spec("apply-cmd-refuses-protected-lines-and-comments")
    @pytest.mark.parametrize(
        ("col_start", "text", "after"),
        [
            pytest.param(
                0, "Some text", "rewritten <!-- a note --> more text.\n", id="the-prose-before"
            ),
            pytest.param(5, "text ", "Some rewritten<!-- a note --> more text.\n", id="up-to-it"),
            pytest.param(
                25, " ", "Some text <!-- a note -->rewrittenmore text.\n", id="just-after"
            ),
        ],
    )
    def it_applies_a_finding_on_the_prose_beside_an_inline_comment(
        self, prose_repo, col_start, text, after
    ):
        (prose_repo.root / "notes.md").write_text("Some text <!-- a note --> more text.\n")
        code, _ = prose_repo.apply(
            [
                prose_repo.finding(1, file="notes.md", col_start=col_start, text=text),
            ]
        )
        assert code == prose.OK
        assert prose_repo.read("notes.md") == after

    @pytest.mark.spec("report-cmd-names-overlaps")
    def it_refuses_two_edits_on_the_same_span_and_names_both(self, prose_repo, target_lines):
        """EditEngine applies a batch from one snapshot. Overlapping spans have
        no defined result, so the batch is turned down rather than resolved by
        whichever sorted first. The refusal names each finding by its place in
        the batch, its line and its rule, since byte offsets send the author
        nowhere.
        """
        line = target_lines["paragraph"]
        before = prose_repo.read()
        first = prose_repo.finding(line, text="used for")
        code, envelope = prose_repo.apply([first, prose_repo.finding(line, text="for something")])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md  finding 1 (target.md:%d, %s) overlaps finding 2 (target.md:%d, %s)"
            % (line, first["rule"], line, first["rule"])
        ]
        assert prose_repo.read() == before


def anchored(prose_repo, line, text, replacement="", **overrides):
    """A finding on doc.md addressed by its line and text. The default
    replacement cuts the text.
    """
    return prose_repo.finding(line, file="doc.md", text=text, replacement=replacement, **overrides)


class DescribeWholeLineCuts:
    """A finding cannot reach past its line's end, so cutting a line used to
    empty it and keep its newline. Cutting a passage left one blank line per
    line it had, and #73 needed them collapsed by hand.
    """

    def write(self, prose_repo, content):
        (prose_repo.root / "doc.md").write_text(content)

    @pytest.mark.spec("apply-cmd-leaves-one-blank-line")
    def it_removes_a_cut_passage_and_keeps_one_blank_line(self, prose_repo):
        self.write(prose_repo, "Keep this.\n\nCut this line.\nAnd this one.\n\nKeep this too.\n")
        code, _ = prose_repo.apply(
            [anchored(prose_repo, 3, "Cut this line."), anchored(prose_repo, 4, "And this one.")]
        )
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "Keep this.\n\nKeep this too.\n"

    @pytest.mark.spec("apply-cmd-leaves-one-blank-line")
    def it_joins_the_lines_around_one_cut_from_a_paragraph(self, prose_repo):
        self.write(prose_repo, "One.\nTwo.\nThree.\n")
        code, _ = prose_repo.apply([anchored(prose_repo, 2, "Two.")])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "One.\nThree.\n"

    @pytest.mark.spec("apply-cmd-leaves-one-blank-line")
    def it_removes_a_line_that_two_findings_empty_between_them(self, prose_repo):
        self.write(prose_repo, "One.\nFirst half, second half.\nThree.\n")
        code, _ = prose_repo.apply(
            [
                anchored(prose_repo, 2, "First half,"),
                anchored(prose_repo, 2, " second half."),
            ]
        )
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "One.\nThree.\n"

    @pytest.mark.spec("apply-cmd-leaves-one-blank-line")
    def it_leaves_the_rest_of_a_partly_cut_line_alone(self, prose_repo):
        self.write(prose_repo, "One.\nKeep, cut.\nThree.\n")
        code, _ = prose_repo.apply([anchored(prose_repo, 2, " cut.")])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "One.\nKeep,\nThree.\n"

    @pytest.mark.spec("apply-cmd-leaves-one-blank-line")
    def it_keeps_a_line_that_also_takes_a_replacement(self, prose_repo):
        self.write(prose_repo, "One.\nOld words.\nThree.\n")
        code, _ = prose_repo.apply(
            [
                anchored(prose_repo, 2, "Old", "New"),
                anchored(prose_repo, 2, " words."),
            ]
        )
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "One.\nNew\nThree.\n"

    @pytest.mark.spec("apply-cmd-leaves-one-blank-line")
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
        code, _ = prose_repo.apply([anchored(prose_repo, line, text)])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == after

    @pytest.mark.spec("apply-cmd-leaves-one-blank-line")
    def it_still_rewrites_a_later_line_after_a_cut(self, prose_repo):
        """Every edit is planned against one snapshot, so removing lines does
        not shift the address of a finding below them.
        """
        self.write(prose_repo, "Keep.\n\nCut.\n\nOld.\n")
        code, _ = prose_repo.apply(
            [anchored(prose_repo, 3, "Cut."), anchored(prose_repo, 5, "Old.", "New.")]
        )
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "Keep.\n\nNew.\n"


class DescribeAnchoredFindings:
    """A finding may leave its columns out and let apply find its text.

    The model used to count the columns itself. One off-by-one read as stale
    text, and the next run of apply-prose wrote a helper to do the counting.
    """

    def write(self, prose_repo, content):
        (prose_repo.root / "doc.md").write_text(content)

    @pytest.mark.spec("report-cmd-locates-findings-by-text")
    def it_finds_the_text_on_its_line(self, prose_repo):
        self.write(prose_repo, "- First item starts here and\n  continues on this line.\n")
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 2, "continues on this line.", "goes on here.")]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "- First item starts here and\n  goes on here.\n"

    @pytest.mark.spec("report-cmd-locates-findings-by-text")
    def it_refuses_text_that_does_not_start_on_its_line(self, prose_repo):
        self.write(prose_repo, "One line.\nAnother line.\n")
        before = prose_repo.read("doc.md")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "Another line.")])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1: 'Another line.' does not start on this line. Re-run the report."
        ]
        assert prose_repo.read("doc.md") == before

    @pytest.mark.spec("report-cmd-locates-findings-by-text")
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

    @pytest.mark.spec("report-cmd-locates-findings-by-text")
    def it_takes_col_start_to_say_which_match(self, prose_repo):
        self.write(prose_repo, "the cat and the dog\n")
        code, _ = prose_repo.apply([anchored(prose_repo, 1, "the", "a", col_start=12)])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "the cat and a dog\n"

    @pytest.mark.spec("report-cmd-locates-findings-by-text")
    def it_refuses_a_col_start_past_the_end_of_the_line(self, prose_repo):
        """Text.offset adds the column blind, so col_start=40 on a short line
        would look for the text on a later line instead.
        """
        self.write(prose_repo, "Short.\nThe cat sat.\n")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "cat", "dog", col_start=11)])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["doc.md:1  column 11 is outside the line (6 characters)"]

    @pytest.mark.spec("report-cmd-locates-findings-by-text")
    @pytest.mark.parametrize("command", ["report", "apply"])
    @pytest.mark.parametrize(
        "col_start",
        [
            pytest.param("x", id="a-word"),
            pytest.param("4", id="a-numeral-in-a-string"),
            pytest.param(4.5, id="a-fraction"),
            pytest.param(True, id="a-boolean"),
        ],
    )
    def it_refuses_a_col_start_that_is_not_a_whole_number(self, prose_repo, command, col_start):
        """The findings are the model's JSON, so col_start can arrive as any
        value. int() would read "4", 4.5 and true as columns the finding did
        not give. The rest of the batch is checked as usual.
        """
        self.write(prose_repo, "The colour is red.\nThe cat sat.\n")
        bad = anchored(prose_repo, 1, "colour", "color", col_start=col_start)
        good = anchored(prose_repo, 2, "cat", "dog")
        if command == "report":
            code, envelope = prose_repo.report([bad, good])
        else:
            code, envelope = prose_repo.apply([bad, good], "--partial")
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1: col_start %s is not a whole number" % json.dumps(col_start)
        ]
        if command == "report":
            assert [r["finding"] for r in envelope["data"]["findings"]] == [2]
        else:
            assert prose_repo.read("doc.md") == "The colour is red.\nThe dog sat.\n"

    @pytest.mark.spec("report-cmd-locates-findings-by-text")
    @pytest.mark.parametrize("command", ["report", "apply"])
    def it_refuses_a_finding_without_text(self, prose_repo, command):
        """A finding with no text used to be applied to its whole line, so it
        was never checked against the text the model saw.
        """
        self.write(prose_repo, "One line.\n")
        record = anchored(prose_repo, 1, "One line.", "x")
        del record["text"]
        code, envelope = getattr(prose_repo, command)([record])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1 has no text; copy it from the segment it rewrites"
        ]
        assert prose_repo.read("doc.md") == "One line.\n"

    @pytest.mark.spec("report-cmd-locates-findings-by-text")
    @pytest.mark.parametrize("command", ["report", "apply"])
    def it_refuses_a_finding_with_col_end(self, prose_repo, command):
        self.write(prose_repo, "One line.\n")
        record = anchored(prose_repo, 1, "One", "Single", col_start=0, col_end=3)
        code, envelope = getattr(prose_repo, command)([record])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1 has col_end; leave it out, and give col_start only when "
            "the text starts at more than one place on the line"
        ]
        assert prose_repo.read("doc.md") == "One line.\n"

    @pytest.mark.spec("report-cmd-refuses-empty-spans")
    @pytest.mark.parametrize(
        "where",
        [
            pytest.param({"text": ""}, id="an-empty-text"),
            pytest.param({"text": "", "col_start": 3}, id="an-empty-text-at-a-column"),
        ],
    )
    def it_refuses_a_finding_with_an_empty_span(self, prose_repo, where):
        self.write(prose_repo, "One line.\n")
        record = prose_repo.finding(1, file="doc.md", replacement="x", **where)
        for code, envelope in (prose_repo.report([record]), prose_repo.apply([record])):
            assert code == prose.PROBLEMS
            assert errors_of(envelope) == [
                "doc.md:1  finding 1: the text is empty, so this would insert;"
                " rewrite the text beside the gap instead"
            ]
        assert prose_repo.read("doc.md") == "One line.\n"

    @pytest.mark.spec("report-cmd-refuses-stale-findings")
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

    @pytest.mark.spec("apply-cmd-rewrites-wrapped-findings")
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

    @pytest.mark.spec("apply-cmd-rewrites-wrapped-findings")
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

    @pytest.mark.spec("apply-cmd-refuses-protected-lines-and-comments")
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

    @pytest.mark.spec("apply-cmd-refuses-protected-lines-and-comments")
    def it_refuses_a_span_that_reaches_a_protected_line(self, prose_repo):
        self.write(prose_repo, "Some prose.\n> A quotation.\n")
        before = prose_repo.read("doc.md")
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, "prose.\n> A")])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["doc.md:2  is a blockquote; prose rules do not apply there"]
        assert prose_repo.read("doc.md") == before

    @pytest.mark.spec("apply-cmd-leaves-one-blank-line")
    def it_removes_the_lines_a_span_cuts_whole(self, prose_repo):
        self.write(prose_repo, "Keep this.\n\nCut this line.\nAnd this one.\n\nKeep this too.\n")
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 3, "Cut this line.\nAnd this one.")]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "Keep this.\n\nKeep this too.\n"

    @pytest.mark.spec("apply-cmd-rewrites-wrapped-findings")
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

    @pytest.mark.spec("apply-cmd-indents-list-items")
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

    @pytest.mark.spec("apply-cmd-indents-list-items")
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

    @pytest.mark.spec("apply-cmd-indents-list-items")
    def it_leaves_a_new_line_indented_past_the_item_text_as_written(self, prose_repo):
        self.write(prose_repo, self.WRAPPED)
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 2, "continues on this line.", "continues:\n    - deeper.")]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == (
            "- First item starts here and\n  continues:\n    - deeper.\n- Second item.\n"
        )

    @pytest.mark.spec("apply-cmd-indents-list-items")
    def it_leaves_a_new_line_in_a_paragraph_after_the_list_unindented(self, prose_repo):
        self.write(prose_repo, "- An item.\n\nA paragraph.\n")
        code, envelope = prose_repo.apply([anchored(prose_repo, 3, "A paragraph.", "One.\nTwo.")])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "- An item.\n\nOne.\nTwo.\n"


class DescribeCodeSpans:
    """A code span quotes code. A finding may rewrite the prose around one,
    but not the code inside it."""

    LINE = "Run `issues.py claim 64` and wait.\n"
    RUNS = (
        pytest.param(("report",), id="report"),
        pytest.param(("apply",), id="apply"),
        pytest.param(("apply", "--partial"), id="apply-partial"),
    )

    def write(self, prose_repo, body=LINE):
        (prose_repo.root / "doc.md").write_text(body)

    @pytest.mark.spec("apply-cmd-keeps-code-spans")
    @pytest.mark.parametrize("run", RUNS)
    @pytest.mark.parametrize(
        ("text", "col_start"),
        [
            pytest.param("claim 64", 15, id="inside-it"),
            pytest.param("Run `issues.py", 0, id="into-its-start"),
            pytest.param("64` and", 21, id="out-of-its-end"),
        ],
    )
    def it_refuses_a_finding_that_cuts_into_a_code_span(self, prose_repo, run, text, col_start):
        self.write(prose_repo)
        before = prose_repo.read("doc.md")
        finding = anchored(prose_repo, 1, text, "changed", col_start=col_start)
        code, envelope = getattr(prose_repo, run[0])([finding], *run[1:])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  columns %d-%d cut into a code span; prose rules do not apply there"
            % (col_start, col_start + len(text))
        ]
        assert prose_repo.read("doc.md") == before

    @pytest.mark.spec("apply-cmd-keeps-code-spans")
    @pytest.mark.parametrize("run", RUNS)
    @pytest.mark.parametrize(
        "replacement",
        [
            pytest.param("Wait.", id="dropped"),
            pytest.param("Run `issues.py claim 65` and wait.", id="changed"),
        ],
    )
    def it_refuses_a_replacement_that_loses_a_code_span(self, prose_repo, run, replacement):
        self.write(prose_repo)
        before = prose_repo.read("doc.md")
        finding = anchored(prose_repo, 1, self.LINE.strip(), replacement)
        code, envelope = getattr(prose_repo, run[0])([finding], *run[1:])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1's replacement does not keep the code span "
            "`issues.py claim 64` as it was"
        ]
        assert prose_repo.read("doc.md") == before

    @pytest.mark.spec("apply-cmd-keeps-code-spans")
    def it_refuses_a_replacement_that_swaps_two_code_spans(self, prose_repo):
        self.write(prose_repo, "Run `a` then `b`.\n")
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 1, "Run `a` then `b`.", "Run `b` then `a`.")]
        )
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1's replacement does not keep the code span `b` as it was"
        ]

    @pytest.mark.spec("apply-cmd-keeps-code-spans")
    def it_closes_a_code_span_within_its_paragraph(self, prose_repo):
        """The backtick left open in the first paragraph would otherwise pair
        with the first in the second, and turn `and` into code."""
        self.write(prose_repo, "Open `tick.\n\nRun `x` and `y` now.\n")
        code, envelope = prose_repo.apply([anchored(prose_repo, 3, "and", "or")])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "Open `tick.\n\nRun `x` or `y` now.\n"

    @pytest.mark.spec("apply-cmd-keeps-code-spans")
    def it_rewrites_a_sentence_around_a_code_span_it_keeps(self, prose_repo):
        self.write(prose_repo)
        code, envelope = prose_repo.apply(
            [anchored(prose_repo, 1, self.LINE.strip(), "Wait after `issues.py claim 64`.")]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "Wait after `issues.py claim 64`.\n"


class DescribeNewBlockMarkers:
    """Markdown reads a list, heading or blockquote marker at the start of a
    wrapped line as a new block, even in the middle of a sentence."""

    ITEM = "- `lint` names it and exits\n  1, and it warns on a rule.\n"
    RUNS = DescribeCodeSpans.RUNS

    def write(self, prose_repo, body):
        (prose_repo.root / "doc.md").write_text(body)

    @pytest.mark.spec("apply-cmd-refuses-new-block-markers")
    @pytest.mark.parametrize("run", RUNS)
    def it_refuses_a_rewrite_that_turns_a_wrapped_line_into_a_list(self, prose_repo, run):
        self.write(prose_repo, self.ITEM)
        before = prose_repo.read("doc.md")
        finding = anchored(prose_repo, 2, "1, and it warns", "1. It warns")
        code, envelope = getattr(prose_repo, run[0])([finding], *run[1:])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:2  finding 1 starts line 2 with 1., which markdown reads as a new "
            "list item; reword it so the line does not start with 1."
        ]
        assert prose_repo.read("doc.md") == before

    @pytest.mark.spec("apply-cmd-refuses-new-block-markers")
    @pytest.mark.parametrize(
        ("replacement", "kind", "marker"),
        [
            pytest.param("- warns", "list item", "-", id="bullet"),
            pytest.param("# warns", "heading", "#", id="heading"),
            pytest.param("> warns", "blockquote", ">", id="blockquote"),
        ],
    )
    def it_refuses_each_kind_of_marker(self, prose_repo, replacement, kind, marker):
        self.write(prose_repo, "It names it and\nthen warns on a rule.\n")
        code, envelope = prose_repo.apply([anchored(prose_repo, 2, "then warns", replacement)])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:2  finding 1 starts line 2 with %s, which markdown reads as a new %s; "
            "reword it so the line does not start with %s" % (marker, kind, marker)
        ]

    @pytest.mark.spec("apply-cmd-refuses-new-block-markers")
    def it_refuses_a_marker_on_a_later_line_of_a_rewrite_across_lines(self, prose_repo):
        self.write(prose_repo, self.ITEM)
        finding = anchored(prose_repo, 1, "exits\n  1, and it warns", "exits\n  1. It warns")
        code, envelope = prose_repo.apply([finding])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:1  finding 1 starts line 2 with 1., which markdown reads as a new "
            "list item; reword it so the line does not start with 1."
        ]

    @pytest.mark.spec("apply-cmd-refuses-new-block-markers")
    @pytest.mark.parametrize(
        ("body", "text", "replacement"),
        [
            pytest.param("- An item.\n", "- An item.", "- One item.", id="bullet"),
            pytest.param("1. An item.\n", "1. An item.", "1. One item.", id="ordered"),
            pytest.param("## A heading\n", "## A heading", "## The heading", id="heading"),
        ],
    )
    def it_keeps_a_marker_the_line_already_starts_with(self, prose_repo, body, text, replacement):
        self.write(prose_repo, body)
        code, envelope = prose_repo.apply([anchored(prose_repo, 1, text, replacement)])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == replacement + "\n"

    @pytest.mark.spec("apply-cmd-refuses-new-block-markers")
    def it_lets_a_rewrite_that_adds_lines_lay_out_a_list(self, prose_repo):
        self.write(prose_repo, "It checks the id,\nthe title and the example.\n")
        finding = anchored(
            prose_repo,
            1,
            "It checks the id,\nthe title and the example.",
            "It checks:\n\n- the id.\n- the title.\n- the example.",
        )
        code, envelope = prose_repo.apply([finding])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == (
            "It checks:\n\n- the id.\n- the title.\n- the example.\n"
        )


class DescribeListStyle:
    """A finding cannot put a marker at the start of a line, so a list's
    markers change only through `list` on the finding on its first item."""

    LIST = "Then it:\n\n- files the issues.\n- links them.\n- files the tracking issue.\n\nDone.\n"
    NUMBERED = (
        "Then it:\n\n1. files the issues.\n2. links them.\n3. files the tracking issue.\n\nDone.\n"
    )
    RUNS = DescribeCodeSpans.RUNS

    def write(self, prose_repo, body):
        (prose_repo.root / "doc.md").write_text(body)

    def restyle(self, prose_repo, line, text, style="numbered", replacement=None):
        return anchored(
            prose_repo, line, text, text if replacement is None else replacement, list=style
        )

    @pytest.mark.spec("apply-cmd-restyles-lists")
    def it_numbers_a_bulleted_list_that_report_showed_whole(self, prose_repo):
        self.write(prose_repo, self.LIST)
        finding = self.restyle(prose_repo, 3, "files the issues.")
        code, envelope = prose_repo.report([finding])
        assert code == prose.OK, envelope["errors"]
        [row] = envelope["data"]["findings"]
        assert row["current"] == "- files the issues.\n- links them.\n- files the tracking issue."
        assert (
            row["proposed"] == "1. files the issues.\n2. links them.\n3. files the tracking issue."
        )
        path = str(prose_repo.root / "findings.json")
        token = envelope["data"]["token"]
        code, envelope = prose_repo.run("apply", "--findings", path, "--token", token)
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == self.NUMBERED

    @pytest.mark.spec("apply-cmd-restyles-lists")
    def it_makes_the_findings_own_rewrite_too(self, prose_repo):
        self.write(prose_repo, self.LIST)
        finding = self.restyle(prose_repo, 3, "files the issues.", replacement="files each issue.")
        code, envelope = prose_repo.apply([finding])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == self.NUMBERED.replace(
            "files the issues.", "files each issue."
        )

    @pytest.mark.spec("apply-cmd-restyles-lists")
    def it_moves_each_items_later_lines_with_its_text(self, prose_repo):
        self.write(
            prose_repo,
            "- one\n  more\n  - nested\n\n  ```\n  code\n  ```\n- two\nlazy\n",
        )
        code, envelope = prose_repo.apply([self.restyle(prose_repo, 1, "one")])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == (
            "1. one\n   more\n   - nested\n\n   ```\n   code\n   ```\n2. two\nlazy\n"
        )

    @pytest.mark.spec("apply-cmd-restyles-lists")
    @pytest.mark.parametrize(
        ("body", "after"),
        [
            pytest.param("- a\n  - b\n- c\n", "1. a\n   - b\n2. c\n", id="nested-list-closes"),
            pytest.param("1. a\n1. b\n1) c\n", "1. a\n2. b\n1) c\n", id="numbered-again"),
        ],
    )
    def it_numbers_only_the_items_of_the_list(self, prose_repo, body, after):
        self.write(prose_repo, body)
        code, envelope = prose_repo.apply([self.restyle(prose_repo, 1, "a")])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == after

    @pytest.mark.spec("apply-cmd-restyles-lists")
    def it_leaves_a_list_of_another_bullet_alone(self, prose_repo):
        self.write(prose_repo, "- one\n- two\n* three\n")
        code, envelope = prose_repo.apply([self.restyle(prose_repo, 1, "one")])
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == "1. one\n2. two\n* three\n"

    @pytest.mark.spec("apply-cmd-restyles-lists", "script-keeps-every-byte")
    def it_gives_back_the_bulleted_list_it_numbered(self, prose_repo):
        self.write(prose_repo, self.NUMBERED)
        code, envelope = prose_repo.apply(
            [self.restyle(prose_repo, 3, "files the issues.", "bulleted")]
        )
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read("doc.md") == self.LIST

    @pytest.mark.spec("apply-cmd-restyles-lists")
    @pytest.mark.parametrize("run", RUNS)
    @pytest.mark.parametrize(
        ("line", "text", "overrides", "error"),
        [
            pytest.param(
                4,
                "links them.",
                {},
                "doc.md:4  finding 1 sets list, but line 4 is not the first item of its "
                "list; put the finding on line 3",
                id="later-item",
            ),
            pytest.param(
                1,
                "Then it:",
                {},
                "doc.md:1  finding 1 sets list, but line 1 does not start a list item",
                id="not-an-item",
            ),
            pytest.param(
                3,
                "- files",
                {"replacement": "- files"},
                "doc.md:3  finding 1 sets list, but its text takes in the list marker; "
                "start it at the item's text",
                id="takes-marker",
            ),
            pytest.param(
                3,
                "files",
                {"list": "ordered"},
                'doc.md:3  finding 1: list is "ordered"; give numbered or bulleted',
                id="unknown-style",
            ),
            pytest.param(
                3,
                "files",
                {"dismiss": "it stays", "replacement": None},
                "doc.md:3  finding 1 has both dismiss and list; a dismissed match stays "
                "as it is, so give list to a finding with a replacement",
                id="dismissal",
            ),
        ],
    )
    def it_refuses_list_anywhere_else(self, prose_repo, run, line, text, overrides, error):
        self.write(prose_repo, self.LIST)
        finding = self.restyle(prose_repo, line, text)
        finding.update(overrides)
        finding = {k: v for k, v in finding.items() if v is not None}
        code, envelope = getattr(prose_repo, run[0])([finding], *run[1:])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [error]
        assert prose_repo.read("doc.md") == self.LIST

    @pytest.mark.spec("apply-cmd-restyles-lists")
    def it_refuses_a_second_finding_on_the_same_list(self, prose_repo):
        self.write(prose_repo, self.LIST)
        first = self.restyle(prose_repo, 3, "files")
        second = self.restyle(prose_repo, 3, "the issues.", "bulleted")
        code, envelope = prose_repo.apply([first, second])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:3  finding 2 sets list, but finding 1 already gives this list its markers"
        ]

    @pytest.mark.spec("apply-cmd-restyles-lists", "apply-cmd-refuses-new-block-markers")
    def it_still_refuses_a_rewrite_that_numbers_the_next_item(self, prose_repo):
        self.write(prose_repo, self.LIST)
        finding = anchored(
            prose_repo, 3, "files the issues.\n- links", "files the issues.\n2. links"
        )
        code, envelope = prose_repo.apply([finding])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "doc.md:3  finding 1 starts line 4 with 2., which markdown reads as a new "
            "list item; reword it so the line does not start with 2."
        ]


class DescribeHelp:
    @pytest.mark.spec("apply-cmd-describes-finding-fields-in-help")
    def it_describes_every_field_of_a_finding(self, capsys):
        with pytest.raises(SystemExit) as exit:
            prose.main(["apply", "--help"])
        assert exit.value.code == prose.OK
        out = capsys.readouterr().out
        for field in ("file", "line", "rule", "text", "replacement", "list", "col_start"):
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
                replacement="The closing paragraph.",
            ),
            prose_repo.finding(target_lines["fence"]),
        ]

    @pytest.mark.spec("repo:command-applies-rest-if-partial")
    def it_writes_nothing_when_one_finding_is_bad(self, prose_repo, target_lines):
        before = prose_repo.read()
        code, envelope = prose_repo.apply(self.records(prose_repo, target_lines))
        assert code == prose.PROBLEMS
        assert envelope["data"]["applied"] == []
        assert envelope["errors"][-1] == "nothing was written; pass --partial to apply the rest"
        assert prose_repo.read() == before

    @pytest.mark.spec("repo:command-applies-rest-if-partial")
    def it_writes_the_good_finding_with_partial(self, prose_repo, target_lines):
        code, envelope = prose_repo.apply(self.records(prose_repo, target_lines), "--partial")
        assert code == prose.PROBLEMS
        assert [a["line"] for a in envelope["data"]["applied"]] == [target_lines["last-paragraph"]]
        assert "The closing paragraph." in prose_repo.read()

    @pytest.mark.spec(
        "apply-cmd-refuses-protected-lines-and-comments", "repo:command-applies-rest-if-partial"
    )
    def it_still_leaves_the_protected_line_alone_with_partial(self, prose_repo, target_lines):
        prose_repo.apply(self.records(prose_repo, target_lines), "--partial")
        line = prose_repo.read().splitlines()[target_lines["fence"] - 1]
        assert line == "x = 1"


class DescribeDryRun:
    @pytest.mark.spec("repo:command-never-writes-in-preview")
    def it_reports_without_writing(self, prose_repo, target_lines):
        before = prose_repo.read()
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(
                    target_lines["last-paragraph"],
                    replacement="The closing paragraph.",
                ),
            ],
            "--dry-run",
        )
        assert code == prose.OK
        assert len(envelope["data"]["applied"]) == 1
        assert prose_repo.read() == before


# The rule every finding cites unless it names another.
RULE_ID = "sentences-own-subject"
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
                    text="Final paragraph.",
                    replacement="The closing paragraph.",
                )
            )
            findings.append(
                prose_repo.finding(
                    target_lines["paragraph"],
                    file=rel,
                    rule=OTHER_RULE,
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

    @pytest.mark.spec("apply-cmd-obeys-filters")
    def it_writes_every_finding_given_no_filter(self, prose_repo, four):
        code, _ = prose_repo.apply(four)
        assert code == prose.OK
        assert len(self.written(prose_repo)) == 4

    @pytest.mark.spec("apply-cmd-obeys-filters")
    def it_writes_only_the_named_rules(self, prose_repo, four):
        code, _ = prose_repo.apply(four, "--only", OTHER_RULE)
        assert code == prose.OK
        assert self.written(prose_repo) == {("target.md", OTHER_RULE), ("other.md", OTHER_RULE)}

    @pytest.mark.spec("apply-cmd-obeys-filters")
    def it_writes_only_the_named_files(self, prose_repo, four):
        before = prose_repo.read("other.md")
        code, _ = prose_repo.apply(four, "--file", "target.md")
        assert code == prose.OK
        assert self.written(prose_repo) == {
            ("target.md", "sentences-own-subject"),
            ("target.md", OTHER_RULE),
        }
        assert prose_repo.read("other.md") == before

    @pytest.mark.spec("apply-cmd-obeys-filters")
    def it_writes_every_file_named_by_a_repeated_flag(self, prose_repo, four):
        code, _ = prose_repo.apply(four, "--file", "target.md", "--file", "other.md")
        assert code == prose.OK
        assert len(self.written(prose_repo)) == 4

    @pytest.mark.spec("apply-cmd-obeys-filters")
    def it_writes_only_findings_that_pass_both_filters(self, prose_repo, four):
        code, envelope = prose_repo.apply(four, "--only", OTHER_RULE, "--file", "other.md")
        assert code == prose.OK
        assert self.written(prose_repo) == {("other.md", OTHER_RULE)}
        assert len(envelope["data"]["applied"]) == 1

    @pytest.mark.spec("apply-cmd-obeys-filters")
    def it_matches_a_file_given_with_a_leading_dot_slash(self, prose_repo, four):
        code, _ = prose_repo.apply(four, "--file", "./other.md")
        assert code == prose.OK
        assert {rel for rel, _ in self.written(prose_repo)} == {"other.md"}

    @pytest.mark.spec("apply-cmd-names-empty-filters")
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

    @pytest.mark.spec("apply-cmd-names-empty-filters")
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


class DescribeSameRewrites:
    """One rewrite can fix two rules, and the model then writes a finding for
    each, with the same text and the same replacement. Two edits starting at
    one offset are an overlap, so report used to ask the author to choose
    between two identical sides, and either choice left the file the same.
    """

    @pytest.fixture
    def pair(self, prose_repo, target_lines):
        style = prose_repo.root / prose.CONFIG_PATH
        style.write_text(style.read_text() + OTHER_RULE_TEXT)
        return [
            prose_repo.finding(
                target_lines["last-paragraph"],
                rule=rule,
                text="Final paragraph.",
                replacement="The closing paragraph.",
            )
            for rule in (RULE_ID, OTHER_RULE)
        ]

    @pytest.mark.spec("report-cmd-merges-same-rewrites", "report-cmd-names-overlaps")
    def it_reports_the_pair_as_one_change_and_no_overlap(self, prose_repo, pair):
        code, envelope = prose_repo.report(pair)
        assert code == prose.OK, envelope["errors"]
        assert envelope["data"]["overlaps"] == []
        assert [r["same_rewrite"] for r in envelope["data"]["findings"]] == [[1, 2], [1, 2]]

    @pytest.mark.spec("report-cmd-merges-same-rewrites")
    def it_names_every_finding_and_rule_in_one_heading(self, prose_repo, pair, target_lines):
        _code, envelope = prose_repo.report(pair)
        with open(envelope["data"]["report"], encoding="utf-8") as fh:
            page = fh.read()
        heading = "## `target.md:%d`, `%s` and `%s` (findings 1 and 2)\n" % (
            target_lines["last-paragraph"],
            RULE_ID,
            OTHER_RULE,
        )
        assert heading in page
        assert page.count("Final paragraph.") == 1

    @pytest.mark.spec("report-cmd-merges-same-rewrites")
    def it_prints_the_pair_once_on_stdout(self, prose_repo, pair, target_lines, capsys):
        path = prose_repo.findings_file(pair)
        capsys.readouterr()
        code = prose.main(["report", "--findings", path, "-C", str(prose_repo.root)])
        out, err = capsys.readouterr()
        assert code == prose.OK, err
        assert (
            "target.md:%d  %s and %s  (findings 1 and 2)\n"
            % (
                target_lines["last-paragraph"],
                RULE_ID,
                OTHER_RULE,
            )
            in out
        )
        assert out.count("The closing paragraph.") == 1

    @pytest.mark.spec("report-cmd-merges-same-rewrites")
    @pytest.mark.parametrize(
        "flags",
        [
            pytest.param((), id="every-finding"),
            pytest.param(("--only", RULE_ID), id="first-rule"),
            pytest.param(("--only", OTHER_RULE), id="second-rule"),
            pytest.param(("--file", "target.md"), id="file"),
        ],
    )
    def it_writes_the_rewrite_once_whichever_side_is_selected(self, prose_repo, pair, flags):
        before = prose_repo.read()
        code, envelope = prose_repo.apply(pair, *flags)
        assert code == prose.OK, envelope["errors"]
        assert prose_repo.read() == before.replace("Final paragraph.", "The closing paragraph.")

    @pytest.mark.spec("report-cmd-names-overlaps")
    def it_still_refuses_a_pair_whose_rewrites_differ(self, prose_repo, pair):
        pair[1]["replacement"] = "The last paragraph."
        before = prose_repo.read()
        code, envelope = prose_repo.apply(pair)
        assert code == prose.PROBLEMS
        assert len(errors_of(envelope)) == 1
        assert "overlaps" in errors_of(envelope)[0]
        assert prose_repo.read() == before

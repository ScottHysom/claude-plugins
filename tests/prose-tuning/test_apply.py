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
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([finding])))
        code, _ = prose_repo.run("apply", "--findings", "-")
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

    def it_refuses_two_edits_on_the_same_span(self, prose_repo, target_lines):
        """EditEngine applies a batch from one snapshot. Overlapping spans have
        no defined result, so the batch is turned down rather than resolved by
        whichever sorted first.
        """
        line = target_lines["paragraph"]
        before = prose_repo.read()
        code, envelope = prose_repo.apply(
            [
                prose_repo.finding(line, col_start=0, col_end=10),
                prose_repo.finding(line, col_start=5, col_end=15),
            ]
        )
        assert code == prose.PROBLEMS
        assert "overlapping edits" in errors_of(envelope)[0]
        assert prose_repo.read() == before


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

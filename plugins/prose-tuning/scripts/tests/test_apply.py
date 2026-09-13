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
import pytest

import prose


def errors_of(envelope):
    """Rejections, minus the trailing advice line apply appends in whole-batch
    mode. That line is about the run, not about a finding.
    """
    return [e for e in envelope["errors"] if not e.startswith("nothing was")]


def test_a_clean_finding_is_written(prose_repo, target_lines):
    code, envelope = prose_repo.apply([
        prose_repo.finding(target_lines["last-paragraph"],
                           col_start=0, col_end=16,
                           text="Final paragraph.",
                           replacement="The closing paragraph."),
    ])
    assert code == prose.OK
    assert envelope["errors"] == []
    assert "The closing paragraph." in prose_repo.read()


class TestGuards:
    """One malformed finding, one named rejection, and nothing on disk."""

    @pytest.mark.parametrize("kind", ["frontmatter", "blockquote", "fence"])
    def test_a_protected_line_is_refused(self, prose_repo, target_lines, kind):
        before = prose_repo.read()
        code, envelope = prose_repo.apply([
            prose_repo.finding(target_lines[kind]),
        ])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  is a %s; prose rules do not apply there"
            % (target_lines[kind], kind)]
        assert prose_repo.read() == before

    @pytest.mark.parametrize("line", [
        pytest.param(0, id="before-the-first-line"),
        pytest.param(-1, id="negative"),
        pytest.param(999, id="past-the-last-line"),
    ])
    def test_a_line_outside_the_file_is_refused(self, prose_repo, line):
        before = prose_repo.read()
        code, envelope = prose_repo.apply([prose_repo.finding(line)])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  line is outside the file" % line]
        assert prose_repo.read() == before

    def test_a_missing_file_is_refused(self, prose_repo):
        code, envelope = prose_repo.apply([
            prose_repo.finding(1, file="nowhere.md"),
        ])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == ["nowhere.md  no such file"]

    def test_a_rule_the_config_does_not_define_is_refused(self, prose_repo,
                                                          target_lines):
        code, envelope = prose_repo.apply([
            prose_repo.finding(target_lines["paragraph"], rule="made-up-rule"),
        ])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "finding 1 names rule 'made-up-rule', which is not in "
            "prose-style.md"]

    def test_text_that_moved_since_the_report_is_refused(self, prose_repo,
                                                         target_lines):
        """The report and the rewrite are two runs. If the document changed
        between them the offsets still resolve, they just resolve onto the
        wrong words - so the finding carries the text it expects to find.
        """
        before = prose_repo.read()
        code, envelope = prose_repo.apply([
            prose_repo.finding(target_lines["last-paragraph"],
                               col_start=0, col_end=16,
                               text="Something else entirely."),
        ])
        assert code == prose.PROBLEMS
        assert "the text moved" in errors_of(envelope)[0]
        assert prose_repo.read() == before

    @pytest.mark.parametrize("replacement", [
        pytest.param("a | b", id="pipe"),
        pytest.param("a\nb", id="newline"),
    ])
    def test_a_replacement_that_would_break_a_table_is_refused(
            self, prose_repo, target_lines, replacement):
        code, envelope = prose_repo.apply([
            prose_repo.finding(target_lines["table"], col_start=2, col_end=7,
                               replacement=replacement),
        ])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  a table cell cannot contain | or a newline"
            % target_lines["table"]]

    @pytest.mark.parametrize("cols", [
        pytest.param((0, 900), id="past-the-end"),
        pytest.param((-4, 6), id="negative"),
        pytest.param((9, 3), id="inverted"),
    ])
    def test_columns_outside_the_line_are_refused(self, prose_repo,
                                                  target_lines, cols):
        """Text.offset checks the line and then adds the column blind, so an
        out-of-range column lands somewhere else in the file. col_end=900 on a
        short line put a rewrite at the end of the document.
        """
        line = target_lines["paragraph"]
        before = prose_repo.read()
        code, envelope = prose_repo.apply([
            prose_repo.finding(line, col_start=cols[0], col_end=cols[1]),
        ])
        assert code == prose.PROBLEMS
        assert "are outside the line" in errors_of(envelope)[0]
        assert prose_repo.read() == before

    def test_a_multi_line_replacement_outside_a_paragraph_is_refused(
            self, prose_repo, target_lines):
        code, envelope = prose_repo.apply([
            prose_repo.finding(target_lines["heading"], col_start=2, col_end=9,
                               replacement="two\nlines"),
        ])
        assert code == prose.PROBLEMS
        assert errors_of(envelope) == [
            "target.md:%d  a heading replacement cannot span lines"
            % target_lines["heading"]]

    def test_two_edits_on_the_same_span_are_refused(self, prose_repo,
                                                    target_lines):
        """EditEngine applies a batch from one snapshot. Overlapping spans have
        no defined result, so the batch is turned down rather than resolved by
        whichever sorted first.
        """
        line = target_lines["paragraph"]
        before = prose_repo.read()
        code, envelope = prose_repo.apply([
            prose_repo.finding(line, col_start=0, col_end=10),
            prose_repo.finding(line, col_start=5, col_end=15),
        ])
        assert code == prose.PROBLEMS
        assert "overlapping edits" in errors_of(envelope)[0]
        assert prose_repo.read() == before


class TestPartial:
    """Whole-batch by default, --partial to take what is good.

    The default is the safe one: a batch containing a bad finding writes
    nothing, so the author fixes the report rather than reconciling a document
    that took half of it.
    """

    def records(self, prose_repo, target_lines):
        return [
            prose_repo.finding(target_lines["last-paragraph"],
                               col_start=0, col_end=16,
                               replacement="The closing paragraph."),
            prose_repo.finding(target_lines["fence"]),
        ]

    def test_by_default_one_bad_finding_writes_nothing(self, prose_repo,
                                                       target_lines):
        before = prose_repo.read()
        code, envelope = prose_repo.apply(
            self.records(prose_repo, target_lines))
        assert code == prose.PROBLEMS
        assert envelope["data"]["applied"] == []
        assert envelope["errors"][-1] == \
            "nothing was written; pass --partial to apply the rest"
        assert prose_repo.read() == before

    def test_partial_writes_the_good_finding(self, prose_repo, target_lines):
        code, envelope = prose_repo.apply(
            self.records(prose_repo, target_lines), "--partial")
        assert code == prose.PROBLEMS
        assert [a["line"] for a in envelope["data"]["applied"]] == \
            [target_lines["last-paragraph"]]
        assert "The closing paragraph." in prose_repo.read()

    def test_partial_still_leaves_the_protected_line_alone(self, prose_repo,
                                                           target_lines):
        prose_repo.apply(self.records(prose_repo, target_lines), "--partial")
        line = prose_repo.read().splitlines()[target_lines["fence"] - 1]
        assert line == "x = 1"


def test_dry_run_reports_without_writing(prose_repo, target_lines):
    before = prose_repo.read()
    code, envelope = prose_repo.apply([
        prose_repo.finding(target_lines["last-paragraph"],
                           col_start=0, col_end=16,
                           replacement="The closing paragraph."),
    ], "--dry-run")
    assert code == prose.OK
    assert len(envelope["data"]["applied"]) == 1
    assert prose_repo.read() == before

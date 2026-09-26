"""report is what the author approves, so it has to be what apply will do.

Before it existed the model retyped every finding into a table by hand, and
the approved table and the file apply ran were two texts nothing compared. So
report reads each finding against the file as it is now, refuses what apply
would refuse, and names every pair of findings that apply could not do both
of, before the author is asked anything.
"""

import pytest

import prose

# A wrapped sentence, then a paragraph whose dash fix sits inside a cut of the
# whole paragraph: the pair the apply-prose run behind #73 caught by eye.
DOC = """Intro line.

Able to state
  what is inside the file.

This holds - until it does not.
A closing restatement.
"""

WRAPPED = "Able to state\n  what is inside the file."
CUT = "This holds - until it does not.\nA closing restatement."


def write_doc(prose_repo):
    (prose_repo.root / "doc.md").write_text(DOC)


def wrapped(prose_repo, **overrides):
    record = dict(
        file="doc.md",
        text=WRAPPED,
        replacement="A reader can state what is inside the file.",
        why="it borrows its subject",
    )
    record.update(overrides)
    return prose_repo.finding(3, **record)


def dash(prose_repo):
    return prose_repo.finding(
        6, file="doc.md", text=" - until", replacement=". It stops holding until"
    )


def cut(prose_repo):
    return prose_repo.finding(6, file="doc.md", text=CUT, replacement="")


def human_report(prose_repo, capsys, findings):
    """stdout of a clean report run without --json."""
    path = prose_repo.findings_file(findings)
    capsys.readouterr()
    code = prose.main(["report", "--findings", path, "-C", str(prose_repo.root)])
    out, err = capsys.readouterr()
    assert code == prose.OK, err
    return out


class DescribeReport:
    @pytest.mark.spec("wrapped-finding")
    def it_shows_a_finding_across_a_line_break_with_its_text_whole(self, prose_repo):
        write_doc(prose_repo)
        code, envelope = prose_repo.report([wrapped(prose_repo)])
        assert code == prose.OK
        assert envelope["data"]["findings"] == [
            {
                "finding": 1,
                "file": "doc.md",
                "line": 3,
                "rule": wrapped(prose_repo)["rule"],
                "current": WRAPPED,
                "proposed": "A reader can state what is inside the file.",
                "why": "it borrows its subject",
            }
        ]
        assert envelope["data"]["overlaps"] == []

    @pytest.mark.spec("wrapped-finding")
    def it_indents_a_wrapped_text_under_its_first_line_on_stdout(self, prose_repo, capsys):
        write_doc(prose_repo)
        path = prose_repo.findings_file([wrapped(prose_repo)])
        capsys.readouterr()
        code = prose.main(["report", "--findings", path, "-C", str(prose_repo.root)])
        out, err = capsys.readouterr()
        assert code == prose.OK
        assert err == ""
        assert (
            "doc.md:3  %s  (finding 1)\n"
            "  current   |Able to state|\n"
            "            |  what is inside the file.|\n"
            "  proposed  |A reader can state what is inside the file.|\n"
            "  why       it borrows its subject\n" % wrapped(prose_repo)["rule"]
        ) in out

    @pytest.mark.spec("report-reads-file")
    def it_fences_a_text_so_a_leading_or_trailing_space_shows(self, prose_repo, capsys):
        write_doc(prose_repo)
        finding = dict(dash(prose_repo), replacement=". It stops holding until ")
        out = human_report(prose_repo, capsys, [finding])
        assert "  current   | - until|\n" in out
        assert "  proposed  |. It stops holding until |\n" in out

    @pytest.mark.spec("report-reads-file")
    def it_shows_a_text_of_only_spaces_as_its_fence(self, prose_repo, capsys):
        write_doc(prose_repo)
        # Line 4 opens with the two spaces that indent the wrapped sentence.
        finding = prose_repo.finding(4, file="doc.md", text="  ", replacement=" ")
        out = human_report(prose_repo, capsys, [finding])
        assert "  current   |  |\n" in out
        assert "  proposed  | |\n" in out

    @pytest.mark.spec("report-reads-file")
    def it_leaves_the_placeholder_for_an_empty_text_unfenced(self, prose_repo, capsys):
        write_doc(prose_repo)
        out = human_report(prose_repo, capsys, [cut(prose_repo)])
        assert "  proposed  %s\n" % prose.REPORT_CUT in out

    def it_takes_the_current_text_from_the_file_when_the_finding_gives_only_columns(
        self, prose_repo
    ):
        write_doc(prose_repo)
        finding = prose_repo.finding(1, file="doc.md", col_start=0, col_end=5)
        code, envelope = prose_repo.report([finding])
        assert code == prose.OK
        assert envelope["data"]["findings"][0]["current"] == "Intro"

    @pytest.mark.spec("overlaps-named")
    def it_names_both_findings_of_an_overlapping_pair(self, prose_repo):
        write_doc(prose_repo)
        findings = [wrapped(prose_repo), dash(prose_repo), cut(prose_repo)]
        rule = findings[0]["rule"]
        code, envelope = prose_repo.report(findings)
        assert code == prose.PROBLEMS
        assert envelope["errors"] == [
            "doc.md  finding 3 (doc.md:6, %s) overlaps finding 2 (doc.md:6, %s); "
            "they cannot both apply" % (rule, rule)
        ]
        ref = {"file": "doc.md", "line": 6, "rule": rule}
        assert envelope["data"]["overlaps"] == [
            {"first": [dict(ref, finding=3)], "second": [dict(ref, finding=2)]}
        ]
        # Every finding is still shown, so the author can choose between them.
        assert [r["finding"] for r in envelope["data"]["findings"]] == [1, 2, 3]

    @pytest.mark.spec("overlaps-named", "repo:plain-output-streams")
    def it_writes_the_overlap_to_stderr_and_the_findings_to_stdout(self, prose_repo, capsys):
        write_doc(prose_repo)
        path = prose_repo.findings_file([dash(prose_repo), cut(prose_repo)])
        capsys.readouterr()
        code = prose.main(["report", "--findings", path, "-C", str(prose_repo.root)])
        out, err = capsys.readouterr()
        assert code == prose.PROBLEMS
        assert "overlaps" in err
        assert "overlaps" not in out
        assert "doc.md:6" in out

    def it_drops_an_overlap_the_filters_leave_one_side_of(self, prose_repo):
        """The report for an approval by rule is the batch apply gets with the
        same flags, and that batch no longer holds both findings.
        """
        style = prose_repo.root / prose.CONFIG_PATH
        style.write_text(style.read_text() + "\n### standing-no-em-dash: No em-dash\n\nA dash.\n")
        write_doc(prose_repo)
        findings = [dict(dash(prose_repo), rule="standing-no-em-dash"), cut(prose_repo)]
        code, envelope = prose_repo.report(findings, "--only", "standing-no-em-dash")
        assert code == prose.OK
        assert [r["finding"] for r in envelope["data"]["findings"]] == [1]

    @pytest.mark.spec("stale-finding-refused")
    def it_refuses_a_finding_whose_text_has_moved(self, prose_repo):
        write_doc(prose_repo)
        code, envelope = prose_repo.report([wrapped(prose_repo, text="Able to say")])
        assert code == prose.PROBLEMS
        assert "does not start on this line" in envelope["errors"][0]
        assert envelope["data"]["findings"] == []

    @pytest.mark.spec("report-reads-file")
    def it_leaves_the_file_as_it_was(self, prose_repo):
        write_doc(prose_repo)
        prose_repo.report([wrapped(prose_repo), dash(prose_repo), cut(prose_repo)])
        assert prose_repo.read("doc.md") == DOC

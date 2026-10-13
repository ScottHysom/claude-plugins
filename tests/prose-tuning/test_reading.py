"""`report` checks that each part holding a rule without a pattern was read.

apply-prose checked those rules by reading every segment against every rule
at once, and the report said they were all checked by reading whether or not
any reading happened. A run of three in specs/repo.md went through that way,
and only the owner's review caught it (#532). Now the model reads a part at a
time, adds the read record `pass --part` ends with to the findings, and
`report` fails on a part it has no current record for.
"""

import json

import pytest

import prose

STYLE = """---
name: Probe
---

## Sentences

### sentences-own-subject: Carries its own subject

A sentence that borrows its subject from the heading above it is incomplete.

> **Before.** Curated, not collected.
> **After.** The list is curated, not collected.

### register-plain-words: Say it plainly

**Pattern.** `(?i)in order to`

> **Before.** In order to run it.
> **After.** To run it.
"""

OWN = "sentences-own-subject"
PLAIN = "register-plain-words"
DOC = "# Notes\n\nIt ran to ship.\n"
OWN_PART = "sentences@doc.md:1-3"


@pytest.fixture
def read_repo(prose_repo):
    (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
    (prose_repo.root / "doc.md").write_text(DOC)
    return prose_repo


def record(repo, part, *flags):
    """The read record `pass --part` prints for this part."""
    _, shown = repo.run("pass", "--part", part, *flags)
    return shown["data"]["record"]


def unread(part):
    return (
        "%s  has not been read; run pass --part %s, judge it, and add the read "
        "record it ends with to the findings" % (part, part)
    )


class DescribeTheReportOfReading:
    @pytest.mark.spec("report-cmd-fails-unread-rules")
    def it_fails_a_part_that_has_no_read_record(self, read_repo):
        code, envelope = read_repo.report([], "doc.md", read=False)
        assert code == prose.PROBLEMS
        assert envelope["errors"] == [unread(OWN_PART)]
        assert envelope["data"]["token"] is None
        assert envelope["data"]["read"] == {OWN: []}

    @pytest.mark.spec("report-cmd-fails-unread-rules")
    def it_passes_once_every_part_with_such_a_rule_is_read(self, read_repo):
        code, envelope = read_repo.report([record(read_repo, OWN_PART)], "doc.md", read=False)
        assert code == prose.OK, envelope["errors"]
        assert envelope["data"]["token"]

    @pytest.mark.spec("report-cmd-fails-unread-rules")
    def it_fails_a_read_made_before_the_lines_changed(self, read_repo):
        stale = record(read_repo, OWN_PART)
        (read_repo.root / "doc.md").write_text(DOC.replace("ship", "sail"))
        code, envelope = read_repo.report([stale], "doc.md", read=False)
        assert code == prose.PROBLEMS
        assert envelope["errors"] == [
            "%s  was read before its lines or its rules changed; run pass --part %s "
            "again, judge it, and replace its read record" % (OWN_PART, OWN_PART)
        ]

    @pytest.mark.spec("report-cmd-fails-unread-rules")
    def it_fails_a_read_made_before_the_rules_changed(self, read_repo):
        stale = record(read_repo, OWN_PART)
        style = read_repo.root / prose.CONFIG_PATH
        style.write_text(STYLE.replace("is incomplete", "is not complete"))
        code, envelope = read_repo.report([stale], "doc.md", read=False)
        assert code == prose.PROBLEMS
        assert "was read before its lines or its rules changed" in envelope["errors"][0]

    @pytest.mark.spec("report-cmd-fails-unread-rules")
    def it_does_not_ask_for_a_read_of_a_part_whose_rules_all_carry_a_pattern(self, read_repo):
        code, envelope = read_repo.report([], "doc.md", "--rule", PLAIN, read=False)
        assert code == prose.OK, envelope["errors"]
        assert envelope["data"]["read"] == {}

    @pytest.mark.spec("report-cmd-fails-unread-rules")
    @pytest.mark.parametrize(
        "bad",
        [
            pytest.param({"read": OWN_PART}, id="no-digest"),
            pytest.param({"read": OWN_PART, "digest": 7}, id="digest-not-a-string"),
            pytest.param({"read": OWN_PART, "digest": "x", "rule": OWN}, id="another-key"),
        ],
    )
    def it_refuses_a_read_record_it_cannot_check(self, read_repo, bad):
        code, envelope = read_repo.report([bad], "doc.md", read=False)
        assert code == prose.PROBLEMS
        assert envelope["errors"][0] == (
            "read record 1  holds something other than a read and a digest string; "
            "copy the record pass --part prints as it stands"
        )

    @pytest.mark.spec("report-cmd-names-pattern-rules")
    def it_lists_the_files_read_against_each_rule_without_a_pattern(self, read_repo):
        (read_repo.root / "other.md").write_text(DOC)
        reads = [record(read_repo, OWN_PART), record(read_repo, "sentences@other.md:1-3")]
        code, envelope = read_repo.report(reads, "doc.md", "other.md", read=False)
        assert code == prose.OK, envelope["errors"]
        assert envelope["data"]["read"] == {OWN: ["doc.md", "other.md"]}
        page = (read_repo.root / prose.REPORT_FILE).read_text()
        assert "Checked by pattern: `%s`.\n\nChecked by reading:\n\n" % PLAIN in page
        assert "- `%s`: `doc.md`, `other.md`\n" % OWN in page

    @pytest.mark.spec("report-cmd-names-pattern-rules", "report-cmd-checks-named-rules")
    def it_prints_the_files_read_against_each_rule_and_the_rules_given(self, read_repo, capsys):
        path = read_repo.findings_file([], "doc.md", "--rule", OWN)
        code = prose.main(
            ["report", "--findings", path, "doc.md", "--rule", OWN, "-C", str(read_repo.root)]
        )
        out = capsys.readouterr().out.splitlines()
        assert code == prose.OK
        assert out[-5:-1] == [
            "checked by pattern: none",
            "checked by reading:",
            "  %s  doc.md" % OWN,
            "given to --rule: %s" % OWN,
        ]

    @pytest.mark.spec("report-cmd-names-pattern-rules")
    def it_leaves_out_a_file_with_a_part_left_unread(self, read_repo):
        (read_repo.root / "other.md").write_text(DOC)
        code, envelope = read_repo.report(
            [record(read_repo, OWN_PART)], "doc.md", "other.md", read=False
        )
        assert code == prose.PROBLEMS
        assert envelope["data"]["read"] == {OWN: ["doc.md"]}


class DescribeAFindingsFileWrittenInPieces:
    @pytest.mark.spec("report-cmd-reads-joined-findings")
    @pytest.mark.parametrize("command", ["report", "apply"])
    def it_reads_every_array_and_object_one_after_another(self, read_repo, command):
        finding = {
            "file": "doc.md",
            "line": 3,
            "rule": OWN,
            "text": "It ran to ship.",
            "replacement": "The build ran to ship.",
        }
        path = read_repo.root / "findings.json"
        path.write_text(
            "%s\n%s\n" % (json.dumps([finding]), json.dumps(record(read_repo, OWN_PART)))
        )
        code, envelope = read_repo.run("report", "--findings", str(path), "doc.md")
        assert code == prose.OK, envelope["errors"]
        assert [r["finding"] for r in envelope["data"]["findings"]] == [1]
        if command == "apply":
            token = envelope["data"]["token"]
            code, envelope = read_repo.run(
                "apply", "--findings", str(path), "--token", token, "doc.md"
            )
            assert code == prose.OK, envelope["errors"]
            assert read_repo.read("doc.md") == "# Notes\n\nThe build ran to ship.\n"

    @pytest.mark.spec("report-cmd-stops-on-unreadable-findings")
    @pytest.mark.parametrize("content", ["", "  \n", '[] {"read"'])
    def it_stops_on_a_file_with_nothing_or_a_broken_piece(self, read_repo, content):
        path = read_repo.root / "findings.json"
        path.write_text(content)
        code, envelope = read_repo.run("report", "--findings", str(path))
        assert code == prose.CANNOT_RUN
        assert "findings is not valid JSON" in read_repo.err

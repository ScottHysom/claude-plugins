"""`pass` gives apply-prose everything a pass reads, a part at a time.

apply-prose ran `config list`, `segments` and `patterns` one after another,
with nothing decided between them (#196). `pass` printed what each of them
does in one output, until that output ran to twenty times what a Bash result
shows, and a breach the one long read missed left no trace (#532). Now `pass`
lists the parts, one section's rules over a run of one file's lines, and
`pass --part` prints one of them with the read record report checks.
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

RULE = "register-plain-words"
DOC = "# Notes\n\nIt ran in order to ship.\n"


@pytest.fixture
def pass_repo(prose_repo):
    (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
    (prose_repo.root / "doc.md").write_text(DOC)
    return prose_repo


PLAIN_PART = "register@doc.md:1-3"


class DescribeThePassCommand:
    @pytest.mark.spec("pass-cmd-lists-parts")
    def it_lists_a_part_for_each_section_of_each_file(self, pass_repo, capsys):
        code = prose.main(["pass", "doc.md", "-C", str(pass_repo.root)])
        out = capsys.readouterr().out
        assert code == prose.OK
        assert out.splitlines() == [
            "== parts ==",
            "sentences@doc.md:1-3  1 rule(s), 1 checked by reading, %d characters"
            % part_size(pass_repo, "sentences@doc.md:1-3"),
            "%s  1 rule(s), 0 checked by reading, %d characters"
            % (PLAIN_PART, part_size(pass_repo, PLAIN_PART)),
            "",
            "2 part(s) in 1 file(s).",
        ]

    @pytest.mark.spec("pass-cmd-gives-rules-segments-matches")
    def it_prints_a_parts_rules_then_segments_then_matches_then_read_record(
        self, pass_repo, capsys
    ):
        code = prose.main(["pass", "--part", PLAIN_PART, "-C", str(pass_repo.root)])
        out = capsys.readouterr().out
        assert code == prose.OK
        rules, rest = out.split("== segments ==\n")
        segments, rest = rest.split("\n== matches ==\n")
        matches, record = rest.split("== read ==\n")
        assert rules.startswith("== rules ==\n### %s: Say it plainly\n" % RULE)
        assert "### sentences-own-subject" not in rules
        assert segments.splitlines() == [
            "doc.md:1:2-7  heading  Notes",
            "doc.md:3:0-24  paragraph  It ran in order to ship.",
        ]
        assert matches.splitlines() == [
            'doc.md:3:7-18  %s  "in order to"' % RULE,
            "1 match(es) in 1 file(s). Checked by pattern: %s" % RULE,
        ]
        _, shown = pass_repo.run("pass", "--part", PLAIN_PART)
        assert json.loads(record) == shown["data"]["record"]
        assert shown["data"]["record"]["read"] == PLAIN_PART
        _, other = pass_repo.run("pass", "--part", "sentences@doc.md:1-3")
        assert other["data"]["matches"] == []

    @pytest.mark.spec("pass-cmd-gives-rules-segments-matches")
    def it_gives_what_config_list_segments_and_patterns_give(self, pass_repo):
        _, listed = pass_repo.run("config", "list")
        _, segmented = pass_repo.run("segments", "doc.md")
        _, patterned = pass_repo.run("patterns", "doc.md")
        code, envelope = pass_repo.run("pass", "--part", PLAIN_PART)
        assert code == prose.OK
        data = envelope["data"]
        assert data["rules"] == [
            r["id"] for r in listed["data"]["rules"] if r["section"] == "register"
        ]
        assert data["segments"] == segmented["data"]["doc.md"]["segments"]
        assert data["matches"] == patterned["data"]["matches"]

    @pytest.mark.spec("pass-cmd-gives-rules-segments-matches")
    @pytest.mark.parametrize(
        "part", ["register@doc.md:1-2", "register@missing.md:1-3", "register-doc.md"]
    )
    def it_refuses_a_part_the_files_do_not_have_and_says_how_to_list_them(self, pass_repo, part):
        code, envelope = pass_repo.run("pass", "--part", part)
        assert code == prose.CANNOT_RUN
        assert envelope is None
        assert "run pass with no --part" in pass_repo.err

    @pytest.mark.spec("pass-cmd-fits-each-part")
    def it_cuts_a_long_file_into_parts_that_each_fit_one_bash_result(self, pass_repo, capsys):
        doc = "".join("Line %d ran in order to ship it today.\n\n" % n for n in range(4000))
        (pass_repo.root / "long.md").write_text(doc)
        code, envelope = pass_repo.run("pass", "long.md")
        parts = [p for p in envelope["data"]["parts"] if p["section"] == "register"]
        assert code == prose.OK
        assert len(parts) > 2
        seen = []
        for part in parts:
            capsys.readouterr()
            prose.main(["pass", "--part", part["id"], "-C", str(pass_repo.root)])
            assert len(capsys.readouterr().out) <= prose.PART_LIMIT
            _, shown = pass_repo.run("pass", "--part", part["id"])
            seen += [seg["line"] for seg in shown["data"]["segments"]]
        assert seen == list(range(1, 8000, 2))

    @pytest.mark.spec("pass-cmd-lists-parts")
    def it_lists_no_part_for_a_file_without_prose(self, pass_repo):
        (pass_repo.root / "code.md").write_text("```sh\nls\n```\n")
        code, envelope = pass_repo.run("pass", "code.md")
        assert code == prose.OK
        assert envelope["data"]["parts"] == []

    @pytest.mark.spec("segments-cmd-reads-scope-by-default")
    def it_reads_every_file_in_scope_and_names_a_missing_one(self, pass_repo):
        code, envelope = pass_repo.run("pass")
        assert code == prose.OK
        assert sorted(set(p["file"] for p in envelope["data"]["parts"])) == ["doc.md", "target.md"]
        code, envelope = pass_repo.run("pass", "doc.md", "missing.md")
        assert code == prose.PROBLEMS
        assert envelope["errors"] == ["missing.md  no such file"]

    @pytest.mark.spec("patterns-cmd-refuses-unlinted-rules")
    def it_refuses_to_run_on_a_rule_file_lint_refuses(self, pass_repo):
        (pass_repo.root / prose.CONFIG_PATH).write_text(STYLE.replace("`(?i)in order to`", "`(`"))
        code, envelope = pass_repo.run("pass")
        assert code == prose.PROBLEMS
        assert envelope["data"] == {}


def part_size(repo, part):
    """How many characters `pass --part` gives the part before its read record."""
    _, shown = repo.run("pass", "--part", part)
    return shown["data"]["size"]

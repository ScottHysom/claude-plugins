"""`pass` gives apply-prose everything a pass reads, in one output.

apply-prose ran `config list`, `segments` and `patterns` one after another,
with nothing decided between them (#196). `pass` prints what each of them
does, over the same files, so the skill runs one command.
"""

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


class DescribeThePassCommand:
    @pytest.mark.spec("pass-cmd-gives-rules-segments-matches")
    def it_prints_the_rules_then_the_segments_then_the_matches(self, pass_repo, capsys):
        code = prose.main(["pass", "doc.md", "-C", str(pass_repo.root)])
        out = capsys.readouterr().out
        assert code == prose.OK
        rules, rest = out.split("== segments ==\n")
        segments, matches = rest.split("\n== matches ==\n")
        assert rules.startswith("== rules ==\n### sentences-own-subject: Carries its own subject\n")
        assert "### %s: Say it plainly\n\n**Pattern.** `(?i)in order to`" % RULE in rules
        assert segments.splitlines() == [
            "doc.md:1:2-7  heading  Notes",
            "doc.md:3:0-24  paragraph  It ran in order to ship.",
        ]
        assert matches.splitlines()[0] == 'doc.md:3:7-18  %s  "in order to"' % RULE
        assert matches.rstrip().endswith("Checked by pattern: %s" % RULE)

    @pytest.mark.spec("pass-cmd-gives-rules-segments-matches")
    def it_gives_what_config_list_segments_and_patterns_give(self, pass_repo):
        _, listed = pass_repo.run("config", "list")
        _, segmented = pass_repo.run("segments", "doc.md")
        _, patterned = pass_repo.run("patterns", "doc.md")
        code, envelope = pass_repo.run("pass", "doc.md")
        assert code == prose.OK
        data = envelope["data"]
        assert data["rules"] == listed["data"]["rules"]
        assert data["segments"] == {"doc.md": segmented["data"]["doc.md"]["segments"]}
        assert data["matches"] == patterned["data"]["matches"]
        assert data["patterned"] == patterned["data"]["rules"]

    @pytest.mark.spec("segments-cmd-reads-scope-by-default")
    def it_reads_every_file_in_scope_and_names_a_missing_one(self, pass_repo):
        code, envelope = pass_repo.run("pass")
        assert code == prose.OK
        assert sorted(envelope["data"]["segments"]) == ["doc.md", "target.md"]
        code, envelope = pass_repo.run("pass", "doc.md", "missing.md")
        assert code == prose.PROBLEMS
        assert envelope["errors"] == ["missing.md  no such file"]

    @pytest.mark.spec("patterns-cmd-refuses-unlinted-rules")
    def it_refuses_to_run_on_a_rule_file_lint_refuses(self, pass_repo):
        (pass_repo.root / prose.CONFIG_PATH).write_text(STYLE.replace("`(?i)in order to`", "`(`"))
        code, envelope = pass_repo.run("pass")
        assert code == prose.PROBLEMS
        assert envelope["data"] == {}

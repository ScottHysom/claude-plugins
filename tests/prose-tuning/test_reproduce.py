"""The rules update-prose-config writes reproduce the edits they came from.

Step 9 of that skill used to ask the model to judge, by reading, whether the
new rules would have made the author's edits, and two runs could disagree.
`reproduce` settles the part a pattern can: it runs each rule's pattern over
the file as it was at HEAD, says for each edit whether a match overlaps what
the edit changed, and names the rules with no pattern, which only reading can
check.
"""

import prose

# The conftest's rule, which has no pattern, beside one that has.
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
UNPATTERNED = "sentences-own-subject"

BEFORE = """# Notes

We run it in order to check the build.

It keeps the notes short, and the lists shorter.
"""


def reproduce(prose_repo, after):
    """Commit BEFORE under STYLE, write after in its place, and run reproduce."""
    (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
    (prose_repo.root / "target.md").write_text(BEFORE)
    prose_repo.commit()
    (prose_repo.root / "target.md").write_text(after)
    code, envelope = prose_repo.run("reproduce")
    assert code == prose.OK, envelope and envelope["errors"]
    return envelope["data"]


class DescribeReproduce:
    def it_reports_an_edit_a_pattern_reproduces(self, prose_repo):
        data = reproduce(prose_repo, BEFORE.replace("in order to", "to"))
        [edit] = data["edits"]
        assert (edit["start"], edit["reproduced"]) == (3, True)
        assert [(m["rule"], m["line"], m["text"]) for m in edit["matches"]] == [
            (RULE, 3, "in order to")
        ]

    def it_reports_an_edit_no_pattern_reproduces(self, prose_repo):
        data = reproduce(prose_repo, BEFORE.replace("It keeps", "The rule keeps"))
        [edit] = data["edits"]
        assert (edit["start"], edit["reproduced"], edit["matches"]) == (5, False, [])

    def it_does_not_credit_a_match_on_a_line_the_edit_changed_elsewhere(self, prose_repo):
        """The pattern matches the line, but not the words the edit changed,
        so the rule did not make this edit.
        """
        data = reproduce(prose_repo, BEFORE.replace("the build", "the whole build"))
        [edit] = data["edits"]
        assert edit["reproduced"] is False

    def it_credits_an_insertion_at_the_edge_of_a_match(self, prose_repo):
        data = reproduce(prose_repo, BEFORE.replace("in order to", "in order to,"))
        [edit] = data["edits"]
        assert edit["reproduced"] is True

    def it_never_credits_a_pure_insertion(self, prose_repo):
        data = reproduce(prose_repo, BEFORE + "\nWe run it in order to see.\n")
        [edit] = data["edits"]
        assert (edit["change"], edit["reproduced"]) == ("insert", False)

    def it_lists_the_rules_with_no_pattern_by_id(self, prose_repo):
        data = reproduce(prose_repo, BEFORE.replace("It keeps", "The rule keeps"))
        assert data["unpatterned"] == [UNPATTERNED]
        assert data["patterned"] == [RULE]

    def it_finds_a_match_on_a_later_line_of_a_hunk(self, prose_repo):
        """The heading, the blank line and the sentence all changed, so one
        hunk spans them, and the match on its third line has to be placed on
        that line at HEAD, not on the first.
        """
        data = reproduce(
            prose_repo,
            BEFORE.replace("# Notes\n\nWe run it in order to", "# Our notes\nWe run it to"),
        )
        [edit] = data["edits"]
        assert (edit["change"], edit["reproduced"]) == ("replace", True)
        assert [m["line"] for m in edit["matches"]] == [3]

    def it_prints_each_edit_and_the_rules_left_to_reading(self, prose_repo, capsys):
        reproduce(prose_repo, BEFORE.replace("in order to", "to"))
        capsys.readouterr()
        assert prose.main(["reproduce", "-C", str(prose_repo.root)]) == prose.OK
        out = capsys.readouterr().out
        assert "target.md:3  reproduced  %s" % RULE in out
        assert "Checked by reading, no pattern: %s" % UNPATTERNED in out

    def it_refuses_to_run_on_a_rule_file_lint_refuses(self, prose_repo):
        (prose_repo.root / prose.CONFIG_PATH).write_text(
            STYLE.replace("`(?i)in order to`", "`in order (to`")
        )
        code, envelope = prose_repo.run("reproduce")
        assert code == prose.PROBLEMS
        assert any("does not compile" in e for e in envelope["errors"])

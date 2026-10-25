"""`check` gives another skill what it needs to check one file against the rules.

check-prose is handed a file by a skill of another plugin, such as a drafted
pull request description in $TMPDIR, with the rules files to check it against.
So `check` reads the file wherever it sits and whatever git holds, reports each
pattern match with the sentence it falls in, and lists the parts for the read,
for each rules file named (#755).
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

# A second rules file, as a project keeps rules for pull requests beside its
# repository-wide ones.
PR_STYLE = """---
name: Pull requests
---

## Headings

### headings-no-summary: A description does not open with a summary

**Pattern.** `(?i)\\bsummary\\b`

> **Before.** ## Summary
> **After.** ## Scenario
"""

DRAFT = """## Summary

The tool runs. We wrote it in order to
check drafts quickly. It stops there.
"""

PLAIN = "register-plain-words"
NO_SUMMARY = "headings-no-summary"


@pytest.fixture
def repo(prose_repo):
    (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
    return prose_repo


@pytest.fixture
def draft(tmp_path):
    """A draft outside the project, as open-pr leaves one in $TMPDIR."""
    path = tmp_path / "outside" / "pr-draft.md"
    path.parent.mkdir()
    path.write_text(DRAFT)
    return str(path)


def pr_rules(repo):
    path = repo.root / ".flywheel" / "pr-style.md"
    path.parent.mkdir()
    path.write_text(PR_STYLE)
    return str(path)


class DescribeCheckMatches:
    @pytest.mark.spec("check-cmd-reports-match-sentences")
    def it_reports_each_match_with_the_sentence_it_falls_in(self, repo, draft):
        code, envelope = repo.run("check", draft)
        assert code == prose.OK, repo.err
        [rules] = envelope["data"]["rules"]
        [match] = rules["matches"]
        assert match["rule"] == PLAIN
        assert match["line"] == 3
        assert match["text"] == "in order to"
        assert match["sentence"] == "We wrote it in order to check drafts quickly."

    @pytest.mark.spec("check-cmd-reports-match-sentences")
    def it_lists_the_parts_of_the_file(self, repo, draft):
        _code, envelope = repo.run("check", draft)
        [rules] = envelope["data"]["rules"]
        assert [p["section"] for p in rules["parts"]] == ["sentences", "register"]
        assert rules["parts"][0]["file"] == draft

    @pytest.mark.spec("check-cmd-reports-match-sentences")
    def it_prints_the_sentence_beside_the_rule(self, repo, draft, capsys):
        capsys.readouterr()
        code = prose.main(["check", draft, "-C", str(repo.root)])
        out = capsys.readouterr().out
        assert code == prose.OK
        assert (
            '%s:3:27  %s  "We wrote it in order to check drafts quickly."' % (draft, PLAIN) in out
        )


class DescribeSentenceAround:
    @pytest.mark.spec("check-cmd-reports-match-sentences")
    @pytest.mark.parametrize(
        ("string", "matched", "sentence"),
        [
            ("One. Two words here. Three.", "words", "Two words here."),
            ("Only one sentence", "one", "Only one sentence"),
            ("It ends here. Next one.", "here.", "It ends here."),
            ("First ends. Second starts", "ends. Second", "First ends. Second starts"),
            ("See e.g. this one. Done.", "this", "See e.g. this one."),
            ('He said "stop." Then left.', "stop", 'He said "stop."'),
        ],
    )
    def it_finds_the_sentence_a_span_falls_in(self, string, matched, sentence):
        a = string.index(matched)
        assert prose.sentence_around(string, a, a + len(matched)) == sentence


class DescribeCheckRulesFiles:
    @pytest.mark.spec("check-cmd-reads-named-rules")
    def it_checks_against_each_rules_file_named(self, repo, draft):
        pr = pr_rules(repo)
        code, envelope = repo.run("check", draft, "--rules", prose.CONFIG_PATH, "--rules", pr)
        assert code == prose.OK, repo.err
        files = envelope["data"]["rules"]
        assert [f["path"] for f in files] == [prose.CONFIG_PATH, ".flywheel/pr-style.md"]
        assert [m["rule"] for m in files[0]["matches"]] == [PLAIN]
        assert [m["rule"] for m in files[1]["matches"]] == [NO_SUMMARY]
        assert files[1]["matches"][0]["sentence"] == "Summary"
        assert [p["section"] for p in files[1]["parts"]] == ["headings"]

    @pytest.mark.spec("check-cmd-reads-named-rules")
    def it_reads_the_projects_rules_when_none_is_named(self, repo, draft):
        pr_rules(repo)
        _code, envelope = repo.run("check", draft)
        assert [f["path"] for f in envelope["data"]["rules"]] == [prose.CONFIG_PATH]


class DescribeCheckPart:
    @pytest.mark.spec("check-cmd-prints-part")
    def it_prints_a_parts_rules_and_lines(self, repo, draft, capsys):
        pr = pr_rules(repo)
        _code, envelope = repo.run("check", draft, "--rules", pr)
        part = envelope["data"]["rules"][0]["parts"][0]["id"]
        capsys.readouterr()
        code = prose.main(["check", draft, "--rules", pr, "--part", part, "-C", str(repo.root)])
        out = capsys.readouterr().out
        assert code == prose.OK
        assert "### headings-no-summary:" in out
        assert "%s:3:0-38  paragraph  The tool runs. We wrote it in order to" % draft in out
        assert "sentences-own-subject" not in out

    @pytest.mark.spec("check-cmd-prints-part")
    def it_refuses_a_part_with_more_than_one_rules_file(self, repo, draft):
        pr = pr_rules(repo)
        code, _envelope = repo.run(
            "check", draft, "--rules", pr, "--rules", prose.CONFIG_PATH, "--part", "x@y:1-2"
        )
        assert code == prose.CANNOT_RUN
        assert "one --rules" in repo.err

    @pytest.mark.spec("check-cmd-prints-part")
    def it_refuses_a_part_the_file_does_not_have(self, repo, draft):
        code, _envelope = repo.run("check", draft, "--part", "headings@%s:1-4" % draft)
        assert code == prose.CANNOT_RUN
        assert "run check with no --part" in repo.err


class DescribeCheckWhereverTheFileSits:
    @pytest.mark.spec("check-cmd-ignores-scope-and-git")
    def it_checks_a_file_outside_the_project(self, repo, draft):
        code, envelope = repo.run("check", draft)
        assert code == prose.OK, repo.err
        assert envelope["data"]["file"] == draft

    @pytest.mark.spec("check-cmd-ignores-scope-and-git")
    def it_checks_while_governed_documents_are_uncommitted(self, repo, draft):
        repo.commit()
        (repo.root / "target.md").write_text("An uncommitted edit.\n")
        code, _envelope = repo.run("preflight", "--for", "apply")
        assert code == prose.PROBLEMS
        code, envelope = repo.run("check", draft)
        assert code == prose.OK, repo.err
        assert envelope["data"]["rules"][0]["matches"]


class DescribeCheckRefusals:
    @pytest.mark.spec("check-cmd-refuses-without-rules")
    def it_refuses_when_the_project_has_no_rules(self, repo, draft):
        (repo.root / prose.CONFIG_PATH).unlink()
        code, envelope = repo.run("check", draft)
        assert code == prose.CANNOT_RUN
        assert envelope is None
        assert prose.CONFIG_PATH in repo.err
        assert "config init" in repo.err

    @pytest.mark.spec("check-cmd-refuses-without-rules")
    def it_refuses_a_named_rules_file_that_is_missing(self, repo, draft):
        code, _envelope = repo.run("check", draft, "--rules", "nowhere.md")
        assert code == prose.CANNOT_RUN
        assert "nowhere.md" in repo.err

    @pytest.mark.spec("check-cmd-refuses-without-rules")
    def it_refuses_a_rules_file_that_lint_refuses(self, repo, draft):
        bad = repo.root / "CLAUDE.md"
        bad.write_text("# Notes\n\nNot a rules file.\n")
        code, _envelope = repo.run("check", draft, "--rules", str(bad))
        assert code == prose.CANNOT_RUN
        assert "CLAUDE.md" in repo.err
        assert "config lint --file" in repo.err

    @pytest.mark.spec("check-cmd-refuses-without-rules")
    def it_refuses_a_file_that_does_not_exist(self, repo, tmp_path):
        code, _envelope = repo.run("check", str(tmp_path / "gone.md"))
        assert code == prose.CANNOT_RUN
        assert "gone.md" in repo.err

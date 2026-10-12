"""`--rule` checks the documents against only the rules it names.

After update-prose-config wrote rules from the review of #527, the agent
searched by hand for the other places each new rule was broken, and rewrote
them without a report (#543). `pass`, `report` and `apply` now take the ids
of those rules, so the same report and approval cover a pass over just them.
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

### standing-no-em-dash: Prefer a period over the em-dash

**Pattern.** `\\s--\\s`

> **Before.** It holds -- until it does not.
> **After.** It holds. Then it does not.
"""

PLAIN = "register-plain-words"
DASH = "standing-no-em-dash"
DOC = "# Notes\n\nIt ran in order to ship.\n\nIt held -- for a while.\n"


@pytest.fixture
def rule_repo(prose_repo):
    (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
    (prose_repo.root / "doc.md").write_text(DOC)
    return prose_repo


def plain_finding(replacement="It ran to ship."):
    return {
        "file": "doc.md",
        "line": 3,
        "rule": PLAIN,
        "text": "It ran in order to ship.",
        "replacement": replacement,
    }


def dash_finding():
    return {
        "file": "doc.md",
        "line": 5,
        "rule": DASH,
        "text": "It held -- for a while.",
        "replacement": "It held for a while.",
    }


class DescribeThePassCommandGivenRules:
    @pytest.mark.spec("pass-cmd-reads-named-rules")
    def it_prints_only_the_named_rules_and_their_matches(self, rule_repo):
        code, envelope = rule_repo.run("pass", "doc.md", "--rule", PLAIN)
        assert code == prose.OK
        data = envelope["data"]
        assert [r["id"] for r in data["rules"]] == [PLAIN]
        assert [m["rule"] for m in data["matches"]] == [PLAIN]
        assert data["patterned"] == [PLAIN]

    @pytest.mark.spec("pass-cmd-reads-named-rules")
    def it_prints_only_the_named_rules_under_the_rules_heading(self, rule_repo, capsys):
        code = prose.main(["pass", "doc.md", "--rule", PLAIN, "-C", str(rule_repo.root)])
        rules = capsys.readouterr().out.split("== segments ==\n")[0]
        assert code == prose.OK
        assert "### %s:" % PLAIN in rules
        assert "### sentences-own-subject:" not in rules
        assert "### %s:" % DASH not in rules

    @pytest.mark.spec("pass-cmd-reads-named-rules")
    def it_prints_every_rule_named_in_the_file_order(self, rule_repo):
        code, envelope = rule_repo.run("pass", "doc.md", "--rule", DASH, "--rule", PLAIN)
        assert code == prose.OK
        assert [m["rule"] for m in envelope["data"]["matches"]] == [PLAIN, DASH]
        assert [r["id"] for r in envelope["data"]["rules"]] == [PLAIN, DASH]


class DescribeTheReportCommandGivenRules:
    @pytest.mark.spec("report-cmd-checks-named-rules")
    def it_passes_with_a_match_of_another_rule_left_uncovered(self, rule_repo):
        code, envelope = rule_repo.report([plain_finding()], "doc.md", "--rule", PLAIN)
        assert code == prose.OK, envelope["errors"]
        assert envelope["data"]["checked_by_pattern"] == [PLAIN]
        assert envelope["data"]["rules"] == [PLAIN]
        page = (rule_repo.root / prose.REPORT_FILE).read_text()
        assert "Every other rule given to --rule was checked by reading. Given: `%s`." % PLAIN in (
            page
        )

    @pytest.mark.spec("report-cmd-checks-named-rules")
    def it_fails_on_an_uncovered_match_of_a_named_rule(self, rule_repo):
        code, envelope = rule_repo.report(
            [plain_finding()], "doc.md", "--rule", PLAIN, "--rule", DASH
        )
        assert code == prose.PROBLEMS
        assert any(DASH in e and "no finding or dismissal" in e for e in envelope["errors"])

    @pytest.mark.spec("report-cmd-checks-named-rules")
    def it_refuses_a_finding_of_a_rule_it_was_not_given(self, rule_repo):
        findings = [plain_finding(), dash_finding()]
        code, envelope = rule_repo.report(findings, "doc.md", "--rule", PLAIN)
        assert code == prose.PROBLEMS
        assert envelope["data"]["token"] is None
        assert envelope["errors"] == [
            "finding 2 names rule %s, and report was given --rule %s only; "
            "drop the finding, or give report its rule too" % (DASH, PLAIN)
        ]

    @pytest.mark.spec("report-cmd-checks-named-rules")
    def it_fails_a_rewrite_that_breaks_a_rule_it_was_not_given(self, rule_repo):
        finding = plain_finding(replacement="It ran -- to ship.")
        code, envelope = rule_repo.report([finding], "doc.md", "--rule", PLAIN)
        assert code == prose.PROBLEMS
        assert any("%s's pattern matches" % DASH in e for e in envelope["errors"])


class DescribeTheTokenGivenRules:
    @pytest.mark.spec("report-cmd-shows-whole-batch")
    def it_applies_given_the_rules_report_was_given(self, rule_repo):
        code, envelope = rule_repo.report([plain_finding()], "doc.md", "--rule", PLAIN)
        token = envelope["data"]["token"]
        path = str(rule_repo.root / "findings.json")
        code, envelope = rule_repo.run(
            "apply", "--findings", path, "--token", token, "doc.md", "--rule", PLAIN
        )
        assert code == prose.OK, envelope["errors"]
        assert "It ran to ship." in rule_repo.read("doc.md")

    @pytest.mark.spec("report-cmd-shows-whole-batch")
    @pytest.mark.parametrize("given", [[], ["--rule", PLAIN, "--rule", DASH]])
    def it_refuses_apply_given_other_rules_than_report(self, rule_repo, given):
        code, envelope = rule_repo.report([plain_finding()], "doc.md", "--rule", PLAIN)
        token = envelope["data"]["token"]
        path = str(rule_repo.root / "findings.json")
        code, envelope = rule_repo.run(
            "apply", "--findings", path, "--token", token, "doc.md", *given
        )
        assert code == prose.PROBLEMS
        assert "run report again and show it to the author" in envelope["errors"][0]
        assert rule_repo.read("doc.md") == DOC


class DescribeTheRuleFlag:
    @pytest.mark.spec("report-cmd-names-unknown-rule-ids")
    @pytest.mark.parametrize("command", ["pass", "report", "apply"])
    def it_names_an_id_the_rule_file_does_not_define(self, rule_repo, command):
        path = rule_repo.findings_file([plain_finding()])
        argv = {
            "pass": ["pass"],
            "report": ["report", "--findings", path],
            "apply": ["apply", "--findings", path, "--token", "0"],
        }[command]
        code, envelope = rule_repo.run(*argv, "--rule", PLAIN, "--rule", "register-missing")
        assert code == prose.CANNOT_RUN
        assert envelope is None
        assert "--rule register-missing: %s does not define it" % prose.CONFIG_PATH in (
            rule_repo.err
        )

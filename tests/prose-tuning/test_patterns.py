"""A rule's pattern finds its breaches, the same ones on every run.

Before `patterns` existed, the apply-prose run behind #73 found its dashes with
a grep the model wrote on the spot, which missed a dash that wrapped and
checked a list of spellings made up that run. So a rule carries its own
patterns, `config lint` refuses one that cannot run, and `patterns` searches
exactly what `segments` hands out, reading a paragraph's lines as one passage.
"""

import pytest

import prose

# The throwaway repo's rule file, with a rule that carries patterns. It keeps
# the conftest's rule too, so a finding built from a match can name either.
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
**Pattern.** `—`

> **Before.** In order to run it.
> **After.** To run it.
"""

RULE = "register-plain-words"


def patterned(tmp_path, doc, style=STYLE):
    """A rule file and one document, as a Config and a Text."""
    path = tmp_path / "prose-style.md"
    path.write_text(style)
    config = prose.Config(str(path))
    assert not config.errors, config.errors
    return config, prose.Text(doc)


def matches(tmp_path, doc, style=STYLE):
    config, text = patterned(tmp_path, doc, style)
    return prose.pattern_matches(text, prose.Blocks(text), config.patterned())


def rule_with(line):
    """A rule file whose one rule carries this line in its body."""
    return STYLE.replace("**Pattern.** `(?i)in order to`", line)


class DescribePatternLines:
    def it_reads_every_pattern_a_rule_carries(self, config_from):
        config = config_from(STYLE)
        assert config.by_id()[RULE].patterns == [(16, "(?i)in order to"), (17, "—")]
        assert not config.errors

    def it_reads_a_pattern_fenced_in_two_backticks(self, config_from):
        config = config_from(rule_with("**Pattern.** `` `x` ``"))
        assert config.by_id()[RULE].patterns[0] == (16, "`x`")

    def it_lists_the_patterns_with_the_rule(self, config_from):
        rule = config_from(STYLE).by_id()[RULE].as_dict()
        assert rule["patterns"] == ["(?i)in order to", "—"]

    @pytest.mark.parametrize(
        ("line", "message"),
        [
            ("**Pattern.** `in order (to`", "does not compile"),
            ("**Pattern.** in order to", "one code span and nothing else"),
            ("**Pattern.** `in order` to", "one code span and nothing else"),
            ("**Pattern.** `x*`", "matches an empty string"),
            ("**Pattern.** `in (?i)order`", "part way along"),
        ],
    )
    def it_refuses_a_pattern_that_cannot_run(self, prose_repo, line, message):
        (prose_repo.root / prose.CONFIG_PATH).write_text(rule_with(line))
        code, envelope = prose_repo.run("config", "lint")
        assert code == prose.PROBLEMS
        assert len(envelope["errors"]) == 1
        assert ":16  " in envelope["errors"][0]
        assert message in envelope["errors"][0]

    @pytest.mark.parametrize(
        ("line", "message"),
        [
            ("**Pattern.** `run it`\n**Pattern.** `ran`", "matches the After example"),
            ("**Pattern.** `ship`", "finds anything in its Before example"),
        ],
    )
    def it_holds_the_patterns_to_the_rules_own_example(self, prose_repo, line, message):
        style = rule_with(line).replace("**Pattern.** `—`\n", "")
        (prose_repo.root / prose.CONFIG_PATH).write_text(style)
        code, envelope = prose_repo.run("config", "lint")
        assert code == prose.PROBLEMS
        assert [e for e in envelope["errors"] if message in e] != []
        assert len(envelope["errors"]) == 1

    def it_leaves_the_patterns_of_a_rule_with_no_example_unchecked(self, config_from):
        style = rule_with("**Pattern.** `ship`").split("> **Before.**")[0]
        assert config_from(style).errors == []


class DescribePatternMatches:
    def it_finds_a_match_on_one_line(self, tmp_path):
        got = matches(tmp_path, "We did it in order to ship.\n")
        assert got == [
            {
                "rule": RULE,
                "line": 1,
                "col_start": 10,
                "end_line": 1,
                "col_end": 21,
                "text": "in order to",
            }
        ]

    def it_finds_a_match_that_wraps_across_a_line_break(self, tmp_path):
        got = matches(tmp_path, "We did it in order\n  to ship.\n")
        assert [(m["line"], m["end_line"], m["text"]) for m in got] == [(1, 2, "in order\n  to")]
        assert (got[0]["col_start"], got[0]["col_end"]) == (10, 4)

    def it_finds_a_match_that_wraps_within_a_list_item(self, tmp_path):
        got = matches(tmp_path, "- We did it in order\n  to ship.\n")
        assert [m["text"] for m in got] == ["in order\n  to"]

    @pytest.mark.parametrize(
        "doc",
        [
            "```\nin order to\n```\n",
            "> in order to\n",
            "---\ntitle: in order to\n---\n",
            "<!--\nin order to\n-->\n",
            "Some <!-- in order to --> prose.\n",
            "Run `in order to` as it is.\n",
        ],
        ids=["fence", "blockquote", "front-matter", "comment", "inline-comment", "code-span"],
    )
    def it_never_reads_what_segments_leaves_out(self, tmp_path, doc):
        assert matches(tmp_path, doc) == []

    @pytest.mark.parametrize(
        "doc",
        [
            "We did it in order\n\nto ship.\n",
            "- We did it in order\n- to ship.\n",
            "# We did it in order\nto ship.\n",
            "We did it in order <!-- x -->\nto ship.\n",
        ],
        ids=["blank-line", "next-list-item", "heading", "comment-at-the-break"],
    )
    def it_does_not_read_on_past_the_end_of_a_passage(self, tmp_path, doc):
        assert matches(tmp_path, doc) == []

    def it_leaves_a_line_break_at_the_edge_of_a_match_out_of_its_text(self, tmp_path):
        style = rule_with(r"**Pattern.** `\sto\s`")
        got = matches(tmp_path, "We did it in order to\n  ship.\n", style)
        assert [(m["line"], m["end_line"], m["text"]) for m in got] == [(1, 1, " to")]
        style = rule_with(r"**Pattern.** `\sto\b`")
        got = matches(tmp_path, "We did it in order\n  to ship.\n", style)
        assert [(m["line"], m["col_start"], m["text"]) for m in got] == [(2, 2, "to")]

    def it_reports_a_place_two_patterns_of_one_rule_share_once(self, tmp_path):
        style = rule_with("**Pattern.** `order`\n**Pattern.** `(?i)ORDER`")
        assert [m["text"] for m in matches(tmp_path, "In order.\n", style)] == ["order"]


class DescribePatternsCommand:
    def it_prints_each_match_with_its_address_rule_and_text(self, prose_repo, capsys):
        (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
        (prose_repo.root / "doc.md").write_text("Intro — here.\n\nIt ran in order\n  to ship.\n")
        code = prose.main(["patterns", "doc.md", "-C", str(prose_repo.root)])
        out = capsys.readouterr().out.splitlines()
        assert code == prose.OK
        assert out[:2] == [
            'doc.md:1:6-7  %s  "—"' % RULE,
            'doc.md:3:7-4:4  %s  "in order\\n  to"' % RULE,
        ]
        assert out[-1].endswith("Checked by pattern: %s" % RULE)

    def it_hands_out_a_text_that_apply_accepts_as_a_finding(self, prose_repo):
        (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
        (prose_repo.root / "doc.md").write_text("It ran in order\n  to ship.\n")
        code, envelope = prose_repo.run("patterns")
        assert code == prose.OK
        [m] = envelope["data"]["matches"]
        finding = prose_repo.finding(
            m["line"], file=m["file"], rule=m["rule"], text=m["text"], replacement="to"
        )
        code, _ = prose_repo.apply([finding])
        assert code == prose.OK
        assert prose_repo.read("doc.md") == "It ran to ship.\n"

    def it_refuses_to_run_on_a_rule_file_lint_refuses(self, prose_repo):
        (prose_repo.root / prose.CONFIG_PATH).write_text(rule_with("**Pattern.** `(`"))
        code, envelope = prose_repo.run("patterns")
        assert code == prose.PROBLEMS
        assert envelope["data"] == {}

    def it_says_so_when_no_rule_carries_a_pattern(self, prose_repo):
        code, envelope = prose_repo.run("patterns")
        assert code == prose.OK
        assert envelope["data"]["rules"] == []
        assert envelope["data"]["matches"] == []


class DescribeReportOnPatterns:
    def it_names_the_rules_checked_by_pattern(self, prose_repo, capsys):
        (prose_repo.root / prose.CONFIG_PATH).write_text(STYLE)
        finding = prose_repo.finding(7, text="Curated, not collected.")
        path = prose_repo.findings_file([finding])
        code = prose.main(["report", "--findings", path, "-C", str(prose_repo.root)])
        out = capsys.readouterr().out.splitlines()
        assert code == prose.OK
        assert out[-1] == (
            "checked by pattern: %s. Every other rule was checked by reading." % RULE
        )


class DescribeShippedPatterns:
    """The shipped rules' patterns, against the words each must and must not
    find. A word here that a later edit to a pattern stops finding is a
    regression, and one it starts finding is a false alarm in every project.
    """

    @pytest.fixture(scope="class")
    def shipped(self):
        return prose.Config(prose.shipped_template())

    def found(self, shipped, rid, doc):
        text = prose.Text(doc)
        rule = shipped.by_id()[rid]
        return [m["text"] for m in prose.pattern_matches(text, prose.Blocks(text), [rule])]

    def it_lints_clean(self, shipped):
        assert shipped.errors == []
        assert [r.id for r in shipped.patterned()] == [
            "standing-no-em-dash",
            "standing-us-spelling",
        ]

    @pytest.mark.parametrize(
        ("doc", "want"),
        [
            ("The estimate holds - until it does not.\n", [" - "]),
            ("The estimate holds — until it does not.\n", ["—"]),
            ("The estimate holds\u2013until it does not.\n", []),
            ("The estimate holds \u2013 until it does not.\n", [" \u2013 "]),
            ("The estimate holds -- until it does not.\n", [" -- "]),
            ("The estimate holds -\n  until it does not.\n", [" -"]),
            ("It took 20-30 hrs/wk from 1988-2026.\n", []),
            ("Run it with --dry-run first.\n", []),
            ("A well-known, self-evident fact.\n", []),
        ],
    )
    def it_finds_a_dash_doing_an_em_dash_job(self, shipped, doc, want):
        assert self.found(shipped, "standing-no-em-dash", doc) == want

    @pytest.mark.parametrize(
        "word",
        "behaviour Colourful favourite honour neighbour analyse organisation "
        "recognised prioritise summarising centre litres travelled modelling "
        "counsellor defence licence judgement acknowledgements ageing amongst "
        "catalogue grey programme sceptical tyre whilst".split(),
    )
    def it_finds_a_british_spelling(self, shipped, word):
        assert self.found(shipped, "standing-us-spelling", "A %s here.\n" % word) == [word]

    @pytest.mark.parametrize(
        "word",
        "behavior color hour contour glamour analyses analysis emphasis realism "
        "advise exercise promise precise surprise compromise enterprise center "
        "meter literal traveled cancellation defense license judgment aging gray "
        "program programmer dialogue among skeptical tire".split(),
    )
    def it_leaves_a_us_spelling_alone(self, shipped, word):
        assert self.found(shipped, "standing-us-spelling", "A %s here.\n" % word) == []

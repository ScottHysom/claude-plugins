"""The rule file is the plugin's only persistent state, and it is hand-edited
markdown. The parser has to accept what an author would reasonably write and
name what it cannot accept, once per mistake.
"""

import pytest

import prose

WELL_FORMED = (
    '---\nname: T\nscope:\n  include:\n    - "**/*.md"\n'
    '  exclude:\n    - "x.md"\n---\n\n'
    "## Sentences\n\n"
    "### sentences-own-subject: Carries its own subject\n"
    "<!-- prose-rule: source=shipped -->\n\n"
    "Body text.\n\n> **Before.** a\n> **After.** b\n\n"
    "### sentences-own-subject: Duplicate\n\nBody.\n"
)

# One rule per malformed shape, each with a different fault, plus a good one
# at the end. Five faults must produce five messages and nothing else.
BAD_IDS = (
    "---\nname: T\n---\n\n## Sentences\n\n"
    "### sentences-01: Positional\n"
    "Body.\n> **Before.** a\n> **After.** b\n\n"
    "### sentences-a-b-c-d-e: Five words\n"
    "Body.\n> **Before.** a\n> **After.** b\n\n"
    "### sentences-Own_Subject: Not lower case\n"
    "Body.\n> **Before.** a\n> **After.** b\n\n"
    "### sentences-rule-01: Smuggled ordinal\n"
    "Body.\n> **Before.** a\n> **After.** b\n\n"
    "### sentences: No id at all\n"
    "Body.\n\n"
    "### sentences-sentences-subject: Repeats its section\n"
    "Body.\n> **Before.** a\n> **After.** b\n\n"
    "### sentences-own-subject: Fine\n"
    "Body.\n> **Before.** a\n> **After.** b\n"
)

BAD_ID_ERRORS = [
    "rule id is positional",
    "has 5 words; at most 4",
    "is not lower-case words",
    "carries a number",
    "carries no id",
]


class DescribeWellFormedRuleFile:
    def it_reads_every_rule(self, config_from):
        assert len(config_from(WELL_FORMED).rules) == 2

    def it_parses_the_scope_block(self, config_from):
        cfg = config_from(WELL_FORMED)
        assert cfg.scope_include == ["**/*.md"]
        assert cfg.scope_exclude == ["x.md"]

    def it_reports_a_duplicate_id(self, config_from):
        assert any("duplicate rule id" in e for e in config_from(WELL_FORMED).errors)

    def it_extracts_the_worked_example(self, config_from):
        rule = config_from(WELL_FORMED).rules[0]
        assert (rule.before, rule.after) == ("a", "b")

    def it_refuses_a_taken_id(self, config_from):
        _, problem = config_from(WELL_FORMED).check_id("sentences", "own-subject")
        assert problem is not None

    def it_allows_a_free_id(self, config_from):
        rid, problem = config_from(WELL_FORMED).check_id("sentences", "name-the-role")
        assert (rid, problem) == ("sentences-name-the-role", None)


class DescribeRuleIdGrammar:
    @pytest.mark.parametrize("message", BAD_ID_ERRORS)
    def it_names_each_bad_id_once(self, config_from, message):
        hits = [e for e in config_from(BAD_IDS).errors if message in e]
        assert len(hits) == 1, "matched %d: %s" % (len(hits), hits)

    def it_reports_nothing_else(self, config_from):
        errors = config_from(BAD_IDS).errors
        assert len(errors) == len(BAD_ID_ERRORS), errors

    def it_only_warns_about_a_name_that_repeats_its_section(self, config_from):
        """Readable but redundant - sentences-sentences-subject. Worth a
        nudge, not worth refusing the file.
        """
        cfg = config_from(BAD_IDS)
        opens = [w for w in cfg.warnings if "opens with its own section" in w]
        assert len(opens) == 1

    def it_keeps_a_good_name(self, config_from):
        assert config_from(BAD_IDS).rules[-1].name == "own-subject"


class DescribeFrontMatter:
    def it_refuses_a_key_outside_the_grammar(self, config_from):
        """Silently ignoring a key the author meant to set is worse than refusing
        the file, because the rule file looks like it took effect.
        """
        cfg = config_from("---\nname: T\nscope:\n  nested:\n    deep: 1\n---\n")
        assert cfg.errors


class DescribeRuleSimilarity:
    """The floor under adopt-prose's similar bucket - a candidate list for a
    person to judge, not a decision the script makes.
    """

    SHARED = ("A sentence that borrows its subject from the heading above", "it is incomplete.")

    def rule(self, rid, section, name, body):
        r = prose.Rule(rid, section, name, "T", 1)
        r.body = list(body)
        return r

    def it_scores_the_same_rule_renamed_high(self):
        a = self.rule("sentences-own-subject", "sentences", "own-subject", self.SHARED)
        b = self.rule("voice-carries-subject", "voice", "carries-subject", self.SHARED)
        assert prose.rule_similarity(a, b)[2] >= 0.9

    def it_still_scores_on_a_shared_name_alone(self):
        a = self.rule("sentences-own-subject", "sentences", "own-subject", self.SHARED)
        b = self.rule(
            "voice-own-subject",
            "voice",
            "own-subject",
            ["Commit messages name the file they touch."],
        )
        assert prose.rule_similarity(a, b)[2] >= 0.6

    def it_scores_unrelated_rules_low(self):
        a = self.rule("sentences-own-subject", "sentences", "own-subject", self.SHARED)
        b = self.rule(
            "headings-noun-phrase",
            "headings",
            "noun-phrase",
            ["Commit messages name the file they touch."],
        )
        assert prose.rule_similarity(a, b)[2] < 0.6


class DescribeBodyKey:
    def rule(self, body):
        r = prose.Rule("x-thing", "x", "thing", "T", 1)
        r.body = list(body)
        return r

    def it_ignores_a_fill_marker(self):
        """A rule awaiting an example is still the same rule. If the marker
        counted, adopt-prose would offer to add what is already there.
        """
        with_marker = self.rule(["Same rule.", "<!-- FILL: supply an example. -->", ""])
        without = self.rule(["Same", "rule."])
        assert with_marker.body_key() == without.body_key()

    def it_gives_different_bodies_different_keys(self):
        assert self.rule(["Same rule."]).body_key() != self.rule(["A different rule."]).body_key()


class DescribeConfigClassify:
    """adopt-prose's step 2. Every source rule lands in one bucket, and two
    runs on the same pair of files land it in the same one.
    """

    HEAD = "---\nname: T\n---\n\n"
    SHARED = "A sentence that borrows its subject from the heading above it is incomplete."

    def rule(self, rid, body):
        return "### %s: Title\n\n%s\n\n" % (rid, body)

    def classify(self, prose_repo, source, target):
        src, tgt = prose_repo.root / "source.md", prose_repo.root / "target-style.md"
        src.write_text(self.HEAD + "## Sentences\n\n" + "".join(source))
        tgt.write_text(self.HEAD + "## Sentences\n\n" + "".join(target))
        code, env = prose_repo.run("config", "classify", "--file", str(src), "--to", str(tgt))
        assert code == prose.OK
        return {r["id"]: r for r in env["data"]["rules"]}

    def it_puts_a_rule_the_target_lacks_in_new(self, prose_repo):
        rules = self.classify(
            prose_repo,
            [self.rule("sentences-own-subject", self.SHARED)],
            [self.rule("sentences-count-needs-list", "A count needs its list nearby.")],
        )
        assert rules["sentences-own-subject"]["bucket"] == prose.BUCKET_NEW
        assert rules["sentences-own-subject"]["target"] is None

    def it_puts_a_same_id_same_body_rule_in_identical(self, prose_repo):
        rules = self.classify(
            prose_repo,
            [self.rule("sentences-own-subject", self.SHARED)],
            [self.rule("sentences-own-subject", self.SHARED)],
        )
        got = rules["sentences-own-subject"]
        assert (got["bucket"], got["target"]) == (prose.BUCKET_IDENTICAL, "sentences-own-subject")

    def it_puts_a_same_id_different_body_rule_in_colliding(self, prose_repo):
        rules = self.classify(
            prose_repo,
            [self.rule("sentences-own-subject", self.SHARED)],
            [self.rule("sentences-own-subject", "Commit messages name the file they touch.")],
        )
        got = rules["sentences-own-subject"]
        assert (got["bucket"], got["target"]) == (prose.BUCKET_COLLIDING, "sentences-own-subject")

    def it_puts_a_renamed_rule_in_similar_with_its_candidate(self, prose_repo):
        rules = self.classify(
            prose_repo,
            [self.rule("sentences-own-subject", self.SHARED)],
            [self.rule("sentences-carries-subject", self.SHARED)],
        )
        got = rules["sentences-own-subject"]
        assert got["bucket"] == prose.BUCKET_SIMILAR
        assert got["target"] == "sentences-carries-subject"
        assert [c["target"] for c in got["candidates"]] == ["sentences-carries-subject"]

    def it_treats_a_body_differing_only_by_a_fill_marker_and_rewrap_as_identical(self, prose_repo):
        """The bodies differ as text, so comparing `body` would make this a
        collision, and nearly every shipped rule would look like one.
        """
        rewrapped = "A sentence that borrows its subject\nfrom the heading above it is incomplete."
        rules = self.classify(
            prose_repo,
            [self.rule("sentences-own-subject", self.SHARED)],
            [self.rule("sentences-own-subject", rewrapped + "\n<!-- FILL: an example. -->")],
        )
        assert rules["sentences-own-subject"]["bucket"] == prose.BUCKET_IDENTICAL

    def it_settles_a_shared_id_before_scoring_similarity(self, prose_repo):
        rules = self.classify(
            prose_repo,
            [self.rule("sentences-own-subject", self.SHARED)],
            [
                self.rule("sentences-own-subject", "Commit messages name the file they touch."),
                self.rule("sentences-carries-subject", self.SHARED),
            ],
        )
        got = rules["sentences-own-subject"]
        assert (got["bucket"], got["candidates"]) == (prose.BUCKET_COLLIDING, [])

    def it_refuses_a_missing_target_file(self, prose_repo):
        src = prose_repo.root / "source.md"
        src.write_text(self.HEAD + "## Sentences\n\n" + self.rule("sentences-own-subject", "x"))
        missing = str(prose_repo.root / "nowhere.md")
        code, env = prose_repo.run("config", "classify", "--file", str(src), "--to", missing)
        assert (code, env) == (prose.CANNOT_RUN, None)
        assert "nowhere.md does not exist" in prose_repo.err


class DescribeConfigAdopt:
    """adopt-prose's step 3. A new rule reaches the target as the source wrote
    it, with only its metadata replaced, and never over a rule the target has.
    """

    HEAD = "---\nname: T\n---\n\n"
    # Odd wrapping, a pattern and a worked example: everything a hand copy
    # could lose.
    OWN_SUBJECT = (
        "### sentences-own-subject: Carries its own subject\n"
        "<!-- prose-rule: source=inferred -->\n"
        "\n"
        "A sentence that borrows its subject\n"
        "   from the heading   above it is incomplete.\n"
        "\n"
        "**Pattern.** `^Able to`\n"
        "\n"
        "> **Before.** Able to state it.\n"
        "> **After.** A reader can state it.\n"
    )
    COUNT = (
        "### sentences-count-needs-list: A count needs a list\n"
        "\n"
        "A count needs its list nearby.\n"
        "\n"
        "> **Before.** Three rules apply.\n"
        "> **After.** These rules apply:\n"
    )
    TONE = (
        "### register-plain-words: Plain words\n"
        "\n"
        "Use plain words over jargon.\n"
        "\n"
        "> **Before.** Leverage it.\n"
        "> **After.** Use it.\n"
    )

    def files(self, prose_repo, source, target):
        src, tgt = prose_repo.root / "source.md", prose_repo.root / "target-style.md"
        src.write_text(self.HEAD + source)
        tgt.write_text(self.HEAD + target)
        return src, tgt

    def adopt(self, prose_repo, src, tgt, *argv):
        return prose_repo.run("config", "adopt", "--file", str(src), "--to", str(tgt), *argv)

    def it_copies_a_rule_byte_for_byte(self, prose_repo):
        src, tgt = self.files(
            prose_repo, "## Sentences\n\n" + self.OWN_SUBJECT, "## Sentences\n\n" + self.COUNT
        )
        code, _ = self.adopt(prose_repo, src, tgt, "--rule", "sentences-own-subject")
        assert code == prose.OK
        body = self.OWN_SUBJECT.split("\n", 2)[2]
        assert "\n" + body in tgt.read_text()

    def it_writes_the_origin_comment(self, prose_repo):
        src, tgt = self.files(
            prose_repo, "## Sentences\n\n" + self.OWN_SUBJECT, "## Sentences\n\n" + self.COUNT
        )
        code, env = self.adopt(prose_repo, src, tgt, "--rule", "sentences-own-subject")
        assert (code, env["data"]["origin"]) == (prose.OK, "repo")
        text = tgt.read_text()
        assert (
            "### sentences-own-subject: Carries its own subject\n"
            "<!-- prose-rule: source=adopted origin=repo -->\n\n"
        ) in text
        assert "source=inferred" not in text

    def it_takes_the_origin_it_is_given(self, prose_repo):
        src, tgt = self.files(prose_repo, "## Sentences\n\n" + self.OWN_SUBJECT, "")
        self.adopt(prose_repo, src, tgt, "--rule", "sentences-own-subject", "--origin", "game")
        assert "source=adopted origin=game -->" in tgt.read_text()

    def it_refuses_an_origin_with_a_space(self, prose_repo):
        src, tgt = self.files(prose_repo, "## Sentences\n\n" + self.OWN_SUBJECT, "")
        code, _ = self.adopt(
            prose_repo, src, tgt, "--rule", "sentences-own-subject", "--origin", "two words"
        )
        assert code == prose.CANNOT_RUN

    def it_refuses_an_id_the_target_has(self, prose_repo):
        src, tgt = self.files(
            prose_repo,
            "## Sentences\n\n" + self.OWN_SUBJECT,
            "## Sentences\n\n" + self.OWN_SUBJECT.replace("incomplete", "unfinished"),
        )
        before = tgt.read_bytes()
        code, env = self.adopt(prose_repo, src, tgt, "--rule", "sentences-own-subject")
        assert code == prose.PROBLEMS
        assert [r["id"] for r in env["data"]["refused"]] == ["sentences-own-subject"]
        assert "collision" in env["errors"][0]
        assert tgt.read_bytes() == before

    def it_refuses_an_id_the_source_lacks(self, prose_repo):
        src, tgt = self.files(prose_repo, "## Sentences\n\n" + self.OWN_SUBJECT, "")
        code, env = self.adopt(prose_repo, src, tgt, "--rule", "sentences-no-such-rule")
        assert code == prose.PROBLEMS
        assert [r["id"] for r in env["data"]["refused"]] == ["sentences-no-such-rule"]

    def it_places_a_rule_after_the_last_of_its_section(self, prose_repo):
        src, tgt = self.files(
            prose_repo,
            "## Sentences\n\n" + self.OWN_SUBJECT,
            "## Sentences\n\n" + self.COUNT + "\n## Register\n\n" + self.TONE,
        )
        code, env = self.adopt(prose_repo, src, tgt, "--rule", "sentences-own-subject")
        assert code == prose.OK
        text = tgt.read_text()
        assert (
            text.index("sentences-count-needs-list")
            < text.index("sentences-own-subject")
            < text.index("## Register")
        )
        assert "> **After.** These rules apply:\n\n### sentences-own-subject" in text
        assert "> **After.** A reader can state it.\n\n## Register" in text
        line = env["data"]["adopted"][0]["line"]
        assert text.split("\n")[line - 1].startswith("### sentences-own-subject:")

    def it_adds_the_section_heading_when_the_target_has_none(self, prose_repo):
        src, tgt = self.files(
            prose_repo,
            "## Register\n\n" + self.TONE,
            "## Sentences\n\n" + self.COUNT,
        )
        code, _ = self.adopt(prose_repo, src, tgt, "--rule", "register-plain-words")
        assert code == prose.OK
        assert "These rules apply:\n\n## Register\n\n### register-plain-words" in tgt.read_text()

    def it_keeps_the_source_order_for_rules_going_to_one_place(self, prose_repo):
        src, tgt = self.files(
            prose_repo,
            "## Sentences\n\n" + self.OWN_SUBJECT + "\n" + self.COUNT,
            "## Register\n\n" + self.TONE,
        )
        code, _ = self.adopt(
            prose_repo,
            src,
            tgt,
            "--rule",
            "sentences-count-needs-list",
            "--rule",
            "sentences-own-subject",
        )
        assert code == prose.OK
        text = tgt.read_text()
        assert text.count("## Sentences") == 1
        assert text.index("sentences-own-subject") < text.index("sentences-count-needs-list")

    def it_writes_nothing_on_a_dry_run(self, prose_repo):
        src, tgt = self.files(prose_repo, "## Sentences\n\n" + self.OWN_SUBJECT, "")
        before = tgt.read_bytes()
        code, env = self.adopt(prose_repo, src, tgt, "--rule", "sentences-own-subject", "--dry-run")
        assert code == prose.OK
        assert [a["id"] for a in env["data"]["adopted"]] == ["sentences-own-subject"]
        assert tgt.read_bytes() == before

    def it_writes_nothing_when_one_id_is_refused(self, prose_repo):
        src, tgt = self.files(
            prose_repo, "## Sentences\n\n" + self.OWN_SUBJECT, "## Sentences\n\n" + self.COUNT
        )
        before = tgt.read_bytes()
        code, env = self.adopt(
            prose_repo, src, tgt, "--rule", "sentences-own-subject", "--rule", "sentences-nope"
        )
        assert (code, env["data"]["adopted"]) == (prose.PROBLEMS, [])
        assert tgt.read_bytes() == before

    def it_writes_the_rest_with_partial(self, prose_repo):
        src, tgt = self.files(
            prose_repo, "## Sentences\n\n" + self.OWN_SUBJECT, "## Sentences\n\n" + self.COUNT
        )
        code, _ = self.adopt(
            prose_repo,
            src,
            tgt,
            "--rule",
            "sentences-own-subject",
            "--rule",
            "sentences-nope",
            "--partial",
        )
        assert code == prose.PROBLEMS
        assert "### sentences-own-subject" in tgt.read_text()

    def it_leaves_a_target_that_lints_clean(self, prose_repo):
        src, tgt = self.files(
            prose_repo,
            "## Sentences\n\n" + self.OWN_SUBJECT + "\n## Register\n\n" + self.TONE,
            "## Sentences\n\n" + self.COUNT,
        )
        self.adopt(
            prose_repo,
            src,
            tgt,
            "--rule",
            "sentences-own-subject",
            "--rule",
            "register-plain-words",
        )
        code, env = prose_repo.run("config", "lint", "--file", str(tgt))
        assert (code, env["data"]["rules"]) == (prose.OK, 3)

    def it_refuses_a_source_that_does_not_lint(self, prose_repo):
        src, tgt = self.files(prose_repo, "## Sentences\n\n### sentences-01: Bad\n\nBody.\n", "")
        code, _ = self.adopt(prose_repo, src, tgt, "--rule", "sentences-01")
        assert code == prose.CANNOT_RUN
        assert "does not lint clean" in prose_repo.err

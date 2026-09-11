"""The rule file is the plugin's only persistent state, and it is hand-edited
markdown. The parser has to accept what an author would reasonably write and
name what it cannot accept, once per mistake.
"""
import pytest

import prose

WELL_FORMED = (
    '---\nname: T\nscope:\n  include:\n    - "**/*.md"\n'
    '  exclude:\n    - "x.md"\n---\n\n'
    '## Sentences\n\n'
    '### sentences-own-subject: Carries its own subject\n'
    '<!-- prose-rule: source=shipped -->\n\n'
    'Body text.\n\n> **Before.** a\n> **After.** b\n\n'
    '### sentences-own-subject: Duplicate\n\nBody.\n'
)

# One rule per malformed shape, each with a different fault, plus a good one
# at the end. Five faults must produce five messages and nothing else.
BAD_IDS = (
    '---\nname: T\n---\n\n## Sentences\n\n'
    '### sentences-01: Positional\n'
    'Body.\n> **Before.** a\n> **After.** b\n\n'
    '### sentences-a-b-c-d-e: Five words\n'
    'Body.\n> **Before.** a\n> **After.** b\n\n'
    '### sentences-Own_Subject: Not lower case\n'
    'Body.\n> **Before.** a\n> **After.** b\n\n'
    '### sentences-rule-01: Smuggled ordinal\n'
    'Body.\n> **Before.** a\n> **After.** b\n\n'
    '### sentences: No id at all\n'
    'Body.\n\n'
    '### sentences-sentences-subject: Repeats its section\n'
    'Body.\n> **Before.** a\n> **After.** b\n\n'
    '### sentences-own-subject: Fine\n'
    'Body.\n> **Before.** a\n> **After.** b\n'
)

BAD_ID_ERRORS = [
    "rule id is positional",
    "has 5 words; at most 4",
    "is not lower-case words",
    "carries a number",
    "carries no id",
]


class TestWellFormedRuleFile:
    def test_every_rule_is_read(self, config_from):
        assert len(config_from(WELL_FORMED).rules) == 2

    def test_the_scope_block_is_parsed(self, config_from):
        cfg = config_from(WELL_FORMED)
        assert cfg.scope_include == ["**/*.md"]
        assert cfg.scope_exclude == ["x.md"]

    def test_a_duplicate_id_is_reported(self, config_from):
        assert any("duplicate rule id" in e
                   for e in config_from(WELL_FORMED).errors)

    def test_the_worked_example_is_extracted(self, config_from):
        rule = config_from(WELL_FORMED).rules[0]
        assert (rule.before, rule.after) == ("a", "b")

    def test_check_id_refuses_a_taken_id(self, config_from):
        _, problem = config_from(WELL_FORMED).check_id("sentences",
                                                       "own-subject")
        assert problem is not None

    def test_check_id_allows_a_free_id(self, config_from):
        rid, problem = config_from(WELL_FORMED).check_id("sentences",
                                                         "name-the-role")
        assert (rid, problem) == ("sentences-name-the-role", None)


class TestRuleIdGrammar:
    @pytest.mark.parametrize("message", BAD_ID_ERRORS)
    def test_each_bad_id_is_named_once(self, config_from, message):
        hits = [e for e in config_from(BAD_IDS).errors if message in e]
        assert len(hits) == 1, "matched %d: %s" % (len(hits), hits)

    def test_nothing_else_is_reported(self, config_from):
        errors = config_from(BAD_IDS).errors
        assert len(errors) == len(BAD_ID_ERRORS), errors

    def test_a_name_repeating_its_section_only_warns(self, config_from):
        """Readable but redundant - sentences-sentences-subject. Worth a
        nudge, not worth refusing the file.
        """
        cfg = config_from(BAD_IDS)
        opens = [w for w in cfg.warnings if "opens with its own section" in w]
        assert len(opens) == 1

    def test_a_good_name_survives(self, config_from):
        assert config_from(BAD_IDS).rules[-1].name == "own-subject"


def test_front_matter_outside_the_grammar_is_refused(config_from):
    """Silently ignoring a key the author meant to set is worse than refusing
    the file, because the rule file looks like it took effect.
    """
    cfg = config_from('---\nname: T\nscope:\n  nested:\n    deep: 1\n---\n')
    assert cfg.errors


class TestRuleSimilarity:
    """The floor under adopt-prose's similar bucket - a candidate list for a
    person to judge, not a decision the script makes.
    """

    SHARED = ["A sentence that borrows its subject from the heading above",
              "it is incomplete."]

    def rule(self, rid, section, name, body):
        r = prose.Rule(rid, section, name, "T", 1)
        r.body = list(body)
        return r

    def test_the_same_rule_renamed_scores_high(self):
        a = self.rule("sentences-own-subject", "sentences", "own-subject",
                      self.SHARED)
        b = self.rule("voice-carries-subject", "voice", "carries-subject",
                      self.SHARED)
        assert prose.rule_similarity(a, b)[2] >= 0.9

    def test_a_shared_name_alone_still_scores(self):
        a = self.rule("sentences-own-subject", "sentences", "own-subject",
                      self.SHARED)
        b = self.rule("voice-own-subject", "voice", "own-subject",
                      ["Commit messages name the file they touch."])
        assert prose.rule_similarity(a, b)[2] >= 0.6

    def test_unrelated_rules_score_low(self):
        a = self.rule("sentences-own-subject", "sentences", "own-subject",
                      self.SHARED)
        b = self.rule("headings-noun-phrase", "headings", "noun-phrase",
                      ["Commit messages name the file they touch."])
        assert prose.rule_similarity(a, b)[2] < 0.6


class TestBodyKey:
    def rule(self, body):
        r = prose.Rule("x-thing", "x", "thing", "T", 1)
        r.body = list(body)
        return r

    def test_a_fill_marker_does_not_change_the_key(self):
        """A rule awaiting an example is still the same rule. If the marker
        counted, adopt-prose would offer to add what is already there.
        """
        with_marker = self.rule(
            ["Same rule.", "<!-- FILL: supply an example. -->", ""])
        without = self.rule(["Same", "rule."])
        assert with_marker.body_key() == without.body_key()

    def test_different_bodies_differ(self):
        assert self.rule(["Same rule."]).body_key() \
            != self.rule(["A different rule."]).body_key()

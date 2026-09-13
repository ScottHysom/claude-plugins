"""Short functions that larger decisions rest on: which files the rules
govern, whether a rule id is well formed, whether an edit was a prose decision
at all.

An example test picks an input and checks the output for that input. These
state a rule the output has to follow for every input - "a rule name is
accepted if and only if it is lower-case words joined by hyphens, at most
MAX_NAME_WORDS of them" - and hypothesis tries to find an input that breaks it.

The difference matters most when the function changes. A new branch that
changes the answer for inputs no example happened to use passes every example
test; it cannot pass these without the rule here being changed too.
"""
from hypothesis import assume, example, given
from hypothesis import strategies as st

import prose

NAME_CHARS = "abz-019_A"
PATH_CHARS = "ab/.-"


class TestValidateRuleName:
    """Several refusal branches, one rule for what they add up to.

    validate_rule_name refuses bad names in several distinct ways, and its
    docstring promises at most one message per mistake. The test below states
    the single rule those branches are supposed to implement between them, so
    a branch that starts refusing a good name - or letting a bad one through -
    fails here whichever branch it is.
    """

    @given(st.text(alphabet=NAME_CHARS, max_size=12))
    @example("own-subject")
    @example("sentences-01")
    @example("a-b-c-d-e")
    @example("Own_Subject")
    @example("")
    def test_a_name_is_accepted_exactly_when_it_is_short_and_lower_case(self,
                                                                       name):
        ok = bool(prose.RULE_NAME.match(name)) and \
            len(name.split("-")) <= prose.MAX_NAME_WORDS
        assert (prose.validate_rule_name(name) is None) is ok

    @given(st.text(alphabet=NAME_CHARS, max_size=12))
    def test_a_refusal_quotes_the_name_it_refused(self, name):
        problem = prose.validate_rule_name(name)
        assume(problem is not None)
        assert "rule id is positional" in problem or repr(name) in problem


class TestGlobTranslation:
    """Scope patterns are author-written and arrive unvalidated."""

    @given(st.text(alphabet="ab/*?.[]()+|^$\\", max_size=10))
    def test_any_pattern_compiles(self, pattern):
        """Everything that is not a wildcard goes through re.escape, so no
        pattern a person can type is a regex error.
        """
        assert prose.glob_to_regex(pattern) is not None

    @given(st.text(alphabet=PATH_CHARS, max_size=10))
    def test_a_pattern_with_no_wildcard_matches_only_itself(self, path):
        assume("*" not in path and "?" not in path)
        assert bool(prose.glob_to_regex(path).match(path))

    @given(st.text(alphabet=PATH_CHARS, max_size=8),
           st.text(alphabet=PATH_CHARS, min_size=1, max_size=8))
    def test_matching_is_anchored_at_both_ends(self, pattern, extra):
        """A pattern matches whole paths. If it matched prefixes, every rule
        scoped to `README.md` would also govern `README.md.bak`.
        """
        assume("*" not in pattern and "?" not in pattern)
        assume(not extra.startswith("*"))
        assert not prose.glob_to_regex(pattern).match(pattern + extra)


class TestClassifySignal:
    """An edit that only moved a number, a link or some whitespace is not a
    prose decision, and must not reach the model as evidence for a rule.
    """

    VALUES = (None, "numeric-only", "whitespace-only", "link-only")

    @given(st.text(max_size=20), st.text(max_size=20))
    def test_the_answer_is_always_one_of_four(self, before, after):
        assert prose.classify_signal(before, after) in self.VALUES

    @given(st.text(max_size=20))
    def test_a_line_against_itself_changed_nothing(self, line):
        assert prose.classify_signal(line, line) == "whitespace-only"

    @given(st.text(max_size=20), st.text(max_size=20))
    def test_the_answer_does_not_depend_on_which_side_is_which(self, before,
                                                               after):
        """evidence computes old-to-new; a caller comparing the other way round
        must not get a different verdict about whether this was prose.
        """
        assert prose.classify_signal(before, after) == \
            prose.classify_signal(after, before)


class TestRuleSimilarity:
    """The floor under adopt-prose's similar bucket."""

    @staticmethod
    def rule(name, body):
        made = prose.Rule("x-%s" % name, "x", name, "T", 1)
        made.body = list(body)
        return made

    BODIES = st.lists(st.text(alphabet="abcde ", max_size=20), max_size=4)

    @given(BODIES)
    def test_a_rule_is_identical_to_itself(self, body):
        same = prose.rule_similarity(self.rule("thing", body),
                                     self.rule("thing", body))
        assert same == (1.0, 1.0, 1.0)

    @given(BODIES, BODIES)
    def test_every_score_is_a_proportion(self, one, two):
        body, name, score = prose.rule_similarity(self.rule("a", one),
                                                  self.rule("b", two))
        assert 0.0 <= body <= 1.0 and 0.0 <= name <= 1.0
        assert score == max(body, name)

    def test_the_body_score_is_not_symmetric(self):
        """Pinned, not endorsed, and deliberately not written as @given.

        difflib.SequenceMatcher.ratio() is not symmetric - about one random
        rule pair in five scores differently depending on argument order. It
        matters because `config similar` loops `for a in config.rules: for b in
        other.rules`, so which project you adopt *from* changes which pairs
        clear the threshold. Asserting symmetry here would be asserting
        something false; this records the asymmetry so that making it symmetric
        is a decision somebody takes, not a surprise.
        """
        a = self.rule("a", [" eeed bbe"])
        b = self.rule("b", ["abeebde"])
        assert prose.rule_similarity(a, b)[0] != prose.rule_similarity(b, a)[0]


class TestBodyKey:
    """Two rules are the same rule when their bodies say the same thing,
    whatever the line wrapping and whatever FILL markers are outstanding.
    """

    WORDS = st.lists(st.text(alphabet="abc", min_size=1, max_size=4),
                     min_size=1, max_size=8)

    @given(WORDS, st.integers(1, 4))
    def test_rewrapping_a_body_does_not_change_its_key(self, words, width):
        flat = TestRuleSimilarity.rule("thing", [" ".join(words)])
        wrapped = TestRuleSimilarity.rule("thing", [
            " ".join(words[i:i + width]) for i in range(0, len(words), width)])
        assert flat.body_key() == wrapped.body_key()

    @given(WORDS, st.text(alphabet="abc ", max_size=10))
    def test_a_comment_does_not_change_its_key(self, words, note):
        plain = TestRuleSimilarity.rule("thing", [" ".join(words)])
        marked = TestRuleSimilarity.rule("thing", [
            " ".join(words), "<!-- FILL: %s -->" % note, ""])
        assert plain.body_key() == marked.body_key()

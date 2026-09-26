"""TagScanner reads the review markup: what is a tag, what only looks like one,
and what is malformed.

Two properties matter here. Markup inside code is not markup - a document that
discusses <del> has to survive a tagging pass. And one mistake produces one
message: a parser that says two things about a single typo teaches the author
to skim its output, which is how the malformed tags got in the first time.
"""

import pytest

import prose


def scan(src):
    return prose.TagScanner(prose.Text(src), None, "t.md")


class DescribeTagScanner:
    @pytest.mark.spec("code-markup-is-prose")
    def it_leaves_markup_inside_a_code_fence_as_prose(self, sample):
        """The sample's python fence contains a <del> that must stay prose."""
        assert scan(sample).all == []

    @pytest.mark.spec("code-markup-is-prose")
    def it_leaves_markup_inside_a_code_span_as_prose(self):
        src = (
            "A `<del>` in prose is a quotation.\n\n"
            "| `<repl>x</repl>` | note |\n|---|---|\n| a | b |\n\n"
            "<del>this one is real</del>\n"
        )
        scanner = scan(src)
        assert scanner.errors == []
        assert [n.kind for n in scanner.roots] == ["del"]

    @pytest.mark.spec("bare-pair-is-replacement")
    def it_reads_a_bare_del_ins_pair_as_one_replacement(self):
        pairs, _ = scan("<del>a</del><ins>b</ins>\n").pairs()
        assert len(pairs) == 1


class DescribeMalformedMarkup:
    """What the scanner says when the markup is wrong, and how much of it."""

    @pytest.mark.spec("markup-faults-named")
    @pytest.mark.parametrize(
        ("src", "expected"),
        [
            pytest.param("<del>unclosed\n", "never closed", id="unclosed"),
            pytest.param("</del>\n", "stray", id="stray-close"),
            pytest.param(
                "<repl><ins>new</ins><del>old</del></repl>\n",
                "before",
                id="repl-children-out-of-order",
            ),
            pytest.param("<repl><del>old</del></repl>\n", "exactly one", id="repl-missing-ins"),
            pytest.param(
                '<del bogus="x">a</del>\n', "no 'bogus' attribute", id="unknown-attribute"
            ),
            pytest.param(
                "<ins><del>no</del></ins>\n", "not allowed inside", id="del-nested-in-ins"
            ),
            pytest.param("<del why=x>a</del>\n", "need quotes", id="unquoted-attribute"),
        ],
    )
    def it_names_what_is_wrong_with_the_markup(self, src, expected):
        assert any(expected in e for e in scan(src).errors), "errors were %s" % (scan(src).errors,)

    @pytest.mark.spec("markup-faults-named")
    def it_warns_of_a_question_with_no_id_at_its_line(self):
        """A hand-written <q> is legal markup, so this is a warning, not an
        error: `tags insert` numbers every question it writes.
        """
        scanner = scan("One.\n\n<q>why?</q>\n")
        assert scanner.errors == []
        assert [w.split("  ")[0] for w in scanner.warnings] == ["t.md:3"]

    @pytest.mark.spec("markup-faults-named")
    @pytest.mark.parametrize(
        "src",
        [
            pytest.param("<del>text with no close\n", id="unclosed"),
            pytest.param("text\n</del>\n", id="stray-close"),
            pytest.param("<del>text</ins>\n", id="mismatched-close"),
            pytest.param("<del>text</de>\n", id="misspelled-close"),
            pytest.param('<del reason="x">text</del>\n', id="unknown-attribute"),
            pytest.param("<ins><del>no</del></ins>\n", id="del-nested-in-ins"),
            pytest.param("<repl><del>old</del></repl>\n", id="repl-missing-ins"),
            pytest.param(
                "<repl><ins>new</ins><del>old</del></repl>\n", id="repl-children-out-of-order"
            ),
            pytest.param('<q id="1">a</q>\n<q id="1">b</q>\n', id="duplicate-q-id"),
        ],
    )
    def it_reports_one_message_for_one_fault(self, src):
        errors = scan(src).errors
        assert len(errors) == 1, "reported %d: %s" % (len(errors), errors)

"""The property the whole plugin rests on: neutralize text the author tagged,
and the untagged text comes back byte-identical.

evidence diffs the neutralized file against the last commit, so a byte lost
here is reported as an edit the author never made, and a rule gets learned
from it. Each case names a shape of markup in the sample document.
"""

import pytest

import prose


class DescribeNeutralize:
    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    def it_returns_the_text_of_an_inline_deletion(self, round_trip):
        round_trip([{"kind": "del", "line": 8, "cols": (0, 19), "why": "restates the passage"}])

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    def it_returns_the_lines_of_a_block_deletion(self, round_trip):
        round_trip([{"kind": "del", "lines": (10, 12)}])

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    @pytest.mark.parametrize(
        ("first", "last"),
        [
            pytest.param(7, 9, id="ends-on-blank"),
            pytest.param(9, 12, id="starts-on-blank"),
            pytest.param(10, 13, id="ends-on-blank-after-list"),
        ],
    )
    def it_keeps_a_blank_line_at_the_edge_of_a_block_deletion(self, round_trip, first, last):
        """tidy_block used to strip every edge blank, which turned the author's
        own blank line into a phantom deletion on the next evidence run.
        """
        round_trip([{"kind": "del", "lines": (first, last)}])

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    def it_returns_a_last_line_that_has_no_newline(self, round_trip):
        round_trip([{"kind": "del", "lines": (23, 23)}])

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    def it_returns_the_old_text_of_a_replacement(self, round_trip):
        round_trip(
            [
                {"kind": "repl", "line": 7, "cols": (0, 7), "with": "Chosen", "alt": "plain words"},
                {"kind": "pair", "line": 11, "cols": (2, 8), "with": "2nd"},
                {"kind": "repl", "lines": (23, 23), "with": "The closing paragraph."},
            ]
        )

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    def it_drops_an_insertion_and_a_standalone_proposal(self, round_trip):
        round_trip(
            [
                {"kind": "ins", "line": 7, "col": 23, "text": " Mostly."},
                {"kind": "alt", "line": 10, "text": "List items take the same register."},
            ]
        )

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    def it_drops_a_proposal_set_apart_as_a_paragraph(self, round_trip):
        round_trip([{"kind": "alt", "line": 7, "text": "Say what earns a place.", "apart": True}])

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    @pytest.mark.parametrize(
        ("tagged", "untagged"),
        [
            pytest.param("A.\n\n<ins>B.</ins>\n\nC.\n", "A.\n\nC.\n", id="between-paragraphs"),
            pytest.param("<alt>x</alt>\n\nA.\n", "A.\n", id="first-line"),
            pytest.param("A.\n\n<alt>x</alt>\n", "A.\n", id="last-line"),
            pytest.param(
                "A.\n\n<alt>x</alt>\n\n<alt>y</alt>\n\nB.\n", "A.\n\nB.\n", id="two-in-a-row"
            ),
            pytest.param("A.\n\n\n<alt>x</alt>\nB.\n", "A.\n\n\nB.\n", id="own-two-blanks"),
        ],
    )
    def it_drops_the_blank_line_added_with_a_tag_on_its_own_line(self, tagged, untagged):
        """A tag between two paragraphs needs a blank line on each side, and
        evidence reported the one the author added as an untagged edit. A pair
        of blank lines the author wrote has no tag between them, and stays.
        """
        assert prose.neutralize(prose.Text(tagged)) == untagged

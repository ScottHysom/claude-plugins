"""The property the whole plugin rests on: neutralize text the author tagged,
and the untagged text comes back byte-identical.

evidence diffs the neutralized file against the last commit, so a byte lost
here is reported as an edit the author never made, and a rule gets learned
from it. Each case names a shape of markup in the sample document.
"""

import pytest


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

"""The property the whole plugin rests on: insert tags, then strip them, and
the file comes back byte-identical.

Everything else prose.py does is recoverable. This is not - a tagging pass that
loses a byte has rewritten the author's document, and the only evidence is a
diff nobody asked for. Each case names a span shape in the sample document.
"""
import pytest


def test_inline_del(round_trip):
    round_trip([
        {"file": "sample.md", "kind": "del", "start": 8, "col_start": 0,
         "col_end": 38, "why": "restates the passage"},
    ])


def test_block_del(round_trip):
    round_trip([{"file": "sample.md", "kind": "del", "start": 10, "end": 12}])


@pytest.mark.parametrize("start,end", [
    pytest.param(7, 9, id="ends-on-blank"),
    pytest.param(9, 12, id="starts-on-blank"),
    pytest.param(10, 13, id="ends-on-blank-after-list"),
])
def test_block_del_with_a_blank_line_at_an_edge(round_trip, start, end):
    """tidy_block used to strip every edge blank, which turned the author's
    own blank line into a phantom deletion on the next evidence run.
    """
    round_trip([
        {"file": "sample.md", "kind": "del", "start": start, "end": end},
    ])


def test_inline_repl(round_trip):
    """Named line 6 with columns 2-9 until the property tests went in.

    Line 6 is blank, so those columns were outside it, and Text.offset added
    them blind: the record silently edited "urated," on line 7 instead. It
    round-tripped, so nothing noticed for as long as the case existed. It now
    names the line it always meant.
    """
    round_trip([
        {"file": "sample.md", "kind": "repl", "start": 7, "col_start": 1,
         "col_end": 8, "with": "urated,"},
    ])


def test_a_batch_of_mixed_kinds(round_trip):
    """Inserts are planned together and applied back to front. A batch is
    where offsets computed against the original text go stale.
    """
    round_trip([
        {"file": "sample.md", "kind": "del", "start": 7, "col_start": 0,
         "col_end": 13, "why": "opens with the count"},
        {"file": "sample.md", "kind": "q", "start": 10,
         "text": "Do list items take the same register?"},
        {"file": "sample.md", "kind": "repl", "start": 23, "col_start": 0,
         "col_end": 16, "with": "The closing paragraph."},
    ])

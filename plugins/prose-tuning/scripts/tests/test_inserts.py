"""Spans that cannot be tagged safely are refused rather than mangled.

A tag opened inside a code fence or across a table row does not survive a
round trip, so the planner turns those down at plan time with a reason the
author can act on.
"""
import pytest

import prose


@pytest.mark.parametrize("record,reason", [
    pytest.param({"kind": "del", "start": 5}, "heading", id="heading"),
    pytest.param({"kind": "del", "start": 19}, "fence", id="inside-a-fence"),
    pytest.param({"kind": "del", "start": 14}, "table", id="table-row"),
    pytest.param({"kind": "del", "start": 7, "col_start": 5, "end": 8,
                  "col_end": 3}, "straddles", id="straddles-two-lines"),
])
def test_unsafe_spans_are_refused(sample, record, reason):
    text = prose.Text(sample)
    blocks = prose.Blocks(text)
    with pytest.raises(prose.InsertRefusal) as caught:
        prose.plan_one_insert(text, blocks, record, "sample.md", 1)
    assert reason in str(caught.value)


def test_segments_skip_protected_regions(sample):
    """Front matter and code are not prose. Offering them for review invites
    a rewrite of a config key or a variable name.
    """
    text = prose.Text(sample)
    segments = prose.segments_for(text, prose.Blocks(text))
    bodies = [s["text"] for s in segments]
    assert not any("x = 1" in b for b in bodies)
    assert not any("title: sample" in b for b in bodies)


def test_segments_include_table_cells_and_headings(sample):
    text = prose.Text(sample)
    kinds = {s["kind"] for s in prose.segments_for(text, prose.Blocks(text))}
    assert "table-cell" in kinds
    assert "heading" in kinds

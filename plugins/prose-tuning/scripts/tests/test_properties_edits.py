"""EditEngine is where a batch of rewrites becomes one new file.

Two things about it are load-bearing and non-obvious. It applies edits
bottom-up
from a single snapshot, because any other order leaves later edits pointing at
offsets that have already moved. And conflicts() decides overlap by comparing
only *adjacent* pairs after a sort - which is sound and complete, but only
because replace() refuses start > end. A future change to that sort key would
break the overlap check silently, with no example test noticing.

The domain here is a string and a list of spans, so there is nothing to
generate but integers. That makes this the cheapest property in the suite and
the one guarding the most subtle code.
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

import prose

TEXT = st.text(alphabet="abcdefgh \n", min_size=1, max_size=60)


@st.composite
def spans(draw, source, max_edits=5):
    """Any list of (start, end, replacement) that replace() will accept."""
    out = []
    for _ in range(draw(st.integers(0, max_edits))):
        a = draw(st.integers(0, len(source)))
        b = draw(st.integers(a, len(source)))
        out.append((a, b, draw(st.text(alphabet="XYZ", max_size=4))))
    return out


def conflicting(edits):
    """The definition conflicts() has to agree with, computed the slow obvious
    way: every pair, no sort, no adjacency argument.

    Two edits interact if their half-open ranges overlap, or if they begin at
    the same offset - where which one lands first decides the answer.
    """
    for i, (a0, a1, _) in enumerate(edits):
        for b0, b1, _ in edits[i + 1 :]:
            if a0 < b1 and b0 < a1:
                return True
            if a0 == b0:
                return True
    return False


def engine_with(source, edits):
    engine = prose.EditEngine(prose.Text(source))
    for start, end, replacement in edits:
        engine.replace(start, end, replacement)
    return engine


@given(source=TEXT, data=st.data())
def test_the_adjacent_pair_scan_finds_every_overlap(source, data):
    """conflicts() checks neighbours; the definition is pairwise."""
    edits = data.draw(spans(source))
    assert bool(engine_with(source, edits).conflicts()) is conflicting(edits)


@given(source=TEXT, data=st.data())
def test_conflicts_and_result_agree(source, data):
    """A reported conflict is exactly the case result() refuses to apply."""
    edits = data.draw(spans(source))
    engine = engine_with(source, edits)
    if engine.conflicts():
        try:
            engine.result()
        except prose.Fatal:
            return
        raise AssertionError("result() applied a conflicting batch")
    engine.result()


@given(source=TEXT, data=st.data())
def test_the_result_grows_by_exactly_what_was_spliced(source, data):
    edits = data.draw(spans(source))
    assume(not conflicting(edits))
    grown = sum(len(r) - (end - start) for start, end, r in edits)
    assert len(engine_with(source, edits).result()) == len(source) + grown


@given(source=TEXT, data=st.data())
def test_the_result_is_the_source_with_each_span_replaced(source, data):
    """A full specification, not a sampled fact: build the expected string the
    obvious left-to-right way and demand the engine match it exactly.

    This is what "bottom-up from one snapshot" is supposed to be equivalent to.
    Stating the equivalence is the point - the bottom-up pass is an
    optimisation of this, and the two only agree while the offsets are all
    read from the same snapshot.
    """
    edits = data.draw(spans(source))
    assume(not conflicting(edits))
    assume(len({e[0] for e in edits}) == len(edits))
    expected, cursor = "", 0
    for start, end, replacement in sorted(edits, key=lambda e: e[0]):
        expected += source[cursor:start] + replacement
        cursor = end
    assert engine_with(source, edits).result() == expected + source[cursor:]


@given(source=TEXT, data=st.data())
def test_the_result_does_not_depend_on_insertion_order(source, data):
    """A batch is a set, not a sequence. The caller collects records in
    whatever order it found them.
    """
    edits = data.draw(spans(source))
    assume(not conflicting(edits))
    # Coincident zero-width inserts are the one exception, pinned below.
    assume(len({e[0] for e in edits}) == len(edits))
    assert (
        engine_with(source, edits).result() == engine_with(source, list(reversed(edits))).result()
    )


def test_two_inserts_at_one_point_are_a_conflict():
    """Two edits at one offset have no right answer, so there is no answer.

    result()'s reverse sort is stable, so it would emit them in the order
    opposite to the one they were added in - which is a coin flip dressed up as
    a rule. Refusing is what lets the round-trip property hold.
    """
    engine = prose.EditEngine(prose.Text("0123456789"))
    engine.replace(5, 5, "<A>")
    engine.replace(5, 5, "<B>")
    assert engine.conflicts()
    with pytest.raises(prose.Fatal):
        engine.result()


def test_edits_that_merely_touch_are_not_a_conflict():
    """The boundary the clause above must not swallow: one span ending exactly
    where the next begins is two disjoint edits, and they compose.
    """
    engine = prose.EditEngine(prose.Text("0123456789"))
    engine.replace(0, 5, "<A>")
    engine.replace(5, 10, "<B>")
    assert engine.conflicts() == []
    assert engine.result() == "<A><B>"

"""The property the whole plugin rests on, stated for every record shape rather
than for the seven somebody wrote down.

README.md puts it plainly: for any batch, insert then strip returns the file
byte-identical. That is a claim about all inputs, and test_round_trip.py checks
it against seven. The gap between those two is where four separate guard bugs
lived - a <q> accepted inside a code fence, unchecked columns that wrapped a
closing tag around the whole document, zero-width spans emitting </del><del>,
and block tags that ate a blank line. Of the records the planner accepted,
roughly a third broke the round trip.

The key move is generating the *records* against a fixed document rather than
generating markdown. plan_one_insert's contract is about records; SAMPLE is
already the document with one of everything in it.

The property is a disjunction on purpose: refuse, or round-trip. Refusing is a
correct outcome - most of prose.py's safety is refusal - so the test says
nothing about which records ought to be refused. test_inserts.py does that.
"""
from hypothesis import HealthCheck, assume, event, example, given, settings
from hypothesis import strategies as st

import prose

from conftest import SAMPLE

LINES = prose.Text(SAMPLE).line_count()

# The lines the rules govern: prose, not structure. Computed rather than listed
# so that editing SAMPLE cannot leave a stale line number behind.
_BLOCKS = prose.Blocks(prose.Text(SAMPLE))
PROSE_LINES = [n for n in range(1, LINES + 1)
               if _BLOCKS.kind(n) in ("paragraph", "list-item")]

# The unbroken stretches within that: a multi-line span has to stay inside one,
# or it crosses something the planner will refuse it for.
_RUNS = []
for _n in PROSE_LINES:
    if _RUNS and _RUNS[-1][-1] == _n - 1:
        _RUNS[-1].append(_n)
    else:
        _RUNS.append([_n])
RUN_OF = {_n: _run for _run in _RUNS for _n in _run}
WORDS = st.text(alphabet="abc ", min_size=1, max_size=8)


@st.composite
def records(draw, max_records=3):
    """Insert records shaped the way a skill emits them, plus the shapes a
    skill emits when it has miscounted - out-of-range columns, inverted spans,
    zero-width points. Those are the ones that found the bugs.
    """
    out = []
    for _ in range(draw(st.integers(1, max_records))):
        kind = draw(st.sampled_from(prose.INSERTABLE))
        # Weighted towards lines and columns that are actually in range. An
        # unweighted draw spends most of its budget on records the planner
        # turns down at the first guard, which proves only that refusing works
        # - the interesting failures were pairs of records that both got past
        # the guards and then interfered with each other.
        start = draw(st.one_of(st.sampled_from(PROSE_LINES),
                               st.integers(1, LINES)))
        width = len(prose.Text(SAMPLE).bare(start))
        rec = {"file": "sample.md", "kind": kind, "start": start}
        if kind in ("q", "alt"):
            rec["text"] = draw(WORDS)
        else:
            if draw(st.booleans()):
                rec["end"] = draw(st.integers(start, min(LINES, start + 3)))
            else:
                rec["col_start"] = draw(st.one_of(
                    st.integers(0, max(width, 1)), st.integers(-2, 90)))
                rec["col_end"] = draw(st.one_of(
                    st.integers(0, max(width, 1)), st.integers(-2, 90)))
            if kind == "repl":
                rec["with"] = draw(WORDS)
            if kind == "ins":
                rec["text"] = draw(WORDS)
            if draw(st.booleans()):
                rec["why"] = draw(WORDS)
        out.append(rec)
    return out


def insert_then_strip(batch):
    """Run the real pipeline. Returns the outcome as a word, for event()."""
    text = prose.Text(SAMPLE)
    blocks = prose.Blocks(text)
    engine, refusals, _ = prose.apply_inserts(
        text, blocks, batch, "sample.md", 1)
    if refusals:
        return "refused", None
    try:
        tagged = prose.Text(engine.result())
    except prose.Fatal:
        return "refused", None       # the engine turned the batch down
    scanner = prose.TagScanner(tagged, None, "sample.md")
    assert not scanner.errors, \
        "accepted a batch whose own output does not parse: %s" % scanner.errors
    back, _ = prose.resolve_text(tagged, prose.REJECT, None, "sample.md")
    return "round-tripped", back


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(records())
@example([{"file": "sample.md", "kind": "q", "start": 19, "text": "why?"}])
@example([{"file": "sample.md", "kind": "del", "start": 7,
           "col_start": 0, "col_end": 900}])
@example([{"file": "sample.md", "kind": "del", "start": 7,
           "col_start": 5, "col_end": 5}])
@example([{"file": "sample.md", "kind": "del", "start": 9, "end": 9}])
@example([{"file": "sample.md", "kind": "del", "start": 23, "end": 23}])
@example([{"file": "sample.md", "kind": "del", "start": 22, "end": 23}])
@example([{"file": "sample.md", "kind": "repl", "start": 22, "end": 23,
           "with": "New ending."}])
@example([{"file": "sample.md", "kind": "q", "start": 10, "text": "why?"},
          {"file": "sample.md", "kind": "del", "start": 10, "end": 12}])
def test_insert_then_strip_is_the_identity(batch):
    """Either the planner refuses the batch, or stripping gives the file back.

    The six pinned examples are the bugs this found, smallest first: a <q>
    inside a fence, a column past the end of its line, a zero-width span, a
    block tag over a lone blank line, a block tag on the unterminated final
    line - inline and block form both, because they reach it through different
    code - and two records whose edits land on the same offset.
    """
    outcome, back = insert_then_strip(batch)
    event(outcome)
    if outcome == "round-tripped":
        assert back == SAMPLE


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(records())
def test_a_refusal_names_a_reason(batch):
    """A refusal is only a good outcome if the author can act on it."""
    text = prose.Text(SAMPLE)
    _, refusals, _ = prose.apply_inserts(
        text, prose.Blocks(text), batch, "sample.md", 1)
    for refusal in refusals:
        assert refusal.strip()
        assert "sample.md" in refusal


@st.composite
def well_formed(draw):
    """Records a skill emits when it has counted correctly: a real span, on a
    line the rules actually govern, with columns inside that line.
    """
    line = draw(st.sampled_from(PROSE_LINES))
    kind = draw(st.sampled_from(prose.INSERTABLE))
    rec = {"file": "sample.md", "kind": kind, "start": line}
    if kind in ("q", "alt"):
        rec["text"] = draw(WORDS)
        return rec
    width = len(prose.Text(SAMPLE).bare(line))
    if kind == "ins":
        rec["col_start"] = rec["col_end"] = draw(st.integers(0, width))
        rec["text"] = draw(WORDS)
        return rec
    if draw(st.booleans()):
        # Within one unbroken stretch of prose. Drawing an end line and then
        # filtering threw away a quarter of every run, which is budget spent
        # generating nothing.
        run = [n for n in RUN_OF[line] if n >= line]
        rec["end"] = draw(st.sampled_from(run))
    else:
        rec["col_start"] = draw(st.integers(0, width - 1))
        rec["col_end"] = draw(st.integers(rec["col_start"] + 1, width))
    if kind == "repl":
        rec["with"] = draw(WORDS)
    return rec


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(well_formed())
def test_a_well_formed_record_is_accepted_and_round_trips(record):
    """The other half of the property above, and the guard against it going
    vacuous.

    "Refuse or round-trip" is satisfied by a planner that refuses everything.
    Four new refusals went in with these tests; this is what says they did not
    reach past the malformed records they were aimed at.
    """
    text = prose.Text(SAMPLE)
    _, refusals, _ = prose.apply_inserts(
        text, prose.Blocks(text), [record], "sample.md", 1)
    assert not refusals, refusals[0]
    outcome, back = insert_then_strip([record])
    assert outcome == "round-tripped"
    assert back == SAMPLE


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(well_formed(), min_size=2, max_size=3))
@example([{"file": "sample.md", "kind": "q", "start": 10, "text": "a"},
          {"file": "sample.md", "kind": "del", "start": 10, "end": 12}])
@example([{"file": "sample.md", "kind": "del", "start": 7,
           "col_start": 0, "col_end": 7},
          {"file": "sample.md", "kind": "del", "start": 7,
           "col_start": 7, "col_end": 12}])
def test_a_batch_of_well_formed_records_refuses_or_round_trips(batch):
    """Records that are each fine, together.

    This is where the last two bugs were, and neither is reachable one record
    at a time: a <q> on the first line of a block <del> shares an offset with
    it, and two neighbouring inline <del> spans put one's closing tag on the
    other's opening offset. Both produced a different file depending on the
    order the records arrived in, and one of the orders did not parse.

    The adversarial generator above mostly gets turned down at the first guard,
    which says nothing about what happens after two records are both accepted.
    This batch is well-formed by construction, so it gets there.
    """
    outcome, back = insert_then_strip(batch)
    event("batch: %s" % outcome)
    if outcome == "round-tripped":
        assert back == SAMPLE

"""The property the whole plugin rests on, stated for every record shape rather
than for the ones somebody wrote down.

README.md puts it plainly: for any batch, insert then strip returns the file
byte-identical. That is a claim about all inputs, and test_round_trip.py checks
it against a handful. The gap between the two is where the planner's guard bugs
lived - records it accepted and then mangled, none of them among the examples.
test_inserts.py names each one this has found.

The key move is generating the *records* against a fixed document rather than
generating markdown. plan_one_insert's contract is about records; SAMPLE is
already the document with one of everything in it.

The property is a disjunction on purpose: refuse, or round-trip. Refusing is a
correct outcome - most of prose.py's safety is refusal - so the test says
nothing about which records ought to be refused. test_inserts.py does that.
"""

import pytest
from hypothesis import HealthCheck, event, example, given, settings
from hypothesis import strategies as st

import prose
from prose_samples import SAMPLE

LINES = prose.Text(SAMPLE).line_count()

# The lines the rules govern: prose, not structure. Computed rather than listed
# so that editing SAMPLE cannot leave a stale line number behind.
_BLOCKS = prose.Blocks(prose.Text(SAMPLE))
PROSE_LINES = [n for n in range(1, LINES + 1) if _BLOCKS.kind(n) in ("paragraph", "list-item")]

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
_TEXT = prose.Text(SAMPLE)


def starts_at(text, line):
    """The columns on line where text starts, as the planner looks for it."""
    base = _TEXT.offset(line)
    width = len(_TEXT.bare(line))
    return [c for c in range(width + 1) if SAMPLE.startswith(text, base + c)]


@st.composite
def passages(draw, line, wrap=True):
    """Text copied from the file at line: a slice of it, or, within a run of
    prose and when wrap allows, its lines whole from the first word, as a
    skill copies them.
    """
    bare = _TEXT.bare(line)
    run = [n for n in RUN_OF.get(line, [line]) if n >= line]
    if wrap and len(run) > 1 and draw(st.booleans()):
        end = draw(st.sampled_from(run[1:]))
        a = _TEXT.offset(line) + len(bare) - len(bare.lstrip())
        return SAMPLE[a : _TEXT.offset(end) + len(_TEXT.bare(end))]
    if not bare:
        return ""
    a = draw(st.integers(0, len(bare) - 1))
    return bare[a : draw(st.integers(a + 1, len(bare)))]


@st.composite
def records(draw, max_records=3):
    """Insert records shaped the way a skill emits them, plus the shapes a
    skill emits when it has miscounted - out-of-range columns, inverted spans,
    zero-width points. Those are the ones that found the bugs.
    """
    out = []
    for _ in range(draw(st.integers(1, max_records))):
        kind = draw(st.sampled_from(prose.INSERTABLE))
        # Weighted toward lines and columns that are actually in range. An
        # unweighted draw spends most of its budget on records the planner
        # turns down at the first guard, which proves only that refusing works
        # - the interesting failures were pairs of records that both got past
        # the guards and then interfered with each other.
        start = draw(st.one_of(st.sampled_from(PROSE_LINES), st.integers(1, LINES)))
        width = len(prose.Text(SAMPLE).bare(start))
        rec = {"file": "sample.md", "kind": kind, "start": start}
        if kind in ("q", "alt"):
            rec["text"] = draw(WORDS)
        else:
            shape = draw(st.sampled_from(("lines", "columns", "text")))
            if shape == "lines":
                rec["end"] = draw(st.integers(start, min(LINES, start + 3)))
            elif shape == "columns":
                rec["col_start"] = draw(
                    st.one_of(st.integers(0, max(width, 1)), st.integers(-2, 90))
                )
                rec["col_end"] = draw(st.one_of(st.integers(0, max(width, 1)), st.integers(-2, 90)))
            else:
                # Copied from the file, from some other line, or made up, and
                # sometimes with a col_start that may or may not be one of its
                # matches.
                other = draw(st.sampled_from(PROSE_LINES))
                anchor = draw(st.one_of(passages(start), passages(other), WORDS))
                rec["after" if kind == "ins" else "text"] = anchor
                if draw(st.booleans()):
                    rec["col_start"] = draw(st.integers(-2, max(width, 1)))
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
    engine, refusals, _ = prose.apply_inserts(text, blocks, batch, "sample.md", 1)
    if refusals:
        return "refused", None
    try:
        tagged = prose.Text(engine.result())
    except prose.Fatal:
        return "refused", None  # the engine turned the batch down
    scanner = prose.TagScanner(tagged, None, "sample.md")
    assert not scanner.errors, (
        "accepted a batch whose own output does not parse: %s" % scanner.errors
    )
    back, _ = prose.resolve_text(tagged, prose.REJECT, None, "sample.md")
    return "round-tripped", back


class DescribeGeneratedRecords:
    """Records shaped the way a skill emits them, miscounts included."""

    @pytest.mark.spec("insert-strip-round-trip")
    @settings(suppress_health_check=[HealthCheck.too_slow])
    @given(records())
    @example([{"file": "sample.md", "kind": "q", "start": 19, "text": "why?"}])
    @example([{"file": "sample.md", "kind": "del", "start": 7, "col_start": 0, "col_end": 900}])
    @example([{"file": "sample.md", "kind": "del", "start": 7, "col_start": 5, "col_end": 5}])
    @example([{"file": "sample.md", "kind": "del", "start": 9, "end": 9}])
    @example([{"file": "sample.md", "kind": "del", "start": 23, "end": 23}])
    @example([{"file": "sample.md", "kind": "del", "start": 22, "end": 23}])
    @example([{"file": "sample.md", "kind": "repl", "start": 22, "end": 23, "with": "New ending."}])
    @example(
        [
            {"file": "sample.md", "kind": "q", "start": 10, "text": "why?"},
            {"file": "sample.md", "kind": "del", "start": 10, "end": 12},
        ]
    )
    def it_returns_the_original_bytes_or_refuses_the_batch(self, batch):
        """Either the planner refuses the batch, or stripping gives the file back.

        Each @example above is a batch this property once failed on, pinned so it
        is checked on every run rather than only when the seed happens to find it.
        The matching test in test_inserts.py says what was wrong with it.
        """
        outcome, back = insert_then_strip(batch)
        event(outcome)
        if outcome == "round-tripped":
            assert back == SAMPLE

    @pytest.mark.spec("repo:answers-checked")
    @settings(suppress_health_check=[HealthCheck.too_slow])
    @given(records())
    def it_names_a_reason_for_every_refusal(self, batch):
        """A refusal is only a good outcome if the author can act on it."""
        text = prose.Text(SAMPLE)
        _, refusals, _ = prose.apply_inserts(text, prose.Blocks(text), batch, "sample.md", 1)
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
        rec["text"] = draw(WORDS)
        if draw(st.booleans()):
            rec["after"] = draw(passages(line, wrap=False))
            found = starts_at(rec["after"], line)
            if len(found) > 1:
                rec["col_start"] = draw(st.sampled_from(found))
        else:
            rec["col_start"] = rec["col_end"] = draw(st.integers(0, width))
        return rec
    shape = draw(st.sampled_from(("lines", "columns", "text")))
    if shape == "text":
        # The text a skill copies, and the col_start the refusal would ask
        # for when it starts at more than one place on the line.
        anchor = draw(passages(line))
        rec["text"] = anchor
        found = starts_at(anchor, line)
        if len(found) > 1:
            rec["col_start"] = draw(st.sampled_from(found))
    elif shape == "lines":
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


class DescribeWellFormedRecords:
    @pytest.mark.spec("insert-strip-round-trip")
    @settings(suppress_health_check=[HealthCheck.too_slow])
    @given(well_formed())
    def it_accepts_a_well_formed_record_and_returns_the_original_bytes(self, record):
        """The other half of the property above, and the guard against it going
        vacuous.

        "Refuse or round-trip" is satisfied by a planner that refuses everything.
        Every refusal added to make the property pass is a way to over-correct;
        this is what says none of them reached past the malformed records it was
        aimed at.
        """
        text = prose.Text(SAMPLE)
        _, refusals, _ = prose.apply_inserts(text, prose.Blocks(text), [record], "sample.md", 1)
        assert not refusals, refusals[0]
        outcome, back = insert_then_strip([record])
        assert outcome == "round-tripped"
        assert back == SAMPLE

    @pytest.mark.spec("insert-strip-round-trip")
    @settings(suppress_health_check=[HealthCheck.too_slow])
    @given(st.lists(well_formed(), min_size=2, max_size=3))
    @example(
        [
            {"file": "sample.md", "kind": "q", "start": 10, "text": "a"},
            {"file": "sample.md", "kind": "del", "start": 10, "end": 12},
        ]
    )
    @example(
        [
            {"file": "sample.md", "kind": "del", "start": 7, "col_start": 0, "col_end": 7},
            {"file": "sample.md", "kind": "del", "start": 7, "col_start": 7, "col_end": 12},
        ]
    )
    def it_returns_the_original_bytes_or_refuses_a_batch_of_them(self, batch):
        """Records that are each fine, together.

        Some failures are not reachable one record at a time. A <q> on the first
        line of a block <del> shares an offset with it; two neighboring inline
        <del> spans put one's closing tag on the other's opening offset; an <ins>
        inside another record's <del> is a grammar the scanner rejects. Each record
        passes every guard on its own, and the batch is still wrong.

        The adversarial generator above mostly gets turned down at the first guard,
        which says nothing about what happens after two records are both accepted.
        This batch is well-formed by construction, so it gets there.
        """
        outcome, back = insert_then_strip(batch)
        event("batch: %s" % outcome)
        if outcome == "round-tripped":
            assert back == SAMPLE

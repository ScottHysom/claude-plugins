"""The property the whole plugin rests on, stated for every shape of markup an
author writes rather than for the ones somebody wrote down.

Neutralizing author-tagged text returns the untagged text, byte for byte.
evidence diffs that neutralized text against the last commit, so a byte it
loses or invents becomes an edit the author never made. test_round_trip.py
checks the claim against a handful of shapes, and this checks it against every
set of marks hypothesis can build.

The key move is generating the *marks* against a fixed document rather than
generating markdown. SAMPLE is already the document with one of everything in
it, and prose_samples.tagged writes each mark in the form an author writes it.
"""

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

import prose
from prose_samples import SAMPLE, tagged

_TEXT = prose.Text(SAMPLE)
LINES = _TEXT.line_count()

# The lines the rules govern: prose, not structure. Computed rather than listed
# so that editing SAMPLE cannot leave a stale line number behind.
_BLOCKS = prose.Blocks(_TEXT)
PROSE_LINES = [n for n in range(1, LINES + 1) if _BLOCKS.kind(n) in ("paragraph", "list-item")]

# The unbroken stretches within that, which a block-form mark stays inside.
_RUNS = []
for _n in PROSE_LINES:
    if _RUNS and _RUNS[-1][-1] == _n - 1:
        _RUNS[-1].append(_n)
    else:
        _RUNS.append([_n])
RUN_OF = {_n: _run for _run in _RUNS for _n in _run}
WORDS = st.text(alphabet="abc ", min_size=1, max_size=8)
KINDS = ("del", "repl", "pair", "ins", "alt", "block-del", "block-repl")


@st.composite
def mark(draw, line, below):
    """One mark starting on line, ending above the line below."""
    kind = draw(st.sampled_from(KINDS))
    width = len(_TEXT.bare(line))
    rec = {"kind": kind, "line": line}
    if kind == "alt":
        rec["text"] = draw(WORDS)
        return rec
    if kind.startswith("block-"):
        rec["kind"] = kind[len("block-") :]
        run = [n for n in RUN_OF[line] if line <= n < below]
        rec["lines"] = (line, draw(st.sampled_from(run)))
        del rec["line"]
    elif kind == "ins":
        rec["col"] = draw(st.integers(0, width))
        rec["text"] = draw(WORDS)
    else:
        start = draw(st.integers(0, width - 1))
        rec["cols"] = (start, draw(st.integers(start + 1, width)))
        if draw(st.booleans()):
            rec["alt"] = draw(WORDS)
    if rec["kind"] in ("repl", "pair"):
        rec["with"] = draw(WORDS)
    if rec["kind"] != "pair" and draw(st.booleans()):
        rec["why"] = draw(WORDS)
    return rec


@st.composite
def marks(draw):
    """One to three marks on lines apart from one another."""
    lines = sorted(draw(st.sets(st.sampled_from(PROSE_LINES), min_size=1, max_size=3)))
    return [draw(mark(line, below)) for line, below in zip(lines, [*lines[1:], LINES + 1])]


class DescribeAuthorMarkup:
    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    @settings(suppress_health_check=[HealthCheck.too_slow])
    @given(marks())
    @example([{"kind": "del", "line": 12, "cols": (0, 7)}])
    @example([{"kind": "repl", "lines": (23, 23), "with": "a"}])
    @example([{"kind": "alt", "line": 10, "text": "a"}, {"kind": "del", "lines": (11, 12)}])
    def it_neutralizes_to_the_untagged_text(self, batch):
        """Each @example is a shape that sits on an edge: a tag wrapping a
        whole line, so it reads as block form, the last line with no newline,
        and a proposal directly above a block in a list.
        """
        text = prose.Text(tagged(SAMPLE, batch))
        scanner = prose.TagScanner(text, None, "sample.md")
        assert not scanner.errors, scanner.errors
        assert prose.neutralize(text, None, "sample.md") == SAMPLE

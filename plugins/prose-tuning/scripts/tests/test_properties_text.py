"""Text is the coordinate system every rewrite is expressed in.

A span is a line and a column, and the file that gets written is the one Text
reassembled. So two things have to hold for any text at all, not just for text
somebody thought to write down: the bytes survive the trip, and the two ways of
naming a position agree with each other.

"For any text at all" is the part examples cannot say. test_text.py asserts the
byte property over seven strings a person chose; this asserts it over whatever
hypothesis can build, which is how the line-splitting divergence below was
found.
"""
import pytest
from hypothesis import assume, example, given
from hypothesis import strategies as st

import prose

# Everything str.splitlines() treats as a line break but a markdown file,
# git and every editor do not. Before the fix, a document containing one of
# these made Text count more lines than the author's editor showed, and every
# line number reported after it was wrong.
EXOTIC_BREAKS = "\v\f\x1c\x1d\x1e\x85  "


@given(st.text())
@example("")
@example("a")
@example("a\n")
@example("a\r\nb")
@example("trailing blank\n\n")
@example("a\fb")
def test_lines_rejoin_to_the_original(source):
    assert "".join(prose.Text(source).lines) == source


@given(st.text())
@example("a\fb")
@example("a b")
@example("a\x85b")
def test_only_newlines_start_a_new_line(source):
    """A line break is \\n, and nothing else.

    Text used to cut on str.splitlines(), which breaks on eight more
    characters. A .md file containing a form feed made prose.py count 7 lines
    where git counted 6, so a report saying landscape.md:42 sent the author to
    the wrong passage - which is the whole reason the line number is in the
    report.
    """
    assert prose.Text(source).line_count() == source.count("\n") + \
        (1 if source and not source.endswith("\n") else 0)


@given(st.text())
def test_a_line_is_its_own_bytes(source):
    """line(n) is a slice of the original at offset(n), every time."""
    text = prose.Text(source)
    for n in range(1, text.line_count() + 1):
        start = text.offset(n)
        assert text.s[start:start + len(text.line(n))] == text.line(n)


@given(st.text())
def test_lines_are_contiguous(source):
    """Each line begins where the one before it ended - no gap, no overlap."""
    text = prose.Text(source)
    for n in range(1, text.line_count()):
        assert text.offset(n) + len(text.line(n)) == text.offset(n + 1)


@given(st.text())
@example("a\r\nb")
def test_line_of_inverts_offset(source):
    """The two ways of naming a position agree, for every position."""
    text = prose.Text(source)
    for n in range(1, text.line_count() + 1):
        for col in range(len(text.bare(n)) + 1):
            assert text.line_of(text.offset(n, col)) == n


@given(st.text())
def test_bare_is_the_line_without_its_ending(source):
    text = prose.Text(source)
    for n in range(1, text.line_count() + 1):
        raw, bare = text.line(n), text.bare(n)
        assert raw.startswith(bare)
        assert raw[len(bare):] in ("", "\n", "\r\n")


@given(st.text(alphabet=EXOTIC_BREAKS, min_size=1))
def test_an_exotic_separator_is_ordinary_text(source):
    """One line, however many form feeds are on it."""
    assume("\n" not in source)
    text = prose.Text(source)
    assert text.line_count() == 1
    assert text.bare(1) == source


def test_an_empty_file_has_no_lines():
    """The one asymmetry worth pinning: line_of answers for offset 0 even
    though there is no line 1 for offset() to find.
    """
    text = prose.Text("")
    assert text.line_count() == 0
    assert text.line_of(0) == 1
    with pytest.raises(prose.Fatal):
        text.offset(1)

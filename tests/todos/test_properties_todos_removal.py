"""Removing every TODO from a file whose only changes were TODOs, with blank
lines around them, gives back its last commit byte for byte.

The examples in test_todos_removal.py run `file` itself; this drives the same
Pending and Removal that `file` uses, without git, so that each example is
cheap enough for Hypothesis to try many.
"""

import os

import pytest
from hypothesis import event, example, given, settings
from hypothesis import strategies as st

import todos

ENDINGS = (b"\n", b"\r\n")

# Committed lines. None of them is or holds a TODO.
BASE_LINES = (b"alpha", b"  beta = 2", b"# gamma", b"", b"<p>delta</p>", b"- item", b"   ")


def todo_form(n):
    """Every form scan reads, as (name, lines), numbered so no two match."""
    return [
        ("line", [b"# TODO: t%d" % n]),
        ("line with detail", [b"# TODO(bug): t%d" % n, b"# why %d" % n, b"# and %d" % n]),
        ("indented line", [b"    // TODO(fix): t%d" % n, b"    // detail %d" % n]),
        ("title only", [b"TODO: t%d" % n]),
        ("list item", [b"- TODO(docs): t%d" % n]),
        ("one-line block", [b"<!-- TODO(prose): t%d -->" % n]),
        ("one-line c block", [b"/* TODO(change): t%d */" % n]),
        ("block", [b"<!-- TODO(design): t%d" % n, b"more %d" % n, b"-->"]),
        ("c block", [b"/* TODO: t%d" % n, b" * more %d" % n, b" */"]),
    ]


FORMS = len(todo_form(0))

blanks = st.lists(st.sampled_from([b"", b"  "]), max_size=2)


@st.composite
def todo_only_files(draw):
    """(base, now, how many TODOs): a committed file, and the same file
    with TODOs and blank lines added."""
    base_lines = draw(st.lists(st.sampled_from(BASE_LINES), max_size=6))
    ending = draw(st.sampled_from(ENDINGS))
    final = draw(st.booleans())
    bom = draw(st.booleans())
    count = draw(st.integers(min_value=1, max_value=4))
    inserts = {}
    for n in range(count):
        at = draw(st.integers(min_value=0, max_value=len(base_lines)))
        name, lines = todo_form(n)[draw(st.integers(min_value=0, max_value=FORMS - 1))]
        event(name)
        inserts.setdefault(at, []).append(draw(blanks) + lines + draw(blanks))
    now_lines = []
    for i in range(len(base_lines) + 1):
        for block in inserts.get(i, []):
            now_lines.extend(block)
        if i < len(base_lines):
            now_lines.append(base_lines[i])

    def render(lines):
        out = b"".join(line + ending for line in lines)
        if not final and out:
            out = out[: -len(ending)]
        return (todos.BOM if bom else b"") + out

    event("bom" if bom else "no bom")
    event("final newline" if final else "no final newline")
    return render(base_lines), render(now_lines), count


def remove_all(base, now):
    """The file once every TODO scan finds is removed, bottom up, and how
    many it found."""
    pending = todos.Pending("notes.txt", now, base)
    found = pending.found.todos
    removal = todos.Removal(os.devnull, pending)
    for todo in sorted(found, key=lambda t: -t["first"]):
        removal.remove(todo["first"], todo["last"])
    return removal.content(), len(found)


def longest_common(a, b):
    """The length of a longest common subsequence, the slow and plain way."""
    table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            if a[i] == b[j]:
                table[i][j] = table[i + 1][j + 1] + 1
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])
    return table[0][0]


lines = st.lists(st.sampled_from([b"a", b"b", b""]), max_size=10)


@pytest.mark.spec("scan-cmd-reads-pending-lines")
class DescribeComparingWithTheLastCommit:
    @given(lines, lines)
    @example([b"b", b"b", b"b"], [b"b", b"t", b"", b"b", b"b"])
    def it_keeps_as_many_lines_as_any_comparison_could(self, base, now):
        kept = todos.kept_lines(base, now)
        assert all(base[i] == now[j] for i, j in kept)
        assert all(x[0] < y[0] and x[1] < y[1] for x, y in zip(kept, kept[1:]))
        assert len(kept) == longest_common(base, now)

    def it_never_reads_a_repeated_committed_line_as_added(self):
        added, base_of = todos.compare([b"b", b"b", b"b"], [b"b", b"t", b"", b"b", b"b"])
        assert added == {1, 2}
        assert base_of == {0: 1, 3: 2, 4: 3}

    def it_hands_a_file_with_many_edits_to_difflib(self, monkeypatch):
        monkeypatch.setattr(todos, "MAX_EDITS", 1)
        added, base_of = todos.compare([b"a", b"b", b"c"], [b"x", b"a", b"y", b"c", b"z"])
        assert added == {0, 2, 4}
        assert base_of == {1: 1, 3: 3}


@pytest.mark.spec("file-cmd-restores-todo-only-files", "file-cmd-tidies-blank-lines")
class DescribeRemovingEveryTodo:
    @given(todo_only_files())
    @example((b"a\nb", b"a\nb\n# TODO: t0", 1))
    @example((b"a\r\n\r\nb", b"a\r\n\r\n\r\n# TODO: t0\r\n  \r\nb", 1))
    @example((todos.BOM + b"a\n", todos.BOM + b"<!-- TODO: t0\nmore\n-->\na\n", 1))
    @settings(max_examples=300)
    def it_gives_back_the_last_commit_byte_for_byte(self, case):
        base, now, count = case
        got, found = remove_all(base, now)
        assert found == count
        assert got == base

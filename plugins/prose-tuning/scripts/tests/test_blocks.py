"""Blocks decides what each line of a document is, and three of those kinds are
off limits to every rewrite the plugin makes.

This is the classifier the apply guard consults. Asserting it here means a
change to what counts as a fence fails against the classifier itself, rather
than surfacing as one confusing case in test_apply.py.
"""
import pytest

import prose

PROTECTED = ["frontmatter", "blockquote", "fence"]


def test_the_line_map_matches_what_blocks_says(target, target_lines):
    """conftest's TARGET_LINES is load-bearing - other tests address spans in
    that document by kind. Editing the document without editing the map would
    otherwise leave them silently aimed at the wrong line.
    """
    blocks = prose.Blocks(prose.Text(target))
    named = dict(target_lines)
    last = named.pop("last-paragraph")
    got = {kind: blocks.kind(line) for kind, line in named.items()}
    assert got == {kind: kind for kind in named}
    assert blocks.kind(last) == "paragraph"


@pytest.mark.parametrize("kind", PROTECTED)
def test_protected_kinds_are_protected(target, target_lines, kind):
    blocks = prose.Blocks(prose.Text(target))
    assert blocks.is_protected(target_lines[kind]) is True


@pytest.mark.parametrize("kind", ["heading", "paragraph", "table"])
def test_prose_kinds_are_not_protected(target, target_lines, kind):
    blocks = prose.Blocks(prose.Text(target))
    assert blocks.is_protected(target_lines[kind]) is False

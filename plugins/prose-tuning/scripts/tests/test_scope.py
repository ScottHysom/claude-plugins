"""Glob patterns in the rule file's scope block decide which files are
governed. A pattern that over-matches puts prose rules on a changelog; one
that under-matches silently governs nothing.
"""
import pytest

import prose


@pytest.mark.parametrize("pattern,path,matches", [
    ("**/*.md", "a.md", True),
    ("**/*.md", "x/y/a.md", True),
    ("*.md", "x/a.md", False),
    ("skills/**", "skills/a/b.md", True),
    ("skills/**", "skill/a.md", False),
    ("**/README.md", "README.md", True),
    ("**/README.md", "docs/README.md", True),
    ("prose-style.md", "a/prose-style.md", False),
])
def test_glob_translation(pattern, path, matches):
    assert bool(prose.glob_to_regex(pattern).match(path)) is matches

"""Shared fixtures for the prose.py suite.

prose.py is a standalone script, not an installed package. It ships inside a
plugin, lands wherever `/plugin marketplace add` puts it, and runs against the
standard library alone - so there is no package to install and import by name.
The tests put the scripts directory on sys.path here rather than in a
root-level config, so a second plugin adding its own scripts/tests needs no
edit anywhere but its own directory.

pytest is a contributor dependency only. Nothing under scripts/ imports it, and
nothing a user installs sees it.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import prose  # noqa: E402  - must follow the sys.path insert above


# A document with one of everything the parser has to tell apart: front
# matter, a heading, a paragraph, a list, a table, a fenced block containing
# something that looks like markup but is not, and a final line with no
# trailing newline. Line numbers are load-bearing - tests address spans in it
# by line - so edit it only by appending.
SAMPLE = """---
title: sample
---

# Heading

Curated, not collected. A resource earns a place here only after it has been
used for something. A bookmark list is not this document.

- first item
- second item with more words in it
- third

| Term | Meaning |
|---|---|
| model | a large file of numbers |

```python
# <del>this is not markup</del>
x = 1
```

Final paragraph."""


@pytest.fixture
def sample():
    return SAMPLE


@pytest.fixture
def round_trip():
    """Insert tags, parse the result, strip them, demand the original back.

    Returns a callable so a test can round-trip several record sets and report
    which one broke. Raises AssertionError at the first step that fails, which
    is where the failure actually is - a refusal, a parse error and a corrupted
    strip are three different bugs.
    """
    def run(records, source=SAMPLE):
        text = prose.Text(source)
        blocks = prose.Blocks(text)
        engine, refusals, _ = prose.apply_inserts(
            text, blocks, records, "sample.md", 1)
        assert not refusals, "insert refused: %s" % (refusals[0],)

        tagged = prose.Text(engine.result())
        scanner = prose.TagScanner(tagged, None, "sample.md")
        assert not scanner.errors, \
            "tagged text does not parse: %s" % (scanner.errors[0],)

        back, _ = prose.resolve_text(tagged, prose.REJECT, None, "sample.md")
        assert back == source, "strip did not restore the original"
    return run


@pytest.fixture
def config_from(tmp_path):
    """Write rule-file text to a temp path and parse it.

    Config reads from a path rather than a string, so a test that exercises
    the parser has to put its source on disk first.
    """
    def build(src, name="prose-style.md"):
        path = tmp_path / name
        prose.Text(src).write(str(path))
        return prose.Config(str(path))
    return build

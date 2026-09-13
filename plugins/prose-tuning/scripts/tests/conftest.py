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

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402
from hypothesis import settings  # noqa: E402

import prose  # noqa: E402  - must follow the sys.path insert above


# Property tests explore a different set of inputs on every run, which is the
# point of them locally and a liability in CI: a seed that happens to find an
# old bug turns an unrelated pull request red, and the next run may not
# reproduce it. So CI runs a fixed seed - a red build there is always caused by
# the diff - and a developer machine explores. A counterexample found while
# exploring is pinned with @example so CI checks it from then on.
#
# GitHub Actions sets CI itself, so the workflow needs no flag for this.
settings.register_profile("dev", max_examples=50)
settings.register_profile("ci", derandomize=True, max_examples=200)
settings.load_profile("ci" if os.environ.get("CI") else "dev")


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
        engine, refusals, _ = prose.apply_inserts(text, blocks, records, "sample.md", 1)
        assert not refusals, "insert refused: %s" % (refusals[0],)

        tagged = prose.Text(engine.result())
        scanner = prose.TagScanner(tagged, None, "sample.md")
        assert not scanner.errors, "tagged text does not parse: %s" % (scanner.errors[0],)

        back, _ = prose.resolve_text(tagged, prose.REJECT, None, "sample.md")
        assert back == source, "strip did not restore the original"

    return run


# A document with one line of every kind the block classifier separates, used
# by the tests that drive a whole command rather than a function. TARGET_LINES
# is the map from kind to line number; test_blocks.py asserts the map against
# what Blocks actually says, so editing the document below fails there loudly
# rather than quietly pointing these tests at the wrong line.
TARGET = """---
title: target
---

# Heading

Curated, not collected. A resource earns a place here only after it has been
used for something.

> A quotation carries someone else's voice, not this document's.

| Term | Meaning |
|---|---|
| model | a large file of numbers |

```python
x = 1
```

Final paragraph.
"""

TARGET_LINES = {
    "frontmatter": 2,
    "heading": 5,
    "paragraph": 8,
    "blockquote": 10,
    "table": 14,
    "fence": 17,
    "last-paragraph": 20,
}

# The one rule the throwaway repo's rule file defines. apply rejects a finding
# naming anything else, so every test record has to cite this.
RULE_ID = "sentences-own-subject"

STYLE = """---
name: Probe
---

## Sentences

### sentences-own-subject: Carries its own subject

A sentence that borrows its subject from the heading above it is incomplete.

> **Before.** Curated, not collected.
> **After.** The list is curated, not collected.
"""


class ProseRepo:
    """A throwaway repo: a rule file, one document, and a way to run a command.

    `git init` and nothing more. apply reads the working tree and never reads a
    ref, so there is no commit here and no git identity to configure - which
    also keeps the fixture from failing on a machine whose global git config
    signs commits.
    """

    def __init__(self, root, capsys):
        self.root = root
        self._capsys = capsys

    def read(self, rel="target.md"):
        return (self.root / rel).read_text()

    def finding(self, line, **overrides):
        """One approved rewrite. Defaults to a rewrite that would succeed, so
        a test names only the field whose guard it is aiming at.
        """
        record = {"rule": RULE_ID, "file": "target.md", "line": line, "replacement": "rewritten"}
        record.update(overrides)
        return record

    def apply(self, findings, *flags):
        """Run `prose.py apply`. Returns (exit code, parsed envelope).

        Driven through main() rather than cmd_apply() so the argparse defaults
        are the real ones - a flag added later reaches these tests instead of
        needing a hand-built Namespace kept in step by hand.
        """
        path = self.root / "findings.json"
        path.write_text(json.dumps(findings))
        self._capsys.readouterr()  # drop anything already buffered
        code = prose.main(
            ["apply", "-C", str(self.root), "--findings", str(path), "--json"] + list(flags)
        )
        return code, json.loads(self._capsys.readouterr().out)


@pytest.fixture
def target():
    return TARGET


@pytest.fixture
def target_lines():
    return dict(TARGET_LINES)


@pytest.fixture
def prose_repo(tmp_path, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    # capture_output so git's default-branch hint stays out of the CI log.
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / "prose-style.md").write_text(STYLE)
    (root / "target.md").write_text(TARGET)
    return ProseRepo(root, capsys)


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

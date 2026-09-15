"""Test documents shared by the prose.py suite.

A separate module, not conftest.py, because some tests need these at import
time - a Hypothesis strategy is built when its module loads, before any fixture
exists. Importing from conftest by name breaks when another plugin's conftest
is loaded in the same pytest run; ruff.toml bans it and says why. The module is
named after the plugin so it cannot collide with another plugin's helper.
"""

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

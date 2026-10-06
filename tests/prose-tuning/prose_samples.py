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


def tagged(source, marks):
    """source with markup written into it the way an author writes it by hand.

    Each mark is a dict naming its kind and where it goes, by 1-indexed line:

    - `del`, `repl` or `pair` with `line` and `cols`, (start, end) on that
      line, marks the text between them inline. `repl` and `pair` take the new
      text as `with`; a `pair` is a bare `<del>` then `<ins>`.
    - `del` or `repl` with `lines`, (first, last), marks those lines whole in
      block form, its tags on lines of their own. The last line of a document
      with no final newline takes the closing tag straight after its text, so
      no newline is invented.
    - `ins` with `line`, `col` and `text` adds text at a point.
    - `alt` with `line` and `text` puts a proposal on a line of its own above
      that line.

    Any mark but `alt` takes an optional `why` attribute, and an inline one an
    optional `alt` child. The marks have to cover lines apart from one another.
    """
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    edits = []
    for m in marks:
        kind = m["kind"]
        why = ' why="%s"' % m["why"] if m.get("why") else ""
        alt = "<alt>%s</alt>" % m["alt"] if m.get("alt") else ""
        if kind == "alt":
            at = starts[m["line"] - 1]
            edits.append((at, at, "<alt>%s</alt>\n" % m["text"]))
        elif kind == "ins":
            at = starts[m["line"] - 1] + m["col"]
            edits.append((at, at, "<ins%s>%s%s</ins>" % (why, m["text"], alt)))
        elif "lines" in m:
            first, last = m["lines"]
            a, b = starts[first - 1], starts[last]
            body = source[a:b]
            first_line = lines[first - 1]
            indent = first_line[: len(first_line) - len(first_line.lstrip(" "))]
            close = indent if body.endswith("\n") else ""
            end = "\n" if body.endswith("\n") else ""
            if kind == "del":
                out = "%s<del%s>\n%s%s</del>%s" % (indent, why, body, close, end)
            else:
                out = "%s<repl%s>\n%s<del>\n%s%s</del>\n%s<ins>\n%s%s\n%s</ins>\n%s</repl>%s" % (
                    indent,
                    why,
                    indent,
                    body,
                    close,
                    indent,
                    indent,
                    m["with"],
                    indent,
                    indent,
                    end,
                )
            edits.append((a, b, out))
        else:
            base = starts[m["line"] - 1]
            a, b = base + m["cols"][0], base + m["cols"][1]
            old = source[a:b]
            if kind == "del":
                out = "<del%s>%s%s</del>" % (why, old, alt)
            elif kind == "repl":
                out = "<repl%s><del>%s</del><ins>%s</ins>%s</repl>" % (why, old, m["with"], alt)
            else:
                out = "<del%s>%s%s</del><ins>%s</ins>" % (why, old, alt, m["with"])
            edits.append((a, b, out))
    for a, b, out in sorted(edits, reverse=True):
        source = source[:a] + out + source[b:]
    return source

# The markup vocabulary

Normative. `prose.py tags check` enforces every rule on this page, and reports
one line per problem.

The markup is temporary. It is inserted to say something about a passage, read
once by `update-prose-config`, and removed by `tags resolve` before anything is
committed. A tag that reaches a commit is a bug.

## The five tags

| Tag | Means | Resolves to |
|---|---|---|
| `<ins>new text</ins>` | Add this. | the text, on accept; nothing, on strip |
| `<del>old text</del>` | Cut this. | nothing, on accept; the text, on strip |
| `<repl>…</repl>` | Swap one for the other. | the `<ins>`, on accept; the `<del>`, on strip |
| `why` | Why the edit was made. | nothing |
| `<alt>…</alt>` | A proposed rule, or an equivalent rewrite. | nothing |

Plus one pair for the interview: `<q id="N">question</q>` and `<a>answer</a>`.

## A replacement is a del and an ins

```
<del>which is the whole point</del><ins></ins>
```

A `<del>` immediately followed by an `<ins>`, with only whitespace between, is
one replacement. Nothing else is needed for the common case.

`<del>` and `<ins>` are real HTML5 elements. GitHub's sanitizer allows them and
every markdown preview renders them as strikethrough and inserted text, so a
replacement **looks like an edit** in the preview being read while tagging. An
invented element - `<with>`, `<old>`, `<new>` - is auto-closed by the browser
and shows both versions run together with nothing between them. That is the
whole reason the vocabulary reuses these two rather than inventing a separator.

Wrap the pair in `<repl>` when commentary needs somewhere to attach:

```
<repl why="heading is a noun phrase">
  <del>The size arithmetic, which is the whole point</del>
  <ins>The size arithmetic</ins>
</repl>
```

`<repl>` holds exactly one `<del>` then one `<ins>`, in that order. This is the
only nesting the grammar permits between edit tags; `<ins>`, `<del>` and
`<repl>` never otherwise contain each other. Forbidding the rest is what keeps
the parser from needing to disambiguate which span a closing tag closes.

## Commentary

Two keywords, because rationale and exemplars are different inputs to a rule
and routing them by hand is work the parser can do for free.

**`why` is the reason, and nothing else.** Short form is an attribute. Long
form, or any text containing a double quote, is a child element:

```
<del why="restates the passage">A bookmark list is not this document.</del>
```

**`<alt>` is a proposal.** A rule the edit implies, or an equivalent rewrite,
or several. It repeats, and it is also valid on its own at the top level, tied
to no passage:

```
<repl>
  <why>Three sentences carrying one claim.</why>
  <alt>Keep the sentence holding the fact; cut the rest.</alt>
  <alt>"Curated. A resource earns a place after it has been used."</alt>
  <del>Curated, not collected. A bookmark list is not this document.</del>
  <ins>A resource earns a place here only after it has been used.</ins>
</repl>

<alt>Standalone: headings never editorialize, even in pirate voice.</alt>
```

Commentary binds to the tag carrying it. A `why` on the `<repl>` describes the
swap; a `why` on the inner `<del>` describes only the deletion.

## The interview

```
<q id="3">Does the pirate register apply to headings?</q>
<a>Body only. Headings stay plain noun phrases.</a>
```

Ids are assigned by `tags insert`, never by hand, because hand-numbering
collides across files. An `<a>` answers the nearest `<q>` above it. A `<q>` with
no `<a>` is reported as open by `status` and `evidence`.

## Inline and block form

**The script picks the form, not the author.** `tags insert` uses inline form
when the span fits on one line, and it never splits a line: a split survives the
strip and leaves the document permanently reflowed. Block form is used only when
the span starts and ends on block boundaries, and the tags are indented to match
the span's own first line so an enclosing list survives.

A span is refused when it starts mid-line and ends on a different line, or when
it touches a code fence, a heading, a table or front matter. Markup inside any
of those breaks the thing it sits in.

Tags inside a fenced code block are ignored, so a document that discusses this
vocabulary can quote it without being parsed as marked up.

## What the parser rejects

One fault produces one message. A parser that says two things about one typo
teaches the author to skim its output.

| Written | Reported |
|---|---|
| `<del>text` | `<del> is never closed` |
| `</del>` alone | `stray </del> closing nothing` |
| `<del>text</ins>` | `</ins> closes <del> opened at line N` |
| `<del reason="x">` | `<del> has no 'reason' attribute; allowed: why` |
| `<ins><del>no</del></ins>` | `<del> is not allowed inside <ins>` |
| `<repl><del>old</del></repl>` | `<repl> holds 1 <del> and 0 <ins>` |
| `<repl><ins>…</ins><del>…</del></repl>` | `<repl> has <ins> before <del>` |
| two `<q id="1">` | `duplicate question id 1; first at line N` |

`<a href="…">` is an HTML anchor and is skipped rather than reported. An `<a>`
carrying any attribute is not an answer tag. Without that exemption ordinary
markdown would fail to parse.

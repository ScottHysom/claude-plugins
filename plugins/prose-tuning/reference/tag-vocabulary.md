# The markup vocabulary

This page is normative. `prose.py preflight` and `prose.py evidence` enforce
every rule on this page, and report one line per problem.

The markup is temporary. The author writes it to say something about an edit.
`update-prose-config` reads it and leaves it in place, and `apply-prose` runs
`tags resolve` to remove it once the rules are learned. A tag that reaches a
commit is a bug.

## The tags

| Tag | Means | Resolves to |
|---|---|---|
| `<ins>new text</ins>` | Add this. | the text |
| `<del>old text</del>` | Cut this. | nothing |
| `<repl>…</repl>` | Swap one for the other. | the `<ins>` |
| `why` | Why the edit was made. | nothing |
| `<alt>…</alt>` | A proposed rule, or an equivalent rewrite. | nothing |

## A replacement is a del and an ins

```markdown
<del>which is the whole point</del><ins></ins>
```

A `<del>` immediately followed by an `<ins>`, with only whitespace between, is
one replacement. Nothing else is needed for the common case.

Wrap the pair in `<repl>` when commentary needs somewhere to attach:

```markdown
<repl why="heading is a noun phrase">
  <del>The size arithmetic, which is the whole point</del>
  <ins>The size arithmetic</ins>
</repl>
```

`<repl>` holds exactly one `<del>` then one `<ins>`, in that order. This is the
only nesting the grammar permits between edit tags; `<ins>`, `<del>` and
`<repl>` never otherwise contain each other.

## Commentary

Commentary takes two keywords, `why` and `<alt>`.

**`why` is the reason, and nothing else.** Short form is an attribute. Long
form, or any text containing a double quote, is a child element:

```markdown
<del why="restates the passage">A bookmark list is not this document.</del>
```

**`<alt>` is a proposal.** It offers a rule the edit implies, or an equivalent rewrite,
or several. It repeats, and it is also valid on its own at the top level, not tied
to any passage:

```markdown
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

## Inline and block form

A tag in inline form sits inside one line. A tag in block form has its opening
and closing tags on lines of their own, around whole lines, indented to match
the first of them. A tag that starts mid-line and ends on a different line
straddles blocks, so write it as one or the other.

Keep markup out of a code fence, a heading, a table and front matter, since it
breaks the thing it sits in. A block-form tag between two list items ends the
list, which `tags resolve` warns about.

Tags inside a code block, fenced or indented, or inside an HTML block such as
`<div>`, are ignored, so a document that discusses this vocabulary can quote
it without being parsed as marked up. A line holding only one of these tags
is markup, not an HTML block.

## What the parser rejects

One fault produces one message.

| Written | Reported |
|---|---|
| `<del>text` | `<del> is never closed` |
| `</del>` alone | `stray </del> closing nothing` |
| `<del>text</ins>` | `</ins> closes <del> opened at line N` |
| `<del reason="x">` | `<del> has no 'reason' attribute; allowed: why` |
| `<ins><del>no</del></ins>` | `<del> is not allowed inside <ins>` |
| `<repl><del>old</del></repl>` | `<repl> holds 1 <del> and 0 <ins>` |
| `<repl><ins>…</ins><del>…</del></repl>` | `<repl> has <ins> before <del>` |

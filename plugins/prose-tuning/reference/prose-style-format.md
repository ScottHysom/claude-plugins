# The format of prose-style.md

Normative. `prose.py config lint` enforces every rule on this page.

The file lives at the root of a project repo. It is read by every agent that
edits a document there, which is why it is a document rather than a section
inside a skill: not every agent loads the skill, and a project is expected to
diverge from the shipped default.

## Front matter

```yaml
---
name: AI Learning Plan prose style
scope:
  include:
    - "**/*.md"
  exclude:
    - "prose-style.md"
    - "project-instructions.md"
    - "**/README.md"
    - "skills/**"
---
```

**The grammar is deliberately small, not accidentally small.** `prose.py` is
stdlib-only and has no YAML parser, so anything richer would be parsed by
guesswork. What is allowed: top-level `key: value` pairs, and exactly one
`scope:` block holding `include:` and `exclude:` lists. Anything else is an
error, not a shrug - a silently dropped key is a scope override that appears to
work.

`include` and `exclude` replace the defaults wholesale when present. Partial
override was considered and rejected: "which of the four defaults am I still
getting" is not a question anyone should answer by reading a script.

`prose-style.md` is excluded whatever the override says. A conformance pass
rewriting its own rulebook is not a thing anyone wants to debug.

Glob syntax: `**/` matches any number of directories, `**` matches anything,
`*` matches within one path segment, `?` matches one character. Patterns match
the whole repo-relative path, so `prose-style.md` matches only at the root and
`**/README.md` matches at any depth.

## A rule

```markdown
### sentences-01: Every sentence carries its own subject
<!-- prose-rule: source=shipped -->

A sentence that borrows its subject from the heading above it, from the
sentence before it, or from the reader's inference is incomplete.

**Check.** Read the sentence with nothing before it. If it no longer says who
or what, its subject is missing.

> **Before.** Able to state what is inside the file.
> **After.** A reader can state what is inside the file.
```

**The id is in the heading.** `### <id>: <Title>`, split on the first `: `. It
renders, it greps, and a report reading `sentences-01 at landscape.md:42` can be
checked by eye against the file. Ids are `<section>-<NN>`. Shipped sections are
`standing`, `prose`, `decisions`, `sentences`, `headings` and `register`; a
project adds its own, and `voice` is the usual name for the section where a
project diverges.

Content-hash ids were rejected as unreadable in a report. Free-form slugs were
rejected because they drift the moment a rule is reworded, which is exactly what
a stable id exists to survive.

**The metadata comment carries at most two keys.** `source` is one of `shipped`,
`inferred`, `interview` or `adopted`. `origin=<project>` appears only on a rule
that arrived through `adopt-prose`, because an adopted rule is the one most
likely to be wrong for its new home.

**The example is a two-line blockquote** with fixed lead words, `> **Before.**`
and `> **After.**`. They come as a pair; half an example is an error. A rule
with no example at all is a warning, not an error, because a one-line standing
instruction like "use US spelling" does not need one.

`**Check.**` is conventional rather than required. A rule that can state a
mechanical test should.

## No retired rules

There is no `status: retired` and no `supersedes:`. When a later run contradicts
an earlier rule, the new text **replaces the body of the existing id**. The old
text is in git.

Carrying retired rules in the file is history in the content, which is the one
thing this family of documents exists to prevent. It would also raise a question
with no good answer: whether a conformance pass should honour them.

## Sections

`##` headings group rules and carry free prose. The parser ignores anything
between a `##` and the first `###` under it, so a section can explain itself to
a reader without confusing a tool. Use that for the FILL markers that tell a
project what to supply.

## Checking a file

```sh
python3 "$PROSE" config lint --file prose-style.md
python3 "$PROSE" config list --file prose-style.md
```

`lint` exits 1 on any error and prints one line per problem. `list` prints the
rules and marks with `!` any rule carrying no worked example.

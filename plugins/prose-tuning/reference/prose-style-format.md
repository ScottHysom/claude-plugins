# The format of prose-style.md

This page is normative. `prose.py config lint` enforces every rule on this page.

The file lives at `.claude/rules/prose-style.md` in a project repo. Claude Code
and Cowork both load every file in `.claude/rules/` into their sessions, so
every agent writing in the project has the rules without a skill running. That covers commit messages, pull request text
and code comments as much as documents. COWORK.md, in the claude-plugins repo,
has what each product loads and when. It is a file rather than a section inside
a skill because not every agent loads the skill, and a project is expected to
diverge from the shipped default.

The front matter never carries `paths:`. That key would stop the file loading
in every session, so `config lint` rejects it.

A project whose `prose-style.md` is still at its root, where nothing loads it,
runs `config move`. It copies the file across, byte for byte, and leaves the
root copy for the author to delete: the script only reads git, and Cowork's
bridge cannot delete a file. Preflight refuses to run while the root copy is
there.

## Front matter

```yaml
---
name: AI Learning Plan prose style
scope:
  include:
    - "**/*.md"
  exclude:
    - ".claude/**"
    - "project-instructions.md"
    - "**/README.md"
    - "skills/**"
---
```

**The grammar is deliberately small, not accidentally small.** `prose.py` is
stdlib-only and has no YAML parser, so anything richer would be parsed by
guesswork. What is allowed: top-level `key: value` pairs, and exactly one
`scope:` block holding `include:` and `exclude:` lists. Anything else is an
error, not a shrug. A silently dropped key is a scope override that appears to
work.

`include` and `exclude` replace the defaults wholesale when present.

The rules file is excluded whatever the override says. A conformance pass
rewriting its own rulebook is not a thing anyone wants to debug.

Glob syntax: `**/` matches any number of directories, `**` matches anything,
`*` matches within one path segment, `?` matches one character. Patterns match
the whole repo-relative path, so `CLAUDE.md` matches only at the root and
`**/README.md` matches at any depth.

## A rule

```markdown
### sentences-own-subject: Every sentence carries its own subject
<!-- prose-rule: source=shipped -->

A sentence that borrows its subject from the heading above it, from the
sentence before it, or from the reader's inference is incomplete.

**Check.** Read the sentence with nothing before it. If it no longer says who
or what, its subject is missing.

> **Before.** Able to state what is inside the file.
> **After.** A reader can state what is inside the file.
```

**The id is in the heading.** `### <id>: <Title>`, split on the first `: `. It
renders, it greps, and a report reading `sentences-own-subject at
landscape.md:42` can be checked by eye against the file.

**An id is `<section>-<name>`.** The section is one lower-case word. The name is
one to four lower-case words joined by `-`, and no word may start with a digit.
Shipped sections are `standing`, `decisions`, `sentences`, `headings` and
`register`; a project adds its own, and `voice` is the usual name for the
section where a project diverges.

The name says what the rule means, which is the whole point of it:
`sentences-count-needs-list` is legible in a report where `sentences-09` sends
the reader back to the file. The four-word ceiling is there because a rule whose
subject cannot be said in four words has not been decided yet.

**A rule keeps its name for life.** This is the same discipline as the
no-retired-rules rule below, and it has the same reason: the id is identity.
Reword the body freely; the name survives, because the name is about the
subject, not the wording. A rule whose subject moved far enough to want a
different name is a different rule, and the one it replaced should have been
rewritten in place.

Nothing enforces the naming discipline. `config lint` checks the grammar and the
word count and stops there, the same way it cannot tell that two rules
contradict each other. Both are judgment, and both are stated here so that the
judgment is at least a shared one.

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

## A pattern

A rule whose breaches a regular expression can find carries a `**Pattern.**`
line, and `prose.py patterns` runs it:

```markdown
### standing-no-em-dash: Prefer a period over the em-dash
<!-- prose-rule: source=shipped -->

Ranges keep their en-dash.

**Pattern.** `—`
**Pattern.** `\s(?:--?|–)(?:\s|$)`
```

**The line holds one code span and nothing else.** The span holds a Python
regular expression. A pattern with a backtick in it goes in a span of two
backticks, as markdown has it. A rule can carry any number of pattern lines,
and a match of any one of them is a match for the rule. A word list reads more
easily as one line per family of words than as one long alternation.

**A flag such as `(?i)` goes at the very start.** Python 3.11 refuses one
anywhere else, so `config lint` refuses it on every version.

**A pattern reads what `segments` returns, and nothing else.** Front matter,
fences, blockquotes, HTML comments and a table's delimiter row are never
searched. A match that touches a code span is dropped too, since a code span
quotes code. The lines of one paragraph or list item are searched as one
passage, with each line break read as a single space, so `in order to` finds
a sentence that wraps after `order`.

`config lint` rejects a `**Pattern.**` line that is not one code span, a
pattern that does not compile, and a pattern that matches an empty string,
which would match everywhere.

**A pattern answers to its rule's worked example.** When a rule has both
halves of an example, at least one of its patterns must find something in the
Before text, and none may match the After text. `config lint` fails the file
otherwise. The example is the evidence the rule was written from, so a pattern
that misses it finds nothing the rule is about, and one that matches the
rewrite flags prose the rule holds up as right.

A pattern finds places to look, and the model still judges each one. A
spaced hyphen can be a minus sign. The pattern does not replace the rule's
prose either. A misspelling missing from a word list still breaks the rule.

### When a rule gets a pattern

A rule gets a pattern when what breaks it is a fixed form: a character such as
the em-dash, a word such as `behaviour`, or a phrase such as `in order to`. A
pattern that matches every one of those forms and little else is exhaustive,
and the rule is checked in every file on every run.

A rule about meaning gets none. `sentences-own-subject` and
`headings-noun-phrase` need a reading of the sentence, and a pattern
approximating them would flag a pile of passages that are fine. The model
then learns to skim the matches.

Write the narrowest pattern that finds the rule's own Before text. A word
list is written from the forms the evidence showed and the obvious members of
the same family, one `**Pattern.**` line per family.

## No retired rules

There is no `status: retired` and no `supersedes:`. When a later run contradicts
an earlier rule, the new text **replaces the body of the existing id**. The old
text is in git.

Carrying retired rules in the file is history in the content, which is the one
thing this family of documents exists to prevent. It would also raise a question
with no good answer: whether a conformance pass should honor them.

## Sections

`##` headings group rules and carry free prose. The parser ignores anything
between a `##` and the first `###` under it, so a section can explain itself to
a reader without confusing a tool. Use that for the FILL markers that tell a
project what to supply.

## Checking a file

```sh
python3 "$PROSE" config lint
python3 "$PROSE" config list
```

Both read the project's `.claude/rules/prose-style.md`. `--file <path>` reads
another one instead.

`lint` exits 1 on any error and prints one line per problem. `list` prints the
rules and marks with `!` any rule carrying no worked example.

Before adding a rule, have the script rule on the name:

```sh
python3 "$PROSE" config check-id --section sentences --name own-subject
```

It exits non-zero when the name is malformed or already taken. There is no
allocator to pair with it, because with a positional id gone there is nothing
left to allocate.

## Migrating a file that still uses positional ids

A `prose-style.md` written before this format change carries `sentences-01` and
its kind, and `config lint` now reports every one of them as an error. There is
no `config migrate`, and there should not be: naming a rule is a reading of what
that rule means, which is the one thing in this file a script cannot do. Open
the file, name each rule, and change the headings. Nothing else in a rule moves.

Anything outside the file that quoted an old id (a report, a commit message, a
cross-reference in another document) is stale afterwards. The cross-references
are worth fixing. The reports are history, and history stays as it was written.

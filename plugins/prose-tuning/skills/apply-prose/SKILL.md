---
name: apply-prose
description: Conform a project's markdown to the rules in its prose-style.md. Reports findings first - file, line, rule id, proposed rewrite - and changes nothing until the author approves. Uses scripts/prose.py to resolve scope, to skip code fences, mermaid blocks, front matter, table structure and quoted material, to find the breaches a rule's pattern can, and to apply approved rewrites in place. Use when asked to apply the house style, conform documents to prose-style.md, run a style pass over the docs, check a document against the prose rules, or clean up the prose across a project. Refuses to run while a prose-tuning markup pass is in progress, and never commits.
---

# Conform the documents to prose-style.md

`update-prose-config` learns the rules. This skill applies them to everything
written before the rules existed.

**Report first. Change nothing until the author says so.** A style pass that
silently rewrites three hundred lines produces exactly the diff nobody reads,
and a reader cannot tell a rule being applied correctly from a rule being
misapplied without seeing which rule was claimed.

## Locate the script

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"
PROSE="$ROOT/scripts/prose.py"
ls "$PROSE" || echo "prose-tuning is not installed as a plugin here"
python3 "$PROSE" setup --json
```

Run the block as one command, because the next command's shell will not have
`$PROSE`. Then follow `$ROOT/reference/setup.md`. It says where every command below
runs.

## Step 1: refuse early

```sh
python3 "$PROSE" preflight --for apply
```

`preflight` exits 1 on either of two states, both meaning an `update-prose-config` run is
underway:

- **markup present in any governed file.** Conforming a half-tagged tree
  destroys the evidence that run was gathering.
- **an uncommitted governed document.** The author is mid-edit, and a rewrite
  landing on top of that is unreviewable.

An uncommitted `prose-style.md` is not a blocker. It is the expected output of
the run whose rules this pass is about to check.

`--force` exists. Use it only when the author has asked for it by name.

## Step 2: the rules and the files

```sh
python3 "$PROSE" config list --json
python3 "$PROSE" segments --summary
```

`segments --summary` prints one line per file in scope, with its segment count
and the characters of prose in them, then the totals. State the totals before
reading anything, so the size of the pass is known up front. When the author
asks why a file was skipped:

```sh
python3 "$PROSE" scope --all
```

which prints every markdown file with the pattern that included or excluded it.

## Step 3: run the rules' patterns

```sh
python3 "$PROSE" patterns
```

A rule can carry a regular expression that finds its breaches, such as a
spaced hyphen for `standing-no-em-dash`. `patterns` runs every one over the
same spans `segments` returns, in every file in scope, and prints one line per
match:

```text
notes.md:12:40-42  standing-no-em-dash  " -"
notes.md:30:61-31:4  register-plain-words  "in order\n  to"
```

The address is `file:line:col_start-col_end`, with `end_line:col_end` after
the dash when the match wraps onto the next line. Then come the rule id and
the matched text, as a JSON string that goes into a finding's `text` as it
stands. The last line names the rules checked by pattern.

When it says no rule carries one, the project's rules were written before
rules could, and every rule is checked by reading. Tell the author that
`adopt-prose` from the shipped rules brings in their patterns.

A pattern finds places to look, so judge each match. A spaced hyphen can be a
minus sign. Every match that breaks its rule becomes a finding in step 5,
usually with a longer `text` than the match, since the rewrite is of the
sentence.

**Never search the prose with a command of your own,** such as `grep` over
the `segments` output. A search written during a run finds a different set on
the next run, and nothing records which rules it covered. A rule with no
pattern is checked by reading, in step 4. A break of a patterned rule that
reading turns up anyway is still a finding. Tell the author the pattern
missed it, since the pattern is theirs to extend.

## Step 4: read only the eligible prose

```sh
python3 "$PROSE" segments
```

With no path, `segments` reads every file in scope, so one run covers the
whole pass. Name files after it to read only those.

**Never read the raw file to judge conformance.** `segments` returns only the
spans a prose rule may touch, one per line:

```text
landscape.md:42:2-40  list-item  Able to state what is inside the file.
```

The line starts with the address `file:line:col_start-col_end`. Then come the
kind and the text, each after two spaces. The text runs to the end of the line.

| Kind | Is |
|---|---|
| `paragraph` | body prose, the usual case |
| `list-item` | the text after the bullet, not the bullet |
| `list-continuation` | a later line of a list item's text. A new line in its replacement is indented to stay in the item |
| `heading` | the text after the `#`s. Headings have rules too |
| `table-cell` | one cell's text, without its pipes |

What never appears, and why: fenced code and mermaid blocks are code, front
matter is structured data, blockquotes are usually somebody else's words, HTML
comments are notes for people rather than the document's prose, and a table's
delimiter row is structure. A comment part way along a line is cut out, and
the prose either side of it comes back as separate segments.

## Step 5: produce findings

<!-- no-command: judgment. The model writes each finding, and step 6's report checks them. -->

Each finding is one JSON object in a findings file:

| Field | Content |
|---|---|
| `file`, `line` | where the text starts |
| `rule` | the id from `prose-style.md`, exactly one |
| `text` | the text as it stands |
| `replacement` | the rewrite |
| `why` | one clause, in the rule's own terms |

**A finding names exactly one rule.** A passage breaking two rules is two
findings, because the author may accept one and reject the other.

**Rewrite the prose, never the facts.** A rule is about how a sentence reads. A
proposed rewrite that changes a number, a name, a date or a claim is out of
scope for this skill no matter how badly the sentence reads.

Write the findings file outside the project, so no stray file is left in it:

```sh
cat > "${TMPDIR:-/tmp}/prose-findings.json" <<'END'
[{"file":"landscape.md","line":42,"rule":"sentences-own-subject",
  "text":"<the current text, copied from the segment>",
  "replacement":"<the rewrite>","why":"<one clause>"}]
END
```

`file` and `line` come from the segment's address, and `text` is copied
exactly from the segment's text. Leave the columns out: `apply` finds the text
on its line.
When it is refused because the text starts at more than one place on the line,
add the `col_start` the refusal lists. A sentence wrapped onto the next line is
one finding, with the newline and the next line's indent in `text`.

`python3 "$PROSE" apply --help` describes every field of a finding, and which
kinds of line a replacement may put a newline in.

To cut text, give `"replacement":""`. A line that the cuts cover whole goes
with its newline, and when a cut takes a whole block `apply` keeps one blank
line between the blocks either side.

## Step 6: one approval round

```sh
python3 "$PROSE" report --findings "${TMPDIR:-/tmp}/prose-findings.json"
```

`report` prints each finding with its `file:line`, rule id, current text,
proposed text and why. It reads the current text from the file as it is now.
Each line of a current or proposed text sits between `|` marks, so a space at
either end shows. `(cut)` and `(nothing: this inserts)` stand for an empty
text and carry no marks.
Show the author that output as it stands. Never retype it into a table of
your own, because the author then approves a text that `apply` never sees.
Its next-to-last line names the rules `patterns` checked in every file, and
says that every other rule was checked by reading. Its last line, printed only
when it exits 0, is the approval token, such as
`approval token: 3f9a1c0e7b2d4a68`. Keep the token from the run the author
approved; step 7 needs it.

`report` exits 1 when a finding cannot apply, and says why on stderr:

- **a finding `apply` would refuse**, such as one whose text has moved. Fix
  the finding and run `report` again.
- **two findings that overlap**, named as `finding 3 (notes.md:96,
  standing-no-em-dash) overlaps finding 7 (notes.md:94,
  sentences-no-restating-close)`. Each can apply alone, and the pair cannot.
  Put the pair to the author in this round, and let the author choose which
  one to keep. Never drop one yourself.

Take one decision. It covers the whole set, a set of rule ids, or a set of
files, and says which side of each overlap stays. Batch it; do not ask per
finding.

Then remove the side of each overlap the author turned down from the findings
file, and run `report` again. It has to exit 0 before step 7, and its token is
the one step 7 takes.

## Step 7: apply

Hand the approval to `apply` as flags, with the token `report` printed.
The flags select within the approved set and leave the token as it is.

| Approved | Flags |
|---|---|
| the whole set | none |
| by rule id | `--only sentences-own-subject,headings-noun-phrase` |
| by file | `--file landscape.md --file resources.md`, one per file |
| rule ids in some files | both; a finding must pass each |

Run it with `--dry-run` first, then without:

```sh
python3 "$PROSE" apply --findings "${TMPDIR:-/tmp}/prose-findings.json" \
  --token 3f9a1c0e7b2d4a68 --only sentences-own-subject --file landscape.md --dry-run
python3 "$PROSE" apply --findings "${TMPDIR:-/tmp}/prose-findings.json" \
  --token 3f9a1c0e7b2d4a68 --only sentences-own-subject --file landscape.md
```

A rule id or file that matches no finding is an error, not an empty run.

`apply` exits 1 and writes nothing when the findings file, a document a finding
names or `prose-style.md` has changed since that `report`. Run `report` again
and show its output to the author before applying anything.

`apply` is all-or-nothing by default, so a partial pass cannot leave half the addresses
stale. `--partial` applies what is valid and reports the rest.

The engine rejects a finding rather than trusting it when:

- the `text` starts nowhere on its line, or no longer matches what is at its
  columns, which means the report is stale and must be regenerated
- the `text` starts at more than one place on its line and no `col_start` says
  which
- the rule id is not in `prose-style.md`
- the text reaches front matter, a fence, a blockquote or an HTML comment
- the text crosses a line that is not part of a paragraph or a list item, such
  as a blank line or a heading
- a `table-cell` replacement contains a `|` or a newline, which would silently
  restructure the table
- two findings overlap, which `report` names in step 6

## Step 8: report and stop

<!-- no-command: hand-off to the author. The output of apply in step 7 is the report. -->

The output of `apply` in step 7 is the report of what changed: the edits per
file and per rule id. Show it to the author as it stands. Leave the working
tree dirty.
**Never commit.** The project's own maintenance skill owns that.

## What this skill does not do

It does not add rules. A passage that reads badly under no existing rule is a
note to the author and a candidate for `update-prose-config`. Editing it here
would be a freelance rewrite wearing a rule's clothing, and nothing downstream
could tell the difference.

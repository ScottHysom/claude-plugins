---
name: apply-prose
description: Conform a project's markdown to the rules in its prose-style.md. Reports findings first - file, line, rule id, proposed rewrite - and changes nothing until the author approves. Uses scripts/prose.py to resolve scope, to skip code fences, mermaid blocks, front matter, table structure and quoted material, and to apply approved rewrites in place. Use when asked to apply the house style, conform documents to prose-style.md, run a style pass over the docs, check a document against the prose rules, or clean up the prose across a project. Refuses to run while a prose-tuning markup pass is in progress, and never commits.
---

# Conform the documents to prose-style.md

`update-prose-config` learns the rules. This skill applies them to everything
written before the rules existed.

**Report first. Change nothing until the author says so.** A style pass that
silently rewrites three hundred lines produces exactly the diff nobody reads,
and a reader cannot tell a rule being applied correctly from a rule being
misapplied without seeing which rule was claimed.

**Claude Code against a local checkout is the primary surface.** On Cowork this
needs a marketplace install, because `propose_skills` cannot carry
`scripts/prose.py`.

## Locate the script

```sh
PROSE="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}/scripts/prose.py"
ls "$PROSE" || echo "prose-tuning is not installed as a plugin here"
```

## Step 1: refuse early

```sh
python3 "$PROSE" preflight --for apply
```

Exits 1 on either of two states, both meaning an `update-prose-config` run is
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
python3 "$PROSE" scope
```

State the file count before reading anything, so the size of the pass is known
up front. When the author asks why a file was skipped:

```sh
python3 "$PROSE" scope --all
```

which prints every markdown file with the pattern that included or excluded it.

## Step 3: read only the eligible prose

```sh
python3 "$PROSE" segments <file> --json
```

**Never read the raw file to judge conformance.** `segments` returns only the
spans a prose rule may touch, each with its line, columns and kind.

| Kind | Is |
|---|---|
| `paragraph` | body prose, the usual case |
| `list-item` | the text after the bullet, not the bullet |
| `heading` | the text after the `#`s. Headings have rules too |
| `table-cell` | one cell's text, without its pipes |

What never appears, and why: fenced code and mermaid blocks are code, front
matter is structured data, blockquotes are usually somebody else's words, and a
table's delimiter row is structure.

Telling a model "do not touch code fences" is a rule that gets broken. Never
showing it the fence makes the mistake unavailable, and shrinks the context at
the same time.

## Step 4: produce findings

One row per finding:

| Column | Content |
|---|---|
| `file:line` | where |
| rule | the id from `prose-style.md`, exactly one |
| current | the text as it stands |
| proposed | the rewrite |
| why | one clause, in the rule's own terms |

**A finding names exactly one rule.** A passage breaking two rules is two
findings, because the author may accept one and reject the other.

**Rewrite the prose, never the facts.** A rule is about how a sentence reads. A
proposed rewrite that changes a number, a name, a date or a claim is out of
scope for this skill no matter how badly the sentence reads.

Write the findings to a file for step 6:

```json
[{"file":"landscape.md","line":42,"col_start":0,"col_end":74,
  "rule":"sentences-01","text":"<the current text>",
  "replacement":"<the rewrite>"}]
```

## Step 5: one approval round

Present the findings and take one decision. Whole set, by rule id, or by file.
Batch it; do not ask per finding.

## Step 6: apply

```sh
python3 "$PROSE" apply --findings findings.json --only sentences-01,headings-01 --dry-run
python3 "$PROSE" apply --findings findings.json --only sentences-01,headings-01
```

All-or-nothing by default, so a partial pass cannot leave half the addresses
stale. `--partial` applies what is valid and reports the rest.

The engine rejects a finding rather than trusting it when:

- the `text` no longer matches what is at that address, which means the report
  is stale and must be regenerated
- the rule id is not in `prose-style.md`
- the line is front matter, a fence or a blockquote
- a `table-cell` replacement contains a `|` or a newline, which would silently
  restructure the table

Judgement proposes. The engine enforces.

## Step 7: report and stop

Say what changed, per file and per rule id. Leave the working tree dirty.
**Never commit.** The project's own maintenance skill owns that.

## What this skill does not do

It does not add rules. A passage that reads badly under no existing rule is a
note to the author and a candidate for `update-prose-config`. Editing it here
would be a freelance rewrite wearing a rule's clothing, and nothing downstream
could tell the difference.

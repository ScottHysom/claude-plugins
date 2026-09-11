---
name: update-prose-config
description: Infer prose and style rules from the uncommitted markdown edits in a project repo and write them into that project's prose-style.md with stable rule ids. Reads explicit <ins>/<del>/<repl> markup and untagged diff hunks through scripts/prose.py, asks the author about anything ambiguous in one batch, then resolves the markup so the working tree is committable. Use when asked to learn the house style from edits just made, to update or set up prose-style.md, to tag passages for a style pass, to turn an editing pass into rules, or to record why a passage was cut. Never commits and never writes outside the project repo.
---

# Learn the house prose style from edits already made

The author edits documents by hand. This skill reads those edits, works out what
rule each one implies, and writes the rules into `prose-style.md` so every later
agent applies them without being asked.

**Claude Code against a local checkout is the primary surface.** On Cowork this
works only when the plugin is installed from the marketplace: `propose_skills`
takes a single `SKILL.md` and no bundled files, and this skill cannot run
without `scripts/prose.py`. Say so early rather than letting the author discover
it after answering an interview.

## Locate the script

```sh
PROSE="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}/scripts/prose.py"
ls "$PROSE" || echo "prose-tuning is not installed as a plugin here"
```

Stop if that `ls` fails. Every step below is a call into it, and a missing
script surfaces three commands later as something unrelated.

Read `reference/tag-vocabulary.md` before inserting any markup. It is normative
and the script enforces it.

## Step 1: refuse early

```sh
python3 "$PROSE" preflight --for config
python3 "$PROSE" status
```

`preflight` exits 1 on a blocker: unbalanced markup left by an abandoned run, or
a `prose-style.md` that does not parse. `status` is the progress view, and it
exits 0 even with markup present, because markup present is the normal middle of
this skill's own run.

If there is no `prose-style.md`, offer `config init`. A project that has never
had one starts from the scaffold's shipped default rather than from nothing:

```sh
python3 "$PROSE" config init --from <path to templates/prose-style.md>
```

## Step 2: read the rules that already exist

```sh
python3 "$PROSE" config list --json
```

**Do this before inferring anything.** A second run that has not read the first
run's rules invents parallel rules that say the same thing in different words,
and neither can then be pointed at. Every candidate below is checked against
this list.

## Step 3: gather the evidence

```sh
python3 "$PROSE" evidence --json
```

One command returns everything: explicit markup, untagged edits, and any open
questions. Two halves matter differently.

**`explicit`** is markup the author wrote: an `<ins>`, `<del>` or `<repl>` with
its `why` and its `<alt>` proposals. The author has already said what they mean.
Take it at face value.

**`inferred`** is an untagged diff hunk. Treat every one as a statement about
prose, not a factual correction - that is the working assumption of this whole
skill. The escape hatch is the `signal` field: a hunk marked `numeric-only`,
`link-only` or `whitespace-only` may be a fact that got fixed in passing. Those
go into the interview, never straight into a rule.

**`evidence` computes a tag-neutral diff**, which is why it can tell the two
apart at all. A plain `git diff` on a tagged tree reports this skill's own
markup back as author evidence.

**Do not edit any file between `evidence` and `tags insert`.** Every address in
the payload is a working-tree line number, and any write invalidates the rest.
If something must be edited first, re-run `evidence` afterwards.

## Step 4: the threshold for calling something a rule

A candidate becomes a rule when one of these holds:

- it occurs **two or more times** independently, or
- the author attached a `why` or an `<alt>` to it, or
- an answered `<q>` settles it.

Anything else becomes a question, not a rule. A rule inferred from one sentence
with no commentary is a rule about one sentence, and it will fire on every
document in the project forever.

## Step 5: tag what needs the author's eye

One call, one batch, JSON on stdin:

```sh
python3 "$PROSE" tags insert --batch - <<'END'
[{"file":"current-state.md","start":42,"col_start":0,"col_end":58,
  "kind":"del","why":"restates the passage"},
 {"file":"landscape.md","start":60,
  "kind":"q","text":"Did the vendor count change as a fact, or as prose?"}]
END
```

**The batch is the only correct form.** Each insertion shifts every line number
below it, so twenty separate calls would leave nineteen stale addresses. The
script applies the whole batch bottom-up from one snapshot, and writes nothing
at all if any record is refused.

| Field | Means |
|---|---|
| `start`, `end` | 1-indexed lines. `end` defaults to `start` |
| `col_start`, `col_end` | 0-indexed columns. Default to the whole line |
| `kind` | `ins`, `del`, `repl`, `q` or `alt` |
| `why` | short rationale, becomes an attribute |
| `with` | the replacement text, for `repl` |
| `text` | the content, for `ins`, `q` and `alt` |

The script picks inline or block form, never splits a line, and refuses a span
that straddles blocks or touches a fence, heading, table or front matter. Do not
argue with a refusal; give it whole lines instead. Question ids are assigned by
the script, never by hand.

## Step 6: the interview, once

**Budget: one `AskUserQuestion` batch of at most eight questions, plus one
approval at the end.** A second round means the first asked the wrong things.
The first run of this workflow by hand took nine exchanges, and almost all of
them were settling conventions that are now either in `reference/` or enforced
by the script.

What always belongs in the batch:

- every hunk with a `signal`, asked as one question, not one question each
- every single-occurrence candidate with no commentary
- every candidate that touches a subject an existing rule already covers

The in-file route is for an author working asynchronously: this skill writes
`<q>` into the documents, the author answers with `<a>`, and `evidence` reports
answers from either channel. Prefer the batch when the author is present.

## Step 7: write the rules

```sh
python3 "$PROSE" config next-id --section sentences
```

Read `reference/prose-style-format.md` for the shape. Every rule carries a
worked before-and-after taken from the actual edit, because that example is the
rule's provenance as well as its explanation.

**When a new rule contradicts an existing one, rewrite the body of the existing
id.** Do not add a second rule, and do not mark the old one retired. The id is
the identity, the body is current truth, and `git log -p prose-style.md` holds
what it used to say.

**The script cannot detect a contradiction** and does not try. Nothing in
`config lint` can tell that `sentences-04` and a new `register-03` disagree. That
is why step 2 is mandatory and why a candidate touching covered ground goes to
the author instead of into the file. Never reconcile two rules unilaterally.

```sh
python3 "$PROSE" config lint
```

Must pass before going on.

## Step 8: resolve the markup

```sh
python3 "$PROSE" tags resolve
python3 "$PROSE" tags check
```

`resolve` takes the edits the markup proposes - `<ins>` stays, `<del>` goes,
`<repl>` keeps the replacement - and removes every tag. What is left is
committable prose. `tags check` must then find nothing: **markup is never
committed.**

Read the warnings. A block-form tag resolved inside a list is the one case worth
eyeballing, because a tag between two list items ends the list.

## Step 9: validate by reproduction

Run `apply-prose` in its report mode over the files this run touched. The rules
just written should reproduce the edits the author just made. A rule that does
not reproduce its own evidence is wrong or incomplete; say which, and fix the
rule rather than the document.

## Step 10: hand off

Report what changed, which files are dirty, and stop. **Never commit.** The
project's own maintenance skill owns commit types, message format, and the
bridge's lock-file workaround; duplicating any of that here would create a
second source of truth for it.

## Abandoning a run

```sh
python3 "$PROSE" tags strip                    # markup goes, edits revert
python3 "$PROSE" restore --file <path>         # a mangled file goes back to HEAD
```

Not `sed -i ''`, which is BSD syntax and fails on the Linux bridge. Not
`git checkout`, which fails on the bridge because it cannot unlink. `restore`
does `git show HEAD:<file>` into the file, which works on both.

## Scope

This skill writes inside the project repo it was invoked in, and nowhere else.
Carrying a rule upstream into the scaffold's shipped default is `adopt-prose`'s
job, and it is deliberate rather than automatic.

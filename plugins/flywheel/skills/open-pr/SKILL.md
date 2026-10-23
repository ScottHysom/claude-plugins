---
name: open-pr
description: Open a pull request once its work is committed, with a description in the project's own shape that the owner can review without the session's context. Uses scripts/flywheel.py pr draft for the shape and a file to draft in, pr check to check the draft's sections, lines and Closes line, gives the draft to a subagent that has none of the session's context to find each term it leaves undefined, and opens the pull request with pr open from the checked file. Claude Code only. Use when opening, creating or raising a pull request, or when asked to put the work up for review, in a project that has no skill of its own for opening one.
---

# Open a pull request

The owner reviews a pull request from its description, and is its first
reader. The project sets the description's **shape**: the sections it holds,
in order, the subsections under each, and the one section that names the
requirement ids. merge-check and the reviewer read the ids from that section,
so a description in another shape is held for the owner.

The agent that writes the description has the change's vocabulary in
context, so a term it leaves undefined still reads as plain to it. This skill
checks the draft, has a reader without that context read it, and opens the
pull request from the file that reader saw.

Run every command from the root of the clone, on the branch to open, with the
work committed. Never open a pull request with `gh pr create` directly.

## Locate the script

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"
FLYWHEEL="$ROOT/scripts/flywheel.py"
ls "$FLYWHEEL" || echo "flywheel is not installed as a plugin here"
python3 "$FLYWHEEL" setup --json
```

Run the block as one command. If the `ls` fails, the plugin is not installed
here, so stop.

`setup` copies the script into the project at `.flywheel/`, which git
ignores. Each later command starts a fresh shell, so start every one with
`data.prefix` and `&&`, as the steps below do.

## Step 1: draft the description
<!-- spec: prskill-drafts-from-template, prdraft-cmd-makes-own-file -->

Make a file for the draft, and read the project's shape:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" pr draft --json
```

`data.path` is a file that no other run is given. Name it in every later
step by the path exactly as `pr draft` printed it, never through `$TMPDIR` or
another variable. The commands below show it as
`/var/folders/k2/T/pr-x8q1zv.md`.

`data.sections` lists the sections in order. Each has its `heading`, its
`guidance`, its `subsections`, each with a `heading` and `guidance`, and
`ids`, true for the section that names the requirement ids. Write a `##`
heading for each section and a `###` heading for each subsection, in that
order, with what the guidance asks under each. In the section whose `ids` is
true, name in backticks each requirement id the pull request adds, changes
or removes, or say that it does not change any.

Write the title as the project's commits are written, as `git log` shows
them. End the description with `Closes #N` for the issue the branch works,
then the attribution line the session gives for pull requests. Write each
paragraph and each list item on one line, since GitHub renders a newline
inside one as a line break.

Explain each term on first use that the owner would have to guess: a term the
change introduced, or one that a spec, a script or a skill gives its own
meaning. Explain it by the first of these ways that works:

1. Reword the sentence to point back to an earlier sentence that already
   explains the term.
2. Add a qualifier that names the term's kind, where two of a kind meet.
3. Define what the term is, in one clause.

## Step 2: check the draft
<!-- spec: prskill-checks-draft, prcheck-cmd-requires-shape, prcheck-cmd-refuses-split-lines, prcheck-cmd-requires-closes -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" pr check --body-file /var/folders/k2/T/pr-x8q1zv.md --json
```

When it exits 1, its `errors` name each fault. Fix them in the draft and run
it again. Go on to step 3 when it exits 0.

## Step 3: have the draft read cold
<!-- spec: prskill-gives-draft-to-cold-reader -->
<!-- no-command: platform. The model starts a subagent with the Agent tool, which a script cannot do. -->

Start a subagent with the Agent tool, `subagent_type` `flywheel:cold-reader`.
Give it this prompt and nothing else: no summary of the work, no issue, no
file paths. Put the title in place of `<the title>`, and the draft in place
of `<the draft>`, exactly as the file holds it.

```text
You are reviewing a pull request description for an owner who reads it
without having seen the work. Treat the owner as an engineer who knows the
project's languages and tools, git and GitHub. The owner does not know the
terms that the project's specs, scripts or skills give their own meaning, or
the vocabulary the change introduced. Do not read any file or run any tool.
Use only the text below.

Reply in exactly this form:

SUMMARY: <in your own words: who meets this change, and what it changes for
them>

BLOCKING:
- <term>: <the sentence it first appears in>

BORDERLINE:
- <term>: <the sentence it first appears in>

List each word or phrase the description uses with a meaning the owner would
have to guess, and that the description does not define where it first uses
it. Put it under BLOCKING when the owner could not follow the change without
it, and under BORDERLINE when the owner could guess it from the text around
it. Write "none" under a heading that lists nothing.

The title:

<the title>

The description:

<the draft>
```

Compare the reply with the change:

- Each term under BLOCKING is explained at its first use by the first of
  step 1's ways that works, or gives way to a plain word.
- A term under BORDERLINE that the text around it already explains stays as
  it is. Give any other the same as a blocking term when one clause does it.
- When the subagent's summary misstates who meets the change or what it
  changes, rewrite the description until a reader without the work would
  state it correctly.

After any revision, go back to step 2, and give the revised draft to a new
subagent. Go on to step 4 only when a subagent lists "none" under BLOCKING
and its summary matches the change.

## Step 4: open the pull request
<!-- spec: prskill-opens-through-script, propen-cmd-refuses-failing-draft, propen-cmd-opens-from-file -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" pr open --title "<the title>" --body-file /var/folders/k2/T/pr-x8q1zv.md --json
```

It checks the file again, pushes the branch and opens the pull request
against the repository's default branch. When it exits 1, the draft changed
after step 3 and fails the check, so go back to step 2. When it exits 2, its
message names what to do.

On exit 0, tell the owner `data.url`, and the issue the pull request closes.

---
name: open-pr
description: Open a pull request once its work is committed, with a description in the project's own shape that the owner can review without the session's context. Uses scripts/flywheel.py pr draft for the shape and a file to draft in, pr check to check the draft's sections, lines and Closes line, gives the draft to a subagent that has none of the session's context to find each term it leaves undefined, hands it at the same time to the skill the pull request template names to check it against the project's prose rules, and opens the pull request with pr push and the session's own gh pr create from the checked file. Claude Code only. Use when opening, creating or raising a pull request, or when asked to put the work up for review, in a project that has no skill of its own for opening one.
---

# Open a pull request

The owner reviews a pull request from its description, and is its first
reader. The project sets the description's **shape**: the sections it holds,
in order, the subsections under each, and the one section that names the
requirement ids. merge-check and the reviewer read the ids from that section,
so a description in another shape is held for the owner.

The agent that writes the description has the change's vocabulary in
context, so a term it leaves undefined still reads as plain to it. This skill
checks the draft, has a reader without that context read it, has the skill
the project names hold it to the project's prose rules, and opens the pull
request from the file those checks saw.

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
`ids`, true for the section that names the requirement ids. `data.prose_rules`
lists the files of the project's prose rules. `data.prose_check` names the
skill that step 3 hands the draft to, to check it against those files, or is
null. Write a `##` heading for each section and a `###` heading for each
subsection, in that order, with what the guidance asks under each. In the section whose `ids` is
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

## Step 3: have the draft read
<!-- spec: prskill-gives-draft-to-cold-reader, prskill-gives-draft-to-style-reader -->
<!-- no-command: platform. The model starts a subagent with the Agent tool and hands the draft to a skill with the Skill tool, which a script cannot do. -->

A **round** is one read of the draft by each of these:

- the **cold reader**, a subagent started with the Agent tool, which lists
  each term the draft leaves undefined.
- the **prose check**, the skill that step 1's `data.prose_check` names,
  called with the Skill tool. It runs the patterns of the project's prose
  rules and reads the draft against every rule. A **pattern** is a regular
  expression in a rule that finds a likely breach without a reader. A round
  has no prose check when `data.prose_check` is null, or when the session's
  skills do not include the one it names.

Start the cold reader and call the skill in one message, so that both read
the same draft at once. The skill runs in the session while the subagent
reads.

### The cold reader

Start it with `subagent_type` `flywheel:cold-reader`, and the prompt below.
Give it nothing else: no summary of the work, no issue, no file paths. Put
the title in place of `<the title>`, and the draft in place of `<the draft>`,
exactly as the file holds it.

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

### The prose check

Hand the draft to the skill that `data.prose_check` names. Pass these in its
arguments:

- the draft's path, exactly as step 1 printed it.
- each path from `data.prose_rules`.
- the checkout's root and branch.
- after a revision, the line numbers and text of each line that the
  revision changed, so that the skill checks the rewrites.
- that another reader checks each term the draft leaves undefined, so the
  skill leaves out a breach that asks for a term to be defined or explained.

### The revision

Compare the cold reader's reply with the change:

- Each term under BLOCKING is explained at its first use by the first of
  step 1's ways that works, or gives way to a plain word.
- A term under BORDERLINE that the text around it already explains stays as
  it is. Give any other the same as a blocking term when one clause does it.
- When the subagent's summary misstates who meets the change or what it
  changes, rewrite the description until a reader without the work would
  state it correctly.

Rewrite each sentence that a match or a breach from the prose check falls
in, so that it follows the rule. Leave a sentence as it is only when the
rule's own text shows that the sentence follows it. A term reaches a
revision only from the cold reader's lists, so leave as it is a breach that
asks for a term to be defined or explained.

After any revision, go back to step 2, so that `pr check` checks the revised
draft, then start a new round. Go on to step 4 only when, in one round, the
cold reader lists "none" under BLOCKING, its summary matches the change, and
the prose check leaves every sentence as it is.

## Step 4: open the pull request
<!-- spec: prskill-opens-through-script, prskill-runs-pr-create-itself, prpush-cmd-refuses-failing-draft, prpush-cmd-pushes-checked-draft -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" pr push --body-file /var/folders/k2/T/pr-x8q1zv.md --json && gh pr create --title "<the title>" --body-file /var/folders/k2/T/pr-x8q1zv.md
```

`pr push` checks the file again and pushes the branch. `gh pr create` then
opens the pull request against the repository's default branch, and only
when `pr push` exited 0. Run `gh pr create` in this command and not in a
script, since the desktop app binds a pull request to the session only when
the session's own command runs it. When `pr push` exits 1, the draft changed
after step 3 and fails the check, so go back to step 2. When `pr push` exits
2, its message names what to do. When `gh pr create` fails after `pr push`
exited 0, the branch is pushed and no pull request was opened: relay gh's
error to the owner. When the error says a pull request already exists for
the branch, report that pull request's url instead of opening another.

On success, tell the owner the url that `gh pr create` printed, and the issue the pull request closes.
When `data.prose_rules` names a file and the rounds had no prose check, also
tell the owner that the draft was not checked against the prose rules, and
why: the template names no skill in a `prose-check` line, or the session
does not have the skill it names.

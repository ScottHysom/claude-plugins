---
name: open-pr
description: Open a pull request in this repo once its work is committed, with a description the owner can review without the session's context. Uses .github/scripts/check-pr.py description to check the drafted description opens with its scenario, gives the draft to a subagent that has none of the session's context to find each term it leaves undefined, gives it to a second subagent to find each breach of the prose rules, and opens the pull request with check-pr.py open from the checked file. Use when opening, creating or raising a pull request, or when asked to put the work up for review.
---

# Open a pull request

The owner reviews a pull request from its description, and is its first
reader. The agent that writes the description has the change's vocabulary in
context, so a term it leaves undefined still reads as plain to it. This
skill checks the draft, has a reader without that context read it, has a
second reader hold it to the prose rules, and opens the pull request from the
file those readers saw.

Run every command from the root of the clone, on the branch to open, with the
work committed. Never open a pull request with `gh pr create` directly.

## Step 1: draft the description
<!-- spec: openpr-drafts-description, openpr-drafts-in-own-file, draft-cmd-makes-own-file -->

Write the title as a Conventional Commit subject, as `git log` shows them.

Write the description with the headings CLAUDE.md gives under "Workflow", in
its order: `## Scenario`, `## Change`, `## Requirements` and `## Test plan`.
Follow them with `Closes #N` for the issue the branch works, and end with the
attribution line the session gives for pull requests. Write each paragraph
and each list item on one line, as CLAUDE.md says there. Where a Before or
an After covers more than one behavior, give each behavior as a bullet, with
the After's bullets in the Before's order.

Follow the rules in `.claude/rules/prose-style.md` as you write the draft.
The rules a description most often breaks are judgment rules, which do not have a
pattern a script can match:

- `standing-bullet-over-run`: a run of three or more phrases becomes
  bullets.
- `standing-list-says-any-or-all`: a list of conditions says in its lead-in
  whether any or all must hold.
- `sentences-say-it-once`: a command, a fact or a reason appears in one
  section, such as the After or the Change, and not both.

Explain on first use each term the owner does not know, as
`standing-define-terms` in `.claude/rules/prose-style.md` asks. CLAUDE.md,
under "Workflow", says which terms those are. A plugin's name is not one of
them. Explain a term by the first of these ways that works:

1. Reword the sentence to point back to an earlier sentence that already
   explains the term.
2. Add a qualifier that names the term's kind, where two of a kind meet,
   such as "the Claude Code hook" beside a git hook, or "the implementer
   agent" beside the agent that runs a skill.
3. Define what the term is, in one clause. Say what it does only where the
   Scenario or the Change relies on that.

Make a file for the draft:

```sh
python3 .github/scripts/check-pr.py draft --json
```

`data.path` is a file that no other run is given. Write the draft there, and
name it in every later step by the path exactly as `draft` printed it, never
through `$TMPDIR` or another variable. The commands below show it as
`/var/folders/k2/T/pr-x8q1zv.md`.

```sh
cat > /var/folders/k2/T/pr-x8q1zv.md <<'END'
## Scenario

<who, by role, does what>

### Before

<what happened before the change>

### After

<what happens after it>

## Change

<...>
END
```

## Step 2: check the draft
<!-- spec: openpr-checks-draft, description-cmd-reads-body-file -->

```sh
python3 .github/scripts/check-pr.py description --body-file /var/folders/k2/T/pr-x8q1zv.md --json
```

When it exits 1, its `errors` name each fault. Fix them in the draft and run
it again. When it exits 0, `data.scenario` is the Scenario section as CI
will read it.

## Step 3: have the draft read cold
<!-- spec: openpr-gives-draft-to-cold-reader -->
<!-- no-command: platform. The model starts a subagent with the Agent tool, which a script cannot do. -->

Start a subagent with the Agent tool, `subagent_type` `cold-reader`. That
agent, defined in `.claude/agents/cold-reader.md`, starts without any
CLAUDE.md, rules file or tool. Give it this prompt and nothing else: no
summary of the work, no issue, no file paths. Put the title in place of `<the title>`, and the draft in place
of `<the draft>`, exactly as the file holds it.

```text
You are reviewing a pull request description for an owner who reads it
without having seen the work. Treat the owner as an engineer who knows git,
GitHub, Python, pytest, shell, CI, JSON and Claude Code skills. The owner
knows each of this repository's plugins by name and what it is for. The
owner does not know the terms that a plugin, a spec or a script gives its
own meaning, or the vocabulary the change introduced. Do not read any file
or run any tool. Use only the text below.

Reply in exactly this form:

SCENARIO: <in your own words: who meets this change, what happened before
it, and what happens after it>

BLOCKING:
- <term>: <the sentence it first appears in>

BORDERLINE:
- <term>: <the sentence it first appears in>

List each word or phrase the description uses with a meaning the owner would
have to guess, and that the description does not define where it first uses
it. Put it under BLOCKING when the owner could not follow the scenario or the
change without it, and under BORDERLINE when the owner could guess it from
the text around it. Write "none" under a heading that lists nothing.

The title:

<the title>

The description:

<the draft>
```

Compare the reply with the change:

- Each term under BLOCKING is explained at its first use by the first of
  step 1's ways that works, or gives way to a plain word.
- A term under BORDERLINE that the text around it already explains stays as
  it is. Any other gets the same as a blocking term when one clause does it.
  Otherwise leave it, since each new explanation can bring terms of its own.
- When the subagent's scenario misstates who meets the change, or what
  happens before or after it, the Scenario section is rewritten until a
  reader without the work would state it correctly.

After any revision, go back to step 2, and give the revised draft to a new
subagent. Go on to step 4 only when a subagent lists "none" under BLOCKING and its
scenario matches the change.

## Step 4: have the draft read against the prose rules
<!-- spec: openpr-gives-draft-to-style-reader -->
<!-- no-command: platform. The model starts a subagent with the Agent tool, which a script cannot do. -->

Start a new subagent with the Agent tool, `subagent_type` `general-purpose`.
Give it this prompt and nothing else. Put the title and the draft in place of
`<the title>` and `<the draft>`, exactly as the file holds it.

```text
You are checking a pull request description against this repository's
prose rules. Read `.claude/rules/prose-style.md`, and the section
"Workflow" of `CLAUDE.md`, which gives the description's headings and the
shape of its Before and After. Do not read any other file or run any
other tool.

Read the title and the description against every rule in both. Reply in
exactly this form:

BREACHES:
- <rule id, or "CLAUDE.md Workflow">: "<the sentence, quoted>": <what breaks the rule>

Write "none" under BREACHES when you find no breach.

The title:

<the title>

The description:

<the draft>
```

Rewrite each sentence the reply quotes so that it follows the rule. Leave a
sentence as it is only when the rule's own text shows that the sentence
follows it.

After any revision, go back to step 2: the revised draft is checked, read
cold by a new subagent in step 3, and read here by a new subagent. Go on to
step 5 only when a read here leaves no sentence to rewrite.

## Step 5: open the pull request
<!-- spec: openpr-opens-through-script, open-cmd-refuses-failing-draft, open-cmd-opens-from-file -->

```sh
python3 .github/scripts/check-pr.py open --title "<the title>" --body-file /var/folders/k2/T/pr-x8q1zv.md --json
```

It checks the file again, pushes the branch and opens the pull request
against `main`. When it exits 1, the draft changed after step 4 and fails the
check. Go back to step 2. When it exits 2, its message names what to do.

On exit 0, tell the owner `data.url`, and the issue the pull request closes.

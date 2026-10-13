---
name: open-pr
description: Open a pull request in this repo once its work is committed, with a description the owner can review without the session's context. Uses .github/scripts/check-pr.py description to check the drafted description opens with its scenario, gives the draft to a subagent that has none of the session's context to find each term it leaves undefined, and opens the pull request with check-pr.py open from the checked file. Use when opening, creating or raising a pull request, or when asked to put the work up for review.
---

# Open a pull request

The owner reviews a pull request from its description, and is its first
reader. The agent that writes the description has the change's vocabulary in
context, so a term it leaves undefined still reads as plain to it. This
skill checks the draft, has a reader without that context read it, and opens
the pull request from the file that reader saw.

Run every command from the root of the clone, on the branch to open, with the
work committed. Never open a pull request with `gh pr create` directly.

## Step 1: draft the description
<!-- spec: openpr-drafts-description -->
<!-- no-command: judgment. The model writes the title and the description, and step 2 checks them. -->

Write the title as a Conventional Commit subject, as `git log` shows them.

Write the description with the headings CLAUDE.md gives under "Workflow", in
its order: `## Scenario`, `## Change`, `## Requirements` and `## Test plan`.
Follow them with `Closes #N` for the issue the branch works, and end with the
attribution line the session gives for pull requests.

Define on first use each term the plugin, a spec or a skill gives its own
meaning, as `standing-define-terms` in `.claude/rules/prose-style.md` asks.

Write the draft outside the project:

```sh
cat > "${TMPDIR:-/tmp}/pr.md" <<'END'
## Scenario

<who, by role, does what; what happened before the change; what happens after it>

## Change

<...>
END
```

## Step 2: check the draft
<!-- spec: openpr-checks-draft, description-cmd-reads-body-file -->

```sh
python3 .github/scripts/check-pr.py description --body-file "${TMPDIR:-/tmp}/pr.md" --json
```

When it exits 1, its `errors` name each fault. Fix them in the draft and run
it again. When it exits 0, `data.scenario` is the Scenario section as CI
will read it.

## Step 3: have the draft read cold
<!-- spec: openpr-gives-draft-to-cold-reader -->
<!-- no-command: platform. The model starts a subagent with the Agent tool, which a script cannot do. -->

Start a subagent with the Agent tool, `subagent_type` `general-purpose`.
Give it this prompt and nothing else: no summary of the work, no issue, no
file paths. Put the draft in place of `<the draft>`, exactly as the file
holds it.

```text
You are reviewing a pull request description for an owner who reads it
without having seen the work. Treat the owner as an engineer who knows git,
GitHub, Python, pytest, shell, CI, JSON and Claude Code skills, and does not
know this repository's plugins, specs or scripts. Do not read any file or run
any tool. Use only the text below.

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

The description:

<the draft>
```

Compare the reply with the change:

- Each term under BLOCKING gets a definition at its first use, in one
  clause, or gives way to a plain word.
- A term under BORDERLINE gets the same when one clause does it. Otherwise
  leave it, since each new definition can bring terms of its own.
- When the subagent's scenario misstates who meets the change, or what
  happens before or after it, the Scenario section is rewritten until a
  reader without the work would state it correctly.

After any revision, go back to step 2, and give the revised draft to a new
subagent. Go on to step 4 only when a subagent lists "none" under BLOCKING and its
scenario matches the change.

## Step 4: open the pull request
<!-- spec: openpr-opens-through-script, open-cmd-refuses-failing-draft, open-cmd-opens-from-file -->

```sh
python3 .github/scripts/check-pr.py open --title "<the title>" --body-file "${TMPDIR:-/tmp}/pr.md" --json
```

It checks the file again, pushes the branch and opens the pull request
against `main`. When it exits 1, the draft changed after step 3 and fails the
check. Go back to step 2. When it exits 2, its message names what to do.

On exit 0, tell the owner `data.url`, and the issue the pull request closes.

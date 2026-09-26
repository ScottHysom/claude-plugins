# gitify-cowork-project

This file records what the gitify-cowork-project plugin is for.
SPEC-METHODOLOGY.md, at the repo root, has the grammar of this file and the
steps that add its requirements.

## Out of scope

- Running in Claude Code. The plugin needs a Cowork Project with a connected
  folder.
- Taking over a folder that is already a git repository, which has a history
  of its own.
- Writing documents, or rules about what documents say or how they read. Those
  belong to the project.

## need version-history: Keep a history of a Cowork Project's documents

When a Cowork Project is new or already holds real work, the user wants its
folder under git, so they can see what a document said before and get back
from an edit that went wrong.

Source: README.md, the opening section and "When to use it", and the
gitify-project description.

## need answer-from-history: Ask Claude about the history

When the user wants to know what a document said last week, or when and why a
figure changed, they want Claude to read the history and answer, with nothing
for them to run.

Source: README.md, under "Looking back".

## need review-first-commit: See the first commit before it is made

When the folder goes under git, the user wants Claude to ask about anything
that probably should not be in git, and wants to see every file the first
commit would take before it is made, so large media or exports stay out of the
history.

Source: README.md, under "Setting it up".

## need stop-before-overwrite: Keep the user's files as they are

When the folder is missing, or already has a file with the name of one Claude
would write, the user wants Claude to stop, so nothing of theirs is
overwritten.

Source: README.md, under "Setting it up".

## need versioned-instructions: Put the Project Instructions under version control

When the folder goes under git, the user wants the Project Instructions copied
exactly into `CLAUDE.md`, and the field left with one line that tells Claude to
read it, so the standing instructions have a history like any other file.

Source: README.md, under "Setting it up" and "Changing the standing
instructions", and the gitify-project description.

## need history-skill: Keep the history the same way in every session

When Claude commits or answers about the history, the user wants it to follow
a skill written for the project: how a commit is made from Cowork, commit
messages in the Conventional Commits format with the reasons in the body, and
ISO dates, so the history reads the same whichever session wrote it.

Source: README.md, under "What you get", and the gitify-project description.

## need commit-from-cowork: Commit from a Cowork session

When the user asks Claude to commit what changed, they want Claude to write the
message and leave them one command to run, so the commit is made even though
Claude cannot make it from Cowork.

Source: README.md, under "Committing a change".

## need skill-copy-in-repo: Keep a history of the history skill

When the user changes the history skill, they want the original in the project
folder, committed like any other file, so an edit to the skill can be seen and
undone.

Source: README.md, under "Changing the history skill", and the gitify-project
description.

## need catch-up-with-plugin: Bring a history skill up to the plugin's version

When the plugin changes its history skill template, the user wants Claude to
show which sections of a project's skill differ from it, and carry across only
the ones they agree with, so updating the plugin never rewrites a project's
skill unseen.

Source: README.md, under "Catching up with the plugin", and the gitify-project
description.

## constraint no-commit-from-cowork: Claude cannot make a commit from Cowork

A commit has to run from the user's own terminal.

Source: README.md, under "Committing a change", and COWORK.md.

## constraint instructions-field-closed: Claude cannot write the Project Instructions field

Only the user can change what the field holds.

Source: README.md, under "Setting it up", step 3.

## constraint skill-saved-by-user: Claude can only propose a skill for the account

A skill reaches the user's account only when the user saves it from the review
card, or uploads it under Customize, Skills.

Source: README.md, under "Setting it up", step 2, and "Changing the history
skill".

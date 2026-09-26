# gitify-cowork-project

This file records what the gitify-cowork-project plugin is for.
SPEC-METHODOLOGY.md, at the repo root, has the grammar of this file and the
steps that add its requirements.

## Out of scope

- Running in Claude Code. The plugin needs a Cowork Project with a connected
  folder.
- Taking over a folder that is already a git repository, which has a history
  of its own. The exception is `history-in-git`, which such a folder needs as
  much as one the plugin put under git.
- Writing documents, or rules about what documents say or how they read. Those
  belong to the project. The exception is `history-in-git`, which keeps change
  history out of the documents.
- Conventions for commit messages or dates, such as Conventional Commits or ISO
  dates.

## need version-history: Keep a history of a Cowork Project's documents

When a Cowork Project is new or already holds real work, the user wants its
folder under git, so they can see what a document said before and get back
from an edit that went wrong.

Source: README.md, the opening section and "When to use it", and the
gitify-project description.

## need history-in-git: Leave change history to git

When an agent edits a document in a git-backed Cowork Project, whether or not
the plugin put it under git, the owner wants it to leave the record of the
change out of the document, such as dated sections or "updated on <date>"
notes, and rely on git, so the document holds only what is current. An agent that does not know git is there records the
history in the document instead.

Source: the owner's review of #139.

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

## need commit-from-cowork: Commit from a Cowork session

When the user asks Claude to commit what changed, they want Claude to write the
message and leave them one command to run, so the commit is made even though
Claude cannot make it from Cowork.

Source: README.md, under "Committing a change".

## constraint no-commit-from-cowork: Claude cannot make a commit from Cowork

A commit has to run from the user's own terminal.

Source: README.md, under "Committing a change", and COWORK.md.

## constraint instructions-field-closed: Claude cannot write the Project Instructions field

Only the user can change what the field holds.

Source: README.md, under "Setting it up", step 3.

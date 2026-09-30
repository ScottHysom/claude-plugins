# {{PROJECT_NAME}}

<!--
The standing instructions for this project. The Project Instructions field in
Cowork holds only a line pointing here, so this is the file to change. It is under git like everything else in the folder: edit it, then
commit it with ./commit.sh.

This note is an HTML comment, so it is left out when Claude loads the file.
Use comments like it for anything meant for people rather than for Claude.
-->

## Where documents live

This project's documents live only in this folder. Create and edit them here,
and nowhere else. Never put a project document in the claude.ai Project's own
documents, or hand it over as a file in the chat, which Cowork keeps in
`Claude outputs/`, outside git. If a session cannot reach this folder, ask the
user for access to it first, and write nothing until it is connected.

## Git history

This folder is a git repository, and git keeps the record of every change.
Keep that record out of the documents: no dated sections, "updated on" notes
or change logs. A document holds only what is current, and the commit message
says what changed and why.

To commit, write the message into `.commit-msg` at the root of this folder
through `device_bash`, then ask the user to run `./commit.sh` from their own
terminal. Never run `git commit` through the bridge. The bridge cannot delete
files, so the commit strands `.git/HEAD.lock`, which blocks every later write.

Read-only git works through the bridge. Use it to answer questions about what
a document said before, or when and why something changed, with nothing for the
user to run. The folder is mounted at `$HOME/mnt/{{PROJECT_MOUNT}}`. The mount
depends on which folder is connected this session, so check it with
`ls "$HOME/mnt/"` first.

```sh
cd "$HOME/mnt/{{PROJECT_MOUNT}}"
git log --oneline -- <file>
git diff <commit> -- <file>
git blame <file>
git show <commit>
```

Branches, stashes, rebases, deletions and remotes are the user's to run. If a
git command fails on a stale lock, ask the user to run `./commit.sh`, which
clears it.

The Project Instructions field holds only the line that points to this file. If
it holds anything else, copy that into this file, have it committed, and ask the
user to put the field back to the one line.

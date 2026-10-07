## Git history

This folder is a git repository, and git keeps the record of every change.
Keep that record out of the documents: no dated sections, "updated on" notes
or change logs. A document holds only what is current, and the commit message
says what changed and why.

Never run `git commit`, or any other git command that writes, through the
bridge. The bridge cannot delete files, so the command strands a lock file in
`.git`, which blocks every later write. When a change is ready, give the user
the commit message and ask them to commit from their own terminal.

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
git command fails on a stale lock, ask the user to delete the lock file named
in the error from their own terminal.

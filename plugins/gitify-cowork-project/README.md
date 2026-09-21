# Gitify Cowork Project

Puts a Cowork Project folder you have already been working in under git,
without touching what is in it.

**Cowork only.** It writes to your computer through Cowork's device bridge and
registers a skill through the in-conversation review card. Neither exists in
Claude Code.

## The problem it solves

A Cowork Project usually starts in the app. You work in it for a while, and
only then want history: what a document said last week, why a figure changed,
a way back from an edit that went wrong. By then the folder holds real work,
and the project has settled how its documents are written.

This plugin adds the history and nothing else. It writes no documents and no
rules about what documents say or how they read. Those are the project's own,
and it has already made them.

## What you get

```
<Your Project>/
  (everything already there, untouched)
  .gitignore
  commit.sh                    clears the lock the bridge strands, then commits
  setup.sh                     one time: git init and the first commit
  CLAUDE.md                    the Project Instructions, now under version control
  skills/
    <project>-history/
      SKILL.md                 generated for this project, then registered
```

The generated skill is about history only: committing through a bridge that
cannot delete files, Conventional Commit messages with the reasons in the body,
ISO dates, and keeping the registered skill and the repo copy the same.

## Using it

Install the plugin from the marketplace, then ask Claude to put the project
under git. The skill calls `scripts/gitify.py`, which a skill saved on its own
through the review card would not have.

Claude checks the folder first. It stops if the folder is not there, is
already a git repo, or already has a file with the same name as one of the five
it would write. It lists what is in the folder and asks about anything that
probably should not be in git, such as large media or exports.

Then it leaves you what the bridge cannot do:

1. **Run `sh setup.sh` from your own terminal.** This stages every file in the
   folder and commits nothing. It lists what the first commit would take. Add
   a pattern to `.gitignore` for anything that should stay out, run
   `sh setup.sh` again to see the new list, and when the list is right run
   `sh setup.sh commit`. `sh`, because files written through the bridge lose
   their execute bit; `setup.sh` restores it.
2. Save the proposed skill from the review card.
3. Replace the Project Instructions field with the one line Claude gives you.

## One place for standing instructions

A Cowork Project's instructions field is not versioned, and a copy of it in the
folder drifts from it the first time either is edited. So the field's content
moves into `CLAUDE.md` at the root of the folder, copied exactly, and the field
is left holding one line that points there. That line never needs to change,
so there is nothing left to drift.

Claude cannot write the field itself. That is why replacing it is your step.

Whether Cowork reads a `CLAUDE.md` at the root of a connected folder by itself
is not documented. It has not been tested yet either. Until it is, the pointer
line tells Claude to read the file first, which works whether Cowork loads it or
not.

## Prose and document rules

This plugin writes none. A project that wants a house style can add one
separately; the `prose-tuning` plugin learns one from edits you have already
made.

## Why `commit.sh` exists

Cowork's bridge cannot delete files. Every `git commit` it attempts leaves a
`.git/HEAD.lock` behind, and that lock blocks every later write to the repo.
`commit.sh` clears the debris and makes the commit. Read-only git works fine
from the bridge, so Claude can still run `log`, `diff`, `blame` and `show`.

`commit.sh` refuses to make the first commit. That one is `setup.sh`'s, because
it shows you what it is about to take.

## Relation to cowork-project-scaffold

The script and templates here started as a copy of the `cowork-project-scaffold`
plugin's, adapted. That is deliberate: plugins install separately and cannot
share code. The two will diverge. `cowork-project-scaffold` builds a new
project and decides how its documents are written, and it is expected to be
retired once this plugin has been run end to end.

## Editing the templates

Everything this plugin writes lives in `skills/gitify-project/templates/`.
Change a file there, bump the version as the repo's
[README](https://github.com/ScottHysom/claude-plugins#versioning) describes, and
reinstall.

`{{NAME}}` is a placeholder. A new template file also needs a line in
`MANIFEST` in `scripts/gitify.py`, which says where it lands in the project.
`python3 scripts/gitify.py preflight` checks all of it.

Changing a template does not change projects already set up. Each project's
skill is its own copy from then on.

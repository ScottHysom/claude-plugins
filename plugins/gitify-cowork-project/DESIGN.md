# Gitify Cowork Project: technical design

This file explains why gitify-cowork-project is built the way it is, and how
to change what it writes. Cowork is the Claude desktop app's mode for working
in a folder on the user's computer.
[README.md](https://github.com/ScottHysom/claude-plugins/blob/main/plugins/gitify-cowork-project/README.md)
covers using it. What Cowork allows a plugin in general is in
[Designing for Cowork](https://github.com/ScottHysom/claude-plugins/blob/main/COWORK.md).

## Why it runs only in Cowork

The plugin depends on Cowork's device bridge, which Claude Code does not have.
Cowork runs Claude in a cloud container, which cannot see the user's computer.
The device bridge is the set of tools, such as `device_bash` and
`device_commit_files`, through which Claude reads and writes the connected
folder on that computer. Every file the plugin writes reaches the project this
way.

## The bundled script

A skill is a set of instructions Claude follows for one kind of task, and a
plugin bundles skills with the scripts they call. The `gitify-project` skill
calls `scripts/gitify.py` for everything that should come out the same on every
run. `propose_skills`, the tool through which Claude offers a skill for the
user to save to their account, takes a single `SKILL.md` and no other files. A
copy of `gitify-project` saved on its own that way therefore has no script to
call. A plugin installed from the marketplace, the catalog Cowork installs
plugins from, brings its skills together with its scripts. So the plugin needs a marketplace install, and the
skill's first step says so and stops when the script is missing.

## One place for standing instructions

A Cowork Project's instructions field is not versioned, and a copy of it in the
folder drifts from it the first time either is edited. So the field's content
moves into `CLAUDE.md` at the root of the folder, copied exactly, and the field
holds one line that points there. That line never needs to change, so there is
nothing left to drift.

The note at the top of `CLAUDE.md` says how the file works. It is an HTML
comment on lines of its own, which Cowork leaves out when it loads the file, so
it does not cost any context.

Claude cannot write the field itself. That is why replacing it is the user's
step.

Cowork adds the field to every conversation in the project, so anything left
in it costs context every time. The line stays even though Cowork also loads
the connected folder's `CLAUDE.md` by itself. The field
reaches every conversation from its start, so the line gets `CLAUDE.md` read
wherever Cowork's own loading does not. What Cowork loads, and when, is in
[Designing for Cowork](https://github.com/ScottHysom/claude-plugins/blob/main/COWORK.md#how-instruction-files-load).

A session started from the Claude mobile app gets the field but not the
folder, so `CLAUDE.md` is out of reach there. The line therefore also says the
project's documents live only in that folder, and tells Claude to ask for
access to it and never to write them anywhere else. Without that, Claude saves
lasting work to the claude.ai Project's own documents, outside git and apart
from the rest. `CLAUDE.md` repeats the rule in a section of its own, for a
session that has the folder.

## How Claude learns the folder is under git

A section of `CLAUDE.md` tells Claude that git keeps the history, so change
records stay out of the documents. It also says how a commit is made from
Cowork, how to read the history, and what to do when the Project Instructions
field holds more than its one line. The field's line gets `CLAUDE.md` read in
every conversation, so the section needs nothing registered on the account and
has no second copy to keep in step. It sits outside the note's HTML comment,
because Claude never sees what is inside one.

A folder that is already a git repo gets only this section, from
`templates/git-history.md`, appended to its root `CLAUDE.md` by
`gitify.py history`. The repo is the user's, so the plugin does not write
`commit.sh` there, and the section asks the user to make the commit instead.
The section is appended on the device with a heredoc rather than copied by
`device_commit_files`, which can only replace a whole file. The command
checks the bytes it appended, and does nothing when a `## Git history` line is
already there. Cowork loads only the connected folder's own `CLAUDE.md`, so
`history` takes the connected folder and nothing inside it.

## Why `commit.sh` exists

The device bridge cannot delete files. While git updates a branch it holds a
lock file, `.git/HEAD.lock`, and deletes it when it finishes. Every
`git commit` the bridge attempts therefore leaves that lock behind, and the
lock blocks every later write to the repo. `commit.sh`, run from the user's own
terminal, clears the stranded locks and makes the commit. Read-only git works
fine from the bridge, so Claude can still run `log`, `diff`, `blame` and
`show`.

`commit.sh` refuses to make the first commit. That one is `setup.sh`'s, because
it shows the user what it is about to take.

Files written through the bridge lose their execute bit. The user runs
`setup.sh` with `sh` for that reason, and `setup.sh` sets the bit on both
scripts before git records them. Its own header comment explains why each run
empties the index before staging again.

## Editing the templates

Everything this plugin writes lives in `skills/gitify-project/templates/`.
Change a file there, bump the version as the repo's
[README](https://github.com/ScottHysom/claude-plugins#versioning) describes, and
reinstall.

A placeholder is written `{{NAME}}`, as in `{{PROJECT_NAME}}`. A new template
file also needs a line in `MANIFEST` in `scripts/gitify.py`, which says where
it lands in the project. `python3 scripts/gitify.py preflight` checks all of
it.

Changing a template does not change projects already set up. Each project's
`CLAUDE.md` is its own from then on.

# Gitify Cowork Project: technical design

This file explains why gitify-cowork-project is built the way it is, and how
to change what it writes.
[README.md](https://github.com/ScottHysom/claude-plugins/blob/main/plugins/gitify-cowork-project/README.md)
covers using it. What Cowork allows a plugin in general is in
[Designing for Cowork](https://github.com/ScottHysom/claude-plugins/blob/main/COWORK.md).

## Why it runs only in Cowork

The plugin depends on two things Cowork has and Claude Code does not:

- **The device bridge.** Cowork runs Claude in a cloud container, which cannot
  see the user's computer. The device bridge is the set of tools, such as
  `device_bash` and `device_commit_files`, through which Claude reads and
  writes the connected folder on that computer. Every file the plugin writes
  reaches the project this way.
- **The review card.** When a skill calls `propose_skills`, Cowork shows the
  user a card in the conversation, and saving it registers the proposed skill
  on the user's account. That is how the generated `<project>-history` skill
  comes to run.

## The bundled script

The `gitify-project` skill calls `scripts/gitify.py` for everything that should
come out the same on every run. `propose_skills` takes a single `SKILL.md` and
no other files. A copy of `gitify-project` saved on its own through the review
card therefore has no script to call. The plugin needs a marketplace install,
and the skill's first step says so and stops when the script is missing.

## One place for standing instructions

A Cowork Project's instructions field is not versioned, and a copy of it in the
folder drifts from it the first time either is edited. So the field's content
moves into `CLAUDE.md` at the root of the folder, copied exactly, and the field
holds one line that points there. That line never needs to change, so there is
nothing left to drift.

The note at the top of `CLAUDE.md` says how the file works. It is an HTML
comment on lines of its own, which Cowork leaves out when it loads the file, so
it costs no context.

Claude cannot write the field itself. That is why replacing it is the user's
step.

Cowork adds the field to every conversation in the project, so anything left
in it costs context every time. The line stays even when the project is the
connected folder, whose `CLAUDE.md` Cowork also loads by itself. The field
reaches every conversation from its start, so the line gets `CLAUDE.md` read
wherever Cowork's own loading does not. What Cowork loads, and when, is in
[Designing for Cowork](https://github.com/ScottHysom/claude-plugins/blob/main/COWORK.md#how-instruction-files-load).

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
skill is its own copy from then on, and `gitify.py drift` compares one against
the template.

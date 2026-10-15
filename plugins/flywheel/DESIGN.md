# flywheel: technical design

This file explains why the flywheel plugin is built the way it is, for a
contributor changing it. What the plugin does and how to use it is in
[README.md](README.md). The requirements it serves are in `specs/flywheel.md`,
at the repo root.

## Origin

The owner ran the issue loop by hand: three desktop sessions a round, each
started with its model and effort chosen, told when CI failed or a review
landed, and told when its pull request merged. The parts a script or a skill
could do lived in this repo's `.github/scripts/issues.py` and its
`.claude/skills/`, which no other repo can install. Tracking issue #653 plans
the move into this plugin, one piece per issue. #643 made the plugin exist
with its script's first two commands.

## The copy in `.flywheel/`

`setup` copies `flywheel.py` into the project for the reason todos and
prose-tuning do: each Bash call starts a fresh shell, and the plugin's install
path is too long to repeat in every command. It also copies the roles template
and `plugin.json` beside the script, so the copy can run `config init` and
read the plugin's version without reaching back into the plugin.

The `.gitignore` that `setup` writes names those copies and itself, rather
than `*` as todos does. `.flywheel/` also holds what the owner sets and
commits, starting with `roles.json`.

## The method's docs

`docs/` holds the method the loop follows, copied from the Cowork project
where it was first written, at that project's commit 940ae7a. That project
stays as the archive, with its history, its notes and its own skills; the
plugin is now where the method changes. Its ids become stable once a repo
records an adopted version, and the plugin's version is that version.

`ids` checks that every id the plugin's templates and skills, and
`specs/flywheel.md`, cite as the method's is one the docs define. It reads
the docs from the plugin, so it does not run from the copy in `.flywheel/`.
The script's docstring has the citation form it reads.

## The roles file

A role maps to a tier from the method's roles.md, and the tier is fixed. The
model behind a tier, and its default effort, come only from the owner, so
the template leaves them null and `config init` names each null field it
writes. `config init` fills in the plugin version, so a later version can tell
which template a roles file came from.

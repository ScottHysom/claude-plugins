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
with its script's first two commands, and #645 moved the queue and the claim
lock in from `issues.py`.

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

## The lock

The claim on issue N is the branch `issue/N` on origin, created by a push
that only one claimant can win. flywheel.py's docstring has why the push uses
an empty lease and reads porcelain output rather than its exit code.

Some of the requirements on the lock stay in `specs/repo.md`: the ones this
repo's own CI, hooks and CLAUDE.md meet, since `check-specs.py trace` ties a
repo test or workflow step to `specs/repo.md` only. Those needs appear in both
files, each holding the requirements its side meets.

`queue --tracking N` still names `issues.py plan close` for a finished plan,
until #647 moves the plan commands here.

## The brief

`brief` reads the issue through GitHub's GraphQL API, since only that reports
when the body was last edited and when each label was added. It refuses an
issue edited after `approved` was last added, as `check-specs.py changes`
does for the issues a pull request closes. Agents post under the owner's
account, so `brief` tells the owner's comments from an agent's by the
`**Claude:**` opening that CLAUDE.md asks an agent's comment to carry.

The gate commands live in `.flywheel/gates.json` rather than in the roles
file, since a role is a model choice and a gate is the project's own command.

## The implementer's skill

work-issue is the session a brief starts, and the one a request for "the next
issue" runs. It runs the gate command from `.flywheel/gates.json` itself
rather than through the script, since the command is the project's and a
skill fence runs only the plugin's script. It opens the pull request through
whichever installed skill says it opens one, so a project keeps its own
description rules and the skill names no other plugin.

The watch it turns on is the desktop app's per-session CI monitor, which only
the session's own `set_monitor` tool reaches. #305 found Auto-fix off on
every new pull request, so the skill turns it on rather than leaving it to
the owner.

A lost claim moves on only for an issue the queue offered. One the owner
named stays the owner's to redirect.

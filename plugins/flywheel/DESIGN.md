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

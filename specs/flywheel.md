# flywheel

This file records what the flywheel plugin is for. SPEC-METHODOLOGY.md, at
the repo root, has the grammar of this file and the steps that add its
requirements.

## Out of scope

- Running the loop outside the Claude desktop app. The dispatcher starts its
  sessions through the app.
- Running in Cowork, the Claude desktop app's mode for a user's own files. The
  loop needs Claude Code and a clone with a GitHub remote.
- Issue trackers other than GitHub's.
- Choosing the model behind a role. Only the owner fills it in.

## need owner-installs-loop-as-plugin: Install the issue loop as a plugin

When the owner wants the issue loop in a repo, they want to install one plugin
that carries its script, skills, rules and docs, so the repo adopts it as it
adopts any other plugin.

Source: #643, and the method's `match-capability-to-task` and
`scripts-do-deterministic-work`.

- `setup-cmd-copies-script` (test): When `flywheel.py setup` runs in a
  project, it copies the script to `.flywheel/` beside a `.gitignore` that
  keeps it out of every commit, and prints the prefix later commands start
  with.
- `configinit-cmd-writes-roles-file` (test): When `flywheel.py config init`
  runs, it writes `.flywheel/roles.json` from the plugin's template with one
  entry per role, and refuses to overwrite one that exists.
- `configinit-cmd-names-owner-fields` (test): When `config init` writes a file
  with a field only the owner can fill, it names each such field in its
  result.

## need contributor-reads-method-beside-plugin: Read the method beside the plugin

When a contributor or an adopting owner reads a principle id in a spec, a
template or a skill, they want to open the document that defines it from the
same install, so the id is a definition and not a pointer to another repo.

Source: #644, and the method's `one-home-per-artifact`.

- `ids-cmd-fails-unknown-id` (test): When `flywheel.py ids` finds a principle
  or stage-rule id cited in the plugin's templates, skills or
  `specs/flywheel.md` that no document under `docs/` defines, it names it and
  exits 1.

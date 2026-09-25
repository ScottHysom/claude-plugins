# repo

This file records what the repository as a whole is for: its catalog, its
checks and the conventions every plugin script shares. SPEC-METHODOLOGY.md, at
the repo root, has the grammar of this file and the steps that add its
requirements.

## Out of scope

- Code shared between plugins. Each plugin installs on its own and cannot
  import another's.
- Packages outside the Python standard library in a plugin script.
- Contributor-only files, such as tests and specs, inside an install.

## need model-at-seams: Keep the model to judgment and platform seams

When a skill runs script commands, the owner wants the model between two of
them only where it makes a judgment or calls a tool no script can, so no run
spends context on work a script could do, or gets that work wrong.

Source: #126, and CLAUDE.md, under "Skills and scripts".

## need shared-flags: Read every script's flags the same way

When a contributor runs or writes a repo script, they want the flags every
command takes, `--json`, `-C/--repo`, `--dry-run` and `--partial`, to mean the
same thing in each script, so a skill can read any result and preview or batch
any change the same way.

Source: CLAUDE.md, under "Script conventions".

## need install-from-marketplace: Install any plugin from one marketplace

When the user wants one of the owner's plugins, they want to add the
marketplace once and install any plugin listed in it, so each plugin needs no
setup of its own.

Source: README.md, under "Adding this marketplace".

## need surface-stated: Know which surface a plugin needs before installing it

When the user chooses a plugin, they want its description to say whether it
needs Cowork, Claude Code or either, so a plugin installed on the wrong surface
does not fail confusingly.

Source: README.md, the opening section, and "Adding a plugin", step 3.

## need owner-approves-work: Work only on what the owner approved

When an issue is filed, the owner wants to decide whether it gets worked on,
so an agent posting under the owner's account cannot approve its own work.

Source: README.md, under "Issues" and "Keeping `approved` meaningful".

## need one-claim-per-issue: Keep two agents off the same issue

When two agents are told to take the next issue at the same time, the owner
wants each to get a different one, so no two agents do the same work.

Source: README.md, under "Claiming an issue".

## need skills-match-scripts: Catch a skill that names a missing command

When a contributor renames a script's subcommand or flag, they want CI to fail
every skill that still names the old one, so the failure shows in the pull
request rather than part way through a user's run.

Source: README.md, under "Adding a plugin", step 4.

## need cowork-accepts-description: Keep every skill uploadable to Cowork

When a contributor writes a skill's description, they want CI to fail one that
Cowork's `.plugin` upload would reject, so the user can install the plugin on
Cowork even though a marketplace install and `--strict` accept it.

Source: README.md, under "Adding a plugin", step 4.

## need manifests-agree: Keep the two manifests in step

When a contributor bumps a plugin's version or edits its manifest, they want
CI to fail a catalog entry that disagrees with the plugin's own manifest, so
two files that each validate cannot drift apart.

Source: README.md, under "Adding a plugin", step 4.

## need edit-from-cowork: Commit this repo from a Cowork session

When the owner edits this repo from Cowork, they want to commit from their own
terminal with the message the session wrote, so a lock file the device bridge
strands does not block the commit.

Source: README.md, under "Editing this repo from Cowork".

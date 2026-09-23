---
name: gitify-project
description: Put an existing Cowork Project folder under git - commit.sh, setup.sh, .gitignore, a CLAUDE.md holding the Project Instructions, and a generated per-project history skill that is written into the repo and then proposed to the account. Use when a Cowork Project that already has documents needs version history, when asked to git-back, gitify or add git to a project folder, or to move the Project Instructions into a versioned file. Writes nothing about what the documents say. Also covers checking whether a project's history skill has fallen behind the template.
---

# Putting an existing Cowork Project under git

Requires Cowork with a connected folder. This skill writes to the user's device
through the bridge (`device_bash`, `device_commit_files`) and registers a skill
through `propose_skills`. Neither exists in Claude Code. If the bridge is not
available, say so and stop rather than building the files somewhere they cannot
reach.

The folder already holds the user's work. This skill adds git and nothing else:
it writes no document, and no rule about what documents say or how they read.
Do not offer to add any.

## What this produces

1. Five files in the folder: `.gitignore`, `commit.sh`, `setup.sh`,
   `CLAUDE.md`, and a **per-project history skill** at
   `skills/<skill-name>/SKILL.md`. That file is the versioned original.
2. The **same skill text registered on the account**, via `propose_skills`.
3. A repo, once the user runs `setup.sh` from their own terminal.

Writing the skill file does not install anything: the synced copy on disk is a
read-only cache. Step 5 is what makes the skill run, and skipping it fails
silently.

## Where things run

`gitify.py` does everything that should come out the same on every run. It
runs in **your own shell**, the container, which can read the plugin but
cannot see the user's folder. `device_bash` can see the folder but cannot read
the plugin. The commands `probe` and `render` print bridge the two; do not
retype file contents across them.

## Locate the script

```sh
GITIFY="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}/scripts/gitify.py"
python3 "$GITIFY" preflight
```

- **0**: the templates are complete. Go on.
- **1**: a template is malformed. This is a bug in the plugin; show the user
  the errors and stop.
- **No such file**: the skill was installed without its plugin, for example
  through `propose_skills`. It needs a marketplace install. Say so and stop.

## Step 1: find the folder, and look at it

Call `get_device_info`. `connected_folder` is one of its `connectedFolders`,
exactly as listed. The project folder is the connected folder itself, or a
folder inside it; ask the user which when it is not obvious.

```sh
python3 "$GITIFY" probe --connected-folder "<connected>" [--project-folder "<project>"] --json
```

Exit 1 means one of the paths breaks a rule; `errors` says which. Otherwise run
`data.probe_command` through `device_bash`:

- **2, `missing:`**: the folder is not there. Stop and check the path with the
  user. Do not go on, because `device_commit_files` would create it.
- **1, `repo:`**: the folder is already a git repo. Stop. This skill starts
  git history; it does not adopt a repo that already has some.
- **0**: it prints `files:` with a count, an `entry:` line for each top-level
  entry, and a `large:` line for each file over 10 MB.

Read the listing for things that probably should not be in git: large media,
exports, archives, caches, anything that looks private. Ask the user about each
one you find. Patterns they agree to go in `ignore` below. They get a second
chance at `setup.sh`, which shows every file before anything is committed.

## Step 2: the answers

Write `/tmp/gitify/answers.json`, after `mkdir -p /tmp/gitify`:

```json
{
  "connected_folder": "<as listed>",
  "project_folder": "<the project folder, or null>",
  "values": {
    "PROJECT_NAME": "Foo Research",
    "SKILL_NAME": "foo-research-history",
    "DESCRIPTION": "..."
  },
  "instructions": "<the Project Instructions field, verbatim, or null>",
  "ignore": ["exports/", "*.mov"]
}
```

- `PROJECT_NAME`: the project's display name.
- `SKILL_NAME`: **the project's name**, as `<project>-history`. A generic name
  invites a generic description.
- `DESCRIPTION`: the history skill's description. It is the only part of a
  skill that costs context in every session whether or not it fires, and the
  only thing that keeps it from firing in unrelated conversations. Name the
  project, and what the skill covers in the words a user would use: committing,
  commit messages, checking what changed, the skill's own drift check. No
  generic verbs on their own; "commit changes" fires everywhere. No `<`
  followed by a word, as in `<ins>`: Cowork's plugin upload reads it as an
  XML tag and rejects the skill.
- `instructions`: when this Project's instructions field has content, which
  you can see in your own context, copy it here **exactly**, character for
  character. Do not tidy, summarize or reformat it; it becomes `CLAUDE.md`.
  `null` when the field is empty.
- `ignore`: the patterns from step 1, or `[]`.

`PROJECT_PATH` and `PROJECT_MOUNT` are worked out from the folders. Do not
pass them.

## Step 3: render

```sh
python3 "$GITIFY" render --answers /tmp/gitify/answers.json --json
```

- **0**: every file is staged under `/mnt/user-data/outputs/`.
- **1**: `errors` names every problem. Nothing was written. Fix `answers.json`
  and run it again.
- **2**: the stage directory holds files from something else. Pass
  `--stage /mnt/user-data/outputs/<new directory>`.

`--dry-run` checks the answers without writing.

## Step 4: copy the files onto the device

Take each value from `render`'s `data`, as printed:

1. Run `precheck_command` through `device_bash`. It prints `clear` and exits 0
   when nothing would be overwritten. Anything else is a hard stop: `exists:`
   names a file this would overwrite, and `repo:` and `missing:` mean what they
   meant in step 1. Tell the user and stop. Do not rename, move or merge their
   file to make room.
2. Call `device_commit_files` with `files` set to `commit_files`. Its
   `rejected` list must come back empty.
3. Run `check_command` through `device_bash`. Every line must end `OK`. A line
   ending `FAILED` means that file did not arrive intact: copy it again with
   `device_commit_files`, never by editing it on the device.

Do not `git init`. Step 6 covers why.

## Step 5: register the skill

Read the staged skill, the entry in `files` whose `file` ends in `SKILL.md`,
from its `staged_path`. Call `propose_skills` with exactly that text. Same
name, same description, same body. The user saves it from the review card.

The two copies have to match. If they diverge, the repo looks authoritative and
the account copy is what actually runs. The generated skill carries its own
drift check.

## Step 6: hand off

The bridge cannot complete a `git commit`; the plugin's DESIGN.md, under "Why
`commit.sh` exists", says why. So tell the user to run, from their own
terminal:

```
cd "<project folder>" && sh setup.sh
```

Say what it does, because it is not what they may expect: it stages every file
in the folder and **commits nothing**. It lists the files the first commit
would take. They add a pattern to `.gitignore` for anything that should stay
out, run `sh setup.sh` again to see the new list, and when it is right run
`sh setup.sh commit`. Do not run any of it from here, and do not offer to.

Then name what else only the user can do:

- Save the proposed skill from the review card.
- Change the Project Instructions field. You cannot write it. `CLAUDE.md` now
  holds what was there, and the field keeping a copy is how the two drift
  apart. They replace everything in the field with `data.field_pointer`,
  exactly, even when the project is the connected folder. The field reaches
  every conversation from its start, so this line gets `CLAUDE.md` read
  wherever Cowork's own loading of the file does not reach. COWORK.md, in the
  claude-plugins repo, under "How instruction files load", has what Cowork
  loads and when.

## Checking a project's skill against the template

To check whether a project's history skill has fallen behind, stage it with
`device_stage_files`, then:

```sh
python3 "$GITIFY" drift --skill <staged SKILL.md> --json
```

- **0**: every section matches the template. Substituted names and rewrapped
  lines do not count.
- **1**: `data.sections` marks each `changed` section with a `diff`, and each
  `missing` one. Show the user those, and carry across only what they agree is
  universal. A `project-only` section is the project's own and is not a
  problem.

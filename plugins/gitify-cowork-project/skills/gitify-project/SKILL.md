---
name: gitify-project
description: Put an existing Cowork Project folder under git, writing commit.sh, setup.sh, .gitignore, and a CLAUDE.md holding the Project Instructions and how Claude commits and reads the history. Use when a Cowork Project that already has documents needs version history, when asked to git-back, gitify or add git to a project folder, or to move the Project Instructions into a versioned file. Writes nothing about what the documents say.
---

# Putting an existing Cowork Project under git

Requires Cowork with a connected folder. This skill writes to the user's device
through the bridge (`device_bash`, `device_commit_files`), which Claude Code
does not have. If the bridge is not available, say so and stop rather than
building the files somewhere they cannot reach.

The folder already holds the user's work. This skill adds git and nothing else:
it writes no document, and no rule about what documents say or how they read.
Do not offer to add any.

## What this produces

1. The files in the folder: `.gitignore`, `commit.sh`, `setup.sh` and
   `CLAUDE.md`.
2. A repo, once the user runs `setup.sh` from their own terminal.

## Where things run

`gitify.py` does everything that should come out the same on every run. It
runs in **your own shell**, the container, which can read the plugin but
cannot see the user's folder. `device_bash` can see the folder but cannot read
the plugin. The commands `probe` and `render` print bridge the two; do not
retype file contents across them.

## Locate the script

```sh
mkdir -p /tmp/gitify && ln -sfn "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}" /tmp/gitify/plugin && GITIFY=/tmp/gitify/plugin/scripts/gitify.py && python3 "$GITIFY" preflight
```

This links the plugin at `/tmp/gitify/plugin`, a path short enough to repeat.
Each call to your shell starts afresh, so every later command sets `GITIFY`
again in front, as the steps below show. A command without it runs
`python3 ""`, which fails with "can't find '__main__' module" and names no
script.

- **0**: the templates are complete. Go on.
- **1**: a template is malformed. This is a bug in the plugin; show the user
  the errors and stop.
- **No such file**, from `ln` or `python3`: the skill was installed without its plugin, for example
  through `propose_skills`. It needs a marketplace install. Say so and stop.

## Step 1: find the folder, and look at it
<!-- spec: probe-command-lists-folder, probe-command-stops-on-missing-folder, probe-command-stops-on-existing-repo, gitifyproject-asks-about-unwanted-files -->

Call `get_device_info`. `connected_folder` is one of its `connectedFolders`,
exactly as listed. The project folder is the connected folder itself, or a
folder inside it; ask the user which when it is not obvious.

```sh
GITIFY=/tmp/gitify/plugin/scripts/gitify.py && python3 "$GITIFY" probe --connected-folder "<connected>" [--project-folder "<project>"] --json
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
<!-- spec: gitifyproject-copies-field-exactly, render-command-appends-ignore-patterns -->

<!-- no-command: judgment. The model writes the project name and the ignore list, and step 3's render checks them. -->

Write `/tmp/gitify/answers.json`, in the directory the "Locate the script"
step made:

```json
{
  "connected_folder": "<as listed>",
  "project_folder": "<the project folder, or null>",
  "values": {
    "PROJECT_NAME": "Foo Research"
  },
  "instructions": "<the Project Instructions field, verbatim, or null>",
  "ignore": ["exports/", "*.mov"]
}
```

- `PROJECT_NAME`: the project's display name.
- `instructions`: when this Project's instructions field has content, which
  you can see in your own context, copy it here **exactly**, character for
  character. Do not tidy, summarize or reformat it; it becomes `CLAUDE.md`.
  `null` when the field is empty.
- `ignore`: the patterns from step 1, or `[]`.

`PROJECT_MOUNT` is worked out from the folders. Do not pass it.

## Step 3: render
<!-- spec: render-command-stages-files, repo:script-checks-every-answer -->

```sh
GITIFY=/tmp/gitify/plugin/scripts/gitify.py && python3 "$GITIFY" render --answers /tmp/gitify/answers.json --json
```

- **0**: every file is staged under `/mnt/user-data/outputs/`.
- **1**: `errors` names every problem. Nothing was written. Fix `answers.json`
  and run it again.
- **2**: the stage directory holds files from something else. Pass
  `--stage /mnt/user-data/outputs/<new directory>`.

`--dry-run` checks the answers without writing.

## Step 4: copy the files onto the device
<!-- spec: gitifyproject-stops-on-precheck, gitifyproject-recopies-failed-files, check-command-names-damaged-copies -->

<!-- no-command: hand-off to the device bridge. device_bash and device_commit_files run what render printed. -->

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

Do not `git init`. Step 5 covers why.

## Step 5: hand off
<!-- spec: gitifyproject-hands-off-setup, gitifyproject-hands-off-field-line -->

<!-- no-command: hand-off to the user. The bridge cannot commit, so the user runs setup.sh. -->

The bridge cannot complete a `git commit`; the plugin's DESIGN.md, under "Why
`commit.sh` exists", says why. So tell the user to run, from their own
terminal:

```text
cd "<project folder>" && sh setup.sh
```

Say what it does, because it is not what they may expect: it stages every file
in the folder and **commits nothing**. It lists the files the first commit
would take. They add a pattern to `.gitignore` for anything that should stay
out, run `sh setup.sh` again to see the new list, and when it is right run
`sh setup.sh commit`. Do not run any of it from here, and do not offer to.

Then tell them to change the Project Instructions field, which only they can
do. `CLAUDE.md` now holds what was there, and the field keeping a copy is how
the two drift apart. They replace everything in the field with
`data.field_pointer`, exactly, even when the project is the connected folder.
The field reaches every conversation from its start, so this line gets
`CLAUDE.md` read wherever Cowork's own loading of the file does not reach.
COWORK.md, in the claude-plugins repo, under "How instruction files load", has
what Cowork loads and when.

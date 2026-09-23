---
name: new-cowork-project
description: Scaffold a new Cowork Project folder as a git repo - commit.sh, setup.sh, .gitignore, a project-instructions.md mirror, a seeded current-state.md, and a generated per-project document-maintenance skill that is written into the repo and then proposed to the account. Use when starting a new Cowork Project, setting up a project folder, asking for the project boilerplate or template, or asking to give a project git-backed documents where history lives in commits rather than in the content. Also covers checking whether an existing project's maintenance skill has fallen behind the template.
---

# Scaffolding a new Cowork Project

Requires Cowork with a connected folder. This skill writes to the user's device
through the bridge (`device_bash`, `device_commit_files`) and registers a skill
through `propose_skills`. Neither exists in Claude Code. If the bridge is not
available, say so and stop rather than building the folder somewhere it cannot
reach.

## What this produces

In this order, and the last is the one that is easy to get wrong:

1. A **git-backed project folder** with the process apparatus written in.
2. A **per-project maintenance skill**, written into that repo at
   `skills/<skill-name>/SKILL.md`. That file is the versioned original.
3. The **same text registered on the account**, via the `propose_skills` tool.

Writing the file in step 2 does not install anything: the synced copy on disk
is a read-only cache. Step 3 is what makes the skill run, and skipping it fails
silently. The plugin's README, under "The rules", says why skills work this way
in Cowork.

The generated skill is a single `SKILL.md` with no scripts of its own, because
`propose_skills` accepts nothing else. The by-hand `grep` and `shasum` checks
in `templates/maintain-docs.md` stay by hand for that reason.

## Where things run

`scaffold.py` does everything that should come out the same on every run:
reading the templates, checking your answers, filling them in, laying the files
out for the bridge, and checking they arrived. It runs in **your own shell**,
the container, which can read the plugin but cannot see the user's folder.
`device_bash` can see the folder but cannot read the plugin. The commands
`render` prints bridge the two; do not retype file contents across them.

## Locate the script

```sh
SCAFFOLD="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}/scripts/scaffold.py"
python3 "$SCAFFOLD" preflight
```

- **0**: the templates are complete. Go on.
- **1**: a template is malformed. This is a bug in the plugin; show the user
  the errors and stop.
- **No such file**: the skill was installed without its plugin, for example
  through `propose_skills`. It needs a marketplace install. Say so and stop.

## Step 1: list what needs answering

```sh
mkdir -p /tmp/scaffold
python3 "$SCAFFOLD" markers --json > /tmp/scaffold/markers.json
```

`data.markers` is every place a template needs a decision from the interview.
Each has an `id`, the `heading` it sits under, and the `text` of its comment,
which says what belongs there. `data.skeleton` is the answers file with every
marker listed: write it to `/tmp/scaffold/answers.json` and fill it in as the
interview goes. Never change an `id` or a `digest`; they are how `render` knows
your answer was written against the template as it is now.

Each marker takes one resolution:

| Kind | `action` | Effect |
|---|---|---|
| FILL | `fill`, with `text` | the comment is replaced by `text`; `""` removes it |
| FILL | `leave` | the comment stays, and `render` warns about it |
| OPTIONAL | `keep` | the section stays, without its marker comments |
| OPTIONAL | `delete` | the whole section goes, heading included |

A FILL inside a deleted section takes no resolution; leave it out.

## Step 2: the interview

Ask before touching the filesystem. Use `AskUserQuestion` where the answers are
a small closed set, plain questions otherwise. Ask a few at a time, not all at
once, and write each answer into `answers.json` as it arrives rather than
holding them all to the end. Find markers by `heading`; the ids are not worth
memorising.

1. **Project name and folder.** Call `get_device_info`. `connected_folder` is
   one of its `connectedFolders`, exactly as listed. `project_folder` is the
   project's folder inside it, or `null` when the project is the connected
   folder itself.
2. **What the project is for.** The goal, and what counts as a bonus rather
   than a gating criterion. Fills `current-state.md` under Goal, and its
   Status and Feeds lines.
3. **The constraints.** Budget, milestone, stack, what is out of scope. Fills
   Current Constraints in `current-state.md`, the section the maintenance skill
   points every proposal at, and the short form in `project-instructions.md`.
   It has to be real, not a placeholder.
4. **The document roster.** Which documents will exist, and what each owns.
   Two or three is a normal start. `current-state.md` is always one of them and
   is always the anchor unless the user says otherwise. Fills The documents in
   `maintain-docs.md`.
5. **The phases.** The names of the work buckets. Reused verbatim as the
   `TODO(phase)` vocabulary, so they should be short and stable. Fills TODO
   markers in `maintain-docs.md` and Schedule in `current-state.md`.
6. **Standing prose instructions.** Whether the user has their own. The
   answer fills the markers in `prose-style.md`, not the skill. Those markers
   want a real before-and-after from this project, because a rule with no
   example does not survive contact. `fill` with `""` drops the marker, which
   is allowed and weakens the rule that carries it.
7. **Sourced claims?** Whether the project makes factual claims that need
   provenance flags. `keep` or `delete` the Source-quality flags section.
8. **Repeating sections?** Whether any document will hold many sections that
   must all carry the same slots, one per candidate or vendor or option. Almost
   always no at the start: `delete` the Section template section, and say so
   rather than inventing a template nobody needs yet.
9. **Diagrams?** Whether the owner wants diagrams carrying real weight in the
   documents rather than turning up occasionally. `keep` or `delete` the
   Diagrams section. Ask directly. It is a fact about how the owner reads, and
   nothing about the project's subject predicts it.

If the user is not present to answer, do not guess at 3 and 4: `leave` those
markers, and say plainly what is unanswered.

Fill text may use `{{PROJECT_NAME}}`, `{{ANCHOR_DOC}}` and the other
placeholders; `render` substitutes them.

## Step 3: name the skill and write its description

In `answers.json`, under `values`:

- `PROJECT_NAME`: the project's display name, such as `Foo Research`.
- `SKILL_NAME`: **the project's name, with a verb.** `update-<project>-docs` is
  the shape. A generic name invites a generic description.
- `ANCHOR_DOC`: `current-state.md` unless the user said otherwise.
- `DESCRIPTION`: the skill's description. No `<` followed by a word, as in
  `<ins>`: Cowork's plugin upload reads it as an XML tag and rejects the skill.

The description is the only part of a skill that costs context in every
session whether or not it fires, and the only thing that keeps it from firing
in unrelated conversations. So:

- Name the project and list the actual filenames.
- Name what it covers, in the words a user would use: house style, recording a
  decision, logging a correction, opening or closing a question, checking what
  changed.
- No generic verbs on their own. "update docs" and "commit changes" will fire
  everywhere.

`PROJECT_PATH` and `PROJECT_MOUNT` are worked out from the folders. Do not
pass them.

## Step 4: render

```sh
python3 "$SCAFFOLD" render --answers /tmp/scaffold/answers.json --json
```

- **0**: every file is staged under `/mnt/user-data/outputs/`. `warnings` names
  any marker you left; tell the user about each one in the hand-off.
- **1**: `errors` names every problem - a stale digest, a missing resolution, a
  skill name or description that breaks a rule. Nothing was written. Fix
  `answers.json` and run it again. A stale digest means the templates changed
  since step 1: run `markers` again.
- **2**: the stage directory holds files from something else. Pass
  `--stage /mnt/user-data/outputs/<new directory>`.

`--dry-run` checks the answers without writing.

## Step 5: copy the files onto the device

Take each value from `render`'s `data`, as printed:

1. Run `precheck_command` through `device_bash`. It prints `clear` when nothing
   would be overwritten. If it prints `exists:` lines instead, stop and ask the
   user: the folder already holds a project, or part of one.
2. Call `device_commit_files` with `files` set to `commit_files`. Its
   `rejected` list must come back empty.
3. Run `check_command` through `device_bash`. Every line must end `OK`. A line
   ending `FAILED` means that file did not arrive intact: copy it again with
   `device_commit_files`, never by editing it on the device.

Do not `git init`. Step 7 covers why.

## Step 6: register the skill

Read the staged skill, the entry in `files` whose `file` ends in `SKILL.md`,
from its `staged_path`. Call `propose_skills` with exactly that text. Same
name, same description, same body. The user saves it from the review card.

The two copies have to match. If they diverge, the repo looks authoritative and
the account copy is what actually runs. `skills/README.md` in the new project
documents that convention, and the generated skill carries its own drift check.

`propose_skills` takes a single `SKILL.md` and no bundled files. A skill that
later grows reference files has to be uploaded as a folder under
**Customize → Skills**, or moved into a plugin.

## Step 7: hand off

The bridge cannot complete a `git commit`; the plugin's README, under "Why
`commit.sh` exists", says why. So finish by telling the user to run, from their
own terminal:

```
cd "<project folder>" && sh setup.sh
```

`sh`, because files arrive from the bridge without their execute bit.
`setup.sh` sets it on both scripts. Do not run `git init` and then attempt the
commit from here. Do not offer to.

Then name what else the bridge cannot do:

- Save the proposed skill from the review card.
- Paste `project-instructions.md` into the Project's custom-instructions field.

## Improving the templates

The template decays in one specific way: a rule gets sorted into the wrong pile.
A project-specific rule lands in `maintain-docs.md` and starts misfiring on
projects it was never about. A universal rule stays in one project's skill and
the next project silently does without it.

So when a rule changes:

- **Universal.** Edit the plugin's `templates/maintain-docs.md` in its repo,
  commit, bump the plugin version, and reinstall. Then say which existing
  projects now differ. Regenerating an existing project's skill is a deliberate
  act, not automatic: it discards hand-tuned project-specific content.
- **Project-specific.** Edit that project's `skills/<name>/SKILL.md`, commit it
  in that repo, and re-upload it. Nothing in the plugin changes.

To check whether a project has fallen behind, stage its skill with
`device_stage_files`, then:

```sh
python3 "$SCAFFOLD" drift --skill <staged SKILL.md> --json
```

- **0**: every universal section matches the template. Filled markers,
  substituted names, deleted optional sections and rewrapped lines do not
  count.
- **1**: `data.sections` marks each `changed` section with a `diff`, and each
  `missing` one. Show the user those, and carry across only what they agree is
  universal. A `project-only` section is the project's own and is not a
  problem.

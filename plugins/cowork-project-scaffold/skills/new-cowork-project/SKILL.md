---
name: new-cowork-project
description: Scaffold a new Cowork Project folder as a git repo - commit.sh, setup.sh, .gitignore, a project-instructions.md mirror, a seeded current-state.md, and a generated per-project document-maintenance skill that is written into the repo and then proposed to the account. Use when starting a new Cowork Project, setting up a project folder, asking for the project boilerplate or template, or asking to give a project git-backed documents where history lives in commits rather than in the content. Also covers regenerating an existing project's maintenance skill after the template changes.
---

# Scaffolding a new Cowork Project

Requires Cowork with a connected folder. This skill writes to the user's device
through the bridge (`device_bash`, `device_commit_files`) and registers a skill
through `propose_skills`. Neither exists in Claude Code. If the bridge is not
available, say so and stop rather than building the folder somewhere it cannot
reach.

## What this produces

Three things, in this order. The third is the one that is easy to get wrong.

1. A **git-backed project folder** with the process apparatus written in.
2. A **per-project maintenance skill**, written into that repo at
   `skills/<skill-name>/SKILL.md`. That file is the versioned original.
3. The **same text registered on the account**, via the `propose_skills` tool.

Cowork has no project-scoped skills. Writing the file in step 2 does not
install anything: the synced copy on disk is a read-only cache. Step 3 is what
makes the skill run. Skipping it fails silently, which is the whole reason it
is called out here.

## The templates

They ship with this skill, at `${CLAUDE_SKILL_DIR}/templates/`:

| File | Becomes | Treatment |
|---|---|---|
| `gitignore` | `.gitignore` | verbatim |
| `commit.sh` | `commit.sh` | verbatim, `chmod +x` |
| `setup.sh` | `setup.sh` | verbatim, `chmod +x` |
| `skills-README.md` | `skills/README.md` | verbatim |
| `current-state.md` | `current-state.md` | seeded, filled from the interview |
| `project-instructions.md` | `project-instructions.md` | seeded, filled from the interview |
| `maintain-docs.md` | `skills/<skill-name>/SKILL.md` | substituted, then every marker resolved |

**Read `templates/maintain-docs.md` in full before generating from it.** Do not
work from a remembered version. It is the universal half of the rules and it
changes.

## Step 1: the interview

Ask before touching the filesystem. Use `AskUserQuestion` where the answers are
a small closed set, plain questions otherwise. Ask a few at a time, not all at
once, and write each answer into the draft `current-state.md` as it arrives
rather than holding them all to the end.

1. **Project name and folder.** Confirm against `ls "$HOME/mnt/"`, which lists
   the folders actually connected this session.
2. **What the project is for.** The goal, and what counts as a bonus rather
   than a gating criterion. This becomes `## Goal`.
3. **The constraints.** Budget, milestone, stack, what is out of scope. This
   becomes `## Current Constraints`, the section the maintenance skill points
   every proposal at. It has to be real, not a placeholder.
4. **The document roster.** Which documents will exist, and what each owns.
   Two or three is a normal start. `current-state.md` is always one of them and
   is always the anchor unless the user says otherwise.
5. **The phases.** The names of the work buckets. Reused verbatim as the
   `TODO(phase)` vocabulary, so they should be short and stable.
6. **Standing prose instructions.** Whether the user has their own. The
   template ships a default list; it is a `FILL` block because it is personal.
7. **Sourced claims?** Whether the project makes factual claims that need
   provenance flags. Yes keeps the source-quality section, no deletes it.
8. **Repeating sections?** Whether any document will hold many sections that
   must all carry the same slots, one per candidate or vendor or option. Almost
   always no at the start. Say so and move on rather than inventing a template
   nobody needs yet.

If the user is not present to answer, do not guess at 3 and 4. Scaffold the
folder, leave those sections marked, and say plainly what is unanswered.

## Step 2: write the files onto the device

The templates live wherever this skill is installed, which is usually the cloud
container. The project folder is on the user's device. So this is a transfer,
not a copy. Check first:

```sh
ls "${CLAUDE_SKILL_DIR}/templates/"          # container side
```

**If that path is also reachable from `device_bash`** (a device-installed
plugin, under a connected folder), copy directly:

```sh
cp "<templates>/gitignore" "$DST/.gitignore"
```

**Otherwise, the normal case:** read each verbatim template in the container,
then write it to the device with a `device_bash` heredoc. Use a quoted
delimiter so nothing expands:

```sh
cat > "$DST/.gitignore" <<'END'
<contents>
END
```

Then:

```sh
chmod +x "$DST/commit.sh" "$DST/setup.sh"
mkdir -p "$DST/skills/<skill-name>"
```

Do not `git init`. Step 6 covers why.

## Step 3: substitute

Every placeholder, in every file written:

| Placeholder | Value | Example |
|---|---|---|
| `{{PROJECT_NAME}}` | the project's display name | `Foo Research` |
| `{{PROJECT_PATH}}` | its path on the device | `~/Documents/Claude Projects/Foo Research` |
| `{{PROJECT_MOUNT}}` | its path under `$HOME/mnt/` | `Claude Projects/Foo Research` |
| `{{SKILL_NAME}}` | the maintenance skill's name | `update-foo-research-docs` |
| `{{ANCHOR_DOC}}` | the document that wins conflicts | `current-state.md` |
| `{{DESCRIPTION}}` | the skill description, see step 4 | |

**Name the skill after the project, with a verb.** `update-<project>-docs` is
the shape. A generic name invites a generic description, and the description is
the only scoping mechanism a globally-enabled skill has.

## Step 4: generate the maintenance skill

`templates/maintain-docs.md` becomes `<project>/skills/<skill-name>/SKILL.md`.
Substitute, then resolve every marker. Two kinds:

- `<!-- FILL: ... -->`. Replace with real content from the interview. The
  comment explains what belongs there and is deleted with it.
- `<!-- OPTIONAL SECTION ... -->`. Keep and fill, or delete the whole section
  including both marker comments. Never leave an empty template section behind.
  An unfilled section teaches the next agent that the rules are decorative.

Then write the `description:`. It is the only part of a skill that costs
context in every session whether or not it fires, and the only thing that keeps
it from firing in unrelated conversations. So:

- Name the project and list the actual filenames.
- Name what it covers, in the words a user would use: house style, recording a
  decision, logging a correction, opening or closing a question, checking what
  changed.
- No generic verbs on their own. "update docs" and "commit changes" will fire
  everywhere.

**Before finishing, prove nothing was left behind:**

```sh
cd "$DST"
grep -rn '{{' . ; grep -rn 'FILL:' . ; grep -rn 'OPTIONAL SECTION' .
```

All three must come back empty.

## Step 5: register the skill

Call `propose_skills` with the exact text of the generated `SKILL.md`. Same
name, same description, same body. The user saves it from the review card.

The two copies have to match. If they diverge, the repo looks authoritative and
the account copy is what actually runs. `skills/README.md` in the new project
documents that convention, and the generated skill carries its own drift check.

`propose_skills` takes a single `SKILL.md` and no bundled files. A skill that
later grows reference files has to be uploaded as a folder under
**Customize → Skills**, or moved into a plugin.

## Step 6: hand off

The bridge cannot complete a `git commit`. It cannot delete the
`.git/HEAD.lock` it strands, and that lock blocks every later write to the
repo. So finish by telling the user to run, from their own terminal:

```
cd "<project folder>" && ./setup.sh
```

Do not run `git init` and then attempt the commit from here. Do not offer to.

Then name the two other things the bridge cannot do:

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

To check whether a project has fallen behind, diff the universal sections by
heading rather than by line. A project's copy will legitimately differ
everywhere a `FILL` block was resolved.

---
name: {{SKILL_NAME}}
description: {{DESCRIPTION}}
---

# {{PROJECT_NAME}}: history

How changes to `{{PROJECT_PATH}}` get into git. This skill covers history only.
What the documents say, and how they say it, is up to the project and is not
decided here.

The bridge mounts that folder under `$HOME/mnt/`. The exact mount depends on
which folder is connected this session, so confirm it with `ls "$HOME/mnt/"`
before using a path. The commands below assume `$HOME/mnt/{{PROJECT_MOUNT}}`.

## Before changing anything

1. `CLAUDE.md` at the root of the folder holds the standing instructions for
   this project. Read it first.
2. Stage the current file before revising it. The user edits these files
   directly, and a stale container copy will silently clobber their work. Run
   `device_stage_files` on the device path, then work from the staged copy.
3. If this session will change **this skill**, run the drift check under
   **Skill provenance** below before touching it.

## Committing through the bridge

`device_bash` cannot delete files. Every `git commit` it attempts strands a
`.git/HEAD.lock` that blocks all subsequent writes to the repo. So:

1. Edit the files. Use `device_commit_files`, or `sed` and heredocs via
   `device_bash`. Writes and renames work. Deletes do not.
2. Draft the commit message into `.commit-msg` in the repo root:
   ```sh
   cat > "$HOME/mnt/{{PROJECT_MOUNT}}/.commit-msg" <<'MSG'
   docs: <subject under ~70 chars, imperative, lowercase>

   <body: what changed and why. For corrections, state what was wrong,
   what it is now, and the source.>
   MSG
   ```
3. Tell the user to run `./commit.sh` from their own terminal. Do not attempt
   `git commit` from the bridge.

Read-only git works fine from the bridge and should be used freely:

```sh
cd "$HOME/mnt/{{PROJECT_MOUNT}}"
git log --oneline
git log --stat -- <file>
git log --grep="^fix" --format="%h %s%n%b"   # every correction ever recorded
git diff HEAD~1 -- <file>
git blame -L 100,120 <file>
git show <hash>                              # a whole change with its reasoning
```

Anything structural is the user's to run, not the bridge's. That covers
branches, stashes, rebases, deletions and remotes.

If a read-only command fails with a stale lock, ask the user to run
`./commit.sh`, which clears locks first. `find .git -name '*.lock' -delete`
also works.

## Commit types

[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).
Subject under ~70 chars, imperative, lowercase after the colon.

| Type | Use for |
|---|---|
| `docs:` | new sections, rewrites, expansions. Most commits |
| `fix:` | a claim was wrong and is now right. Always explain in the body |
| `refactor:` | reorganisation with no change of meaning, such as splitting files |
| `chore:` | repo plumbing, gitignore, tooling |
| `feat:` | a genuinely new artifact, such as a new document |

**The body is where the value is.** It is the record of why. For anything
factual, name what was wrong, what it is now, and the source:

```
fix: correct three claims in the <section> section

- <claim> is <right value>, not <wrong value>. Source: <link>
- <claim> is not stated in <source>; it was a passing reference, not a
  sourced figure
```

## Dates

ISO 8601 (`2026-08-20`) wherever a date is written, commit messages included.
Never `08/20/26`.

## Skill provenance

This skill is authored in the repo, at
`skills/{{SKILL_NAME}}/SKILL.md`. The skill registered on the account under
**Customize → Skills** is a deployment artifact built from that file. Cowork has
no project-scoped skills, so the account copy is what actually runs. The repo
copy is what is versioned, and it wins.

**Never edit this skill in the Skills UI.** An edit made there has no commit,
no diff and no way back. Edit the repo file, commit it, then re-upload.

**Drift check.** The container's cache of a synced skill is not reliably fresh.
It has served a superseded copy for the first ten minutes of a session, and a
false claim was made from it. Invoking the skill refreshes the cache, so invoke
first, *then* compare:

```sh
# device
shasum -a 256 "$HOME/mnt/{{PROJECT_MOUNT}}/skills/{{SKILL_NAME}}/SKILL.md"
# container, after invoking the skill
find /root/.claude/skills -name SKILL.md -path '*{{SKILL_NAME}}*' -exec sha256sum {} \;
```

- **Repo ahead.** The account copy is stale. Say so, and do not rely on rules
  the running skill does not have.
- **Account ahead.** Someone edited in the UI. Copy that version into the repo
  and commit it *before* any other work, or the change is lost.

A cheaper check needs no file access at all. The skill listing in the session
prompt always carries the **live registered** description. If it disagrees with
the `description:` in this file's front matter, the copies have drifted. That
proves drift but never its absence. A body-only edit leaves the description
untouched, and body-only is the common case. Treat a match as no information
rather than as an all-clear.

The same rule covers `CLAUDE.md` and the Project Instructions field. The field
holds one line pointing at `CLAUDE.md`. If anything else turns up in the field,
copy it into `CLAUDE.md`, commit it, and ask the user to put the pointer back.

## Scope

`commit.sh`, `setup.sh`, `.gitignore`, `CLAUDE.md` and this skill are the whole
of the history apparatus. Rules about what the documents contain or how they
read are not part of it. A project that wants them adds them separately.

## Improving these rules

This file was generated from the `gitify-cowork-project` plugin, from
`skills/gitify-project/templates/history-skill.md`.

A rule that turns out to be universal belongs back in that template, in the
plugin repo, or the next project will not get it. A rule specific to
{{PROJECT_NAME}} stays here.

Editing the plugin does not change this file, and editing this file does not
change the plugin. They are separate copies on purpose.

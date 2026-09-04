# Project skills

Cowork Projects do not have their own skills. Skills are registered on the
Claude **account**, or provisioned org-wide by an admin, and enabled globally.
There is no per-Project skill list the way there is a per-Project instructions
field and knowledge base. Checked against Anthropic's documentation on
2026-08-24; if that changes, this folder becomes a staging area rather than a
mirror.

This folder is the workaround. Every skill this Project depends on is authored
here, in the repo, and deployed to the account by hand.

## The rule

**The repo is the source. The Claude account is a deployment target.**

Edit the file here, commit it, then upload it under **Customize → Skills**.
Never edit a skill in the Skills UI: an edit made there has no commit, no diff
and no way back, and this folder starts lying the moment it happens.

The same rule governs `project-instructions.md` in the repo root, which mirrors
the Project's custom-instructions field for exactly the same reason.

## Layout

```
skills/
  README.md                  this file
  <skill-name>/
    SKILL.md                 name + description front matter, then the body
```

One directory per skill, matching the layout Claude itself uses on disk. A skill
that grows reference files keeps them beside its `SKILL.md`, and the directory
zips directly into a `.skill` bundle.

Note that a skill saved through Claude's in-conversation review card is a single
`SKILL.md` with no bundled files. Reference files require the upload path.

## Scoping a skill to one Project

Because enabling is global, the **description is the only scoping mechanism**.
Write it so it names this Project's files and vocabulary explicitly. A
description built from generic verbs, such as "update docs" or "commit
changes", will fire in unrelated conversations. The description is also the only
part of a skill that costs context in *every* session, whether or not it
triggers, so it should be specific but not long.

## Drift

The failure mode is silent: the two copies diverge, the repo looks
authoritative, and the account copy is what actually runs. Each skill's
`SKILL.md` carries its own drift-check procedure. The short version:

- The skill listing in the session prompt always carries the **live registered**
  description. Comparing it against the front matter here needs no file access,
  but it only ever proves drift, never its absence. A body-only change leaves
  the description identical, and body-only is the common case.
- The container's cache of a synced skill is **not reliably fresh**. Invoke the
  skill first, which refreshes it, then compare hashes with the copy here.
- Repo ahead: re-upload. Account ahead: commit the account version here first,
  before any other work.

## Where this came from

This file is boilerplate, copied in by the `new-cowork-project` skill from
`_project-template`. Two things make it work, and both are easy to leave out:

1. The direction-of-truth rule, stated once and not negotiable.
2. The drift check living *inside each skill*, where an agent will actually read
   it. Not only here, where it will not.

An improvement made here should go back to `_project-template/skills/README.md`,
or the next project will not get it.

# Flywheel

Flywheel runs a repository's issue loop: it takes an approved GitHub issue to
a merged pull request through Claude sessions that each play one role. A
**role** is one part of the loop:

- the **dispatcher** starts a session for each issue, and starts the next one
  when a pull request merges.
- an **implementer** works one issue and opens its pull request.
- a **reviewer** reviews that pull request.

**Claude Code only.** The loop runs in the Claude desktop app, in a git clone
with a GitHub remote.

This version installs the plugin's script, writes the file that says which
model each role runs on, and ships the docs that define the method the loop
follows. The skills that run the loop arrive in later versions.

## The method

The loop follows a method for building software with agents: every behavior
traces to a need someone stated, and each task gets an agent matched to it.
The plugin's `docs/` folder is the method's home. Start with
[docs/README.md](docs/README.md).

The method's principles and stage rules each have an id, such as
`one-home-per-artifact`. A spec, a template or a skill that cites one points
to the document in `docs/` that defines it. The docs carry the plugin's
version, so a repo that records which flywheel version it adopted has
recorded which version of the method it follows.

## Setting it up in a project

Ask Claude to set up flywheel in the project. Claude runs the plugin's
`setup`, which copies the plugin's script into a `.flywheel/` folder in the
project. Git ignores that copy, so it never reaches a commit.

## Choosing each role's model

Ask Claude to write the flywheel roles file. Claude runs `config init`, which
writes `.flywheel/roles.json` with one entry per role:

```json
"implementer": {
  "tier": 3,
  "model": null,
  "effort": null,
  "version": "0.1.0"
}
```

- `tier` is how much reasoning the role needs, from 1 (the most) to 3.
- `model` and `effort` are left for you. Claude lists each one you need to
  fill in.
- `version` is the version of this plugin the file was written under.

`config init` never overwrites a roles file that already exists. Commit the
file once it is filled in, so every session reads the same choices.

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
model each role runs on, takes and frees the claim on an issue, ships the docs
that define the method the loop follows, and carries the implementer's skill.
The skills for the other roles arrive in later versions.

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

## Claiming an issue

Before a session works an issue, it **claims** it: it creates a branch named
`issue/` and the issue's number on GitHub. Only one session can create that
branch, so two sessions never work the same issue. Claude then adds the
`in-progress` label and a comment, so the claim shows in the issue list.

Ask Claude for the next issue, or for the next few. Claude offers the oldest
approved issues that nobody has claimed and that no open issue blocks. When
a plan groups several issues under one tracking issue, Claude offers them in
the plan's order.

When a session stops without finishing, ask Claude to release the claim.
Claude deletes the branch only when it holds no work. Once the issue's pull
request merges, ask Claude to clear the claim, which removes the branch from
your clone.

## Starting a session on an issue

Ask Claude for the brief for an issue. The brief is the first message for a
new session: the issue as you approved it, your comments since, the
session's role, and your project's gate commands. A **gate command** is the
command that says a piece of work is done, such as running the tests. Claude
refuses the brief for an issue edited after you approved it, until you
approve it again.

List your gate commands in `.flywheel/gates.json`, and commit it:

```json
{
  "gates": {
    "check": "make check",
    "verify": "make verify"
  }
}
```

## Working an issue

Ask Claude to work an issue, such as "fix #12", or to take the next issue, or
start a session with an issue's brief as its first message. Claude follows
the plugin's work-issue skill:

1. It claims the issue and tells you how the claim went, before any other
   work. When it took the issue from the queue and another session got there
   first, it takes the next free issue instead.
2. It works from the issue as you approved it, with your comments since.
3. When the issue is silent or wrong on something the work needs, it stops
   and asks. An idea the issue does not ask for, it files as a new issue for
   you to approve, and goes on.
4. It runs your `check` gate command, and does not open a pull request while
   it fails.
5. It opens the pull request through your project's pull request skill, when
   you have one.
6. It turns on the session's Auto-fix, so the app wakes the session when CI
   fails, the pull request has a conflict or a review comment arrives. It also
   has the app archive the session once the pull request merges or closes.
   The app may ask you to approve that call.

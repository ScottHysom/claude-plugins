# Flywheel

Flywheel runs a repository's issue loop. The loop takes a GitHub issue from
the moment it is filed, through your approval, to a merged pull request. You
file issues by asking Claude, and Claude sessions file them too, as "Filing
an issue or a plan" describes. You approve each issue before any session
works it.

Claude sessions do the rest of the work, each in one role. A **role** is one
part of the loop:

- the **dispatcher** starts a session for each approved issue, and starts the
  next one when a pull request merges.
- an **implementer** works one issue and opens its pull request.
- a **reviewer** reviews that pull request.

**Claude Code only.** The loop runs in the Claude desktop app, in a git clone
with a GitHub remote.

This version of the plugin:

- installs the plugin's script.
- ships the docs that define the method the loop follows.
- assesses which of the method's controls a project holds.
- writes the file that says which model each role runs on, and the review
  and merge policies.
- files an issue or a plan of issues.
- guards the `approved` label.
- takes and frees the claim on an issue.
- carries the dispatcher's, the implementer's and the reviewer's skills.

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

## Adopting the method

The method sorts what a project needs into three levels, each built on the
one below. Level 1 has agents build only what someone asked for, level 2
backs that with checks, and level 3 has the loop measure itself. Each level
lists its **controls**, such as a rules file for agents or a written review
policy, in [docs/adoption.md](docs/adoption.md).

Ask Claude to adopt flywheel in your project, or to assess it. Claude follows
the plugin's adopt skill:

1. It lists each control with what it found in the project, or what is
   missing.
2. It asks you which level to adopt. It never chooses one for you.
3. It writes the roles file and the review and merge policies, and asks you
   for each setting they leave for you.
4. It adds the method's rules for agents, up to your level, to your
   project's `CLAUDE.md`, beside the rules you already have.
5. It records the plugin version, your level and the controls your project
   holds in `.flywheel/adoption.json`.
6. It files each missing control as an issue, all in one plan for you to
   approve.

Commit what it wrote. When you ask again after updating the plugin, Claude
shows only what changed since the record, such as a control the method added.

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

`config init` never overwrites a file that already exists. Commit the file
once it is filled in, so every session reads the same choices.

## Setting the review and merge policies

`config init` also writes two policies into `.flywheel/`. Each is a page you
read and edit, with its settings in a JSON block at the end. Claude lists
each setting you need to fill in. Commit both once they are filled in.

- `review-policy.md` is what the reviewer works from: the passes it reads a
  pull request in, the P0 to P3 scale it gives each finding (P0 is broken or
  unsafe, P3 is a nit), and `p3_cap`, the most P3 findings one review posts.
  Fill in `rules` with the files that hold your project's own rules, such as
  `["CLAUDE.md"]`.
- `merge-policy.md` says which pull requests the dispatcher merges without
  you. A pull request that changes a requirement, touches a path under
  `protected`, has a finding still open, or reaches outside its issue's area
  waits for you. Fill in `areas` with the paths each area label covers, such
  as `{"plugin:todos": ["plugins/todos/", "tests/todos/"]}`.

The merge policy is a request the dispatcher follows. To make GitHub enforce
the checks too, set these on your `main` branch, under the repository's
Settings, then Rules:

1. Require the status check that runs your `verify` gate to pass before
   merging.
2. Require a branch to be up to date with `main` before merging.
3. Allow nobody to bypass the rule, administrators included.

## Creating the loop's labels

The loop sorts issues by label. Each issue Claude files carries one kind
label (`bug`, `enhancement` or `docs`) and one area label (`repo`, or
`plugin:` and a plugin's name). A tracking issue carries `tracking`, an
approved issue `approved`, and a claimed issue `in-progress`. A repository
GitHub has just created lacks most of these, and Claude refuses to file an
issue whose labels the repository does not have. The adopt skill names the
missing labels and creates them once you agree.

## Filing an issue or a plan

An issue reaches the loop from any of these:

- you, when you ask Claude to file an issue, or a plan that splits into
  several issues.
- the adopt skill, which files each control your project is missing, all in
  one plan.
- an implementer, which files an idea its issue does not ask for as a new
  issue, and goes on with its own issue.

Claude files each one the same way. It drafts each issue, then publishes a
report that shows every issue exactly as it will be filed. You read the
report, and comment on it or approve it. Claude files nothing until you
approve, and files exactly what the report showed.

A plan of several issues also gets a **tracking issue**: an issue that lists
the plan's issues in the order to work them, as its sub-issues. Each issue
that waits on another is marked "blocked by" it on GitHub. When every issue
in a plan is closed, ask Claude to close the plan, and Claude closes the
tracking issue.

The report and Claude's record of what it filed live in `.flywheel/plan/`,
which git ignores.

## Approving an issue

A filed issue waits until you approve it by adding the `approved` label.
Claude offers only approved issues for a session to work.

Agents post under your GitHub account, so GitHub cannot tell an agent adding
the `approved` label from you adding it. The plugin's hook stops any command
Claude Code runs that would add it. To approve an issue with Claude's help,
run `! gh issue edit <N> --add-label approved`: the `!` runs it in your own
shell, where the hook does not run. The hook reads the command's text, so it
stops a mistake rather than a determined workaround.

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

Your gate commands go in `.flywheel/gates.json`. `config init` writes
`build`, `test`, `check` and `verify` there for you to fill in, and keeps any
gate the file already gives. Claude offers the command it finds in your
project for each one. Commit the file once it is filled in:

```json
{
  "gates": {
    "check": "make check",
    "verify": "make verify"
  }
}
```

At level 2, the same file also says how to list your tests and how to run
one. Claude writes these for you when your project uses pytest, and asks you
for them otherwise:

```json
{
  "tests": {
    "list": "python3 -m pytest --collect-only -q -p no:cacheprovider",
    "run": "python3 -m pytest -q -p no:cacheprovider {id}",
    "paths": ["tests", "pytest.ini"]
  }
}
```

With them, `flywheel.py fails-on-base` runs each test a pull request adds
against your code as it was before the change, and fails the pull request
when a new test passes there. A test that passes there anyway would pass
without the change, so it proves nothing about it. Have your `verify`
command run it. When a new test passes before the change on purpose, such as
one that pins behavior the change keeps, give its id and the reason in
`.flywheel/passes-on-base.json`:

```json
{
  "tests": {
    "tests/test_app.py::test_keeps_old_format": "pins the format this change keeps"
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
7. When a review comment arrives, it answers each thread with what it changed
   or why not, and leaves resolving the thread to the reviewer.

## Reviewing a pull request

Ask Claude to review a pull request, such as "review #671", or let the
dispatcher start a reviewer. Claude follows the plugin's review-pr skill:

1. It reads your review policy, and the pull request's description, threads
   and diff.
2. It reviews the diff in each of the policy's passes, against the
   requirements the description lists.
3. It posts its findings as one review, each opening with `**Claude:**` and
   its level, and no more P3 findings than the policy allows. It never
   approves a pull request or requests changes.
4. On a second look, once the implementer has answered, it resolves each
   thread whose answer it accepts. A thread it leaves unresolved waits for
   you.

## Running a round of issues

Ask Claude to run a number of issues, such as "run 3 issues", or to run a
plan, such as "run #653 three at a time". That session becomes the
dispatcher and follows the plugin's run skill:

1. It checks that `.flywheel/roles.json` gives the implementer and the
   reviewer a model and an effort, and stops naming each one you still need
   to fill in.
2. It takes the next approved issues, in the plan's order when you named a
   plan.
3. It starts one session per issue, each in its own worktree, with the
   issue's brief as its first message and the implementer's model and
   effort. Each of those sessions works its issue as "Working an issue"
   describes.
4. It tells you each pull request as it opens, and starts a reviewer session
   on it. It starts the reviewer again once the implementer has answered the
   review.
5. It merges a pull request when the merge policy lets it through, and
   otherwise tells you why it waits for you. You merge those yourself.
6. Once a pull request merges, it clears the claim and starts a session on
   the next issue, so the number you named stays in flight. It looks again
   whenever one of its sessions finishes a turn, or when you send it a
   message, such as after a merge.
7. It closes a plan once every issue in it is closed, and stops when no
   issue is left to start and no pull request is open.

The app starts a session at or below the model and effort of the session
that starts it. So run the dispatcher on a model and effort at least as
strong as the implementer's and the reviewer's.

## Measuring the loop

Ask Claude to measure the loop since a date, such as "measure the loop since
2026-10-01". Claude runs `measure`, which reports, for each pull request
merged since then and as a summary:

- **spend**: the tokens Claude Code used on the pull request's branch, read
  from the session records on your machine.
- **first-pass CI**: whether the checks passed the first time CI ran on the
  pull request.
- **findings**: how many findings the reviewer posted, at each level from P0
  to P3.
- **lead time**: the hours from when the issue was approved to the merge.

Read these before and after changing a role's model or effort in
`.flywheel/roles.json`, so you can tell whether the change paid off. Each
measure is there because it informs a decision like that one. A measure that
informs no decision is dropped. `measure` says which measure it could not
compute for a pull request, and why.

The plugin's `templates/loop-report.yml` is a GitHub Actions workflow that
runs `stale` and `measure` on a schedule and records the results in one open
issue titled "Loop report", which it updates on each run. Each run measures
the pull requests merged since the last run. Copy it into your project's
`.github/workflows/`, and set its `cron` line to the schedule you want. It
runs on Mondays until you do. GitHub does not have your session records,
so that report leaves spend out.

## Clearing the label when an issue closes

The plugin's `templates/issue-closed.yml` is a GitHub Actions workflow that
takes the `in-progress` label off an issue when it closes. Copy it into your
project's `.github/workflows/` to keep the label meaning that someone is
working on the issue.

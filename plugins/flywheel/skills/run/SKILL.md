---
name: run
description: Run a round of approved GitHub issues as the dispatcher, starting one implementer session per issue and a new one each time a pull request merges. Checks the implementer's model and effort with flywheel.py role, takes the issues from flywheel.py queue, starts each session in its own worktree with flywheel.py brief as its first message, watches the claim pull requests with flywheel.py events, clears each merged claim and closes a finished plan. Claude Code desktop app only. Use when asked to run, start or work a round of issues, a number of issues at once, or the issues of a plan or tracking issue.
---

# Run a round of issues

The **dispatcher** is the session that runs this skill. It starts an
implementer session for each issue in the round, and starts the next one when
a pull request merges, so that the count the owner named stays in flight. An
**implementer** works one issue with the plugin's work-issue skill and opens
its pull request. A **brief** is the first message `flywheel.py brief N`
prints for the session that works issue N.

The owner names the round as a count, as in "run 3 issues", or as a tracking
issue's plan, as in "run #653", or both. When the owner names a plan without
a count, ask how many sessions to keep in flight.

The dispatcher does not review or merge a pull request. The owner reviews
and merges each one. The dispatcher runs each command below from the root of
the clone.

## Locate the script

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"
FLYWHEEL="$ROOT/scripts/flywheel.py"
ls "$FLYWHEEL" || echo "flywheel is not installed as a plugin here"
python3 "$FLYWHEEL" setup --json
```

Run the block as one command. If the `ls` fails, the plugin is not installed
here, so stop.

`setup` copies the script into the project at `.flywheel/`, which git
ignores. Each later command starts a fresh shell, so start every one with
`data.prefix` and `&&`:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" role implementer --json
```

## Step 1: check the implementer's role
<!-- spec: run-refuses-unmapped-role -->

Read the model and effort the roles file gives the implementer:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" role implementer --json
```

When `role` exits 1, relay its errors to the owner, who fills in each field
it names, and stop.

On exit 0, `data.model` and `data.effort` are what every implementer starts
at. The app starts a session at or below the model and effort of the session
that starts it, and ignores anything higher. So when either is above this
session's own, stop and tell the owner to run this skill from a session at
least that strong.

## Step 2: take the first look
<!-- spec: run-restarts-after-merge -->

Take the first look at the claim pull requests, so later looks name only what
changed since:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --json
```

Keep `data.as_of`. Each later look passes it as `--since` and keeps the new
`data.as_of` in its place.

## Step 3: read the queue
<!-- spec: run-starts-one-session-per-issue, run-closes-finished-plan, run-stops-on-empty-queue -->
<!-- seam: judgment: the owner chose a count or a plan, and the command differs by that choice -->

Ask the queue for as many issues as there are free places in the round. At
the start that is the count; later it is the count less the sessions still
working or waiting on a merge.

For a count alone:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" queue --count 3 --json
```

For a plan, with its tracking issue:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" queue --tracking 653 --count 3 --json
```

What the result means:

- `data.issues` lists the issues to start, in order. Start each as step 4
  says.
- `data.tracking` without `--tracking` is an approved plan that comes before
  every other issue. Ask the owner whether to run that plan, and on a yes,
  read the queue again with `--tracking`.
- `data.finished` true means the plan is finished. Close it as step 7 says.
- Fewer issues than free places, with `data.issues` empty and no session
  still working or waiting on a merge, means the round is over. Stop as step
  8 says.
- On exit 1, relay the errors to the owner and stop starting sessions.

## Step 4: start a worker for each issue
<!-- spec: run-starts-one-session-per-issue -->

For each issue the queue offered, print its brief:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" brief 649 --json
```

When `brief` exits 1, the issue changed after the owner approved it. Tell the
owner the error, start no session on it, and go on with the next issue.

On exit 0, start the session with the app's `start_session` tool:

- `initiation`: `user_asked`, since the owner asked for the round.
- `context`: `fresh`.
- `prompt`: `data.prompt`, as `brief` printed it.
- `background`: that the dispatcher started this session to work issue N as
  the implementer, with the work-issue skill, and that it reports its pull
  request when it opens one.
- `use_worktree`: true, so each implementer has its own worktree.
- `model` and `effort`: the ones step 1 read, never higher.
- `name`: `issue-` and the number, as in `issue-649`.
- `wake_when_done`: true, so this session is woken when the implementer
  ends a turn.

Then tell the owner which sessions started, and end the turn. This session
is woken when an implementer ends a turn. The owner wakes it by sending any
message, such as after merging a pull request.

## Step 5: look again when woken
<!-- spec: run-reports-pull-request, run-restarts-after-merge -->

Each time this session is woken, look again with the last `data.as_of`:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --since 2026-10-15T09:00:00Z --json
```

Keep the new `data.as_of`. Then act on each of these that the look or the
note that woke this session shows:

- A pull request in `data.open` from an issue this round started, that has
  not been reported yet. Report its `url`, `ci` and `review` to the owner,
  who reviews and merges it.
- A pull request in `data.merged`. Clear its claim as step 6 says.
- An implementer that stopped without a pull request. Relay what it said to
  the owner. When it lost its claim to another session, its place in the
  round is free, so read the queue as step 3 says.

## Step 6: clear a merged claim
<!-- spec: run-restarts-after-merge -->

For each issue whose pull request merged, clear its claim:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" clear 649 --json
```

When `clear` exits 1, relay its error to the owner and delete nothing by
hand. Either way, the merge freed a place in the round, so read the queue as
step 3 says.

## Step 7: close a finished plan
<!-- spec: run-closes-finished-plan -->

When the queue says the plan is finished, close its tracking issue:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" plan close 653 --json
```

Tell the owner the plan is closed, or relay the error when `plan close`
exits 1. A finished plan has nothing left to start, so stop as step 8 says
once no session is still working or waiting on a merge.

## Step 8: stop
<!-- spec: run-stops-on-empty-queue -->
<!-- no-command: reports to the owner what the round's earlier looks found -->

When the queue offers nothing and `data.open` in the last look holds no pull
request from this round, report to the owner each pull request in the round
that merged, and each issue that stopped without one. Then stop.

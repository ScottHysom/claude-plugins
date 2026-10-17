---
name: run
description: Run a round of approved GitHub issues as the dispatcher, starting one implementer session per issue, a reviewer session on each pull request, and a new implementer each time a pull request merges. Checks each role's model and effort with flywheel.py role, takes the issues from flywheel.py queue, starts each session in its own worktree with flywheel.py brief as its first message, watches the claim pull requests with flywheel.py events, merges what the merge policy lets flow with flywheel.py merge-check, asks the owner about what it holds, clears each merged claim and closes a finished plan. Claude Code desktop app only. Use when asked to run, start or work a round of issues, a number of issues at once, or the issues of a plan or tracking issue.
---

# Run a round of issues

The **dispatcher** is the session that runs this skill. It starts an
implementer session for each issue in the round, and starts the next one when
a pull request merges, so that the count the owner named stays in flight. An
**implementer** works one issue with the plugin's work-issue skill and opens
its pull request. A **reviewer** reviews a pull request with the plugin's
review-pr skill, from the project's review policy. A **brief** is the first
message `flywheel.py brief N` prints for the session that works issue N.

The owner names the round as a count, as in "run 3 issues", or as a tracking
issue's plan, as in "run #653", or both. When the owner names a plan without
a count, ask how many sessions to keep in flight.

The dispatcher merges a pull request only when `merge-check` reports that it
flows under the project's merge policy, in `.flywheel/merge-policy.md`, and
asks the owner about every other one. It runs each command below from the
root of the clone.

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

## Step 2: check the reviewer's role
<!-- spec: run-refuses-unmapped-role, run-reviews-each-pull-request -->

Read the model and effort the roles file gives the reviewer:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" role reviewer --json
```

Act on the result as step 1 says. `data.model` and `data.effort` are what
every reviewer starts at.

## Step 3: take the first look
<!-- spec: run-restarts-after-merge -->

Take the first look at the claim pull requests, so later looks name only what
changed since:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --json
```

Keep `data.as_of`. Each later look passes it as `--since` and keeps the new
`data.as_of` in its place.

## Step 4: read the queue
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

- `data.issues` lists the issues to start, in order. Start each as step 5
  says.
- `data.tracking` without `--tracking` is an approved plan that comes before
  every other issue. Ask the owner whether to run that plan, and on a yes,
  read the queue again with `--tracking`.
- `data.finished` true means the plan is finished. Close it as step 10 says.
- Fewer issues than free places, with `data.issues` empty and no session
  still working or waiting on a merge, means the round is over. Stop as step
  11 says.
- On exit 1, relay the errors to the owner and stop starting sessions.

## Step 5: start a worker for each issue
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

## Step 6: look again when woken
<!-- spec: run-reports-pull-request, run-restarts-after-merge -->

Each time this session is woken, look again with the last `data.as_of`:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --since 2026-10-15T09:00:00Z --json
```

Keep the new `data.as_of`. Then act on each of these that the look or the
note that woke this session shows:

- A pull request in `data.open` from an issue this round started. Report its
  `url` to the owner the first time a look shows it. Then check it as step 7
  says.
- A pull request in `data.merged` whose claim this session has not cleared
  since step 7 merged it. Clear its claim as step 9 says.
- An implementer that stopped without a pull request. Relay what it said to
  the owner. When it lost its claim to another session, its place in the
  round is free, so read the queue as step 4 says.

## Step 7: check each pull request
<!-- spec: run-merges-what-flows, run-asks-owner-on-hold, run-reviews-each-pull-request -->

For each open pull request from this round, ask the merge policy whether it
flows, and merge it when it does:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" merge-check 671 --merge --json
```

`data.merged` true means `merge-check` squashed it. Clear its claim as step 9
says. Otherwise `data.next` says what comes next, and `data.reasons` says
why it holds:

- `review`: the pull request needs the reviewer's look at its head. Start a
  reviewer as step 8 says, unless a reviewer this session started on it is
  still working.
- `wait`: the implementer has work to do, such as a failing check or a
  thread to answer. Its session is woken by the app's Auto-fix, and nothing
  starts here.
- `ask`: the pull request holds for the owner. Tell the owner its `url` and
  every reason in `data.reasons`, once for each `data.head`. The owner merges
  it on GitHub or says what to do. Until the owner answers, start no
  reviewer on it and merge nothing.

On exit 2, relay the error to the owner and merge nothing.

## Step 8: start a reviewer
<!-- spec: run-reviews-each-pull-request -->
<!-- no-command: calls the desktop app's start_session tool, which a script cannot reach -->

Start the session with the app's `start_session` tool:

- `initiation`: `user_asked`, since the owner asked for the round.
- `context`: `fresh`, so the reviewer starts without any of the
  implementer's context.
- `prompt`: "Review pull request #671 as the reviewer, with the review-pr
  skill.", with the pull request's number.
- `background`: that the dispatcher started this session to review pull
  request N, and that it reports when it has posted its review.
- `use_worktree`: true.
- `model` and `effort`: the ones step 2 read, never higher.
- `name`: `review-` and the number, as in `review-671`.
- `wake_when_done`: true, so this session is woken when the reviewer ends a
  turn. Check the pull request again then, as step 7 says.

## Step 9: clear a merged claim
<!-- spec: run-restarts-after-merge -->

For each issue whose pull request merged, clear its claim:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" clear 649 --json
```

When `clear` exits 1, relay its error to the owner and delete nothing by
hand. Either way, the merge freed a place in the round, so read the queue as
step 4 says.

## Step 10: close a finished plan
<!-- spec: run-closes-finished-plan -->

When the queue says the plan is finished, close its tracking issue:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" plan close 653 --json
```

Tell the owner the plan is closed, or relay the error when `plan close`
exits 1. A finished plan has nothing left to start, so stop as step 11 says
once no session is still working or waiting on a merge.

## Step 11: stop
<!-- spec: run-stops-on-empty-queue -->
<!-- no-command: reports to the owner what the round's earlier looks found -->

When the queue offers nothing and `data.open` in the last look holds no pull
request from this round, report to the owner each pull request in the round
that merged, and each issue that stopped without one. Then stop.

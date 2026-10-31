---
name: run
description: Run a round of approved GitHub issues as the dispatcher, starting one implementer session per issue, a reviewer session beside each, and each issue and pull request to an idle one of them by message as the work appears. Checks each role's model and effort with flywheel.py check-role, takes the issues from flywheel.py queue, starts each session in its own worktree with flywheel.py brief as its first message, watches the claim pull requests with flywheel.py events, merges what the merge policy lets flow with flywheel.py merge-check, asks the owner about what it holds, clears each merged claim and closes a finished plan. Claude Code desktop app only. Use when asked to fix, work, run or start a round of issues, a number of issues at once such as the next 3 issues, particular issues named by number, or the issues of a plan or plan issue, and when asked to fix, work or take an issue, the next issue, or the next issue in a plan, unless the request says to do it here or in this session. Never use it in a session whose first message is a brief, which the work-issue skill takes.
---

# Run a round of issues

The **dispatcher** is the session that runs this skill. It starts an
implementer session for each issue in the round, and hands the next issue to
an idle implementer when a pull request merges, so that the count the owner
named stays in flight. An
**implementer** works one issue with the plugin's work-issue skill and opens
its pull request. A **reviewer** reviews a pull request with the plugin's
review-pr skill, from the project's review policy. A **brief** is the first
message `flywheel.py brief N` prints for the session that works issue N.

The dispatcher starts the round's implementers and reviewers once, on the
owner's message that starts the round, and keeps them for the whole round.
After that it hands every task to an idle one with `SendMessage`, and
empties its conversation first with `clear_session`. The app starts a session
only on a turn that the owner's own message began, and delivers a message on
any turn, so a task handed by message reaches the session when the work
appears. `DESIGN.md` records what was measured. A **place** is one
implementer and the reviewer paired with it, and the round keeps as many
places as the count the owner named.

The owner names the round in one of these ways:

- a count, as in "fix the next 3 issues", with or without an issue to start
  at, as in "starting at #12".
- a plan, named by its plan issue, as in "fix the issues in #653", with or without a
  count, as in "three at a time".
- issues, as in "fix #12 and #14".
- one issue to fix, work or take, as in "fix #12" or "fix issue 12", which is
  a round of that issue.
- the next issue, as in "fix the next issue" or "the next issue in #653",
  which is a round of the one issue the queue offers.

A request to work an issue here, or in this session, is not a round. The
work-issue skill takes it, and this session becomes the implementer.

A number the owner names may be an issue or a plan issue, and step 5
tells them apart. When the owner names a plan without a count, ask how many
sessions to keep in flight. A round of named issues starts each one that can
start at once, and takes nothing more from the queue.

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
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" check-role dispatcher --json
```

## Step 1: check the dispatcher's role
<!-- spec: run-refuses-unmapped-role, run-checks-dispatcher-role -->

Read this session's own model and effort with the app's `get_session` tool.
The app starts a session at or below the model and effort of the session that
starts it, and lowers anything higher. So check the `dispatcher` role against
this session before anything starts, passing the session's model as
`--model` and its effort as `--effort`:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" check-role dispatcher --model claude-opus-5-5 --effort medium --json
```

When `check-role` exits 1 or 2, relay its errors to the owner, who fills in
each field it names or runs this skill from a stronger session, and stop.

## Step 2: check the implementer's role
<!-- spec: run-refuses-unmapped-role, run-starts-one-session-per-issue -->

Check the implementer against this session in the same way:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" check-role implementer --model claude-opus-5-5 --effort medium --json
```

Act on the result as step 1 says. On exit 0, `data.model` and `data.effort`
are what every implementer starts at.

## Step 3: check the reviewer's role
<!-- spec: run-refuses-unmapped-role, run-reviews-each-pull-request -->

Check the reviewer against this session in the same way:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" check-role reviewer --model claude-opus-5-5 --effort medium --json
```

Act on the result as step 1 says. On exit 0, `data.model` and `data.effort`
are what every reviewer starts at.

## Step 4: take the first look
<!-- spec: run-restarts-after-merge -->
<!-- seam: judgment: the owner chose a count, a plan or issues, and the command differs by that choice -->

Take the first look at the claim pull requests, so later looks name only what
changed since. For a plan, with its plan issue:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --plan 653 --json
```

For issues the owner named, with `--issue` once for each:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --issue 12 --issue 14 --json
```

For a count (including one with an issue to start at), or the next issue,
the round has not started any issue yet, so look without naming one:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --json
```

Keep `data.as_of`. Each later look passes it as `--since` and keeps the new
`data.as_of` in its place.

## Step 5: read the queue
<!-- spec: run-starts-one-session-per-issue, run-closes-finished-plan, run-stops-on-empty-queue, run-starts-named-issues, run-takes-issue-requests -->
<!-- seam: judgment: the owner chose a count, a plan or issues, and the command differs by that choice -->

Ask the queue for as many issues as there are free places in the round. At
the start that is the count; later it is the count less the sessions still
working or waiting on a merge.

For a count alone:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" queue --count 3 --json
```

For a count with an issue to start at, pass that issue with `--from` on every
read of the round:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" queue --count 3 --from 12 --json
```

For a plan, with its plan issue:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" queue --plan 653 --count 3 --json
```

What the result means:

- `data.issues` lists the issues to start, in order. Start each as step 6
  says.
- `data.plan` without `--plan` is an approved plan that comes before
  every other issue. Ask the owner whether to run that plan, and on a yes,
  read the queue again with `--plan`.
- `data.finished` true means the plan is finished. Close it as step 11 says.
  When `data.plan` has `closed` true, the plan issue is closed already, so
  step 11 skips `plan close`.
- Fewer issues than free places, with `data.issues` empty and no session
  still working or waiting on a merge, means the round is over. Stop as step
  12 says.
- Each entry in `warnings` names an issue to start at that the queue does
  not offer, and why. Tell the owner each one.
- On exit 1, relay the errors to the owner and stop starting sessions.

For issues the owner named, including one issue to fix, work or take, read
the queue once, at the start of the round, with every number the owner named:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" queue 12 14 --json
```

What the result means:

- `data.issues` lists the named issues that can start. Start each as step 6
  says, even on exit 1.
- Each entry in `errors` names an issue that cannot start and the reason.
  Tell the owner each one, and start no session on it.
- `data.plan` means the one number named is a plan issue. The round
  runs that plan from here, as a plan the owner named. Look again as step 4
  says for a plan, and read the queue with `--plan`.

For the next issue, read the queue once, at the start of the round, for one
issue, with `--plan` when the owner named a plan:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" queue --plan 653 --count 1 --json
```

The issue in `data.issues` is the round, and the round goes on as a round of
that one named issue. Act on `data.plan`, `data.finished` and exit 1 as
for a count or a plan.

Later in a round of named issues, read the queue no more. A merge or a
stopped implementer frees a place that no issue takes, and the round stops
as step 12 says once each named issue has merged or stopped.

## Step 6: start the round's sessions
<!-- spec: run-starts-one-session-per-issue, run-starts-session-at-round-start, run-checks-started-session, run-looks-on-schedule, run-offers-refused-session -->
<!-- seam: platform: start_session and get_session are app tools that a script cannot call -->

Run this step on the owner's message that starts the round, for each issue
the queue offered, and again for a place that has no live session (a
session that stopped or was archived mid-round). The reviewer of a place
starts with it, as step 9 says.

For each issue the queue offered, print its brief:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" brief 649 --json
```

When `brief` exits 1, the issue changed after the owner approved it. Tell the
owner the error, start no session on it, and go on with the next issue.

On exit 0, start the session with the app's `start_session` tool:

- `initiation`: `user_asked`, since the owner asked for the round. On a turn
  the app refuses, offer the session as the end of this step says.
- `context`: `fresh`.
- `prompt`: `data.prompt`, as `brief` printed it.
- `background`: that the dispatcher started this session to work issue N as
  the implementer, with the work-issue skill, that it reports its pull request
  when it opens one, and that the dispatcher sends it its next issue by
  message once its pull request has merged.
- `use_worktree`: true, so each implementer has its own worktree.
- `model` and `effort`: the implementer's, as step 2 read them, never higher.
- `name`: `issue-` and the number, as in `issue-649`.
- `wake_when_done`: true, so this session is woken when the implementer
  ends a turn.

After the call, read the new session with `get_session` and check it
against its role:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" check-role implementer --model claude-opus-5-5 --effort medium --json
```

Pass the new session's model and effort as `--model` and `--effort`. When
`check-role` exits 1, the app ran the session below its role. Tell the owner
what the app started it at, and start nothing else on that issue until the
owner answers.

Then start the place's reviewer as step 9 says. Tell the owner which sessions
started. Before any pull request is open,
nothing else wakes this session while another session it started is working,
so start the watch and schedule the look as step 7 says, without waiting for
a look to show a pull request. Then end the turn. This session is woken when
an implementer ends a turn, by the watch that step 7 starts, and by the look
that step 7 schedules. A message from the owner wakes it too.

### An issue for a place that is free

When a merge, or an implementer that stopped without a pull request, frees a
place and the queue offers an issue, hand the issue to that place's
implementer. Run this on any turn:

1. List the sessions this session started with `list_sessions` and `linked`
   true. When the place's implementer is idle, go on. When it is working,
   leave the issue to the next look. When it has stopped or is archived,
   start a replacement as this step's first part says.
2. Print the issue's brief, as the first part of this step does. When
   `brief` exits 1, tell the owner and leave the implementer as it is.
3. Empty its conversation with `clear_session`, so the implementer carries
   nothing from the last issue.
4. Send `data.prompt` to the implementer with `SendMessage`, to its `local_`
   id. The brief tells it to work the issue with the work-issue skill, which
   claims the issue on its own `issue/N` branch.

### A session the app refuses

The app lets `start_session` start a session only on the owner's own message
to this session. On a turn that a scheduled look, a started session's turn end
or a background command's exit began, it refuses with "Start sessions only on
the user's own words to you here". `DESIGN.md` records what was measured.
Only a replacement for a stopped or archived session can meet that refusal,
since everything else goes by `SendMessage`.

When `start_session` is refused that way, offer the session as a card with
the same fields, except `initiation`, which is `own_initiative`. Then:

- Tell the owner which pull request (for a reviewer) or which issue (for an
  implementer) waits on the card, and that clicking it or sending any message
  starts it.
- Offer each session once. A later look that finds the same pull request or
  issue still waiting offers nothing more and says nothing more.

When the owner next sends this session a message, start each session it
offered that the owner has not started, with `initiation` `user_asked`. List
the sessions this session started with `list_sessions` and `linked` true to
see which have started, whether this session or the owner's click started them. Read each with `get_session` and check it against its role as above, and tell the owner when one runs below its role.

## Step 7: look again when woken
<!-- spec: run-looks-on-schedule, run-reports-pull-request, run-relays-refused-auto-fix, run-restarts-after-merge, run-starts-offered-sessions -->
<!-- seam: judgment: the owner chose a count, a plan or issues, and the command differs by that choice -->

Each time this session is woken, look again with the last `data.as_of`, at
this round's pull requests alone. For a plan, with its plan issue:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --plan 653 --since 2026-10-15T09:00:00Z --json
```

Otherwise, with `--issue` once for each issue this round started, including
those whose pull request merged:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" events --issue 649 --issue 650 --since 2026-10-15T09:00:00Z --json
```

Keep the new `data.as_of`. Each row of `data.open` carries the `next` step
and `reasons` that `merge-check` gives, so one look shows every open pull
request's next step. A row whose `next` is `ask` can carry the error that
kept `events` from assessing that pull request, as its only reason. Tell the
owner that reason as step 8 does.

CI finishing does not wake this session, and neither does a pull request opening
while another session it started is still working. So after each look that shows
an open pull request, or when the app's `list_sessions` tool, with `linked`
true, lists a session this session started that is working, and right after step
6 starts the round's sessions, this session waits on the round with `watch`. It
exits when a pull request of the round changes: its head, its CI, its reviews or
its review threads, or a merge or a close. This session runs one watch at a
time. Before it starts a watch, it stops the kept one with `TaskStop` (which
does nothing when that watch has ended). It starts the new one from a look's
`data.state` (or without `--state` right after step 6, when no look has been
taken), as a background command with `run_in_background` true, and keeps its
task id. Passing the look's state means a change landing between the look and
the start of the watch ends the watch at once. When the look's `data.state` is
null, because `events` could not read the state, start the watch without
`--state`. For a plan:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" watch --plan 653 --state 831:3f9a1c0e7b2d --json
```

Otherwise, with `--issue` once for each issue this round started:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" watch --issue 649 --issue 650 --state 831:3f9a1c0e7b2d --json
```

When the watch exits, the app wakes this session. Its `data.open`,
`data.merged` and `data.closed` hold the rows of the pull requests that
changed, in the shape `events` gives them, so act on them as on a look's rows.
Then look again, which starts the next watch while a pull request of the round
is open or a session this session started is working. When the watch exits 2,
relay its error and look again.

A look every 15 minutes backs the watch up, and starts it again when it has
stopped. It is a `CronCreate` job (`*/15 * * * *`) that lasts this session and
expires after seven days, so on each look check with `CronList` that it is still
there. When a look shows an open pull request, or `list_sessions` lists a
session this session started that is working, or step 6 has just started the
round, and the job is missing, schedule it and keep the job id. Its prompt says
to take this step's look with the last `data.as_of` and to start the watch from
it, which stops the kept watch first. Delete the job with `CronDelete` when step
12 stops the round.

Then act on each of these that the look or the
note that woke this session shows:

- A pull request in `data.open`. Report its `url` to the owner the first
  time a look shows it. Then check it as step 8 says.
- An implementer whose report says Auto-fix is off for its pull request.
  Tell the owner the pull request's `url` and the app's reason, once, so
  the owner can turn Auto-fix on in the app.
- A pull request that `data.open` no longer lists and `data.merged` has not
  named in this or any earlier look of the round, so it closed unmerged.
  Its reviewer is free for the next pull request. Its implementer keeps its
  claim, so tell the owner the pull request closed and wait for their word.
- A pull request in `data.merged` whose claim this session has not cleared
  since step 8 merged it. Clear its claim as step 10 says.
- An implementer that stopped without a pull request. Relay what it said to
  the owner. When it lost its claim to another session, its place in the
  round is free, so read the queue as step 5 says.
- A session that step 6 offered as a card and the owner has not started, on
  a turn that the owner's message began. Start it as step 6 says.
- An issue the queue offered that no free place has taken yet. Hand it to an
  idle implementer as step 6 says.

## Step 8: check each pull request
<!-- spec: run-merges-what-flows, run-asks-owner-on-hold, run-reviews-each-pull-request, run-acts-on-stalled-wait -->

For each pull request in `data.open`, the look has already named the `next`
step, the `head` and the `reasons`. Act on those, and run `merge-check` only
for a row whose `next` is `merge`, to merge it:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" merge-check 671 --merge --json
```

`data.merged` true means `merge-check` squashed it. Clear its claim as step 10
says. When it holds instead, treat its `data.next` and `data.reasons` as the
row's. For every other row, `next` says what comes next, and `reasons` says
why it holds:

- `review`: the pull request needs the reviewer's look at its head. Act on
  the one of these that holds:
  - This session handed it to a reviewer, and the reviewer is working. Leave
    it to the next look.
  - This session handed it to a reviewer, and the reviewer is idle. Send it
    the `url` and the `head` with `SendMessage`, to its `local_` id, and ask
    it to review the pull request again. It keeps its conversation, since
    this is the same pull request.
  - This session has not handed it to a reviewer, or that reviewer's
    session has stopped or is archived. Hand it to a reviewer as step 9
    says.
- `wait`: the pull request waits on its implementer, such as for a failing
  check, a thread to answer or a check still running. The app's Auto-fix
  does not wake the implementer on every failure, so read its state with
  the app's `list_sessions` tool, with `linked` true. When `only_running_check`
  is true, a running check is all the implementer has to wait on. Leave it
  to the next look: message nobody, and do not count it toward telling the
  owner. Otherwise act on the
  one of these that holds:
  - The implementer is working. Nothing starts here.
  - The implementer is idle, and this session has not yet messaged it for
    this `data.head` with these `data.reasons`. Send it the `url` and each
    reason with `SendMessage`, to its `local_` id. Ask it to fix what it
    can, push, and end its turn once nothing is left for it to do.
  - The implementer is idle and this session already messaged it for this
    head and these reasons, or its session has stopped. Tell the owner the
    `url`, each reason, and that the round does not act on this pull
    request again until the owner sends this session a message. Tell them once for each head and
    reasons.
- `ask`: the pull request holds for the owner. Tell the owner its `url` and
  every reason in `data.reasons`, once for each `data.head`. The owner merges
  it on GitHub or says what to do. Tell the owner that this session notices
  the merge and clears the claim by itself, and that a session it then
  offers as a card starts when the owner clicks it or sends a message. Until
  the owner answers, hand it to no reviewer and merge nothing.

On exit 2, relay the error to the owner and merge nothing.

## Step 9: give a pull request to a reviewer
<!-- spec: run-reviews-each-pull-request, run-checks-started-session, run-offers-refused-session -->

Each place has a reviewer, started with the place's implementer on the
owner's message that starts the round. It starts with the app's
`start_session` tool:

- `initiation`: `user_asked`, since the owner asked for the round. On a turn
  the app refuses, offer the session as step 6 says.
- `context`: `fresh`, so the reviewer starts without any of the
  implementer's context.
- `prompt`: "You are a reviewer in a round of flywheel issues. Do nothing now
  and end your turn. The dispatcher sends you each pull request to review
  as a message, to review with the review-pr skill."
- `background`: that the dispatcher started this session to review the pull
  requests of the round, one at a time, and that it reports when it has
  posted a review.
- `use_worktree`: true.
- `model` and `effort`: the reviewer's, as step 3 read them, never higher.
- `name`: `review-` and the number of the place's issue, as in `review-649`.
- `wake_when_done`: true, so this session is woken when the reviewer ends a
  turn. Check the pull request again then, as step 8 says.

After the call, read the new session with `get_session` and check it
against its role:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" check-role reviewer --model claude-opus-5-5 --effort medium --json
```

Pass the new session's model and effort as `--model` and `--effort`. When
`check-role` exits 1, the app ran the session below its role. Tell the owner
what the app started it at, and start nothing else on that place until the
owner answers.

When `merge-check` names `review` for a pull request that no reviewer has
been given, give it to the reviewer of the place whose implementer opened it
(the `issue/N` branch names the issue, and so the place), on any turn:

1. List the sessions this session started with `list_sessions` and `linked`
   true. When that reviewer is idle and holds no open pull request, go on.
   When it is working, or still holds another open pull request, leave this
   one to the next look. When it has stopped or is archived, start a
   replacement as this step's first part says.
2. Empty its conversation with `clear_session`, so the reviewer carries
   nothing from the last review or from any implementer.
3. Send it "Review pull request #671 as the reviewer, with the review-pr
   skill.", with the pull request's number, using `SendMessage` to its
   `local_` id.

A reviewer keeps the pull request it was given until that pull request
merges or closes, and is idle between looks at it. Only then is it free for
the next one.

## Step 10: clear a merged claim
<!-- spec: run-restarts-after-merge -->

For each issue whose pull request merged, clear its claim:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" clear 649 --json
```

`clear` exits 0 for a claim its implementer already cleared. When it exits 1,
relay its error to the owner and delete nothing by hand. Either way, a merge
from this round freed a place in it, so read the queue as step 5 says. Archive
no session now: the place's implementer and reviewer wait idle for the next
issue and pull request.

## Step 11: close a finished plan
<!-- spec: run-closes-finished-plan -->

When the queue says the plan is finished, close its plan issue unless
`data.plan` has `closed` true:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" plan close 653 --json
```

Tell the owner the plan is closed (it is already, when `data.plan` has
`closed` true), or relay the error when `plan close` exits 1. A finished plan has nothing left to start, so stop as step 12 says
once no session is still working or waiting on a merge.

## Step 12: stop
<!-- spec: run-looks-on-schedule, run-stops-on-empty-queue, run-starts-named-issues, run-archives-reviewer -->
<!-- no-command: reports to the owner what the round's earlier looks found, and archives sessions with an app tool -->

When the queue offers nothing, and either the round started no issue or
`data.open` in the last look of step 7 is empty, report to the owner each
pull request in the round that merged, and each issue that stopped without
one. Stop the watch with `TaskStop` and delete the scheduled look with
`CronDelete`. Archive every implementer and reviewer session this session
started, with the app's `archive_session` tool and each one's `local_` id.
When a call is refused, tell the owner that session is ready to archive. Then
stop.

A round of named issues stops the same way once each issue it started has
merged or stopped, without reading the queue again.

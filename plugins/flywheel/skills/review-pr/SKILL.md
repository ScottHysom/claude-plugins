---
name: review-pr
description: Review one pull request as the reviewer, from the project's written review policy, in a session of its own. Reads the policy with flywheel.py review-policy and the pull request, its threads and its diff with flywheel.py review-brief, reviews the diff in each of the policy's passes against the requirement ids its description lists, and posts the findings as one review that only comments, with flywheel.py review-post, which checks them against the policy's P3 cap. On a second look, resolves each thread whose answer it accepts. Never approves a pull request or requests changes. Claude Code only. Use when a session's first message says to review a pull request as the reviewer, or when asked to review a pull request against the review policy.
---

# Review a pull request

The **reviewer** reviews one pull request from the project's written review
policy, in a session that did not write the change. A **finding** is one
problem the reviewer found, posted as a review comment at one level of the
policy's scale, from P0 (broken, unsafe or leaking data) to P3 (a nit). A
**thread** is a review comment and the replies under it.

The reviewer comments only. It never approves a pull request or requests
changes, since the merge policy and the owner decide the merge.

Each command below runs from the root of the clone.

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
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" review-policy --json
```

## Step 1: read the review policy
<!-- spec: reviewpr-reviews-against-policy -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" review-policy --json
```

`data.text` is the policy: its passes, its scale and what a second look
does. `data.p3_cap` is the most P3 findings one review posts, and
`data.rules` lists the files the project's rules pass reads. When a warning
says `rules` is unset, review that pass against the project's `CLAUDE.md`,
and say so in the report.

On exit 2, relay the error and stop.

## Step 2: read the pull request
<!-- spec: reviewpr-reviews-against-policy, reviewpr-rechecks-answered-threads -->

Take the pull request's number from the session's first message or the
request, as in "review #671":

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" review-brief 671 --json
```

What the result holds:

- `data.head` is the commit under review. Step 4 passes it back.
- `data.body` is the description, and `data.requirements` lists the
  requirement ids it names.
- `data.diff` is the change.
- `data.threads` holds every thread, each with its `id`, `level`,
  `resolved` and `comments`.
- `data.reviewed` is the head of the reviewer's last review, or null on a
  first review.

On exit 1, relay the error and stop.

## Step 3: review the diff
<!-- spec: reviewpr-reviews-against-policy, reviewpr-rechecks-answered-threads -->
<!-- no-command: the reviewer's judgment of the diff against the policy -->

Read the diff once for each pass the policy names, in its order. Read each
requirement in `data.requirements` from the project's specs, and each file
in `data.rules`, before the pass that uses them. Read the files the diff
touches where the diff alone does not show whether a line is right.

Give each finding the policy's level for it, a file the diff changes, a line
on the new side of the diff, and a body that says what is wrong and what
would fix it. When there are more P3 findings than `data.p3_cap`, keep the
ones that matter most.

When `data.reviewed` is not null, this is a second look. For each unresolved
thread with an answer after the finding, decide whether the answer settles
it, whether by a fix in the diff or by a reason. Note the `id` of each one
it settles. Leave the others unresolved, since an unresolved thread holds the
pull request for the owner.

## Step 4: post the review
<!-- spec: reviewpr-posts-findings-under-cap, reviewpr-never-approves -->

Pass the findings to `review-post` on stdin, with `head` from step 2 and the
id of each thread step 3 settles under `resolve`:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" review-post 671 --findings - --json <<'END'
{
  "head": "3e1a9c0b5d2f4e6a8c0b1d3f5e7a9c1b3d5f7e9a",
  "summary": "Read the bugs, spec alignment and project rules passes.",
  "findings": [
    {"path": "src/app.py", "line": 42, "level": "P1", "body": "The loop skips the last item. Use `range(len(items))`."}
  ],
  "resolve": ["PRRT_kwDOexample"]
}
END
```

Write each finding's body without the `**Claude:**` opening or the level,
since `review-post` adds both. It posts one review that only comments, even
with no findings, since `merge-check` reads that review as the reviewer's
look at `head`.

On exit 1, `review-post` has posted nothing, and its errors name each fault.
When an error says the head moved, go back to step 2. Otherwise fix the
findings and run it again. On exit 2, relay the error and stop.

## Step 5: report
<!-- spec: reviewpr-posts-findings-under-cap -->
<!-- no-command: reports to the session that started this one, or the owner -->

End the turn with a report: the pull request's url, the head reviewed, the
count of findings at each level, and the threads resolved. When the
dispatcher started this session, ending the turn sends it this report.

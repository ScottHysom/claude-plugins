---
name: file-issue
description: File an issue, or a plan's issues with the "blocked by" links between them and a tracking issue that lists them in order, in the project's GitHub repository, once the owner has approved what will be filed. Claude Code only. Uses scripts/flywheel.py plan report to check every draft and show it exactly as it will be filed, and plan file to file it, link it, group it and read it back. Use when asked to file an issue, file a gap or a candidate need found while working, file a plan, file a tracking issue, or file issues that depend on each other.
---

# File an issue or a plan

This skill files one issue, or a **plan**: a piece of work that splits into
several issues, some waiting on others. A plan's issues are linked to the
issues that block them, and grouped under a **tracking issue** that lists
them in the order to work them. The owner approves what will be filed once,
from the report `plan report` writes, and `plan file` files exactly what that
report showed.

Run every command from the root of the clone. Never file, link or group an
issue with `gh` directly.

## Locate the script

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"
FLYWHEEL="$ROOT/scripts/flywheel.py"
ls "$FLYWHEEL" || echo "flywheel is not installed as a plugin here"
python3 "$FLYWHEEL" setup --json
```

Run the block as one command, from the project root. If the `ls` fails, the
plugin is not installed here, so stop.

`setup` copies the script into the project at `.flywheel/`, beside a
`.gitignore` that keeps it out of every commit. Each later command starts a
fresh shell, so start every one with `data.prefix` and `&&`, as the steps
below do.

## Step 1: draft the issues
<!-- spec: planreport-cmd-checks-each-draft, planreport-cmd-checks-plan-links, planreport-cmd-accepts-one-issue, fileissue-drafts-in-own-file, plandraft-cmd-makes-own-file -->

Split the work into issues, one problem each. Give each issue:

- a `key` of your own, such as `A`, which names it inside the plan.
- a `title` that names the problem, not the fix.
- a `body` that opens with `**Claude:**`, then the headings `## What's
  wrong`, `## Evidence`, `## Done when` and `## Requirements`.
- `labels`: exactly one of `bug`, `enhancement` or `docs`, and exactly one
  area, `plugin:<name>` or the whole-repository area. Never the approval
  label or the plan label. `.flywheel/labels.json` gives those three under
  `roles`, as `repo-area`, `approval` and `plan`, and they are `repo`,
  `approved` and `tracking` where it does not.
- `blocked_by`, when it waits on anything: the keys of the issues in the plan
  it waits on, and the numbers of open issues outside it.

An issue that is open already, such as one filed while working another,
joins a plan as a `key` and its `number`, with `blocked_by` when it waits on
anything, and nothing else. Filing leaves it as it is, and adds it to the
tracking issue in its place in the order.

In a body, name another issue of the plan as `#{KEY}`, never by a number you
expect it to get. Filing puts the issue's number in place of `{KEY}`. A body
can name only an issue filed before it, so name a blocker from the issue it
blocks, not the other way round.

Write each paragraph and each list item of a body, and of the tracking
issue's plan, on one line. GitHub renders a newline inside one as a line
break.

One issue alone takes no `tracking`. A plan of several issues takes a
`tracking` object with a `title` and a `plan`. The plan says:

- what problem the plan fixes.
- how its issues together fix it.
- why they come in their order.

`plan report` adds the opening `**Claude:**` and an Order section written
from the links, so write neither.

Make a file for the drafts:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" plan draft --json
```

`data.path` is a file that no other run is given. Write the drafts there, and
name the file in every later step by the path exactly as `plan draft` printed
it, never through `$TMPDIR` or another variable. The commands below show it
as `/var/folders/k2/T/plan-x8q1zv.json`.

One issue:

```sh
cat > /var/folders/k2/T/plan-x8q1zv.json <<'END'
{"issues": [
  {"key": "A", "title": "<the title>", "labels": ["bug", "repo"],
   "body": "**Claude:**\n\n## What's wrong\n\n<...>"}]}
END
```

A plan:

```sh
cat > /var/folders/k2/T/plan-x8q1zv.json <<'END'
{"issues": [
  {"key": "A", "title": "<the title>", "labels": ["bug", "repo"],
   "body": "**Claude:**\n\n## What's wrong\n\n<...>"},
  {"key": "B", "title": "<the title>", "labels": ["enhancement", "repo"],
   "blocked_by": ["A"], "body": "**Claude:**\n\n## What's wrong\n\nOnce #{A} lands, <...>"},
  {"key": "C", "number": 416, "blocked_by": ["B"]}],
 "tracking": {"title": "<the plan's title>", "plan": "<the problem, how the issues fix it, and why this order>"}}
END
```

## Step 2: check the drafts
<!-- spec: planreport-cmd-checks-each-draft, planreport-cmd-checks-plan-links, planreport-cmd-orders-by-links, planreport-cmd-accepts-one-issue, repo:planreport-cmd-writes-report-file, planreport-cmd-shows-filed-issue -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" plan report --drafts /var/folders/k2/T/plan-x8q1zv.json --json
```

When it exits 1, its `errors` name every fault in the drafts. Fix them all in
the file and run `plan report` again before showing anything to the owner. A
warning names an issue an earlier run filed that the drafts no longer hold.
Tell the owner about it.

When it exits 0, `data.report` is the path of the report: each issue whole,
in the order it will be filed, and the tracking issue's body as it will be
filed, when there is one. The file ends with the approval token, which is
`data.token`. An issue marked "Filed already" was filed before the plan, or
by an earlier run of `plan file` that stopped part way, and step 4 leaves it
as it is.

## Step 3: take the owner's approval
<!-- spec: fileissue-shows-report-whole, repo:fileissue-revises-on-comment -->
<!-- no-command: platform. The model publishes the report and asks the owner, which a script cannot do. -->

Publish the file at `data.report` as a private artifact with the Artifact
tool, as markdown, with the icon `checklist`. After every later run of step
2, publish the same file path again, so the report keeps its address. The
owner reads the report there, and nowhere else. Never retype it or a part of
it into chat or a dialog, because the owner then approves a text that `plan
file` never sees.

Then put one `AskUserQuestion` to the owner, naming the artifact's address
and `data.token`, with these options:

- file it.
- comment first, on the artifact.
- file nothing.

On "comment first", end the turn. A comment the owner sends to Claude starts
a new turn. Revise the drafts as the comment asks, run step 2 again, publish
the report again, and answer in the comment's thread with
`ArtifactComments`, saying what changed. Ask the one question again, with
the new token, once every thread sent to Claude is answered.

When the Artifact tool is not available, or refuses to publish, read the file
at `data.report` and give it whole in your reply, as it stands, then end the
turn. The owner's reply is the decision, and it names the token.

On "file nothing", stop.

## Step 4: file it
<!-- spec: planfile-cmd-requires-token, planfile-cmd-files-in-order, repo:planfile-cmd-resumes-after-failed-call, planfile-cmd-groups-filed-issue, planreport-cmd-accepts-one-issue -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" plan file --drafts /var/folders/k2/T/plan-x8q1zv.json --token 3f9a1c0e7b2d4a68 --json
```

Pass the token from the report the owner approved. Give the Bash call a
timeout of at least a minute for each issue, since each one takes several
calls to GitHub.

`plan file` refuses a token when the drafts, the repository or its labels
have changed since that report, and then files nothing. Run step 2 again and
ask again.

When a call to GitHub fails, `plan file` stops and exits 1, and what it filed
is in `data`. Run the same command again with the same token. It files only
what is missing, and never files an issue twice. When it exits 1 after filing
everything, its `errors` name each link or sub-issue that GitHub does not
hold as the drafts say.

## Step 5: report
<!-- spec: planfile-cmd-files-in-order, planfile-cmd-verifies-links -->
<!-- no-command: hand-off to the owner. The output of plan file in step 4 is the report. -->

Tell the owner:

- each issue in `data.issues`, with its `number` and `url`, and whether this
  run filed it.
- the tracking issue in `data.tracking`, with its `number` and `url`, when
  there is one.
- each link in `data.links` and each sub-issue in `data.sub_issues` this run
  added.
- each error, when `plan file` exited 1.

The owner approves each issue, and the tracking issue when there is one.
Never add `approved` yourself.

---
name: file-plan
description: File a plan's issues in this repo, with the "blocked by" links between them and a tracking issue that lists them in order, once the owner has approved the plan whole. Uses .github/scripts/issues.py plan report to check every draft against CLAUDE.md's rules for issues and show the plan exactly as it will be filed, and plan file to file it, link it, group it and read it back. Use when a plan yields several issues, or when asked to file a plan, file a tracking issue, or file issues that depend on each other.
---

# File a plan as issues

A **plan** is a piece of work the owner has asked for that splits into
several issues, some waiting on others. This skill files them as GitHub
issues, links each to the issues that block it, and groups them under a
**tracking issue** that lists them in the order to work them. The owner
approves the plan once, from the report `plan report` writes, and `plan
file` files exactly what that report showed.

Run every command from the root of the clone. Never file, link or group an
issue with `gh` directly.

## Step 1: draft the plan
<!-- spec: planreport-cmd-checks-each-draft, planreport-cmd-checks-plan-links -->
<!-- no-command: judgment. The model splits the plan into issues and writes each one, and step 2's report checks them. -->

Split the plan into issues, one problem each, as CLAUDE.md asks under
"Issues". Give each issue:

- a `key` of your own, such as `A`, which names it inside the plan;
- a `title` that names the problem, not the fix;
- a `body` that opens with `**Claude:**`, then the headings `## What's
  wrong`, `## Evidence`, `## Done when` and `## Requirements`;
- `labels`: exactly one of `bug`, `enhancement` or `docs`, and exactly one
  area, `plugin:<name>` or `repo`. Never `approved` or `tracking`;
- `blocked_by`, when it waits on anything: the keys of the issues in the plan
  it waits on, and the numbers of open issues outside it.

In a body, name another issue of the plan as `#{KEY}`, never by a number you
expect it to get. Filing puts the issue's number in place of `{KEY}`. A body
can name only an issue filed before it, so name a blocker from the issue it
blocks, not the other way round.

The tracking issue takes a `title` and a `plan`: what the plan is for and why
its issues come in their order. `plan report` adds the opening `**Claude:**`
and an Order section written from the links, so write neither.

Write the plan outside the project:

```sh
cat > "${TMPDIR:-/tmp}/plan.json" <<'END'
{"issues": [
  {"key": "A", "title": "<the title>", "labels": ["bug", "repo"],
   "body": "**Claude:**\n\n## What's wrong\n\n<...>"},
  {"key": "B", "title": "<the title>", "labels": ["enhancement", "repo"],
   "blocked_by": ["A"], "body": "**Claude:**\n\n## What's wrong\n\nOnce #{A} lands, <...>"}],
 "tracking": {"title": "<the plan's title>", "plan": "<what it is for, and why this order>"}}
END
```

## Step 2: check the plan
<!-- spec: planreport-cmd-checks-each-draft, planreport-cmd-checks-plan-links, planreport-cmd-orders-by-links, planreport-cmd-writes-report-file -->

```sh
python3 .github/scripts/issues.py plan report --drafts "${TMPDIR:-/tmp}/plan.json" --json
```

When it exits 1, its `errors` name every fault in the plan. Fix them all in
the plan file and run `plan report` again before showing anything to the
owner. A warning names an issue an earlier run filed that the plan no longer
holds. Tell the owner about it.

When it exits 0, `data.report` is the path of the report: each issue whole,
in the order it will be filed, and the tracking issue's body as it will be
filed. The file ends with the approval token, which is `data.token`. An issue
marked "Filed already" was filed by an earlier run of `plan file` that
stopped part way, and step 4 leaves it as it is.

## Step 3: take the owner's approval
<!-- spec: fileplan-shows-report-whole, fileplan-revises-on-comment -->
<!-- no-command: platform. The model publishes the report and asks the owner, which a script cannot do. -->

Publish the file at `data.report` as a private artifact with the Artifact
tool, as markdown, with the icon `checklist`. After every later run of step
2, publish the same file path again, so the report keeps its address. The
owner reads the plan there, and nowhere else. Never retype the plan or a part
of it into chat or a dialog, because the owner then approves a text that
`plan file` never sees.

Then put one `AskUserQuestion` to the owner, naming the artifact's address
and `data.token`, with these options:

- file the plan;
- comment first, on the artifact;
- file nothing.

On "comment first", end the turn. A comment the owner sends to Claude starts
a new turn. Revise the plan file as the comment asks, run step 2 again,
publish the report again, and answer in the comment's thread with
`ArtifactComments`, saying what changed. Ask the one question again, with
the new token, once every thread sent to Claude is answered.

When the Artifact tool is not available, or refuses to publish, read the file
at `data.report` and give it whole in your reply, as it stands, then end the
turn. The owner's reply is the decision, and it names the token.

On "file nothing", stop.

## Step 4: file the plan
<!-- spec: planfile-cmd-requires-token, planfile-cmd-files-in-order, planfile-cmd-resumes-after-failure -->

```sh
python3 .github/scripts/issues.py plan file --drafts "${TMPDIR:-/tmp}/plan.json" --token 3f9a1c0e7b2d4a68 --json
```

Pass the token from the report the owner approved. Give the Bash call a
timeout of at least a minute for each issue, since each one takes several
calls to GitHub.

`plan file` refuses a token when the plan, the repository or its labels have
changed since that report, and then files nothing. Run step 2 again and ask
again.

When a call to GitHub fails, `plan file` stops and exits 1, and what it filed
is in `data`. Run the same command again with the same token. It files only
what is missing, and never files an issue twice. When it exits 1 after filing
everything, its `errors` name each link or sub-issue that GitHub does not
hold as the plan says.

## Step 5: report
<!-- spec: planfile-cmd-files-in-order, planfile-cmd-verifies-links -->
<!-- no-command: hand-off to the owner. The output of plan file in step 4 is the report. -->

Tell the owner:

- each issue in `data.issues`, with its `number` and `url`, and whether this
  run filed it;
- the tracking issue in `data.tracking`, with its `number` and `url`;
- each link in `data.links` and each sub-issue in `data.sub_issues` this run
  added;
- each error, when `plan file` exited 1.

The owner approves the tracking issue and each issue in it. Never add
`approved` yourself.

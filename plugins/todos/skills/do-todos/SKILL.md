---
name: do-todos
description: File the TODO comments left in a project's uncommitted changes as GitHub issues, or as comments on open issues that already cover them, and take each one out of its file. Claude Code only. Uses scripts/todos.py to find every TODO added since the last commit, in any text file and any comment syntax, with the open issues like each, to check the drafts against the files, the issues and the repository's labels, and to file them through gh once the author approves the report. Asks about every TODO that says too little in one round, before drafting. Use when asked to file the TODOs, turn TODO comments into issues, collect the notes left during a review, or clear the TODOs out of a change. Never commits.
---

# File the TODOs as issues

A TODO is a note the author left in a file while reviewing it: a line that
opens, after its indent and the file's comment marker, with `TODO:` or with a
kind word, as in `TODO(bug):`. This skill drafts an issue for each, or a
comment on an open issue that already covers it, shows the author every draft,
files the ones approved, and removes each TODO from its file once its issue or
comment exists.

## Locate the script

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"
TODOS="$ROOT/scripts/todos.py"
ls "$TODOS" || echo "todos is not installed as a plugin here"
python3 "$TODOS" setup --json
```

Run the block as one command, from the project root. If the `ls` fails, stop:
the plugin is not installed here.

`setup` copies the script into the project at `.todos/`, beside a
`.gitignore` that keeps it out of every commit. Each later command starts a
fresh shell, so start every one with `data.prefix` and `&&`, from the
project root:

```sh
TODOS=.todos/todos.py && python3 "$TODOS" scan --json
```

## Step 1: gather the TODOs
<!-- spec: dotodos-reads-todos-from-scan, dotodos-asks-which-checkout -->
<!-- seam: judgment: the author picks which checkout to collect TODOs from, or none -->

```sh
TODOS=.todos/todos.py && python3 "$TODOS" scan --json
```

`data.todos` lists every TODO added since the last commit. Each has its
`file`, its `first` and `last` lines, its `text` (the first line as it
stands), its `kind` or null, its `title`, its `detail`, `above`, the line
it sits above, or for a TODO at the end of a line that line, and `similar`, the open issues GitHub's search returns for its
title, each with its `number`, `title` and `url`. `data.labels` lists the
labels of `data.repository`, the repository the issues would go to. Each warning names a line that looks like a
TODO and was not read, and why.

**When `data.other_worktrees` is not empty,** this tree does not hold any
TODO and another checkout of the repo does. Put one `AskUserQuestion` to the
author, with an option for each entry giving its `root`, `branch` and
`files`, and an option to collect none. Ask even when there is only one
entry, because filing removes the TODOs from that checkout. On a pick, scan
that one:

```sh
TODOS=.todos/todos.py && python3 "$TODOS" scan --from "<root>" --json
```

Pass the same `--from "<root>"` to `report` and `file` in step 4. If the
author picks none, stop.

When `data.todos` is empty and `data.other_worktrees` is too, tell the author,
with any warnings, and stop.

**Never search the files for TODOs with a command of your own,** such as
`grep`. `scan` reads only the lines added since the last commit, and skips
code fences, binary files and the copy in `.todos/`. A search of your own
finds a different set, and the drafts it yields fail in step 4.

## Step 2: settle what is unclear
<!-- spec: dotodos-asks-at-once -->

<!-- no-command: judgment. The model decides which TODOs need the author, and asks. -->

Read each TODO with the lines around it, from `above` and the file. Find every
TODO where any of these holds:

- it says too little to write an issue that someone else could act on, such
  as what is wrong, or what done means;
- it does not give a kind, and its words do not settle one;
- an issue in its `similar` may cover it, and the issue's title and the TODO
  do not settle whether it does;
- it may repeat another TODO.

Ask about all of them in one round, before writing any draft. Use
`AskUserQuestion`, in as many calls as its limit on questions per call needs,
one after another. Name each TODO by its `file:first` and title. Offer the
likely answers as options, so a one-word TODO costs the author one click.

Ask nothing when every TODO is clear. Never ask one TODO at a time, and never
ask again after drafting starts.

## Step 3: route and draft
<!-- spec: dotodos-follows-project-rules, dotodos-follows-todo-kind, dotodos-reuses-open-issues -->

<!-- no-command: judgment. The model writes each draft, and step 4's report checks them. -->

Read the project's own rules for issues first: its `CLAUDE.md`, and any
templates under `.github/ISSUE_TEMPLATE/`. Follow them for the title, the
body's headings and the labels. Take every label from `data.labels`. `report`
refuses any other, and refuses `approved`, which only the owner adds.

Draft each TODO by its kind, or the kind the author gave in step 2:

| Kind | Draft it as |
|---|---|
| `bug` | a defect: what happens, and what should |
| `fix` | the defect it fixes, with the fix as what done means |
| `change` | an improvement to the code |
| `design` | a change to what the project does or how it is built |
| `docs` | a change to what a document says |
| `prose` | a change to how a passage reads |

Title the problem, not the fix, unless the project's rules say otherwise. Put
the TODO's detail and the author's answers in the body, with the file and line
it was left at.

When an open issue already covers a TODO, from its `similar` or the author's
answer in step 2, route the TODO to `comment` on that issue rather than
drafting a new one. Write the comment's body as what the TODO adds to the
issue, with the file and line it was left at, and follow the project's rules
for replies, such as a prefix its `CLAUDE.md` asks for.

Write the drafts outside the project, one object per TODO:

```sh
cat > "${TMPDIR:-/tmp}/todo-drafts.json" <<'END'
[{"file": "src/run.py", "line": 12, "text": "# TODO(bug): run() waits forever",
  "route": "issue", "title": "<the title>", "body": "<the body>",
  "labels": ["bug"]},
 {"file": "src/run.py", "line": 30, "text": "# TODO: retry on 502",
  "route": "comment", "issue": 7, "body": "<the comment>"}]
END
```

`file`, `line` and `text` are the TODO's `file`, `first` and `text` from
step 1, copied exactly. `route` is `issue`, with `title`, `body` and `labels`,
or `comment`, with `issue`, the open issue's number, and `body`. A TODO the
author wants left in place does not get a draft.

## Step 4: report, approve, file
<!-- spec: dotodos-shows-report-whole -->

<!-- seam: judgment: the author approves the report, or a part of it, before file runs -->

```sh
TODOS=.todos/todos.py && python3 "$TODOS" report --drafts "${TMPDIR:-/tmp}/todo-drafts.json"
```

Add `--from "<root>"` to `report` and `file` when step 1 collected from
another checkout.

`report` names the repository the issues go to, then prints each draft whole,
the TODOs left in place, and `scan`'s warnings. Show the author that output as
it stands. Never retype it into a table of your own, because the author then
approves a text that `file` never sees. Its last line, printed only when it
exits 0, is the approval token, such as `approval token: 3f9a1c0e7b2d4a68`.

When `report` exits 1, its errors name each draft it refused and why. Fix the
drafts and run `report` again before showing it.

Take one decision over the whole set: all of it, a part, or none. When the
author approves a part, take the rest out of the drafts file and run `report`
again. Its TODOs stay in their files. The token `file` takes is the one from
the report the author approved as a whole.

```sh
TODOS=.todos/todos.py && python3 "$TODOS" file --drafts "${TMPDIR:-/tmp}/todo-drafts.json" --token 3f9a1c0e7b2d4a68
```

Give the Bash call a timeout of at least a minute for each draft, since each
issue or comment is one call to GitHub. `file` refuses a token when the drafts, a file
they name, the last commit or the repository has changed since that report,
and then files nothing. Run `report` again and show it to the author.

## Step 5: report and stop
<!-- spec: dotodos-never-commits -->

<!-- no-command: hand-off to the author. The output of file in step 4 is the report. -->

Tell the author:

- each issue filed, with its number and address, from `file`'s output;
- each comment posted, with its issue's number and the comment's address;
- each file changed, which is each file a filed or posted TODO came from,
  and the checkout it is in when step 1 collected from another;
- each TODO left in place: the ones without a draft in step 4's report, and
  any `file` lists as not filed.

When `file` exits 1, say which call failed, from its error. Every TODO whose
issue or comment exists is gone from its file, and every other one is still
there.

Leave the working tree as it is. **Never commit.** The author reviews the
changes and commits them the project's usual way.

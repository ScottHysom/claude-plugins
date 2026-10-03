---
name: do-todos
description: File the TODO comments left in a project's uncommitted changes as GitHub issues, and take each one out of its file. Claude Code only. Uses scripts/todos.py to find every TODO added since the last commit, in any text file and any comment syntax, to check the drafted issues against the files and the repository's labels, and to file them through gh once the author approves the report. Asks about every TODO that says too little in one round, before drafting. Use when asked to file the TODOs, turn TODO comments into issues, collect the notes left during a review, or clear the TODOs out of a change. Never commits.
---

# File the TODOs as issues

A TODO is a note the author left in a file while reviewing it: a line that
opens, after its indent and the file's comment marker, with `TODO:` or with a
kind word, as in `TODO(bug):`. This skill drafts an issue for each, shows the
author every draft, files the ones approved, and removes each TODO from its
file once its issue exists.

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
<!-- spec: dotodos-reads-todos-from-scan -->

```sh
TODOS=.todos/todos.py && python3 "$TODOS" scan --json
```

`data.todos` lists every TODO added since the last commit. Each has its
`file`, its `first` and `last` lines, its `text` (the first line as it
stands), its `kind` or null, its `title`, its `detail`, and `above`, the line
it sits above. `data.labels` lists the labels of `data.repository`, the
repository the issues would go to. Each warning names a line that looks like a
TODO and was not read, and why.

When `data.todos` is empty, tell the author, with any warnings, and stop.

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
- it may repeat an issue already open, or another TODO.

Ask about all of them in one round, before writing any draft. Use
`AskUserQuestion`, in as many calls as its limit on questions per call needs,
one after another. Name each TODO by its `file:first` and title. Offer the
likely answers as options, so a one-word TODO costs the author one click.

Ask nothing when every TODO is clear. Never ask one TODO at a time, and never
ask again after drafting starts.

## Step 3: route and draft
<!-- spec: dotodos-follows-project-rules, dotodos-follows-todo-kind -->

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

Write the drafts outside the project, one object per TODO:

```sh
cat > "${TMPDIR:-/tmp}/todo-drafts.json" <<'END'
[{"file": "src/run.py", "line": 12, "text": "# TODO(bug): run() waits forever",
  "route": "issue", "title": "<the title>", "body": "<the body>",
  "labels": ["bug"]}]
END
```

`file`, `line` and `text` are the TODO's `file`, `first` and `text` from
step 1, copied exactly. `route` is `issue`. A TODO the author wants left in
place does not get a draft.

## Step 4: report, approve, file
<!-- spec: dotodos-shows-report-whole -->

<!-- seam: judgment: the author approves the report, or a part of it, before file runs -->

```sh
TODOS=.todos/todos.py && python3 "$TODOS" report --drafts "${TMPDIR:-/tmp}/todo-drafts.json"
```

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
issue is one call to GitHub. `file` refuses a token when the drafts, a file
they name, the last commit or the repository has changed since that report,
and then files nothing. Run `report` again and show it to the author.

## Step 5: report and stop
<!-- spec: dotodos-never-commits -->

<!-- no-command: hand-off to the author. The output of file in step 4 is the report. -->

Tell the author:

- each issue filed, with its number and address, from `file`'s output;
- each file changed, which is each file a filed TODO came from;
- each TODO left in place: the ones without a draft in step 4's report, and
  any `file` lists as not filed.

When `file` exits 1, say which call failed, from its error. Every TODO whose
issue was filed is gone from its file, and every other one is still there.

Leave the working tree as it is. **Never commit.** The author reviews the
changes and commits them the project's usual way.

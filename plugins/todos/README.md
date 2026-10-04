# TODOs

TODOs turns the notes you leave in your files while reviewing them into
GitHub issues. You write a short TODO comment where you find the work, and
Claude drafts an issue for each one, shows you every draft, files the ones you
approve, and takes each TODO back out of its file.

**Claude Code only.** The plugin needs a git clone with a GitHub remote, and
GitHub's command-line tool, `gh`, installed and signed in (`gh auth login`).

## Leaving a TODO

A TODO is a line that opens, after its indent and the file's own comment
marker, with `TODO:`. The rest of the line is the issue's title:

```python
# TODO: run() waits forever when gh stalls
def run(repo, cmd):
```

Say what kind of work it is with one word in brackets, and Claude drafts it
as that kind without asking:

| Word | The work |
|---|---|
| `TODO(bug):` | something is broken |
| `TODO(fix):` | a fix for something broken |
| `TODO(change):` | an improvement to the code |
| `TODO(design):` | a change to what the project does or how it is built |
| `TODO(docs):` | a change to what a document says |
| `TODO(prose):` | a change to how a passage reads |

Lines straight below a TODO that open with the same comment marker are its
detail, up to a blank line:

```sh
# TODO(bug): the retry loop never gives up
# It retries a 404 too, which will never succeed.
```

A block comment holds its detail inside it:

```markdown
<!-- TODO(docs): the layout leaves out .github/workflows/
and the two JSON lists beside it -->
```

A TODO can also go at the end of the line it is about, after the file's
comment marker. It has a title and no detail:

```python
retries = 3  # TODO(fix): the vendor allows 5 retries
```

Claude reads it only when the TODO is all you changed on that line. When it
is filed, the line goes back to what you last committed. If you changed the
code on the line too, Claude warns about the TODO and leaves it in place.

Any text file works, whatever its language, because the TODO uses the file's
own comment syntax, so the file still runs, compiles and renders as before.
In a markdown file, a TODO inside a code block or a code span is left alone,
so a document can show the syntax.

Only TODOs you have added since your last commit count. A TODO already
committed stays where it is.

Claude may work in a separate copy of your project, which the Claude desktop
app makes for each session. When that copy does not hold any TODOs and the
folder you review in does, Claude names the folder, with its branch and files,
and asks whether to collect them from there. Their issues are filed the same
way, and the TODOs come out of the files in that folder.

## Filing them

Ask Claude to file your TODOs. Claude:

1. Finds every TODO in your uncommitted changes, and warns about any line
   that looks like one but cannot be read.
2. Asks you, in one round, about every TODO that says too little, whose
   kind is unclear, or that may repeat an issue already open.
3. Drafts an issue for each, following your project's own rules for issues
   and using only labels your repository has. When an open issue already
   covers a TODO, Claude drafts a comment on that issue instead, so the
   problem keeps one issue.
4. Shows you the repository the issues will go to, every draft in full, and
   the TODOs that will stay. You approve all of them, some, or none.
5. Files the issues and posts the comments you approved, and removes each
   TODO once its issue or comment exists.

Nothing reaches GitHub before you approve. If anything changes between the
report and the filing, Claude shows you a fresh report first.

## What it changes

Each TODO that is filed or posted comes out of its file, with the blank lines you added
around it. A file whose only changes were TODOs goes back to exactly what it
was at your last commit. Nothing else in your files changes.

The plugin keeps a copy of its script in `.todos/` in your project, with its
own `.gitignore`, so it never shows up in a commit. Claude never commits. You
review the changes and commit them your usual way.

The plugin never puts a label named `approved` on an issue, so approving the
work an issue describes stays with a person.

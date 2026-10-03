# todos: technical design

This file explains why the todos plugin is built the way it is, for a
contributor changing it. What the plugin does and how to use it is in
[README.md](README.md). The requirements it serves are in `specs/todos.md`, at
the repo root.

## Origin

The owner asked, in #311, for a way to leave a note in any file while
reviewing it and have a skill open an issue for each one, with an interview
when a note says too little. Running or compiling the file had to keep
working with the notes in it. #311 records the rulings that shaped the
design, and #312 the half that reaches GitHub.

## Why the marker is read off the line

A TODO's comment marker is whatever comes before `TODO` on its own line, so
the script does not keep a table of comment syntax by file type. The
only syntax it knows is the two block comments, `/* */` and `<!-- -->`. A
marker that is wrong for its file shows up when the file runs, and filing
removes it anyway.

## Why only uncommitted lines

The script reads the lines added since the last commit and nothing else. A
`TODO:` in a committed test fixture, or in a document that quotes the syntax,
is never collected, and filing never removes a committed line. `scan` compares
each file with the last commit by a shortest edit script: the fewest lines
added and removed that turn one into the other. A committed line then never
reads as added, even where the file repeats it, which Python's difflib does
not promise.

## Why a script

The model drafts each issue and decides what to ask the author. The script
does the rest:

- finding the TODOs
- checking each draft against the file as it is now
- calling `gh`
- removing the lines

The removal has to give back the committed file byte for byte. A model
editing by hand gets that wrong eventually, and nothing would notice.

## The report and the token

`report` prints every draft whole and ends with a token that hashes the
drafts file, the repository gh resolves for the clone, the last commit and
every file a draft names. `file` refuses any other token. The author approves
the text `file` will send, in the repository the report named, and a fork
cannot send issues to its upstream, since every gh call after the first passes
that repository as `--repo`.

A partial approval runs `report` again on the trimmed drafts, so `file` has no
`--partial`.

## Filing cannot be undone

Deleting an issue takes admin rights on the repository, which the user may not
hold, so a batch cannot be filed all or nothing. `file` checks everything it
can before its first call to GitHub: the token, every draft, and that it can
open every file it will change for writing. It then removes each TODO as soon
as its issue exists, and stops at the first call that fails, so a run cut
short leaves exactly the TODOs whose issues do not exist.

It works from the last TODO in each file to the first, so removing one never
moves the lines of a TODO still to come.

## Blank lines

A TODO usually sits in blank lines the author added with it. `file` removes
those, keeps every committed blank line, and keeps one added blank line where
it separates new code from the lines around it. When the removal reaches the
end of the file, the line left last gets back the ending it had at the last
commit. The script's docstring has the exact rule. Together these give back
the committed file, byte for byte, when the only changes were TODOs and the
blank lines around them, and
`tests/todos/test_properties_todos_removal.py` checks that for every file
Hypothesis builds.

## `approved`

In the owner's repositories only the owner adds the `approved` label.
`.claude/hooks/issue_guard.py` reads only the text of a Bash command, so it
does not see a script that runs `gh`, and CI does not catch an issue labeled
when it is created. `report` and `file` therefore refuse a draft carrying the
label, in any case.

## Why no skill commits

How a project commits is settled wherever that project settles it, such as
its `CLAUDE.md`. The skill leaves every change uncommitted, and the copy of
the script in `.todos/` carries a `.gitignore` of `*`, so it never reaches a
commit.

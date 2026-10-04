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

## A TODO at the end of a line

The owner ruled in #311 that a TODO may sit at the end of the line it is
about, after the code. Filing it cannot remove its line, so `file` takes the
TODO's text off and leaves the rest. That is only safe when the rest is a
line of the last commit. On a new line it would leave the author's new code
with no TODO, and on a line whose code changed too it could not tell the
TODO from the change. So `scan` reads such a TODO only when the line without
it is a committed line, and warns otherwise.

`scan` finds that out by comparing the file with the last commit as if every
candidate TODO were already gone. A candidate whose line then matches a
committed one is read, and the line counts as committed for the blank-line
tidying too. Where several cuts would leave a committed line, the longest
wins, so a committed trailing space stays.

## TODOs in another checkout

The owner reviews in the main checkout, on a branch of their own, while the
desktop app opens each Claude Code session in a worktree of its own. #301
found the same split for prose-tuning's update-prose-config. When this tree
does not hold a TODO, `scan` scans every other worktree that `git worktree
list` names, and exits 1 naming each one that holds TODOs. `--from` then
points `scan`, `report` and `file` at that worktree, so the TODOs are filed
and removed where the author left them.

prose-tuning's `carry` copies the edits into the session's tree, because
Claude Code refuses a worktree session's edits to the main checkout's
`.claude/`. A TODO can sit in any file, and the probe recorded under
`constraint bash-writes-other-checkout` in `specs/todos.md` found that a
script run through Bash can open one there for writing. So nothing is carried.

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

## Open issues like a TODO

The owner ruled in #313 that a TODO repeating an open issue becomes a comment
on that issue. `scan` lists, beside each TODO, the first five open issues
GitHub's search returns for its title, and the model judges whether one
covers it. GitHub's REST search allows a signed-in client 30 requests a
minute, so `scan` sends every title in one GraphQL query, with an aliased
`search` per title, as `.github/scripts/check-specs.py` does for issue
lookups.

A comment draft names its issue by number. `report` and `file` each look the
issues up, in one query, and refuse a draft whose issue does not exist or is
closed. The token covers the drafts and not the issue, so `file` checks again
rather than trusting the report. `gh api graphql` exits 1 when a lookup finds
nothing, and still prints the data, so the script reads a missing issue from
that output, and stops on any other error.

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

## Handing a TODO to another skill

The owner asked in #319 for a `prose` TODO to reach the skill that learns
prose rules, rather than become an issue, and for a TODO about what a document
says never to reach it. A draft can take the route `skill`, which names a
skill as the Skill tool takes it. The model picks the skill from the skills
the session lists, by their descriptions, so `report` cannot check the name,
and the token is what holds the author's approval of it.

`file` removes a routed TODO like any other, with no call to GitHub, and then
prints one hand-off per skill. Each holds the TODO's title and detail and the
passage it sat above, read once every finished TODO is gone, so its line
numbers are the ones the receiving skill sees. The passage runs from the line
`scan` gave as `above` to the nearest blank line or TODO on either side. The
convention in CLAUDE.md, under "A skill hands work to another plugin's skill
by convention", says what a hand-off carries.

The receiving skill may end the session's work when it stops, so do-todos
gives its report first and invokes the skills as its last act.

## Why no skill commits

How a project commits is settled wherever that project settles it, such as
its `CLAUDE.md`. The skill leaves every change uncommitted, and the copy of
the script in `.todos/` carries a `.gitignore` of `*`, so it never reaches a
commit.

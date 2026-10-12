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
marker that is wrong for its file shows up when the file runs.

## Why only uncommitted lines

The script reads the lines added since the last commit and nothing else. A
`TODO:` in a committed test fixture, or in a document that quotes the syntax,
is never collected, and filing marks only uncommitted lines. `scan` compares
each file with the last commit by a shortest edit script: the fewest lines
added and removed that turn one into the other. A committed line then always
reads as committed, even where the file repeats it, a guarantee Python's
difflib does not make.

## A TODO at the end of a line

The owner ruled in #311 that a TODO may sit at the end of the line it is
about, after the code. `scan` reads such a TODO only when the line without it
is a committed line, and warns otherwise. On a line whose code changed too, it
could not tell the TODO from the change.

`scan` finds that out by comparing the file with the last commit as if every
candidate TODO were already gone. A candidate whose line then matches a
committed one is read, and the line counts as committed in a hand-off's
list of changed lines too. Where several cuts would leave a committed line, the longest
wins, so a committed trailing space stays.

## TODOs in another checkout

The owner reviews in the main checkout, on a branch of their own, while the
desktop app opens each Claude Code session in a worktree of its own. #301
found the same split for prose-tuning's update-prose-config. When this tree
does not hold a TODO, `scan` scans every other worktree that `git worktree
list` names, and exits 1 naming each one that holds TODOs. `--from` then
points `scan`, `report` and `file` at that worktree, so the TODOs are filed
and marked where the author left them.

The author often names the checkout when invoking the skill, as in
`/todos:do-todos in scott/prose-changes`. `--from` takes a branch as well as a
folder, so the skill passes the name as the author gave it and the script
checks it, rather than the model guessing which worktree a name means. A
mistyped name is refused with the list of worktrees and their branches.
`--from` naming this tree reads as if `--from` were left out, so the skill does
not need to tell this tree from another before passing the name on. Each
hand-off from `file --from` names the checkout's root and branch, so the
receiving skill reads the passage where it was left, as CLAUDE.md's hand-off
convention asks, instead of asking the author again.

prose-tuning's `carry` copies the edits into the session's tree, because
Claude Code refuses a worktree session's edits to the main checkout's
`.claude/`. A TODO can sit in any file, and the probe recorded under
`constraint bash-writes-other-checkout` in `specs/todos.md` found that a
script run through Bash can open one there for writing. So the todos script
does not carry any edit across, and marks each TODO in the checkout where it
sits.

## TODOs in a review

Twice in the review of #527, the owner left `TODO(prose):` review comments and
asked the agent to process them with do-todos. #536 records how the agent
then copied each comment into its file by hand, picked one line for each
comment on a range, and took the markers out again before committing. `--pr`
lets `scan` read the comments straight from GitHub instead.

A comment names its lines in the commit it was left on, and later commits may
have moved them. `scan` compares the file at that commit with the file in the
worktree on the pull request's head branch, with the same shortest edit
script it uses against the last commit, so it does not trust GitHub's own
`line`, which knows nothing of commits not yet pushed or of uncommitted
edits. When the lines themselves changed, it still places the TODO, since
dropping a note the owner left is worse than putting it a few lines off, and
it warns so that the author checks.

A review TODO is not in any file, so `file` does not mark it there. It
marks the TODO by a reply in the comment's thread, which holds the same
`TODO-HANDLED(<target>):` a file would. `scan` skips a thread holding one,
so a second run, or one that stopped part way and runs again, does not
collect the TODO again or reply twice. In the review of #527, the agent
replied in each thread by hand after the work was committed, and on the
owner's second request had to tell the one new TODO comment apart from the
five it had already answered (#537).

The reply is a mark, so `report` does not show it and the token does not
cover it. Its words other than the mark are fixed, so two runs on one batch
reply alike. The only part a project's rules can change is how a reply
opens, such as this repo's `**Claude:**`, and the skill passes that as
`--reply-lead`. `file` leaves the thread unresolved, since resolving it is
the reviewer's call.

The approval token covers the named comments' text, since a comment can be
edited after the report.

In the same review, three of the five comments gave the owner's own wording.
update-prose-config learned rules from them as notes on unchanged passages,
writing each rule's After itself, and the agent then typed the wording into
the files by hand (#539). A suggestion block is GitHub's form for that
wording, so `file` writes it over the comment's lines before the hand-off.
The note then reaches update-prose-config as the reason for the author's own
edit, and the rule's example is that edit. update-prose-config does not
write documents, so the write has to happen here, before the hand-off.
`file` writes only lines that are as the comment saw them, so a suggestion
never overwrites a later change.

## Why a script

The model drafts each issue and decides what to ask the author. The script
does the rest:

- finding the TODOs
- checking each draft against the file as it is now
- calling `gh`
- marking each TODO handled

Marking has to change a TODO's word and its wrap, and no other byte. A model
editing by hand gets that wrong eventually, and without the script, neither
the model nor the author would notice the stray byte.

## The report and the token

`report` prints every draft routed to GitHub whole, and ends with a token that
hashes those drafts, the repository gh resolves for the clone, the last
commit and every file those drafts name. `file` refuses any other token. The author approves
the text `file` will send, in the repository the report named, and a fork
cannot send issues to its upstream, since every gh call after the first passes
that repository as `--repo`.

Claude Code shows a command's output to the model, and not reliably to the
author, and the dialog that asks for approval covers the text above it. So
`report` also writes the report as markdown to `.todos/report.md`, and the
skill publishes that file as a private artifact. The author reads every draft
there, comments on one and sends the comment to Claude, and the skill revises
the drafts and republishes to the same address. The approval dialog names
the address and the token, so the author approves the page they read. The
file goes in the session's own tree, even under `--from`, because that is the
tree the session publishes from.

A partial approval runs `report` again on the trimmed drafts, so `file` has no
`--partial`.

## The questions page

do-todos asks about every unclear TODO in one round. One `AskUserQuestion`
call holds at most four questions, and a later dialog covers the one before
it, so the author could not compare two TODOs asked in different dialogs. A
round of five or more questions goes on a page instead. `todos.py questions`
writes each question, under the `file:first` and title of each TODO it asks
about, to `.todos/questions.md`. The skill publishes that file as a private
artifact, and the author answers each question in a comment sent to Claude.
Where the skill cannot publish, it falls back to dialogs of four.

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

## Irreversible filing

Deleting an issue takes admin rights on the repository, which the user may
lack, so a batch cannot be filed all or nothing. `file` checks everything it
can before its first call to GitHub: the token, every draft, and that it can
open every file it will change for writing. It then marks each TODO as soon
as its issue exists, and stops at the first call that fails, so a run cut
short leaves unmarked exactly the TODOs whose issues do not exist.

## Marking a handled TODO

`file` once deleted each TODO it finished. After a run the author could not
tell from the file which TODOs were handled and which were missed, and the
only record was the chat. The owner ruled while planning #333 that `file`
marks a TODO instead. Its word, `TODO` or `TODO(<kind>)`, becomes
`TODO-HANDLED(<target>)`, and the TODO's text and comment syntax stay. A
hand-off's target is the skill's name, because a pull request does not exist yet
when `file` runs. Marking never adds or removes a line, so the line numbers
`scan` gave stay right while `file` works through a file.

In markdown, `file` wraps a marked TODO in an HTML comment unless it already
sits in one, so it does not render. prose-tuning's `evidence` then skips it as
a comment-only hunk (#327), rather than reading the marker as a prose edit.
The wrap runs to the end of the TODO's last line, because a list item, a quote
or a trailing TODO would render too.

`scan` reads a marked TODO, with its detail, so that a second run skips it
silently, and does not read it as the detail of a new TODO
written above it. `tests/todos/test_properties_todos_marking.py` checks, for
every file Hypothesis builds, that:

- `scan` does not report or warn about anything in a file with every TODO
  marked.
- marking leaves every byte outside each word and wrap as it was.
- markdown does not render any part of a marked TODO.

## `approved`

In the owner's repositories only the owner adds the `approved` label.
`.claude/hooks/issue_guard.py` reads only the text of a Bash command, so it
does not see a script that runs `gh`, and CI lets through an issue labeled
when it is created. `report` and `file` therefore refuse a draft carrying the
label, in any case.

## Handing a TODO to another skill

The owner asked in #319 for a `prose` TODO to reach the skill that learns
prose rules, rather than become an issue, and for a TODO about what a document
says never to reach it. A draft can take the route `skill`, which names a
skill as the Skill tool takes it. The model picks the skill from the skills
the session lists, by their descriptions, so `report` cannot check the name.

A routed TODO does not reach GitHub, and the receiving skill asks the author
about it, so `report` leaves it out and the token does not cover it (#533).
Asked in both places, the author approved each note twice. A batch that
routes every TODO to a skill runs `file` without `report` or a token.

`file` marks a routed TODO like any other, with no call to GitHub, and then
prints one hand-off per skill. Each holds the TODO's title and detail and the
passage it sat above. The passage runs from the line `scan` gave as `above` to
the nearest blank line or TODO, marked or not, on either side. A markdown list
does not have blank lines between its items, so in markdown the passage
narrows to the list item that holds that line (#534). A TODO on one item of a
long requirement list in `specs/` otherwise handed on the whole list, and the
receiving skill had to guess which item the note meant. Each hand-off also
names the TODO's line, and whether the TODO sat at its end or above it. The
convention in CLAUDE.md, under "A skill hands work to another plugin's skill
by convention", says what a hand-off carries.

Each hand-off also carries `arguments`: the whole of what the Skill tool call
takes, as one markdown block (#535). do-todos passes it unchanged. When the
model wrote the arguments from the parts, it added claims the parts did not
hold, such as where the notes came from and what a passage's diff held, and
could drop or misstate a field. The passage goes in a code fence longer than
any run of backticks in its text, so a fence in the passage cannot close it.

The receiving skill may end the session's work when it stops, so do-todos
gives its report first and invokes the skills as its last act.

## Why no skill commits

How a project commits is settled wherever that project settles it, such as
its `CLAUDE.md`. The skill leaves every change uncommitted, and the copy of
the script in `.todos/` carries a `.gitignore` of `*`, so it never reaches a
commit.

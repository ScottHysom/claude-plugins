# todos

This file records what the todos plugin is for. SPEC-METHODOLOGY.md, at the
repo root, has the grammar of this file and the steps that add its
requirements.

## Out of scope

- Doing the work an issue describes. The skill files it, and a later session
  does the work.
- Knowing which comment syntax each file type takes. A TODO's own line shows
  its comment marker, and the file's own tools show a wrong one.
- A TODO already committed. The skill reads only the changes since the last
  commit.
- Issue trackers other than GitHub's.
- Running in Cowork, the Claude desktop app's mode for a user's own files. The
  plugin needs Claude Code and a clone with a GitHub remote.
- Writing another plugin's files or markup. A TODO reaches another plugin only
  through that plugin's skill.
- TODOs in a separate clone of the repo. Git lists only the worktrees of the
  repository it is run in.

## need user-leaves-todos-for-filing: Leave a TODO where the work is found

When the user reviews a file and finds work for later, such as a bug, a fix,
or a change to the code, the design or a document, they want to leave a short
TODO on the spot and have Claude file each as an issue, so the review is not
broken off to write issues.

Source: #311, which quotes the owner's request.

- `scan-cmd-reads-pending-lines` (test): When `scan` runs, it reads the lines
  each tracked regular file has gained since the last commit, following
  renames, and every line of a regular file git neither tracks nor ignores,
  and nothing else.
- `scan-cmd-reports-nothing-pending` (test): When `scan` finds neither a
  pending TODO nor another worktree to name, it says so and exits 0.
- `scan-cmd-locates-each-todo` (test): When `scan` reports a TODO, it gives
  these:
  - its file, and its first and last line.
  - the line it sits above, or for a TODO at the end of a line, that line.
  - that line's text as the last commit has it, and its number at the last
    commit when it has one.
  - the last commit's hash, and whether a remote branch holds it.
- `scan-cmd-lists-labels` (test): When `scan` runs, it lists every label of
  the repository with its description.
- `dotodos-reads-todos-from-scan` (step): When do-todos looks for TODOs, it
  takes them from `scan`'s output, and never searches the files with a
  command of its own.
- `report-cmd-shows-each-draft` (test): When `report` runs, it prints each
  draft routed to `issue` or `comment` whole, with its TODO's file and lines
  and its route, and what its route adds:
  - `issue`: its title, labels and body.
  - `comment`: the number and title of its issue, and its body.

  It leaves out a draft routed to `skill`, which the receiving skill shows
  the author.
- `report-cmd-lists-undrafted-todos` (test): When a pending TODO has no draft,
  `report` lists it as left in place.
- `report-cmd-lists-scan-warnings` (test): When `report` runs, it lists every
  warning `scan` gives, with its file and line.
- `report-cmd-refuses-stale-drafts` (test): When a draft's file and line do
  not hold a pending TODO whose first line is the draft's `text`, `report`
  and `file` refuse it and name it by its place in the batch.
- `report-cmd-refuses-drafts-sharing-todo` (test): When two drafts name one
  TODO, `report` and `file` refuse both and name their places.
- `report-cmd-refuses-unknown-labels` (test): When a draft names a label the
  repository does not have, `report` and `file` refuse it.
- `file-cmd-creates-issues` (test): When `file` runs with a current token, it
  creates one issue for each draft routed to `issue`, with its title, body
  and labels, and prints each issue's number and address.
- `dotodos-follows-project-rules` (step): When do-todos drafts an issue or a
  comment, it follows the project's own rules for issues or for replies, from
  its CLAUDE.md and its issue templates, and takes labels only from the list
  `scan` gives.

## need user-sees-handled-todos: See which TODOs were handled

When do-todos has run, the user wants each TODO it handled marked where it was
left, naming the issue, comment or skill it went to. A plain TODO left in a
file is then one it missed, and a search for TODO finds both.

Source: the owner's ruling while planning, 2026-10-04, recorded in #333.

- `file-cmd-marks-handled-todos` (test): When `file` has finished a draft, it
  puts `TODO-HANDLED(<target>)` in place of that TODO's `TODO` or
  `TODO(<kind>)` before it starts the next draft, and does not change any
  other byte but a comment wrap. The target is `#<n>` for an issue, `#<n>
  comment` for a comment on issue `<n>`, and the skill's name for a
  hand-off.
- `file-cmd-wraps-markdown-todos` (test): When `file` marks a TODO in a file
  ending `.md` or `.markdown`, and the TODO is not already in an HTML comment,
  it wraps the TODO, with its detail lines, in `<!--` and `-->`.
- `scan-cmd-skips-handled-todos` (test): When an added line opens with
  `TODO-HANDLED(<target>):`, after its indent and any characters other than
  letters or digits, or holds one that `file` left after the line's other
  text, `scan` neither reports it nor warns. It also does not read an opening
  one or its detail as another TODO's detail or as the line a TODO sits above.
- `file-cmd-replies-to-review-todos` (test): When `file` has finished a draft
  whose TODO came from a review comment, it replies in that comment's thread
  before it starts the next draft. The reply opens with the text given to
  `--reply-lead`, if any, then `TODO-HANDLED(<target>):`, with the target
  `file-cmd-marks-handled-todos` gives, and says where the TODO went. `file`
  leaves the thread unresolved. When the reply is not posted, `file` gives
  the reply and the thread's address, stops, and exits 1.
- `scan-cmd-skips-answered-review-todos` (test): When a review comment's
  thread holds a reply with `TODO-HANDLED(<target>):`, `scan --pr` does not
  read that comment as a TODO.
- `dotodos-leads-review-replies` (step): When do-todos runs `file --pr`, it
  passes `--reply-lead` with the text the project's rules for replies ask a
  reply to open with, such as a prefix its CLAUDE.md names, and leaves it out
  when the rules do not ask for one.

## need user-collects-from-other-checkout: Collect TODOs left in another checkout

When the user has left TODOs in one checkout of the repo and runs the skill
from a session in another, such as a worktree the desktop app made, they want
the skill to find those TODOs, file them and mark them where they are, so
they can review wherever they review.

Source: #315, and #301, which found the same split for update-prose-config.

- `scan-cmd-names-worktrees-with-todos` (test): When this tree does not hold
  any pending TODO and another worktree of the repo does, `scan` names each
  such worktree with its branch and files, and exits 1 naming `scan --from`
  with its path.
- `command-reads-other-worktree-with-from` (test): When `scan`, `report`,
  `file` or `questions` is given `--from` with a worktree of this repo, named
  by its folder or by the branch it has checked out, it reads that worktree's
  TODOs. Given this tree, it behaves as with no `--from`.
- `file-cmd-marks-other-worktree-with-from` (test): When `file` is given
  `--from`, it marks the finished TODOs in that worktree's files.
- `command-refuses-unknown-from-worktree` (test): When `scan`, `report`,
  `file` or `questions` is given `--from` that names neither a worktree of
  this repo nor a branch one has checked out, the command names it, lists
  every worktree with its branch, and exits 2.
- `dotodos-takes-named-checkout` (step): When the author names a checkout in
  the skill's arguments, by its folder or its branch, do-todos passes it to
  `scan --from` as given, and to `report` and `file`, and does not ask which
  checkout to collect from.
- `dotodos-asks-which-checkout` (step): When the author has not named a
  checkout and `scan` names other worktrees, do-todos asks the author in one
  `AskUserQuestion` which to collect from, if any, and runs `scan --from`
  with the one picked.

## need user-leaves-todos-in-review: Leave a TODO in a review comment

When the user reviews a pull request on GitHub and finds work for later, they
want to leave a TODO as a review comment on the lines it is about, and have
do-todos collect it as it collects a TODO left in a file, so the review does
not have to be copied into the files first.

Source: #536, which records the owner's two requests in the review of #527.

- `scan-cmd-reads-review-todos` (test): When `scan` is given `--pr`, it reads
  each top-level review comment on that pull request whose body opens with
  `TODO:` or `TODO(<kind>):`, in place of the tree's pending TODOs. It gives
  these:
  - the rest of the comment's first line as the title, and the rest of its
    body as the detail.
  - its kind, read as a TODO's kind word is read.
  - its file, and the first and last of the lines it covers.
  - the comment's address.
  - the lines of its first suggestion block (a fence marked `suggestion`,
    which holds GitHub's form for the wording the author wants), and whether
    the lines it covers are as they were when the comment was left.

  It skips a comment, and warns with the comment's address, when the comment is on any of these:
  - a whole file.
  - lines the pull request removes.
  - a file the tree lacks.
- `scan-cmd-finds-moved-review-lines` (test): When `scan` reads a review
  comment, it finds the lines the comment covers in the tree as it stands,
  also when a later commit moved them. When a later change altered them, it
  warns naming the comment, and places the TODO on what is left of them, or
  after the nearest line kept before them. When the clone does not hold the
  commit the comment was left on, it names the comment and `git fetch`, and
  exits 2.
- `command-reads-review-with-pr` (test): When `scan`, `report`, `file` or
  `questions` is given `--pr` with a pull request's number, it reads the
  review's TODOs and their passages in the worktree that has the pull
  request's head branch checked out. When that branch is not checked out in
  any worktree, it names the branch and exits 2. It refuses `--pr` beside
  `--from`.
- `file-cmd-leaves-tree-for-review-todos` (test): When `file` finishes a
  TODO taken from a review comment, it does not write the TODO into the
  tree's files. The only lines it writes for such a TODO are a suggestion's,
  under `file-cmd-writes-review-suggestions`.
- `file-cmd-writes-review-suggestions` (test): When a TODO taken from a review
  comment is routed to `skill` and carries a suggestion block, `file` writes
  the block's lines over the lines the comment covers, as an uncommitted
  edit, before it prints the hand-off. The hand-off's passage then holds the
  suggested lines, they are the lines it lists as changed, and the note's
  detail leaves out the block. `file` leaves the lines as they are, warns,
  and keeps the block in the note under any of these conditions:
  - the lines have changed since the comment was left.
  - they overlap the lines of a suggestion it wrote first.
  - the suggestion would leave the file empty.

  Under `--dry-run`, it hands off the passage it would write and writes
  nothing.
- `report-cmd-keeps-review-suggestions` (test): When a draft routed to `issue`
  or `comment` names a TODO whose review comment carries a suggestion block,
  `report` and `file` refuse it unless its body holds the block's lines, and
  `file` leaves the lines the comment covers as they are.
- `dotodos-takes-named-pr` (step): When the author asks do-todos to collect
  the TODOs in a pull request's review, do-todos passes its number to `scan
  --pr`, and to `report`, `file` and `questions`.

## need user-keeps-files-working: Keep a file with TODOs working

When the user leaves a TODO in a file, they want to write it in the file's own
comment syntax, on a line of its own or at the end of the line it is about,
so the file runs, compiles and renders as it did.

Source: #311, which quotes the owner's request, and the owner's rulings
recorded there.

- `scan-cmd-reads-any-symbol-marker` (test): When an added line in any text
  file opens with a TODO, after its indent and a comment marker of characters
  that are not letters, digits or spaces if it has one, `scan` gives the rest
  of the line as the title.
- `scan-cmd-reads-line-detail` (test): When a TODO's marker is neither empty
  nor one of `-`, `*`, `+`, `>` or `|`, `scan` gives as its detail the added
  lines directly below it that open with the same marker at the same indent, up
  to a blank line or the next TODO, marked handled or not.
- `scan-cmd-reads-c-and-html-comments` (test): When a TODO's marker contains
  `/*` or `<!--`, and every line to the comment's `*/` or `-->` was added
  since the last commit, `scan` runs the TODO to there, or to the line above
  the next TODO that opens a line inside the comment, marked handled or not.
  It gives the rest as the detail, and reads that next TODO the same way.
- `scan-cmd-skips-markdown-code-todos` (test): When a TODO sits in a code
  fence or a code span of a file ending `.md` or `.markdown`, `scan` neither
  reads it nor warns.
- `scan-cmd-skips-binary-files` (test): When git reads a file as binary,
  `scan` skips it.
- `scan-cmd-warns-on-unread-todos` (test): When an added line holds `TODO:` or
  `TODO(`, or opens with `TODO` other than `TODO-HANDLED(` after its indent
  and marker, where `scan` does not read a TODO, it warns with the file, the
  line and the reason.
- `scan-cmd-skips-its-copy` (test): When `scan` lists files, it leaves out
  `.todos/`, whatever git ignores.
- `scan-cmd-reads-appended-trailing-todos` (test): When a line differs from
  the last commit only by text at its end that opens with a TODO after any
  comment marker, `scan` reads that text as a TODO that has a title and no
  detail.
- `file-cmd-marks-trailing-todos` (test): When `file` has finished a TODO at
  the end of a line, it marks the TODO there, and leaves the text before it
  as the last commit has it.

## need user-says-what-kind: Say what kind of work a TODO is

When the user leaves a TODO, they want to say in one word whether it is a bug,
a fix, a code change, a design change, a change to what a document says or a
change to how it reads, so Claude drafts it as that kind without asking.

Source: #311, which quotes the owner's message asking for code changes,
design changes, bugs and bug fixes, and the ruling on `TODO(kind):`.

- `scan-cmd-reads-kind-word` (test): When a TODO opens with `TODO(<kind>):`,
  `scan` gives `bug`, `fix`, `change`, `design`, `docs` or `prose` as its
  kind, and for any other word it does not give a kind and warns with the
  word.
- `dotodos-follows-todo-kind` (step): When a TODO names a kind, or do-todos
  infers one from its words, it drafts by that kind:
  - a `bug` as a defect.
  - a `fix` as the defect it fixes, with the fix as what done means.
  - a `change` as an improvement to the code.
  - a `design` as a change to what the project does or how it is built.
  - a `docs` as a change to what a document says.
  - a `prose` as a change to how a passage reads.

  A name that is wrong or out of date is something a document says, so its
  TODO is `docs`. A term chosen for how the passage reads, such as one word
  kept to one meaning, is `prose`.

## need user-answers-in-one-round: Answer every open question at once

When a TODO says too little to make an issue, or Claude cannot tell its kind,
where it goes or whether an issue already covers it, the user wants every such
question asked at once, so a TODO can be one line.

Source: #311, which quotes the owner's request to be interviewed when a
TODO's detail is missing or too sparse.

- `dotodos-asks-at-once` (step): When TODOs say too little to draft, or their
  kind, route or duplicate is unclear, do-todos asks the author about all of
  them in one round, before writing any draft. The round is one
  `AskUserQuestion` call when the questions fit in it, and otherwise one
  page.
- `questions-cmd-writes-page` (test): When `questions` is given the questions
  as JSON with `--batch`, it writes `.todos/questions.md` in the `-C` tree,
  also under `--from`, which git ignores. Each question is numbered, named by
  the `file:first` and title of each TODO it asks about, with its options
  under it. It refuses a question without options, without a TODO, or naming
  a line that does not hold a pending TODO. When it refuses one, the file
  holds the refusals and no question.
- `dotodos-asks-on-page` (step): When the open questions are more than one
  `AskUserQuestion` call holds, do-todos publishes the page `questions`
  writes as a private artifact, takes each answer from a comment sent to
  Claude, replies in each question's thread with the answer it took, and
  drafts only once every question has an answer. Where it cannot publish the
  page, it asks in dialogs of up to four questions each.

## need user-avoids-duplicate-issues: Keep one issue per problem

When a TODO repeats an open issue, the user wants its detail added to that
issue as a comment rather than a second issue opened, so the tracker holds one
issue per problem.

Source: #313, which records the owner's ruling and the owner's figure of
five, and CLAUDE.md, under "Issues": search first, and comment on a match
rather than opening a second.

- `scan-cmd-lists-similar-issues` (test): When `scan` reports a TODO, it lists
  the first five open issues GitHub's search returns for its title, with their
  numbers and titles.
- `report-cmd-checks-comment-targets` (test): When a draft routed to
  `comment` names an issue, `report` and `file` refuse it unless the issue
  exists and is open.
- `file-cmd-posts-comments` (test): When a draft is routed to `comment`,
  `file` posts its body on that issue and prints the comment's address.
- `dotodos-reuses-open-issues` (step): When an open issue already covers a
  TODO, do-todos drafts a comment on that issue rather than a new one.

## need user-approves-each-issue: Approve every issue before it is filed

When Claude has drafted the issues, the user wants to see every draft whole,
with the repository it goes to, and approve all of them or a part before
anything reaches GitHub, since a filed issue is public and stays.

Source: #312, which records the design the owner approved.

- `report-cmd-names-target-repo` (test): When `report` runs, it names the
  repository the drafts will be filed in, as `gh` resolves it for the
  clone.
- `report-cmd-prints-approval-token` (test): When `report` exits 0, it prints
  a token as its last line, and otherwise does not print a token.
- `report-cmd-stops-on-unreadable-drafts` (test): When the file given to
  `--drafts` is unreadable or holds something other than JSON, `report` and
  `file` name the fault and exit 2.
- `file-cmd-requires-token` (test): When the batch holds a draft routed to
  `issue` or `comment`, and `file --token` is missing or differs from the
  token `report` would print, `file` stops before it files, posts or writes
  anything. The token covers the drafts routed to `issue` or `comment`, the
  files they name, the last commit and the target repository as they are
  now. Under `--pr`, it also covers the pull request's number and the title
  and detail of each review comment those drafts name. When every draft is
  routed to `skill`, `file` runs without a token.
- `file-cmd-files-in-reported-repo` (test): When `file` calls `gh`, it passes
  the repository `report` named as `--repo`.
- `file-cmd-never-posts-in-preview` (test): When `file` is given `--dry-run`,
  it prints what it would file, post and mark, and does not file or post
  anything.
- `dotodos-shows-report-whole` (step): When a draft is routed to `issue` or
  `comment` and `report` exits 0, do-todos publishes `.todos/report.md` as a
  private artifact, or shows the file whole where it cannot, and takes one
  decision over those drafts, naming the artifact's address and the token,
  before running `file`. When every draft is routed to `skill`, do-todos
  runs `file` without `report` or a question.
- `drafts-cmd-makes-own-file` (test): When `drafts` runs, it makes an empty
  file in the temporary directory, named so that no other run gets the same
  file, and prints its literal path.
- `dotodos-drafts-in-own-file` (step): When do-todos writes its drafts, it
  writes them to the file `drafts` made for that run, and every later step of
  the run reads that file, so the report does not show drafts another session
  wrote.

## need user-annotates-drafts: Comment on a draft where it is read

When Claude has drafted the issues, the user wants to comment on a draft where
they read it and have Claude revise it before they approve. A change then does
not have to be retyped in chat.

Source: the owner's ruling while planning, 2026-10-04, recorded in #334.

- `dotodos-revises-on-report-comment` (step): When the author sends a comment
  on the published report to Claude, do-todos revises the drafts, runs
  `report` again, republishes the report to the same address and answers in
  the comment's thread.

## need user-reviews-then-commits: Commit each change the user's usual way

When the plugin changes the user's project, the user wants every change left
uncommitted and its own working files kept out of the project's commits, so
they review and commit their usual way.

Source: #312, and prose-tuning's DESIGN.md, under "Why no skill commits".

- `setup-cmd-ignores-its-copy` (test): When `setup` writes the copy of the
  script, a `.gitignore` of `*` beside it keeps the copy out of the project's
  commits.
- `dotodos-never-commits` (step): When `file` has run, do-todos commits nothing, and lists these:
  - the issues filed.
  - the comments posted.
  - each note it will hand off, with the skill it goes to.
  - the files marked.
  - the TODOs left in place.

## need user-sends-todos-to-skills: Hand a TODO to the skill made for it

When a TODO asks for work an installed skill exists to do (such as a change to
how a passage reads, which prose-tuning's update-prose-config learns rules
from), the user wants Claude to hand it to that skill rather than improvise,
and never to hand a change to what a document says to a prose skill, so the
work follows that skill's rules.

Source: #319, which quotes the owner's first use case, and CLAUDE.md, under
"A plugin knows only itself", for the hand-off convention.

- `file-cmd-prints-handoffs` (test): When a draft is routed to `skill`, `file`
  prints the skill's name, the TODO's title and detail, and the passage it sat
  above, with its file and lines and which of them changed since the last
  commit. The passage runs to the nearest blank line or TODO, marked or not,
  and leaves out the text of a trailing TODO. In a file ending `.md` or
  `.markdown`, the passage is the list item that holds the TODO's line. When
  that line is not in a list item, the passage is its paragraph, up to the
  paragraph's first list item. Each hand-off names the line the TODO was at the end of, or the line
  it sat above. For a TODO taken from a review comment, the passage runs from
  the passage around the first line the comment covers to the one around its
  last, and the hand-off names the comment's address and those lines in place
  of a line. When `--from` or `--pr` names another worktree, each hand-off
  also names that worktree's root and branch. Each hand-off also gives, as one
  block of text, the arguments the Skill tool call takes: every TODO routed to
  that skill, with the parts above, in the form CLAUDE.md gives under "A
  skill hands work to another plugin's skill by convention".
- `dotodos-passes-todos-to-skills` (step): When an installed skill's
  description covers the work a TODO asks for, such as a `prose` TODO and a
  skill that learns prose rules, do-todos routes it to that skill, and
  otherwise drafts an issue.
- `dotodos-withholds-facts-from-prose` (step): When a TODO asks to change what
  a document says, including a name that is wrong or out of date, do-todos
  drafts an issue, and never routes it to a prose skill. A term changed only
  for how the passage reads is not one of these, and may go to a prose skill.
- `dotodos-reports-before-handoffs` (step): When `file` prints hand-offs,
  do-todos gives its report, with each note, before it invokes any
  skill.
- `dotodos-invokes-each-skill-once` (step): When `file` prints hand-offs,
  do-todos invokes each skill named once, and passes the arguments `file`
  printed for it as they stand.

## need owner-keeps-approval-label: Keep approved for the owner

When the skill files an issue under the owner's account, the owner wants it
never to carry `approved`. Otherwise an agent could approve its own work
through a script that issue_guard.py (the hook that blocks a Bash command adding `approved`) does not see.

Source: README.md, under "Keeping `approved` meaningful", and #312, which
records the owner's ruling.

- `report-cmd-refuses-approved-label` (test): When a draft carries the label
  `approved`, in any case, `report` and `file` refuse it.

## constraint git-holds-pending-todos: The TODOs are read from git

The plugin finds pending TODOs in git, as the changes since the last commit,
so a project has to be tracked by git and hold a commit.

Source: #311, where the owner approved reading only the changes since the
last commit.

- `command-requires-a-repo` (test): A command names the cause and exits 2 when it runs in any of these places:
  - outside a git repository.
  - in a repository without a commit yet.
  - where git is not installed.

## constraint gh-requires-login: GitHub's command-line tool must be installed and signed in

The script reads labels, searches issues and files them through `gh`, which
has to be on PATH and signed in to the repository's host.

Source: #312, and `.github/scripts/issues.py`, whose docstring needs "an
authenticated gh on PATH".

- `command-requires-signed-in-gh` (test): When `gh` is missing or not signed
  in, a command that needs it names the command that fixes it and exits
  2.

## constraint shell-starts-fresh: Each shell call starts without the last one's variables

Each Bash call in Claude Code starts a fresh shell. The plugin's install path
runs past 200 characters, too long to repeat in every command, so a skill
reaches the script by a shorter path.

Source: CLAUDE.md, under "A shell variable lasts one command".

- `setup-cmd-copies-locally` (test): When `setup` runs, it copies the script
  byte for byte into `.todos/`, and gives the prefix `TODOS=.todos/todos.py`,
  which reaches the copy from the project root.

## constraint bash-hides-output: A command's output does not reliably reach the user

Claude Code shows a Bash command's output to the model and not reliably to
the user, and an `AskUserQuestion` dialog covers the text above it. So a
report the user must approve reaches them as a file or a page, not as a
command's output.

Source: Claude Code's Bash tool description, and the owner's report in #334.

- `report-cmd-writes-report-file` (test): When `report` runs, it writes the
  report as markdown to `.todos/report.md` in the `-C` tree, also under
  `--from`, and gives the file's path. When it refuses a draft, the file holds
  the refusals and no token.

## constraint artifact-sends-comments: A comment sent to Claude reaches the session

An artifact published from Claude Code is private by default. A comment its
owner sends to Claude reaches the session that published it, which can reply
in the thread. A comment sent while the session is busy starts a turn once
the session goes idle.

Source: code.claude.com/docs/en/artifacts.md, under "Collect comments on an
artifact", and the probe recorded in #334. The probe ran on 2026-10-06 from
`.claude/worktrees/issue-347-f948c8`. The owner sent two comments to Claude
on a private artifact the session published. `ArtifactComments` read both as
sent to Claude, and the session's reply posted to the thread. The first
comment, sent while the session was busy, started a turn when that turn
ended.

## constraint bash-writes-other-checkout: A script run through Bash can write another checkout

When a session runs in a worktree the desktop app made, a script it runs
through Bash can open a tracked file in the repo's main checkout, outside
`.claude/`, for writing. So `file --from` marks the TODOs in the checkout
where they were left.

The probe ran Bash without Claude Code's sandbox. It did not test a session
with the sandbox turned on, which limits writes to the working directory. If
the sandbox refuses the open, `file-cmd-checks-writes-first` stops `file`
before it files anything.

Source: #315. The probe ran on 2026-10-03 from
`.claude/worktrees/issue-143-86e92f`, with the main checkout on
`scott/prose-changes`. It opened the main checkout's `README.md` with
`open(path, "r+b")` and closed it, writing nothing. The session's shell ran as
a child of `claude` itself, without `sandbox-exec`.

## constraint github-keeps-filed-issues: A filed issue cannot be counted on to come back

Deleting an issue takes admin rights on the repository, which the user may
lack. A script therefore cannot count on undoing an issue it filed. For the
same reason, a batch cannot be filed all or nothing.

Source: GitHub's documentation, "Deleting an issue".

- `file-cmd-checks-before-filing` (test): When any draft in a batch would be
  refused, `file` does not file or post anything.
- `file-cmd-checks-writes-first` (test): When `file` cannot open a file it
  would change for writing, it names the file and exits 2 before filing or
  posting anything.
- `file-cmd-stops-at-failed-call` (test): When a GitHub call fails, `file`
  stops calling GitHub, leaves the TODOs of the drafts it has not finished,
  lists them and exits 1.

## constraint github-limits-search-rate: GitHub limits how often a client may search

GitHub's REST search allows a signed-in client 30 requests a minute, so one
search per TODO stops working on a long list.

Source: GitHub's REST API documentation, "REST API endpoints for search",
under "Rate limit", checked when #313 was built.

- `scan-cmd-searches-in-one-query` (test): When `scan` looks for similar
  issues, it sends one GraphQL query for every title.

## constraint github-holds-pending-replies: A reply in a pending review publishes with it

A review comment the user has not submitted belongs to their pending review,
which only they can see. GitHub's REST list of a pull request's review
comments leaves it out, and the REST list of the review's own comments gives
its lines as null. GraphQL gives it, with its lines, in the pull request's
review threads. While the user has a pending review on a pull request, GitHub
refuses every REST reply of theirs there, to a submitted comment as well as a
pending one. GraphQL's `addPullRequestReviewThreadReply`, given the pending
review's ID, adds the reply to that review, and the reply appears in its
thread when the user submits the review. Without that ID and with no review
pending, the reply appears at once.

Source: #538. The probe ran on 2026-10-12 from
`.claude/worktrees/issue-544-7f886f`, as the owner, on the owner's pull
request #553. A REST reply to a pending comment, and one to a submitted
comment while another review was pending, each failed with 422 and "user_id
can only have one pending review per pull request". Each GraphQL reply given
the pending review's ID was itself pending, and appeared when the review was
submitted.

- `scan-cmd-reads-pending-review-todos` (test): When the signed-in user has
  a pending review on the pull request, `scan --pr` reads the TODOs in its
  comments as it reads the submitted ones, and says of each TODO whether it
  is in that review.
- `file-cmd-replies-into-pending-review` (test): When the signed-in user has
  a pending review on the pull request, `file` adds each reply it makes there
  to that review, and says that the reply appears when the user submits it.
  When the user does not have a pending review, the reply appears at once.
- `dotodos-names-pending-replies` (step): When `file` added replies to the
  author's pending review, do-todos tells the author that they appear when
  the review is submitted.

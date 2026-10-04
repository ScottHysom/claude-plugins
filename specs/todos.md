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
- Running in Cowork. The plugin needs Claude Code and a clone with a GitHub
  remote.
- Writing another plugin's files or markup. A TODO reaches another plugin only
  through that plugin's skill.
- TODOs in a separate clone of the repo. Git lists only the worktrees of the
  repository it is run in.

## need user-leaves-todos-for-filing: Leave a TODO where the work is found

When the user reviews a file and finds work for later, such as a bug, a fix,
or a change to the code, the design or a document, they want to leave a short
TODO on the spot and have Claude file each as an issue and take it out of the
file, so the review is not broken off to write issues and leaves nothing to
clean up.

Source: #311, which quotes the owner's request.

- `scan-cmd-reads-pending-lines` (test): When `scan` runs, it reads the lines
  each tracked regular file has gained since the last commit, following
  renames, and every line of a regular file git neither tracks nor ignores,
  and nothing else.
- `scan-cmd-reports-nothing-pending` (test): When `scan` does not find a
  pending TODO, and does not name another worktree, it says so and exits 0.
- `scan-cmd-locates-each-todo` (test): When `scan` reports a TODO, it gives
  its file, its first and last line, the line it sits above with that line's
  text and its number at the last commit when it has one, and the last
  commit's hash with whether a remote branch holds it.
- `scan-cmd-lists-labels` (test): When `scan` runs, it lists every label of
  the repository with its description.
- `dotodos-reads-todos-from-scan` (step): When do-todos looks for TODOs, it
  takes them from `scan`'s output, and never searches the files with a
  command of its own.
- `report-cmd-shows-each-draft` (test): When `report` runs, it prints each
  draft whole, with its TODO's file and lines and its route, for a draft
  routed to `issue` its title, labels and body, and for a draft routed to
  `comment` the number and title of its issue and its body.
- `report-cmd-lists-undrafted-todos` (test): When a pending TODO has no draft,
  `report` lists it as left in place.
- `report-cmd-lists-scan-warnings` (test): When `report` runs, it lists every
  warning `scan` gives, with its file and line.
- `report-cmd-refuses-stale-drafts` (test): When a draft's file and line do
  not hold a pending TODO whose first line is the draft's `text`, `report`
  and `file` refuse it and name it by its place in the batch.
- `report-cmd-refuses-repeated-todos` (test): When two drafts name one TODO,
  `report` and `file` refuse both and name their places.
- `report-cmd-refuses-unknown-labels` (test): When a draft names a label the
  repository does not have, `report` and `file` refuse it.
- `file-cmd-creates-issues` (test): When `file` runs with a current token, it
  creates one issue for each draft routed to `issue`, with its title, body
  and labels, and prints each issue's number and address.
- `file-cmd-removes-handled-todos` (test): When `file` has finished a draft,
  it removes that TODO's lines before it starts the next draft, and does not
  change any other byte but the blank lines around them.
- `file-cmd-tidies-blank-lines` (test): When removing a TODO leaves a run of
  blank lines, `file` removes the ones added since the last commit, but keeps
  one where the run does not hold a committed blank line, does not reach
  either end of the file, and borders a line added since the last
  commit.
- `file-cmd-restores-todo-only-files` (test): When `file` has finished every
  TODO in a tracked file whose only changes since the last commit are TODOs
  and blank lines, the file's bytes match what the last commit checks
  out.
- `dotodos-follows-project-rules` (step): When do-todos drafts an issue, it
  follows the project's own rules for issues, from its CLAUDE.md and its
  issue templates, and takes labels only from the list `scan` gives.

## need user-collects-from-other-checkout: Collect TODOs left in another checkout

When the user has left TODOs in one checkout of the repo and runs the skill
from a session in another, such as a worktree the desktop app made, they want
the skill to find those TODOs, file them and take them out where they are, so
they can review wherever they review.

Source: #315, and #301, which found the same split for update-prose-config.

- `scan-cmd-names-other-worktrees` (test): When this tree does not hold any
  pending TODO and another worktree of the repo does, `scan` names each such
  worktree with its branch and files, and exits 1 naming `scan --from` with
  its path.
- `command-reads-other-worktree` (test): When `scan`, `report` or `file` is
  given `--from` with another worktree of this repo, it reads that worktree's
  TODOs.
- `file-cmd-removes-from-other-worktree` (test): When `file` is given
  `--from`, it removes the finished TODOs from that worktree's files.
- `command-refuses-unknown-worktree` (test): When `--from` is not another
  worktree of this repo, the command names it and exits 2.
- `dotodos-asks-which-checkout` (step): When `scan` names other worktrees,
  do-todos asks the author in one `AskUserQuestion` which to collect from, if
  any, and runs `scan --from` with the one picked.

## need user-keeps-files-working: Keep a file with TODOs working

When the user leaves a TODO in a file, they want to write it in the file's own
comment syntax, on a line of its own or at the end of the line it is about,
so the file runs, compiles and renders as it did.

Source: #311, which quotes the owner's request, and the owner's rulings
recorded there.

- `scan-cmd-reads-any-marker` (test): When an added line in any text file
  opens with a TODO, after its indent and a comment marker of characters that
  are not letters, digits or spaces if it has one, `scan` gives the rest of
  the line as the title.
- `scan-cmd-reads-line-detail` (test): When a TODO's marker is not empty and
  is not `-`, `*`, `+`, `>` or `|`, `scan` gives as its detail the added lines
  directly below it that open with the same marker at the same indent, up to
  a blank line or the next TODO.
- `scan-cmd-reads-block-comments` (test): When a TODO's marker contains `/*`
  or `<!--`, and every line to the comment's `*/` or `-->` was added since
  the last commit, `scan` runs the TODO to there and gives the rest of the
  comment as the detail.
- `scan-cmd-skips-quoted-todos` (test): When a TODO sits in a code fence or a
  code span of a file ending `.md` or `.markdown`, `scan` neither reads it nor
  warns.
- `scan-cmd-skips-binary-files` (test): When git reads a file as binary,
  `scan` skips it.
- `scan-cmd-warns-on-unread-todos` (test): When an added line holds `TODO:` or
  `TODO(`, or opens with `TODO` after its indent and marker, where `scan` does
  not read a TODO, it warns with the file, the line and the reason.
- `scan-cmd-skips-its-copy` (test): When `scan` lists files, it leaves out
  `.todos/`, whatever git ignores.

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
  infers one from its words, it drafts by that kind: a `bug` as a defect, a
  `fix` as the defect it fixes with the fix as what done means, a `change` as
  an improvement to the code, a `design` as a change to what the project does
  or how it is built, a `docs` as a change to what a document says, and a
  `prose` as a change to how a passage reads.

## need user-answers-in-one-round: Answer every open question at once

When a TODO says too little to make an issue, or Claude cannot tell its kind,
where it goes or whether an issue already covers it, the user wants every such
question asked at once, so a TODO can be one line.

Source: #311, which quotes the owner's request to be interviewed when a
TODO's detail is missing or too sparse.

- `dotodos-asks-at-once` (step): When TODOs say too little to draft, or their
  kind, route or duplicate is unclear, do-todos asks the author about all of
  them in one round, before writing any draft.

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
  a token as its last line, and otherwise prints none.
- `report-cmd-stops-on-unreadable-drafts` (test): When the file given to
  `--drafts` cannot be read, or is not JSON, `report` and `file` name the
  fault and exit 2.
- `file-cmd-requires-token` (test): When the token passed to `file --token`
  is not the one `report` would print for the drafts, the files they name and
  the target repository as they are now, `file` does not file or post
  anything, and writes nothing.
- `file-cmd-files-in-reported-repo` (test): When `file` calls `gh`, it passes
  the repository `report` named as `--repo`.
- `file-cmd-never-posts-in-preview` (test): When `file` is given `--dry-run`,
  it prints what it would file, post and remove, and does not file or post
  anything.
- `dotodos-shows-report-whole` (step): When `report` exits 0, do-todos shows
  its output as it stands, and takes one decision over the whole set before
  running `file`.

## need user-reviews-then-commits: Commit each change the user's usual way

When the plugin changes the user's project, the user wants every change left
uncommitted and its own working files kept out of the project's commits, so
they review and commit their usual way.

Source: #312, and prose-tuning's DESIGN.md, under "Why no skill commits".

- `setup-cmd-ignores-its-copy` (test): When `setup` writes the copy of the
  script, a `.gitignore` of `*` beside it keeps the copy out of the project's
  commits.
- `dotodos-never-commits` (step): When `file` has run, do-todos lists the
  issues filed, the comments posted, the files changed and the TODOs left in
  place, and commits nothing.

## need owner-keeps-approval-label: Keep approved for the owner

When the skill files an issue under the owner's account, the owner wants it
never to carry `approved`, so an agent cannot approve its own work through a
script that issue_guard.py does not see.

Source: README.md, under "Keeping `approved` meaningful", and #312, which
records the owner's ruling.

- `report-cmd-refuses-approved-label` (test): When a draft carries the label
  `approved`, in any case, `report` and `file` refuse it.

## constraint git-holds-pending-todos: The TODOs are read from git

The plugin finds pending TODOs in git, as the changes since the last commit,
so a project has to be tracked by git and hold a commit.

Source: #311, where the owner approved reading only the changes since the
last commit.

- `command-requires-a-repo` (test): When a command runs outside a git
  repository, in one without a commit yet, or where git is not installed, it
  names the cause and exits 2.

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

## constraint bash-writes-other-checkout: A script run through Bash can write another checkout

A script that a session in a worktree the desktop app made runs through Bash
can open a tracked file in the repo's main checkout, outside `.claude/`, for
writing. So `file --from` removes the TODOs in the checkout where they were
left.

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

Deleting an issue takes admin rights on the repository, which the user may not
hold, so a script cannot count on undoing an issue it filed, and a batch
cannot be filed all or nothing.

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

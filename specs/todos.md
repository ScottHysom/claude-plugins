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
  pending TODO, it says so and exits 0.
- `scan-cmd-locates-each-todo` (test): When `scan` reports a TODO, it gives
  its file, its first and last line, the line it sits above with that line's
  text and its number at the last commit when it has one, and the last
  commit's hash with whether a remote branch holds it.

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

## constraint git-holds-pending-todos: The TODOs are read from git

The plugin finds pending TODOs in git, as the changes since the last commit,
so a project has to be tracked by git and hold a commit.

Source: #311, where the owner approved reading only the changes since the
last commit.

- `command-requires-a-repo` (test): When a command runs outside a git
  repository, in one without a commit yet, or where git is not installed, it
  names the cause and exits 2.

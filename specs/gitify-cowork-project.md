# gitify-cowork-project

This file records what the gitify-cowork-project plugin is for.
SPEC-METHODOLOGY.md, at the repo root, has the grammar of this file and the
steps that add its requirements.

## Out of scope

- Running in Claude Code. The plugin needs a Cowork Project with a connected
  folder.
- Taking over a folder that is already a git repository, which has a history
  of its own. The exception is `history-in-git`, which such a folder needs as
  much as one the plugin put under git.
- Writing documents, or rules about what documents say or how they read. Those
  belong to the project. The exception is `history-in-git`, which keeps change
  history out of the documents.
- Conventions for commit messages or dates, such as Conventional Commits or ISO
  dates.
- A connected folder shared by several Cowork Projects. The project's folder
  is the connected folder itself.

## need version-history: Keep a history of a Cowork Project's documents

When a Cowork Project is new or already holds real work, the user wants its
folder under git, so they can see what a document said before and get back
from an edit that went wrong.

Source: README.md, the opening section and "When to use it", and the
gitify-project description.

- `preflight-templates` (test): When `gitify.py preflight` checks the shipped
  templates, it names each template missing from disk or from `MANIFEST`,
  each unknown placeholder and each stray brace, and exits 1.
- `render-no-leftovers` (test): When a placeholder or brace would survive
  into a rendered file, `render` names it and writes nothing.
- `render-stages-files` (test): When the answers pass every check, `render`
  stages each file the plugin writes and prints the `files` list
  `device_commit_files` takes.
- `ignore-chat-outputs` (test): When `render` writes `.gitignore`, it leaves
  out `Claude outputs/`, where Cowork puts the files Claude hands over in the
  chat.

## need history-in-git: Leave change history to git

When an agent edits a document in a git-backed Cowork Project, whether or not
the plugin put it under git, the owner wants it to leave the record of the
change out of the document, such as dated sections or "updated on <date>"
notes, and rely on git, so the document holds only what is current. An agent that does not know git is there records the
history in the document instead.

Source: the owner's review of #139.

## need answer-from-history: Ask Claude about the history

When the user wants to know what a document said last week, or when and why a
figure changed, they want Claude to read the history and answer, with nothing
for them to run.

Source: README.md, under "Looking back".

## need review-first-commit: See the first commit before it is made

When the folder goes under git, the user wants Claude to ask about anything
that probably should not be in git, and wants to see every file the first
commit would take before it is made, so large media or exports stay out of the
history.

Source: README.md, under "Setting it up". The 10 MB threshold for a large
file is the owner's, in the ruling on #130.

- `probe-lists-folder` (test): When `probe`'s command runs on the device, it
  prints the number of files, a line for each top-level entry, hidden ones
  included, and a line for each file over 10 MB.
- `ask-about-unwanted` (step): When the listing shows large media, exports,
  archives, caches or anything that looks private, gitify-project asks the
  user about each before rendering.
- `ignore-answer` (test): When the answers give `ignore` patterns, `render`
  appends them to `.gitignore` under a heading of their own, and rejects a
  blank, multi-line or repeated pattern.
- `setup-stages-first` (test): When the user runs `sh setup.sh`, it stages
  every file and commits nothing, and lists what the first commit would take.
- `setup-late-ignore` (test): When a pattern is added to `.gitignore` after
  the first run, the next run and `sh setup.sh commit` leave its files out.
- `setup-usage` (test): When `setup.sh` is given an argument other than
  `commit`, it prints its usage, exits 2 and creates no repo.
- `hand-off-setup` (step): When the files are on the device, gitify-project
  tells the user to run `sh setup.sh` from their own terminal, says it commits
  nothing until `sh setup.sh commit`, and runs none of it.

## need stop-before-overwrite: Keep the user's files as they are

When the folder is missing, or already has a file with the name of one Claude
would write, the user wants Claude to stop, so nothing of theirs is
overwritten.

Source: README.md, under "Setting it up".

- `probe-stops-missing` (test): When the project folder is not on the device,
  `probe`'s command and the precheck print `missing:` and exit 2.
- `probe-stops-repo` (test): When the project folder is already a git repo,
  `probe`'s command and the precheck print `repo:` and exit 1.
- `precheck-names-overwrites` (test): When the folder holds a file with the
  name of one `render` would write, the precheck prints `exists:` for each and
  exits 1, and otherwise prints `clear`.
- `stop-on-precheck` (step): When the precheck prints anything but `clear`,
  gitify-project tells the user and stops, and moves none of their files.
- `setup-keeps-history` (test): When the folder already has a commit,
  `setup.sh` changes nothing and points to `commit.sh`.

## need versioned-instructions: Put the Project Instructions under version control

When the folder goes under git, the user wants the Project Instructions copied
exactly into `CLAUDE.md`, and the field left with one line that tells Claude to
read it, so the standing instructions have a history like any other file.

Source: README.md, under "Setting it up" and "Changing the standing
instructions", and the gitify-project description.

- `copy-field-exactly` (step): When the Project Instructions field has
  content, gitify-project passes it to `render` character for character, and
  passes `null` when it is empty.
- `instructions-verbatim` (test): When the answers carry the field's text,
  `render` puts it in `CLAUDE.md` byte for byte after the template's header,
  ends it with a newline, and puts it in no other file.
- `instructions-empty-is-null` (test): When `instructions` is `null`,
  `CLAUDE.md` holds only the header, and a blank or non-text value is
  rejected.
- `claude-md-note-hidden` (test): When Claude loads the rendered `CLAUDE.md`,
  the note for people at its top is an HTML comment and costs no context.
- `field-pointer` (test): When `render` stages the files, it prints the one
  line for the Project Instructions field, naming `CLAUDE.md` at the project's
  path.
- `hand-off-field` (step): When the files are on the device, gitify-project
  gives the user that line to put in place of everything in the field.

## need commit-from-cowork: Commit from a Cowork session

When the user asks Claude to commit what changed, they want Claude to write the
message and leave them one command to run, so the commit is made even though
Claude cannot make it from Cowork.

Source: README.md, under "Committing a change".

- `commit-after-first` (test): When the user runs `./commit.sh` with a
  message after the first commit, it stages every change and commits with
  that message.
- `commit-refuses-first` (test): When the folder has no commit yet,
  `commit.sh` refuses and points to `sh setup.sh`.

## constraint no-commit-from-cowork: Claude cannot make a commit from Cowork

A commit has to run from the user's own terminal.

Source: README.md, under "Committing a change", and COWORK.md.

## constraint instructions-field-closed: Claude cannot write the Project Instructions field

Only the user can change what the field holds.

Source: README.md, under "Setting it up", step 3.

## need gitignore-defaults: Keep system and editor files out of history

When the folder goes under git, the user wants the standard macOS files,
editor swap and backup files, and temporary files left out, since they are not
usually versioned.

Source: the owner's ruling on #130, item 11, and the owner's answer on #162
for temporary files.

- `gitignore-defaults` (test): When `render` writes `.gitignore`, it leaves
  out macOS's `.DS_Store`, `.AppleDouble`, `.LSOverride` and `._*` files,
  editor swap and backup files, and `*.tmp` files, and keeps shared editor settings such as
  `.vscode/settings.json`.

## constraint execute-bits-lost: Files copied through the bridge lose their execute bit

`device_commit_files` drops the execute bit, so a script it copies runs as
`sh x.sh` until something sets the bit again.

Source: COWORK.md, under "Moving files: `device_commit_files`".

- `setup-sets-exec-bits` (test): When the user runs `sh setup.sh`, it makes
  `setup.sh` and `commit.sh` executable before git records them.

## constraint copy-from-outputs: The bridge copies files from the outputs folder only

`device_commit_files` copies byte for byte, and only from
`/mnt/user-data/outputs/`, into a connected folder.

Source: COWORK.md, under "Moving files: `device_commit_files`" and "What the
design follows from this".

- `check-after-copy` (test): When the files are on the device, the check
  `render` printed passes when every file arrived intact, and names each file
  that did not.
- `recopy-on-failure` (step): When the check names a file, gitify-project
  copies it again with `device_commit_files`, and never edits it on the
  device.

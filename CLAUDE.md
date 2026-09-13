# claude-plugins

Guidance for Claude working in this repo. `README.md` covers layout, adding a
plugin, versioning, running the tests and editing from Cowork. Read it rather
than relying on a summary here; this file holds what the README does not.

## Workflow

- Work on a branch off `main`, and open a pull request. Scott reviews and
  merges.
- Until agents have their own GitHub identity, everything posts under Scott's
  account. Start every reply to a review comment with `**Claude:**`, so the
  thread does not read as one person answering themselves.
- Reply to each review thread with what changed and the commit that changed it.
  Leave resolving the thread to the reviewer.
- A review comment that names a kind of problem is about the kind. Look for
  other instances across the branch, not only the flagged line, and say in the
  reply what else turned up.
- Commits follow Conventional Commits, with a body saying why. `git log` shows
  the house style.

## Scripts and tests

- Plugin scripts use the standard library only and must run on Python 3.9.
  Things in `prose.py` that look like bugs and are not are listed in its module
  docstring - read that before "fixing" file writes or git usage.
- A new test is not finished until it has failed. Break the code it guards and
  confirm the test notices; the Properties section of the README says how, and
  why a green first run proves little.

## Comments and docs

- Do not count things that grow - "six cases", "the last two bugs". Say what
  the thing is for and let the code be the list; a count is wrong the moment
  someone adds one.
- Do not repeat an explanation that already lives somewhere. Point to it.
- Plain words over jargon.

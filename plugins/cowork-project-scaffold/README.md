# Cowork Project Scaffold

Sets up a Cowork Project folder as a git repository, and gives it a skill that
keeps the documents inside it honest.

**Cowork only.** It writes to your computer through Cowork's device bridge and
registers a skill through the in-conversation review card. Neither exists in
Claude Code.

## The problem it solves

Ask an agent to revise a document over and over and it starts narrating its own
edits. Revision-history blocks. "Amended 2026-08-26." A trailing changelog.
Within a few weeks a research document is half research and half archaeology,
and nobody can tell what is currently true.

Git already records all of that, better, and out of the way.

## The two rules

**1. Documents state what is currently true. Git states how they got that way.**

No revision blocks, no "amended" lines, no dates on which something was
decided. Those go in the commit message, where `git log --grep` can find them.

Uncertainty is different from history and stays in the document. Gaps,
confidence flags and "could not verify" notes are content a reader needs to
calibrate trust. The test is whether a line describes the world or describes
the editing.

**2. The repo is the source. The Claude account is a deployment target.**

Cowork skills are registered per account, not per project, so a project's
maintenance skill has to be installed globally. It is authored in the project's
own repo, committed there, and only then registered. Editing it in the Skills
UI leaves no commit and no diff, and the two copies drift silently.

## What you get

```
<Your Project>/
  .gitignore
  commit.sh                    clears the lock the bridge strands, then commits
  setup.sh                     one time: git init and the first commit
  current-state.md             the anchor document. Wins on every conflict
  project-instructions.md      mirror of the Project's custom-instructions field
  skills/
    README.md                  the repo-is-source convention, and the drift check
    update-<project>-docs/
      SKILL.md                 generated for this project, then registered
```

The generated skill carries the house rules that turned out to be universal:
front matter, `TODO(phase)` markers, decisions recorded as ADRs, Conventional
Commits with the correction log in the body, ISO dates, the drift check, and
the procedure for committing from a bridge that cannot delete files.

Two sections are optional and get deleted outright when they do not apply: a
template for repeating sections, and source-quality flags for projects that
make sourced factual claims.

## Using it

Ask Claude to start a new Cowork project, or to set up a project folder. The
skill runs a short interview, writes the folder, and proposes the generated
maintenance skill for you to save.

Three things it deliberately leaves to you, because the bridge cannot do them:

1. Run `./setup.sh` from your own terminal to create the repo.
2. Save the proposed skill from the review card.
3. Paste `project-instructions.md` into the Project's custom-instructions field.

## Why `commit.sh` exists

Cowork's bridge cannot delete files. Every `git commit` it attempts leaves a
`.git/HEAD.lock` behind, and that lock blocks every later write to the repo.
`commit.sh` clears the debris and makes the commit. Read-only git works fine
from the bridge, so Claude can still run `log`, `diff`, `blame` and `show`.

## Editing the templates

Everything the scaffolder writes lives in
`skills/new-cowork-project/templates/`. Change a file there, bump the version
in `.claude-plugin/plugin.json`, and reinstall.

Changing a template does not change projects already scaffolded. That is
deliberate. Each project's skill gets hand-tuned during the interview, and
regenerating would discard it.

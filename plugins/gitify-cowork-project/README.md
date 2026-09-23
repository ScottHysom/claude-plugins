# Gitify Cowork Project

Gitify Cowork Project gives a Cowork Project a version history with git,
without touching the documents in it. A Cowork Project is a workspace in the Claude desktop app's
Cowork mode, with its own instructions and a folder on your computer that
Claude reads and writes.

**Cowork only.** The plugin needs a Cowork Project with a connected folder, and
it does not run in Claude Code.

## When to use it

The plugin suits a project whether it is new or already under way:

- **A new project,** before anything is in the folder. History starts with the
  first document.
- **A project you have been working in for a while.** By then the folder holds
  real work. History shows what a document said last week and why a figure
  changed, and it gives a way back from an edit that went wrong.

The plugin adds the history and nothing else. It writes no documents, and no
rules about what documents say or how they read. Those belong to the project,
and a project that wants a house style adds one separately.

## When not to use it

A folder that is already a git repository has a history of its own. The plugin
starts history rather than taking over an existing one, so Claude stops when it
finds one.

## What you get

```
<Your Project>/
  (everything already there, untouched)
  .gitignore
  commit.sh                    makes each commit after the first
  setup.sh                     one time: creates the repository and the first commit
  CLAUDE.md                    the Project Instructions, now under version control
  skills/
    <project>-history/
      SKILL.md                 how Claude handles this project's history
```

A skill is a set of instructions Claude follows for one kind of task. The
`<project>-history` skill is written for this project and saved to your
account. Claude uses it whenever you ask about committing or about what changed.
It covers history only:

- how a commit is made from Cowork
- commit messages in the Conventional Commits format, which opens each message
  with the kind of change, such as `docs:` or `fix:`, and puts the reasons in
  the body
- ISO dates, such as `2026-08-20`
- keeping the saved skill and the copy in the folder the same

## Setting it up

With the plugin installed, ask Claude to put the project under git.

Claude checks the folder first. It stops in any of these cases:

- The folder is not there.
- The folder is already a git repository.
- The folder already has a file with the same name as one Claude would write.

Otherwise Claude lists what is in the folder and asks about anything that
probably should not be in git, such as large media or exports.

Claude then writes the files and leaves you the steps it cannot take:

1. **Run `sh setup.sh` from your own terminal, in the project folder.** The
   first run commits nothing. It lists every file the first commit would take.
   Add a pattern to `.gitignore` for anything that should stay out, and run
   `sh setup.sh` again to see the new list. When the list is right, run
   `sh setup.sh commit`.
2. **Save the proposed skill from the review card.** The review card is the
   card Cowork shows in the conversation when Claude proposes a skill for your
   account.
3. **Replace the Project Instructions field with the one line Claude gives
   you.** Claude cannot write the field itself. Whatever the field held is now
   in `CLAUDE.md`, copied exactly, and the line tells Claude to read it.

## Everyday use

### Committing a change

Ask Claude to commit what changed. Claude writes the commit message into
`.commit-msg` in the project folder and asks you to run `./commit.sh` from your
own terminal, which makes the commit with that message. Claude cannot make a
commit itself from Cowork.

`./commit.sh "docs: add the March figures"` commits with a message of your own
instead.

### Looking back

Claude can read the history at any time, with nothing for you to run. Ask it
questions such as:

- What did this document say last week?
- When did this figure change, and why?
- What corrections have been made to this file?
- Show me the whole of the last change.

The answer to "why" is only as good as the commit message, which is why the
history skill has Claude put the reasons in the body.

### Changing the standing instructions

`CLAUDE.md` holds the project's standing instructions. Edit it, or ask Claude
to, and commit it like any other file. The Project Instructions field keeps
only its one line. If anything else turns up there, Claude copies it into
`CLAUDE.md` and asks you to put the field back.

### Changing the history skill

The copy of the skill in the project folder is the original, and the copy
saved to your account is the one that runs. Edit the file in the folder, commit
it, then upload it again under **Customize → Skills**. An edit made directly in
Customize → Skills has no history and no way back.

### Catching up with the plugin

Each project's history skill is its own copy, so updating the plugin does not
change it. Ask Claude to check the project's history skill against the plugin.
Claude shows you the sections that differ, and carries across only the ones you
agree with.

## Technical design

Why the plugin is built the way it is, and how to change what it writes, is in
[DESIGN.md](https://github.com/ScottHysom/claude-plugins/blob/main/plugins/gitify-cowork-project/DESIGN.md).

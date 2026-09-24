# prose-tuning

prose-tuning teaches Claude how you want a project's documents to read. You
edit a few passages by hand, and Claude works out the rules behind your edits
and saves them in the project. From then on, Claude follows those rules in
everything it writes there. Claude can also check the documents you already
have against the rules and fix what breaks them, once you approve.

prose-tuning works in Claude Code, and in Cowork when you install it from
the marketplace.

## When to use it

Reach for it when you keep correcting the same things in what Claude writes.
Without it, Claude forgets your corrections when a conversation ends, and the
next conversation makes the same mistakes. With it, each correction becomes a
written rule that every later conversation in the project reads.

The plugin needs a project folder tracked by git, because it reads your edits
as the difference from the last commit. A Cowork Project that is not under git
yet can get there with the gitify-cowork-project plugin, from the same
marketplace.

For a single edit to a single document, ask Claude directly. The plugin earns
its place once the same correction comes up a second time.

## What it adds to your project

The rules live in `.claude/rules/prose-style.md`. Claude Code and Cowork load
every file in `.claude/rules/` into each conversation, so the rules apply to
everything Claude writes in the project:

- documents
- commit messages
- pull request titles and descriptions
- issues
- code comments

The whole file goes into every conversation, so a longer rulebook takes up
more of what Claude can hold in mind at once.

Each rule has a short id that says what it means, such as
`sentences-own-subject`. When Claude reports a passage that breaks a rule, it
names the id, so you can find the rule and check the report yourself.

A `.prose-tuning/` folder also appears in the project. It holds a copy of the
plugin's script, which the skills run from there. Git ignores
the folder, so it never reaches your commits. You can delete it whenever you
like, and the next run puts it back.

No skill in this plugin commits anything. Each one leaves its changes for you
to review and commit your usual way.

## Setting up

In Claude Code there is nothing to set up.

In Cowork, add this line to the project's Instructions field:

```
Read .claude/rules/prose-style.md before writing anything in this project.
```

Cowork does not load `.claude/rules/` for every part of a conversation, and
the line covers the gap. Finder hides folders whose names start with a dot,
such as `.claude`. Press Cmd-Shift-. to show them.

The first time you run `update-prose-config` in a project, Claude offers to
start the rules file from a default set the plugin ships. You can also start
from another project's rules, or from an empty file.

A project set up with an earlier version of this plugin keeps
`prose-style.md` at its top level, where nothing loads it. The skills stop
there and offer to copy it into `.claude/rules/`. They leave the old copy for
you to delete.

## The skills

| Skill | What it does | Ask Claude to |
|---|---|---|
| `update-prose-config` | Learns rules from your uncommitted edits and writes them into `.claude/rules/prose-style.md` | "update the prose config" |
| `apply-prose` | Reports where your documents break the rules, and rewrites the passages you approve | "apply the house style" |
| `adopt-prose` | Copies rules from another project's `prose-style.md` into this one | "adopt the prose rules from ..." |

## Teaching it your style

1. Edit some documents the way you want them to read. Leave the changes
   uncommitted.
2. Ask Claude to update the prose config.
3. Claude asks about any edit whose reason it cannot tell, all in one round of
   questions.
4. Claude writes the rules and leaves the changes for you to review and
   commit.

Where an edit needs explaining, say so in the document itself:

```
<del why="restates the passage">A bookmark list is not this document.</del>

<repl>
  <why>Three sentences carrying one claim.</why>
  <alt>Keep the sentence holding the fact; cut the rest.</alt>
  <del>Curated, not collected. A bookmark list is not this document.</del>
  <ins>A resource earns a place here only after it has been used.</ins>
</repl>
```

`<del>` marks text to cut and `<ins>` text to add. Both are real HTML
elements, so a markdown preview shows them as an edit while you write. `<repl>`
swaps one for the other, `why` says why, and `<alt>` offers a rule or another
way to write it. Claude removes all of this markup once the rules are written,
so none of it reaches a commit. The
[full list of tags](https://github.com/ScottHysom/claude-plugins/blob/main/plugins/prose-tuning/reference/tag-vocabulary.md)
has every form they take.

## Checking your documents

Ask Claude to apply the house style. Claude lists each passage that breaks a
rule, with the file, the line, the rule's id and a proposed rewrite. Nothing
changes until you approve. You can approve the whole list, or only some rules,
or only some files.

Two proposed rewrites sometimes touch the same passage, such as a fix inside a
paragraph that another rewrite cuts. Only one of them can apply. Claude shows
you both and asks which to keep.

A rewrite changes how a sentence reads and never what it says. Numbers,
names, dates and claims stay as they are.

The `scope:` list at the top of `prose-style.md` decides which files are
checked. If a file you expected was skipped, ask Claude why.

`apply-prose` will not start while you are partway through teaching it your
style, because rewriting documents you are still editing would tangle the two
sets of changes. Finish that run, or ask Claude to abandon it, first.

## Sharing rules between projects

Ask Claude to adopt the prose rules from another project. Rules this project
lacks are copied across, each with a note of where it came from. Claude asks
you about two cases, side by side and in one round:

- The two projects have a rule with the same id but different wording.
- Two rules say the same thing under different ids.

On Cowork, both projects have to be in folders connected to Cowork.

## Technical design

Why the plugin is built the way it is, from the script behind the skills to
why no skill commits, is in
[DESIGN.md](https://github.com/ScottHysom/claude-plugins/blob/main/plugins/prose-tuning/DESIGN.md).

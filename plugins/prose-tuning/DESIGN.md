# prose-tuning: technical design

This file explains why prose-tuning is built the way it is, for a contributor
changing the plugin. What the plugin does and how to use it is in
[README.md](README.md).

## Origin

Getting a set of documents to sound a particular way is easy to do once by
hand and tedious to repeat. The first run of this workflow, done by hand,
produced eleven good rules across six documents. That run also cost these:

- nine exchanges
- a tag vocabulary invented halfway through
- twenty hand-written anchor strings, of which three missed
- five malformed tags that nothing caught, because no parser existed yet

The rules were the valuable part, and they were lost at the end of the
session. Every later agent editing those documents started from nothing.

The plugin's answer is that prose style becomes a file in the repo rather than
something each session works out again.

## Where the rules live

`prose-style.md` sits in the project's `.claude/rules/` folder. Claude Code and
Cowork both load every file there into each session, so an agent has the rules
whether or not one of these skills is running. The cost is the whole file, in
the context of every session.

Cowork does not load the folder for every part of a conversation, which is why
the README asks Cowork users for a line in the Project's Instructions field.
[Designing for Cowork](https://github.com/ScottHysom/claude-plugins/blob/main/COWORK.md#how-instruction-files-load)
has what Cowork loads and when.

Rules carry ids that say what the rule means, such as
`sentences-own-subject`, rather than numbers given in writing order. A report
can then read `sentences-own-subject at landscape.md:42` and be checked
without opening the rules file. An id stays the same when its rule is
reworded, and stays the same when the rule is copied into another project.

The front matter allows only `key: value` pairs and one `scope:` block, and
`config lint` rejects anything else. `prose.py` is standard library only and has
no YAML parser, so a richer grammar would be parsed by guesswork. A key dropped
without an error would be a scope override that appears to work.

### Edits in another checkout

A session in a worktree the Claude Code desktop app made cannot edit the main
checkout's `.claude/`, so a run started there cannot write the rules beside the
author's edits. `carry` copies the edits into the session's tree instead, and
the run finishes there. It reads the other checkout with plain file reads and
`git show`, never writing to it, and refuses a file whose last commit differs
between the two trees, since the same edit would then read as a different
diff. `specs/prose-tuning.md`, under `constraint worktree-guards-shared-claude`,
has the source.

## Packaging

The skills call a bundled script, `scripts/prose.py`. Cowork's
`propose_skills` takes a single `SKILL.md` with no bundled files, so proposing
one of these skills gives a skill that cannot run. That is why the plugin
supports Cowork only by marketplace install.

On Cowork, the project is visible from the user's computer, and the plugin is
not. The skills therefore copy the script and the shipped rules into the
project, under `.prose-tuning/`. The folder carries its own `.gitignore` of
`*`, and preflight refuses to run from a copy git would commit.

Claude Code makes the same copy, for a different reason. Each Bash call there
starts a fresh shell, so a `$PROSE` set in one call is empty in the next. The
plugin's install path runs past 200 characters, and a model left to repeat it
pastes it into every command. From the project root, `.prose-tuning/prose.py`
is short enough to repeat, and both surfaces then run the same commands.
`reference/setup.md` has the steps the model follows.

## Why no skill commits

How a project commits is settled wherever that project settles it, such as its
`CLAUDE.md` or a commit script. A second set of commit instructions inside
this plugin would drift from the project's own.

## Why a script

`scripts/prose.py` does everything deterministic:

- parsing the markup
- selecting files
- diffing
- resolving tags
- reading the config

The model does only what needs judgment: inferring a rule, writing prose,
deciding whether a passage conforms. The script's module docstring lists its
commands, and the parts of it that look like bugs and are not.

These parts of the script carry the design.

### The tag-neutral diff

When the author has tagged an edit, the working tree differs from the last
commit in two ways at once: the edit, and the tags around it. A plain
`git diff` would report the tags as edits too. So `evidence` takes the markup
out in memory and diffs that instead, and reports each tagged edit once, as an
explicit record.

### The round trip

Neutralizing text the author tagged returns the untagged text, byte for byte.
Every shape the grammar allows holds to this. `evidence` diffs that text, so a
byte lost or invented there is an edit the author never made.

## The markup

A replacement is a `<del>` followed by an `<ins>`. Both are real HTML elements,
which GitHub's sanitizer allows and every markdown preview renders as an edit.
An invented element, such as `<with>`, `<old>` or `<new>`, is closed early by
the browser, which shows both versions run together.

`<repl>` is the only edit tag that holds another, and it holds exactly one
`<del>` and one `<ins>`. With no other nesting, the parser never has to decide
which span a closing tag closes.

The parser reports one message per fault. A parser that says two things about
one typo teaches the author to skim its output.

## Editing the shipped rules

The shipped rules live in `templates/prose-style.md`. `config init` starts a
new project's rules from them, so a project starts from a working set rather
than a blank file, and a project that wants to diverge edits its own copy.

Editing the shipped rules changes what new projects get and changes nothing
about existing ones, which do not update themselves. A rule from a real
project reaches the shipped rules through `adopt-prose`, whose `SKILL.md` says
what that also requires, including the version bump.

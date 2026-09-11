# prose-tuning

Learns a project's house prose style from edits already made, records it as
`prose-style.md` with stable rule ids, and conforms the rest of the documents
to it.

**Claude Code, and Cowork by marketplace install only.** The skills call a
bundled script, and Cowork's `propose_skills` takes a single `SKILL.md` with no
bundled files. Proposing one of these skills gives you a skill that cannot run.

## The problem it solves

Getting a set of documents to sound the way you want is easy to do once by hand
and miserable to repeat. The first run of this workflow produced eleven good
rules across six documents, and cost nine exchanges, a tag vocabulary invented
halfway through, twenty hand-written anchor strings of which three missed, and
five malformed tags that nothing caught because no parser existed yet.

The rules were the valuable part, and they evaporated at the end of the session.
Every later agent editing those documents started from nothing.

## The idea

Prose style becomes a file in the repo, not a thing re-derived per session.

`prose-style.md` sits at the project root. Every agent reads it before editing.
Its rules carry stable ids that say what the rule means, so a note can read
`sentences-own-subject at landscape.md:42` and be checkable without opening the
file.

`cowork-project-scaffold` ships the default, so a new project starts with
twenty-four rules rather than a blank file, and a project that wants to diverge
adds a section instead of rewriting a template.

## The three skills

| Skill | Does |
|---|---|
| `update-prose-config` | Reads your uncommitted edits, works out what rule each implies, asks about the ambiguous ones, writes `prose-style.md` |
| `apply-prose` | Reports where the existing documents break those rules, and rewrites on approval |
| `adopt-prose` | Copies rules between projects, or promotes one into the scaffold's shipped default |

None of them commits. The project's own maintenance skill owns commit
conventions, and a second source of truth for those helps nobody.

## Using it

Edit some documents the way you want them to read. Leave the changes
uncommitted. Then ask to update the prose config.

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

`<del>` and `<ins>` are real HTML elements, so a markdown preview renders that
as an edit while you write it. The markup never reaches a commit: the skill
resolves it once the rules are written. `reference/tag-vocabulary.md` is the
full grammar.

## Why a script

`scripts/prose.py` does everything deterministic - parsing the markup,
selecting files, diffing, inserting and resolving tags, reading the config -
and the model does only what needs judgement: inferring a rule, writing prose,
deciding whether a passage conforms.

Two parts of it carry the design.

**The tag-neutral diff.** Once a question has been inserted into a document, the
working tree differs from `HEAD` for two reasons at once: you edited prose, and
the tool added markup. A plain `git diff` hands the tool its own tags back as
your evidence. So `evidence` strips the markup in memory and diffs that instead.

**Batch-only insertion.** Every insertion shifts the line numbers below it, so
markup goes in as one batch applied bottom-up from a single snapshot. Twenty
separate calls cannot work, which is what the first run discovered the hard way.

Run `python3 scripts/prose.py selftest` to check it. The property that matters
is a round trip: for any batch, insert then strip returns the file
byte-identical.

## Editing the rules

The shipped default lives in the other plugin, at
`plugins/cowork-project-scaffold/skills/new-cowork-project/templates/prose-style.md`.
Editing it changes what new projects get and changes nothing about existing
ones, which do not update themselves.

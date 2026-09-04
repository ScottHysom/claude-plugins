---
name: {{SKILL_NAME}}
description: {{DESCRIPTION}}
---

# {{PROJECT_NAME}}: document maintenance

Working rules for the collateral in `{{PROJECT_PATH}}`.

The bridge mounts that folder under `$HOME/mnt/`. The exact mount depends on
which folder is connected this session, so confirm it with `ls "$HOME/mnt/"`
before using a path. The commands below assume `$HOME/mnt/{{PROJECT_MOUNT}}`.

## Before editing anything

1. `{{ANCHOR_DOC}}` is authoritative **on what is true about the project**.
   It supersedes any other document that contradicts it. This skill is
   authoritative on *how documents are written*. The two never overlap.
2. **This skill is the source of truth for how these documents are written.**
   Judgement and mechanics both live here, and everything below is binding. If
   an editorial rule needs to change, change it here. Do not write it into a
   document in the folder.
3. Stage the current file before revising it. The user edits these documents
   directly, and a stale container copy will silently clobber his work. Run
   `device_stage_files` on the device path, then work from the staged copy.
4. If this session will change **this skill**, run the drift check under
   **Skill provenance** below before touching it.

## The rule that governs every edit

**Documents state what is currently true. Git states how they got that way.**

Never add any of the following:

- a revision-history block
- an "Amended:" line
- an "Added at your request" section opener
- a "Verification note" paragraph
- a trailing changelog
- **a date on which something was decided or written.** "Some decision as of 2026-08-26"
  becomes "Current owner decision: some decision". `git log` holds the when

All of that belongs in the commit message.

Dates that are *part of a fact* stay: a release year, a quarter a figure covers,
a quote's date. The test is whether the date describes the world or describes
the editing.

The distinction that looks identical and isn't:

- **Uncertainty is content.** Keep gaps sections, confidence flags, "could not
  verify" notes, and conflicting-source warnings. A reader needs these to
  calibrate trust in what he is reading.
- **History is metadata.** Move "I corrected X to Y", "this section was added
  on DATE" and "sections were renumbered" into the commit body.

## The documents

<!-- FILL: one bullet per document in the folder, naming what it owns and what
     it must not duplicate. Keep it to one or two lines each. Every document in
     the folder appears here, or an agent will invent a home for new content.
     Shape:
       - `current-state.md` - what is true right now. Constraints, decisions,
         open questions, schedule. Wins on every conflict.
       - `<doc>.md` - <what it owns>. <what belongs elsewhere>.
-->

A fact lives in exactly one document. Other documents reference it rather than
restating it. When two documents could plausibly own something, `{{ANCHOR_DOC}}`
owns it.

## Prose instructions

The project owner's standing instructions. They apply to every document in this
folder, including this skill.

<!-- FILL: replace this list if the owner's standing instructions differ from
     the default below. If they are already set as a Claude preference, restate
     them here anyway. A skill cannot rely on a preference being loaded. -->

- Define jargon and acronyms on first use.
- Don't assume familiarity with named tools, libraries or techniques unless already known.
- Prefer a concrete example over an abstraction.
- Flag when you're simplifying.
- Prefer short sentences over long run-on sentences.
- Prefer a period over the em-dash (ranges are ok).
- Prefer bullet-lists over long sequences of comma- or semi-colon-delimited lists.

How those land in this project specifically:

- **First use is per document, not per project.** A pointer to a glossary is not
  a definition. One clause is enough.
- **"Already known" means the owner's own career.**
  <!-- FILL: name the domains that need no gloss, and the domains in THIS
       project that always do. Both halves matter: without the first, every
       document over-explains; without the second, jargon slips through. -->
- **Concrete means a number, a name or a title.**
  <!-- FILL: one real example from this project, and the vague version it beats. -->
- **Flag a simplification with the word.** Write "Simplifying:" and name what
  was left out.
- **Ranges keep their en-dash.** `20–30 hrs/wk`, `§1–§9`, `1988–2026`. That is
  a different mark doing a different job.
- **Tables follow the same rules.** A cell that reaches for an em-dash almost
  always wants a period or a colon instead.
- **A section marker is a heading, not a bold phrase.** If a bolded phrase sits
  alone on a line and introduces the block beneath it, make it a `###`. Bold
  stays for emphasis *inside* a paragraph, and for the lead-in to a bullet.
- **State a point once, in the place it lands hardest.** A section that opens
  with a claim, lists its parts, then closes by restating the claim has said it
  twice. Keep the version doing work the others do not. Applying a fact
  elsewhere is not restating it: the same fact can appear in two tables doing
  different work in each.
- **A count needs a list.** If a sentence counts something, the thing it counts
  is enumerated in the same document, and near enough to check.

What this does **not** license: cutting nuance to make a sentence short, or
dropping a caveat because it reads as a long clause. Split it into two
sentences instead.

## TODO markers

An open decision, or a question that could still be answered, gets a marker
where the evidence that raised it already sits:

```
TODO(phase): <the action, one or two lines>
```

Phases:
<!-- FILL: the phase vocabulary for this project, as a short list. These are
     work-queue buckets, not dates. Keep it under six. -->

`grep -rn 'TODO(' *.md` is the entire tooling.

`gap` is an extra phase and a different animal. It marks a canonical section
that exists with nothing behind it yet, so the hole is visible where a reader
will look for the content. It is not on the work queue, so keep it out of the
live list:

```sh
grep -rn 'TODO(' *.md | grep -v 'TODO(gap)'   # the actual queue
grep -rn 'TODO(gap)' *.md                     # the research backlog
```

A `gap` marker still names what would fill it. A bare "TODO(gap)" is not useful.

**What is not a TODO.** A documented absence of evidence, such as *"no public
dataset of this exists"*, is a **finding**. It stays prose. So does a `⚠`
caveat, and anything nobody can act on. Marking those makes the grep useless,
which is the one thing this convention has to get right. **When a case is
genuinely borderline, ask rather than assume.**

**Where markers live.** Project-level questions live in `{{ANCHOR_DOC}}` under
**Open questions**, in full. Everything else stays in the document that raised
it and gets one row in the index table under that same section. The index is
navigation, not a second copy of the reasoning.

**Closing one.** Delete the marker and its index row. If it was a decision,
record it under **Decisions made** with the why. Never leave a struck-through
or "resolved, see below" marker behind. That is history, and history lives in
the commit body.

## Front matter

Three lines at most, and only these:

```
**Status:** what stage this is at, and what it is / isn't
**Feeds:** which other document consumes this, if any
**Supersedes:** normally "nothing. {{ANCHOR_DOC}} still wins on conflicts."
```

No created date, no last-modified date, no version number. `git log -1
--format=%cs -- <file>` gives the real date and cannot drift out of sync.

## Decisions

Decisions live in `{{ANCHOR_DOC}}` under **Decisions made**, shaped like an ADR
(architecture decision record: what was decided, when, and why). The why is the
load-bearing part. At a later checkpoint a decision gets questioned and the
original reasoning is no longer in anyone's head. Record the consequence, not
just the choice.

Never record a decision twice. If it is in `{{ANCHOR_DOC}}`, other documents
reference it rather than restating it.

## Cross-references

**Cite a section by its exact heading text**, never by number:
`<file>.md § <Exact Heading>`. Never wrap the reference across a line, or grep
stops finding it. Renaming a heading breaks every reference to it, so sweep
afterwards:

```sh
grep -rn '\.md` §' *.md    # every reference, to check against the headings
```

Numbered sections are not used, because renumbering silently invalidates every
citation and leaves no error behind.

<!-- OPTIONAL SECTION. Keep it only if some document in this project has
     repeating sections that must all carry the same slots (one per genre, one
     per vendor, one per candidate). Delete the whole section otherwise, rather
     than leaving an empty template behind. -->
## Section template for `<document>.md`

Repeating sections are **named, not numbered**, and run **alphabetically**.

<!-- FILL: the slot table. Canonical headings are Title Case and their wording
     does not vary, because they are what a reader scans for.

     | Slot | Heading |
     |---|---|
     | 1 | *no heading.* A short general description under the `##` |
     | 2 | `### <Canonical Heading>` |
     | n | *zero or more freely-titled sections*, sentence case |

     Then the rules that are easy to get wrong. At minimum:
     - which slots are fixed rows in a fixed order, and what they contain
     - which slot is the free-form one, and that it uses sentence case
     - that a slot with nothing behind it still gets its heading, with a
       `TODO(gap):` under it naming what would fill it
     - what, if anything, may follow the last slot
-->

- **A slot with nothing behind it still gets its heading**, with a
  `TODO(gap):` under it naming what would fill it. A missing heading reads as
  "not applicable". An empty one reads as "not done yet", which is the truth.
- **Adding a section is one new section in alphabetical position**, plus its row
  in any roll-up document. Nothing else moves.
<!-- END OPTIONAL SECTION -->

<!-- OPTIONAL SECTION. Keep it only if this project makes sourced factual
     claims. Delete it for a project that is all design or all planning. -->
## Source-quality flags

This project treats estimator data as ordinal, never cardinal. Flag every
non-obvious figure:

<!-- FILL: the flag vocabulary. The four below are the default set and cover
     most research projects. Add or drop, but keep the last one: the distinction
     between a sourced number and your own judgement is the whole point. -->

- `[DISCLOSED]`: the party in question published it.
- `[EST]`: third-party analytics. Usable for ranking, never for arithmetic.
- `[SYNTH]`: an aggregator's synthesis with no stated sample size.
- `[ANALYSIS]`: your own judgment, not a sourced figure. Never attach it to a
  number.

Fact-check load-bearing claims against primary sources before they land in a
document. Record what was wrong and what it is now in the commit body, not in
the document.
<!-- END OPTIONAL SECTION -->

## Committing: the bridge cannot do this alone

`device_bash` cannot delete files. Every `git commit` it attempts strands a
`.git/HEAD.lock` that blocks all subsequent writes to the repo. So:

1. Edit the files. Use `device_commit_files`, or `sed` and heredocs via
   `device_bash`. Writes and renames work. Deletes do not.
2. Draft the commit message into `.commit-msg` in the repo root:
   ```sh
   cat > "$HOME/mnt/{{PROJECT_MOUNT}}/.commit-msg" <<'MSG'
   docs: <subject under ~70 chars, imperative, lowercase>

   <body: what changed and why. For corrections, state what was wrong,
   what it is now, and the source.>
   MSG
   ```
3. Tell the user to run `./commit.sh` from his own terminal. Do not attempt
   `git commit` from the bridge.

Read-only git works fine from the bridge and should be used freely:

```sh
cd "$HOME/mnt/{{PROJECT_MOUNT}}"
git log --oneline
git log --stat -- <file>
git log --grep="^fix" --format="%h %s%n%b"   # every correction ever recorded
git diff HEAD~1 -- <file>
git blame -L 100,120 <file>
git show <hash>                              # a whole change with its reasoning
```

Anything structural is the user's to run, not the bridge's. That covers
branches, stashes, rebases, deletions and remotes.

If a read-only command fails with a stale lock, ask the user to run
`./commit.sh`, which clears locks first. `find .git -name '*.lock' -delete`
also works.

## Commit types

[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).
Subject under ~70 chars, imperative, lowercase after the colon.

| Type | Use for |
|---|---|
| `docs:` | new sections, rewrites, expansions. Most commits |
| `fix:` | a claim was wrong and is now right. Always explain in the body |
| `refactor:` | reorganisation with no change of meaning, such as splitting files |
| `chore:` | repo plumbing, gitignore, tooling |
| `feat:` | a genuinely new artifact, such as a new document |

**The body is where the value is.** It is the corrections log. It just lives in
`git log` rather than in the document. For anything factual, name what was
wrong, what it is now, and the source:

```
fix: correct three claims in the <section> section

- <claim> is <right value>, not <wrong value>. Source: <link>
- <claim> is not stated in <source>; it was a passing reference, not a
  sourced figure
```

## Checking proposals against the constraints

The constraints themselves live in `{{ANCHOR_DOC}}` under **Current
Constraints**. They are not repeated here on purpose. They are facts about the
project, and `{{ANCHOR_DOC}}` owns those. A copy in this skill would go stale
the first time one changed.

**Read that section before evaluating any proposal.** Do not work from memory
or from what a primer says. The constraints change, and `{{ANCHOR_DOC}}` wins
on conflicts.

Then check the proposal against them explicitly. If something will not fit the
budget, say so with a rough estimate rather than hedging. Flag scope creep
early. Flag decisions with downstream consequences the user has not raised.
Treat the listed constraints as settled and do not re-litigate them unless the
user reopens them.

## Dates

ISO 8601 (`2026-08-20`) wherever a date appears in content. Never `08/20/26`.

## Skill provenance

This skill is authored in the repo, at
`skills/{{SKILL_NAME}}/SKILL.md`. The skill registered on the account under
**Customize → Skills** is a deployment artifact built from that file. Cowork has
no project-scoped skills, so the account copy is what actually runs. The repo
copy is what is versioned, and it wins. `skills/README.md` has the full
convention.

**Never edit this skill in the Skills UI.** An edit made there has no commit,
no diff and no way back. Edit the repo file, commit it, then re-upload.

**Drift check.** The container's cache of a synced skill is not reliably fresh.
It has served a superseded copy for the first ten minutes of a session, and a
false claim was made from it. Invoking the skill refreshes the cache, so invoke
first, *then* compare:

```sh
# device
shasum -a 256 "$HOME/mnt/{{PROJECT_MOUNT}}/skills/{{SKILL_NAME}}/SKILL.md"
# container, after invoking the skill
find /root/.claude/skills -name SKILL.md -path '*{{SKILL_NAME}}*' -exec sha256sum {} \;
```

- **Repo ahead.** The account copy is stale. Say so, and do not rely on rules
  the running skill does not have.
- **Account ahead.** Someone edited in the UI. Copy that version into the repo
  and commit it *before* any other work, or the change is lost.

A cheaper check needs no file access at all. The skill listing in the session
prompt always carries the **live registered** description. If it disagrees with
the `description:` in this file's front matter, the copies have drifted. That
proves drift but never its absence. A body-only edit leaves the description
untouched, and body-only is the common case. Treat a match as no information
rather than as an all-clear.

## Scope discipline for the process itself

`commit.sh`, `setup.sh`, `.gitignore`, `project-instructions.md`, `skills/` and
this skill are the entire process apparatus. `skills/README.md` is the one
deliberate addition, documenting the mirror convention. Nothing further:

- no CHANGELOG.md
- no second document about how the research itself is written
- no version numbers
- no templates
- no ISO conformance

## Improving these rules

This file was generated from the `cowork-project-scaffold` plugin, from
`skills/new-cowork-project/templates/maintain-docs.md`.

A rule that turns out to be universal belongs back in that template, in the
plugin repo, or the next project will not get it. A rule specific to
{{PROJECT_NAME}} stays here. Sorting a rule into the wrong pile is the main way
the template decays.

Editing the plugin does not change this file, and editing this file does not
change the plugin. They are separate copies on purpose: this one is tuned to
{{PROJECT_NAME}} and regenerating it would discard that tuning.

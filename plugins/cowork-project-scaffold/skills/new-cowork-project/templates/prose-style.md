---
name: {{PROJECT_NAME}} prose style
scope:
  include:
    - "**/*.md"
  exclude:
    - "prose-style.md"
    - "project-instructions.md"
    - "**/README.md"
    - "skills/**"
---

# {{PROJECT_NAME}}: prose style

The house style for every document in this repo, including this one. The
`{{SKILL_NAME}}` skill is authoritative on document mechanics - front matter,
TODO markers, diagrams, commit format. This file is authoritative on how the
sentences read. The two never overlap.

Every rule has a stable id of the form `<section>-<name>`, where the name is
one to four words saying what the rule means. A report names the id, so
`apply-prose` can say `sentences-own-subject at landscape.md:42` and be checked
by eye. A rule that gets reworded keeps its name. Nothing here is ever marked
retired: a rule that changes is edited in place, and `git log -p prose-style.md`
holds what it used to say.

What none of this licenses: cutting nuance to make a sentence short, or
dropping a caveat because it reads as a long clause. Split it into two
sentences instead.

## Standing instructions

The project owner's standing preferences. They apply to every document in this
folder.

<!-- FILL: replace or extend these if the owner's standing instructions differ
     from the defaults below. If they are already set as a Claude preference,
     restate them here anyway. A skill cannot rely on a preference being
     loaded, and neither can this file. -->

### standing-define-terms: Define jargon and acronyms on first use
<!-- prose-rule: source=shipped -->

First use is per document, not per project. A pointer to a glossary is not a
definition. One clause is enough.

### standing-no-assumed-familiarity: Do not assume familiarity with a named tool or technique
<!-- prose-rule: source=shipped -->

"Already known" means the owner's own career, not the field at large.

<!-- FILL: name the domains that need no gloss, and the domains in THIS
     project that always do. Both halves matter: without the first, every
     document over-explains; without the second, jargon slips through. -->

### standing-concrete-over-abstract: Prefer a concrete example over an abstraction
<!-- prose-rule: source=shipped -->

Concrete means a number, a name or a title.

<!-- FILL: one real example from this project, and the vague version it
     beats. -->

### standing-flag-simplification: Flag a simplification with the word
<!-- prose-rule: source=shipped -->

Write "Simplifying:" and name what was left out. A compression the reader
cannot see is a compression the reader will later mistake for the whole
picture.

### standing-short-sentences: Prefer short sentences over long run-on sentences
<!-- prose-rule: source=shipped -->

Two sentences that each carry one claim beat one sentence carrying both. This
rule loses to nuance, never the other way round: when splitting would drop a
caveat, keep the caveat and split somewhere else.

### standing-no-em-dash: Prefer a period over the em-dash
<!-- prose-rule: source=shipped -->

Ranges keep their en-dash. `20-30 hrs/wk`, `1988-2026`. That is a different
mark doing a different job. Tables follow the same rules: a cell that reaches
for an em-dash almost always wants a period or a colon instead.

> **Before.** The estimate holds - until the vendor changes its pricing.
> **After.** The estimate holds. It stops holding when the vendor changes its pricing.

### standing-bullet-over-run: Prefer a bullet list over a long delimited run
<!-- prose-rule: source=shipped -->

A run of three or more phrases becomes bullets under a lead-in line.

> **Before.** reading papers at the source, contributing to an open-source project, or producing public writing about any of this
> **After.** The ways this could go further:

### standing-us-spelling: Use US spelling
<!-- prose-rule: source=shipped -->

Behavior, not behaviour. Judgment, not judgement.

## Sentences

### sentences-own-subject: Every sentence carries its own subject
<!-- prose-rule: source=shipped -->

A sentence that borrows its subject from the heading above it, from the
sentence before it, or from the reader's inference is incomplete.

**Check.** Read the sentence with nothing before it. If it no longer says who
or what, its subject is missing.

> **Before.** Able to state what is inside the file.
> **After.** A reader can state what is inside the file.

<!-- FILL: replace that example with a real before and after from this
     project. -->

### sentences-name-the-role: Name the role
<!-- prose-rule: source=shipped -->

A project has more than one person in it, and prose names the one it means
rather than leaving it to inference.

<!-- FILL: name this project's roles and say which documents speak of which. A
     common set: the author, who sets the goals and constraints; the reader,
     who works the material; the agent, who edits the documents. Without this
     list every dropped subject returns as "you". -->

### sentences-imperative-no-subject: Imperatives take no subject
<!-- prose-rule: source=shipped -->

An exercise step or a procedure is written as a bare imperative. Second person
is the usual way a dropped role returns.

> **Before.** Write down the number you are actually working with.
> **After.** Write down the resulting number.

### sentences-negation-earns-place: Negation only where its absence would mislead
<!-- prose-rule: source=shipped -->

"A model is not a program. It is a large file of numbers" earns the negation,
because a reader arrives expecting a program. "A bonus, not a gating criterion"
does not, because nobody claimed otherwise. Where the negation is needed, fold
it into the preceding sentence rather than appending it as its own.

> **Before.** Understanding what these involve is in scope. Doing them is not.
> **After.** It is in scope to understand what these involve, and not a requirement to do them.

### sentences-load-bearing-colon: A colon the reader could delete is the wrong mark
<!-- prose-rule: source=shipped -->

Rephrase rather than repunctuate.

> **Before.** A lesson stays current: when something in it is wrong or incomplete, amend it.
> **After.** Keep the lesson content up to date. When something in it is wrong or incomplete, amend it.

### sentences-name-before-count: Name what is counted rather than opening with the count
<!-- prose-rule: source=shipped -->

An opening count makes the reader hold a number until the list arrives. The
count still needs its list, under `sentences-count-needs-list`.

> **Before.** Three glosses, since none of this is obvious from the outside.
> **After.** The terms that need a gloss:

### sentences-simplification-full-sentence: A simplification is flagged in a full sentence
<!-- prose-rule: source=shipped -->

"Simplifying:" reads as a participle attached to the subject rather than as the
author flagging a compression. Name the agent and the compression in one
sentence.

> **Before.** Simplifying: this section treats X as fixed.
> **After.** As a simplification, this section treats X as fixed and leaves Y to §Z.

### sentences-no-restating-close: A closing sentence that restates the passage is cut
<!-- prose-rule: source=shipped -->

Keep the sentence carrying the information.

**Check.** Delete the sentence and see whether the reader has lost a fact.

> **Before.** Curated, not collected. A resource earns a place here only after it has been used for something. A bookmark list is not this document.
> **After.** A resource earns a place here only after it has been used for something.

### sentences-count-needs-list: A count needs a list
<!-- prose-rule: source=shipped -->

If a sentence counts something, the thing it counts is enumerated in the same
document, and near enough to check. This rule is broken far more often by
editing than by writing. See the `{{SKILL_NAME}}` skill,
§ Re-reading after an edit.

### sentences-say-it-once: State a point once, in the place it lands hardest
<!-- prose-rule: source=shipped -->

A section that opens with a claim, lists its parts, then closes by restating
the claim has said it twice. Keep the version doing work the others do not.

Applying a fact elsewhere is not restating it: the same fact can appear in two
tables doing different work in each.

## Headings

### headings-noun-phrase: A heading is a short noun phrase
<!-- prose-rule: source=shipped -->

A heading does not editorialize, does not count its own contents, and is not a
sentence or a question.

> **Before.** ### The size arithmetic, which is the whole point
> **After.** ### The size arithmetic

### headings-first-sentence-standalone: The first sentence of a section stands alone
<!-- prose-rule: source=shipped -->

A reader who jumps to a section, or who quotes one sentence out of it, gets a
complete statement.

> **Before.** ## Kill criteria / Decided in advance, while it is still cheap to decide:
> **After.** ## Kill criteria / The criteria that end the project early include:

### headings-not-bold-phrase: A section marker is a heading, not a bold phrase
<!-- prose-rule: source=shipped -->

If a bolded phrase sits alone on a line and introduces the block beneath it,
make it a `###`. Bold stays for emphasis inside a paragraph, and for the
lead-in to a bullet.

## Register

### register-matches-audience: The register matches the audience
<!-- prose-rule: source=shipped -->

<!-- FILL: name this project's reader and the register that fits. Give one
     colloquial phrase this project has actually produced, and its
     replacement. A rule with no example does not survive contact. -->

### register-no-presuming-adjectives: An adjective that presumes the reader's state is cut
<!-- prose-rule: source=shipped -->

"The non-obvious result is in the bolded column" tells the reader what he has
already found obvious, or has not. Leave the judgement to him.

> **Before.** The non-obvious result is in the bolded column.
> **After.** The result in the bolded column:

## Settled decisions

### decisions-drop-alternatives: A closed decision drops its alternatives
<!-- prose-rule: source=shipped -->

A decision that has been made records what was decided and the constraint that
forced it. The alternatives that lost are editorial. Cut the "the alternative
was X" and "the cost is Y" clauses once the choice is closed. They move to the
commit body.

The exception is a section deliberately authored as a comparison. It keeps its
full pros and cons. A section qualifies when either of these holds:

1. The choice is still live. Keep the comparison while the decision is open,
   and move it to the commit body once the decision is closed.
2. The owner explicitly asked to record it for posterity. Say in the section
   that its purpose is to record the options.

<!-- FILL: point at a section in this project that is deliberately a
     comparison, if one exists. Without an example the exception gets read as
     permission to keep every alternative-and-cost clause. -->

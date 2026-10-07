---
name: claude-plugins prose style
scope:
  include:
    - "**/*.md"
  exclude:
    - ".claude/**"
    - "plugins/prose-tuning/templates/prose-style.md"
---

# claude-plugins: prose style

The house style for everything written in this project: its documents, this
one included, and also commit messages, pull request titles and descriptions,
issues and code comments. It covers how the sentences read. The rules on
headings apply wherever there are headings, a pull request description as much
as a document. A pull request title or a commit subject is not a heading.
Mechanics - front matter, TODO markers, diagrams, commit format - are out of
its scope.

This file sits in `.claude/rules/`, so every session in the project loads it.
The `scope:` block above decides only which files `apply-prose` checks.

Every rule has a stable id of the form `<section>-<name>`, where the name is
one to four words saying what the rule means. A report names the id, so
`apply-prose` can say `sentences-own-subject at landscape.md:42` and be checked
by eye. A rule that gets reworded keeps its name. Nothing here is ever marked
retired: a rule that changes is edited in place, and
`git log -p .claude/rules/prose-style.md` holds what it used to say.

What none of this licenses: cutting nuance to make a sentence short, or
dropping a caveat because it reads as a long clause. Split it into two
sentences instead.

## Standing instructions

The project owner's standing preferences. They apply to everything written in
this repo.

### standing-define-terms: Define jargon and acronyms on first use

First use is per document, not per project. A pointer to a glossary is not a
definition. One clause is enough.

A term the document gives its own meaning is bolded in the sentence that
defines it, and only there.

> **Before.** A need says who wants what outcome, and why.
> **After.** A **need** says who wants what outcome, and why.

### standing-no-assumed-familiarity: Do not assume familiarity with a named tool or technique

"Already known" means the owner's own career, not the field at large.

Git, GitHub, Python, pytest, shell, CI and JSON need no gloss. These always
do:

- Cowork, and its device bridge.
- How plugins, skills and the marketplace fit together.
- prose-tuning's markup.

### standing-concrete-over-abstract: Prefer a concrete example over an abstraction

Concrete means a number, a name or a title.

> **Before.** The claim step can fail if the issue is not ready.
> **After.** `issues.py claim 64` exits 1 when #64 is not labeled `approved`.

### standing-flag-simplification: Flag a simplification and name what was left out

Say in so many words that a passage simplifies, and name what it leaves out.
`sentences-simplification-full-sentence` gives the form. A compression the
reader cannot see is a compression the reader will later mistake for the whole
picture.

### standing-short-sentences: Prefer short sentences over long run-on sentences

Two sentences that each carry one claim beat one sentence carrying both. This
rule loses to nuance, never the other way round: when splitting would drop a
caveat, keep the caveat and split somewhere else.

### standing-no-em-dash: Prefer a period over the em-dash

Ranges keep their en-dash. `20-30 hrs/wk`, `1988-2026`. That is a different
mark doing a different job. Tables follow the same rules: a cell that reaches
for an em-dash almost always wants a period or a colon instead.

**Pattern.** `—`
**Pattern.** `\s(?:--?|–)(?:\s|$)`

> **Before.** The estimate holds - until the vendor changes its pricing.
> **After.** The estimate holds. It stops holding when the vendor changes its pricing.

### standing-bullet-over-run: Prefer a bullet list over a long delimited run

A run of three or more phrases or clauses becomes bullets under a lead-in line.
A run of clauses is often a list of things in disguise, such as the conditions
a check fails on. It counts even when it spans two sentences joined by "It
also fails".

> **Before.** `changes` fails one whose description does not name each requirement id, and one that adds a need no issue it closes names. It also fails one that closes an issue edited after `approved` was last added to it.
> **After.** `changes` runs in CI on a pull request. It fails under any of these conditions:

### standing-hoist-shared-opening: Move a shared opening into the lead-in

When most items of a list open with the same phrase, that phrase moves into a
lead-in line above the list, and every item reads on from it. Rewrite an item
that does not open with the phrase so it reads on too. The phrase is a unit of
the sentence, such as its subject, or its subject and verb. A lone article or
word such as "every" does not count, and nor does half a noun phrase, such as
the "A new" in "A new need" and "A new requirement".

> **Before.** - The tool copies dotfiles. - The tool never writes under `.git`. - Execute bits are lost.
> **After.** The tool: - copies dotfiles. - never writes under `.git`. - loses execute bits.

### standing-us-spelling: Use US spelling

Behavior, not behaviour. Judgment, not judgement. The patterns list the
British forms that turn up most. A word they miss is still wrong.

**Pattern.** `(?i)\b(?:arm|behavi|col|endeavo|fav|flav|harb|hon|hum|lab|neighb|od|parl|rum|sav|splend|val|vig)our\w*`
**Pattern.** `(?i)\b(?:analy|cataly|paraly)s(?:e|ed|ing)\b`
**Pattern.** `(?i)\b(?:apolog|author|capital|categor|character|critic|custom|emphas|final|general|initial|maxim|memor|minim|normal|optim|organ|priorit|real|recogn|serial|special|stabil|standard|summar|synchron|util|visual)is(?:e|es|ed|ing|ation|ations)\b`
**Pattern.** `(?i)\b(?:calib|cent|fib|lit|met|somb|spect|theat)r(?:e|es|ed)\b`
**Pattern.** `(?i)\b(?:cancel|channel|counsel|fuel|label|level|marvel|model|signal|total|travel|tunnel)l(?:ed|ing|er|ers|or|ors|ous)\b`
**Pattern.** `(?i)\b(?:defen|licen|offen|preten)ces?\b`
**Pattern.** `(?i)\b(?:(?:acknowledge|judge)ments?|ageing|aluminium|amongst|analogue|catalogues?|cheques?|greys?|jewellery|learnt|manoeuvres?|moulds?|programmes?|sceptic(?:al|ism)?|storeys|tyres?|whilst)\b`

## Sentences

### sentences-own-subject: Every sentence carries its own subject

A sentence that borrows its subject from the heading above it, from the
sentence before it, or from the reader's inference is incomplete.
A list item that reads on from its lead-in line is part of that line's
sentence, as `standing-hoist-shared-opening` asks, and does not borrow.

**Check.** Read the sentence with nothing before it. If it no longer says who
or what, its subject is missing.

> **Before.** Able to state what is inside the file.
> **After.** A reader can state what is inside the file.

### sentences-name-the-role: Name the role

A project has more than one person in it, and prose names the one it means
rather than leaving it to inference.

The roles in this repo:

- **The owner** approves issues, reviews pull requests and merges them.
- **The agent** is Claude working an issue. It posts under the owner's
  account, so its replies start with `**Claude:**`.
- **A contributor** is anyone changing the repo. `CLAUDE.md`, `README.md` and
  `COWORK.md` speak to them.
- **The user** has installed a plugin. A plugin's `README.md` speaks to them.
- **The model** is Claude following a skill. `SKILL.md` and a plugin's
  `reference/` speak to it.

### sentences-imperative-no-subject: Imperatives take no subject

An exercise step or a procedure is written as a bare imperative. Second person
is the usual way a dropped role returns.

> **Before.** Write down the number you are actually working with.
> **After.** Write down the resulting number.

### sentences-negation-earns-place: Negation only where its absence would mislead

"A model is not a program. It is a large file of numbers" earns the negation,
because a reader arrives expecting a program. "A bonus, not a gating criterion"
does not, because nobody claimed otherwise. Where the negation is needed, fold
it into the preceding sentence rather than appending it as its own.

> **Before.** Understanding what these involve is in scope. Doing them is not.
> **After.** It is in scope to understand what these involve, and not a requirement to do them.

### sentences-negate-the-verb: A negation goes on the verb, not the noun

"Cites no requirement" makes the reader find the negation on the object.
"Does not cite a requirement" puts it on the verb, where the reader looks for
it. The same holds for a subject: "No script can decide" becomes "A script
cannot decide", "tools that no script can reach" becomes "tools that a
script cannot reach", and "Nothing decided anything from the key" becomes
"The key was not read by any code". "Has no", as in "a behavior has no test",
stays.

A negation that covers a list goes on the verb once, and the list follows it.
"Does not find any spec, test or skill step" still fails on each item alone.
Repeating the verb for each item, as in "does not find any spec, does not find
any test or does not find any skill step", adds words and no meaning.

**Pattern.** `\b(?!(?:has|is|was|does)\b)[a-z]+s no\b`
**Pattern.** `\b[a-z]+ed no\b`
**Pattern.** `\b[a-z]+ing no\b`
**Pattern.** `\b(?:under|to (?!(?:why|what|how|where|when)\b)[a-z]+) no\b`
**Pattern.** `\b[Nn]o [a-z]+ can\b`
**Pattern.** `\b(?:by|in|to) no (?!(?:longer|one|matter|more)\b)[a-z]+`
**Pattern.** `\b(?:give|given|put|run|show|shown|take|taken|write|written) no\b`
**Pattern.** `(?i)\b((?:do|does|did|can|could|will|would|is|are|was|were)(?: not|n't) [a-z]+)\b[^.;:]*?\b\1\b`
**Pattern.** `(?:^|[.!?]\s+)Nothing [a-z]+ed\b`

> **Before.** The spec pull request changes no behavior.
> **After.** The spec pull request does not change any behavior.

### sentences-keep-relative-that: A relative clause keeps its "that"

"A line no test runs" drops the word that tells the reader a clause has
started. Write "a line that no test runs", or "a line not run by any test".
Either form is fine.

**Pattern.** `(?i)\b(?!(?:that|which|with|and|or|of|is|has|by|to|in|for|as|under|was|does|are|when|where|why|so|because|if|since|once|until|while|but)\b)(?![a-z]+(?:s|ed)\b)[a-z]+ no (?!(?:longer|matter)\b)[a-z]+ (?:[a-z]+ ){0,4}(?:[a-z]+s|[a-z]+ed|can|has|have|will)\b`
**Pattern.** `(?i)\b(?:a|an|the|every|each|any) [a-z]+ (?:nobody|nothing) (?!else\b)[a-z]+`
**Pattern.** `(?i)\b(?!(?:is|was|has|does|says|means)\b)[a-z]+s (?:nobody|nothing) (?!else\b)[a-z]+s\b`

> **Before.** Read those by hand for behavior no test runs.
> **After.** Read those by hand for behavior that no test runs.

### sentences-load-bearing-colon: A colon the reader could delete is the wrong mark

Rephrase rather than repunctuate.

> **Before.** A lesson stays current: when something in it is wrong or incomplete, amend it.
> **After.** Keep the lesson content up to date. When something in it is wrong or incomplete, amend it.

### sentences-name-before-count: Name what is counted rather than opening with the count

An opening count makes the reader hold a number until the list arrives. The
count still needs its list, under `sentences-count-needs-list`.

> **Before.** Three glosses, since none of this is obvious from the outside.
> **After.** The terms that need a gloss:

### sentences-simplification-full-sentence: A simplification is flagged in a full sentence

"Simplifying:" reads as a participle attached to the subject rather than as the
author flagging a compression. Name the agent and the compression in one
sentence.

> **Before.** Simplifying: this section treats X as fixed.
> **After.** As a simplification, this section treats X as fixed and leaves Y to §Z.

### sentences-no-restating-close: A closing sentence that restates the passage is cut

Keep the sentence carrying the information.

**Check.** Delete the sentence and see whether the reader has lost a fact.

> **Before.** Curated, not collected. A resource earns a place here only after it has been used for something. A bookmark list is not this document.
> **After.** A resource earns a place here only after it has been used for something.

### sentences-count-needs-list: A count needs a list

If a sentence counts something, the thing it counts is enumerated in the same
document, and near enough to check. This rule is broken far more often by
editing than by writing, so after an edit, re-read every count in the section
against the list it counts.

### sentences-say-it-once: State a point once, in the place it lands hardest

A section that opens with a claim, lists its parts, then closes by restating
the claim has said it twice. Keep the version doing work the others do not.

Applying a fact elsewhere is not restating it: the same fact can appear in two
tables doing different work in each.

### sentences-word-reads-one-way: A word that reads two ways is replaced

"No variable kept from the call before" can mean "carried over from" or
"prevented from". Use a word that has only the meaning intended.

**Pattern.** `\bkept from\b`

> **Before.** Every call starts afresh, with no variable or `cd` kept from the call before.
> **After.** Every call starts afresh, with no variable or `cd` retained from the call before.

### sentences-parenthetical-including: An included case goes in parentheses

An aside naming a case that is included goes in parentheses, led by
"including". A trailing "X included" set off by commas reads as part of the
main clause.

**Pattern.** `,\s[^,()]+\sincluded,`
**Pattern.** `,\s[^,()]+\sincluded\.`

> **Before.** A heading that is not a need or a constraint, a misspelled one included, opens no section.
> **After.** A heading that is not a need or a constraint (including a misspelled one) does not open a section.

### sentences-one-negation: A sentence carries one negation

Two negations in one sentence make the reader undo both. Turn one of them
positive.

**Pattern.** `(?i)\b(?:nothing|nobody|no one|not)\b[^.;:]*\bnever\b`

> **Before.** Nothing can show that a behavior was never asked for.
> **After.** No one can know whether a behavior was ever asked for.

### sentences-none-names-noun: "None" gives way to the noun it stands for

"Had none" sends the reader back to the sentence before to learn what there
is none of. Name the noun.

**Pattern.** `(?i)\b(?:has|had|have) none\b`

> **Before.** The lint code that held `source` to its values had none.
> **After.** The lint code that held `source` to its values had no tests.

### sentences-one-meaning-per-term: A term keeps one meaning in a document

A word the document defines, such as a role, is not reused for anything
else, including in a heading.

> **Before.** ## The model
> **After.** ## The method

## Headings

### headings-noun-phrase: A heading is a short noun phrase

A heading does not editorialize, does not count its own contents, and is not a
sentence or a question.

> **Before.** ### The size arithmetic, which is the whole point
> **After.** ### The size arithmetic

### headings-first-sentence-standalone: The first sentence of a section stands alone

A reader who jumps to a section, or who quotes one sentence out of it, gets a
complete statement.

> **Before.** ## Kill criteria / Decided in advance, while it is still cheap to decide:
> **After.** ## Kill criteria / The criteria that end the project early include:

### headings-not-bold-phrase: A section marker is a heading, not a bold phrase

If a bolded phrase sits alone on a line and introduces the block beneath it,
make it a `###`. Bold stays for emphasis inside a paragraph, and for the
lead-in to a bullet.

## Register

### register-matches-audience: The register matches the audience

The contributor docs are plain technical prose for an engineer. A plugin's
`README.md` is for someone who has just installed the plugin and may not write
code.

> **Before.** The grep it replaced went blind the moment its pathspec stopped matching and stayed green.
> **After.** The grep it replaced matched no files once its pathspec went stale, and still passed.

### register-no-presuming-adjectives: An adjective that presumes the reader's state is cut

"The non-obvious result is in the bolded column" tells the reader what they have
already found obvious, or have not. Leave the judgment to them.

> **Before.** The non-obvious result is in the bolded column.
> **After.** The result in the bolded column:

### register-contractions-allowed: Contractions are fine

A contraction such as "won't" is as acceptable as "will not", in every
document. Neither form is preferred.

### register-skill-clauses-change-behavior: In a skill's instructions, every clause changes what the model does

A `SKILL.md` speaks to the model, which reads all of it on every run of the
skill. So does a file in the plugin's `reference/` that the `SKILL.md` sends
the model to read. A clause that records design history, or argues for the
design to a contributor, costs context on each run and can read as an
instruction. A reason stays when it changes a decision the model makes, or
holds a line the model will be pressed to cross. The rest belongs in the
plugin's `DESIGN.md`, the script's docstring or the commit body.

**Check.** Delete the clause and ask whether the model would then do anything
differently. If it would not, the clause goes.

> **Before.** `update-prose-config` deliberately cannot do it: a skill that writes outside the repo it was invoked in is a skill whose blast radius depends on which machine it ran on.
> **After.** `update-prose-config` deliberately cannot do it.

## Settled decisions

### decisions-drop-alternatives: A closed decision drops its alternatives

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

"Schemes considered" in SPEC-METHODOLOGY.md is one, kept at the owner's request.

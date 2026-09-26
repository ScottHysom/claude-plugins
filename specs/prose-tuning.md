# prose-tuning

This file records what the prose-tuning plugin is for. SPEC-METHODOLOGY.md, at
the repo root, has the grammar of this file and the steps that add its
requirements.

## Out of scope

- Writing outside the project repo a skill was invoked in.
- A single edit to a single document, which the user asks Claude for
  directly.
- Putting a project under git, which gitify-cowork-project does.

## need remembered-corrections: Keep a correction past the conversation

When the user keeps correcting the same things in what Claude writes in a
project, they want each correction kept as a written rule that every later
conversation there reads, so the next conversation does not repeat the
mistake.

Source: README.md, under "When to use it" and "What it adds to your project".

## need learn-from-edits: Teach the style by editing

When the user has edited documents the way they want them to read, they want
Claude to work out the rules behind the uncommitted edits and write them into
`prose-style.md`, so the user teaches the style by editing rather than by
writing rules.

Source: README.md, the opening section and "Teaching it your style", and the
update-prose-config description. The two occurrences that make a candidate a
rule are the owner's figure, in the ruling on #132.

- `inferred-hunks` (test): When the author has edited a file in scope without
  markup, `evidence` reports each changed run of lines since the last commit
  as one inferred record, with its lines before and after.
- `markup-not-evidence` (test): When a file holds markup, `evidence` diffs it
  with the markup taken out, and numbers each hunk by its line in the working
  file.
- `explicit-records` (test): When a file holds the author's `<ins>`, `<del>`
  or `<repl>`, `evidence` reports each as an explicit record with its old and
  new text, and the `why` and `<alt>` it carries.
- `hunk-signal` (test): When an inferred hunk changed only numbers, only link
  targets or only whitespace, `evidence` marks it `numeric-only`, `link-only`
  or `whitespace-only`.
- `signal-to-interview` (step): When a hunk carries a signal,
  update-prose-config takes it to the interview and never straight into a
  rule.
- `rule-threshold` (step): When a candidate occurs two or more times
  independently, carries a `why` or an `<alt>`, or is settled by an answered
  question, update-prose-config makes it a rule, and anything else a
  question.
- `reproduce-overlap` (test): When `reproduce` runs, it reports each edit since
  the last commit as reproduced when a rule's pattern, run over the file as it
  was at the last commit, matches text the edit changed. A pure insertion is
  never reproduced.
- `reproduce-lists-unpatterned` (test): When `reproduce` runs, it lists by id
  every rule with no pattern.
- `reproduce-refuses-unlinted` (test): When `prose-style.md` does not lint
  clean, `reproduce` names the fault and exits 1 before reading any file.
- `fix-the-rule` (step): When an edit is reproduced by no pattern and
  accounted for by no unpatterned rule, update-prose-config fixes the rule
  rather than the document.

## need one-question-round: Answer every open question at once

When Claude cannot tell the reason for an edit, the user wants every such
question asked in one round, so learning the rules takes a single exchange.

Source: README.md, under "Teaching it your style", step 3, and the
update-prose-config description.

- `interview-one-batch` (step): When update-prose-config has open questions,
  it puts all of them to the author in one `AskUserQuestion` call, with every
  hunk that carries a signal asked as one question.

## need explain-in-place: Say why an edit was made, in the document

When an edit needs explaining, the user wants to mark it in the document
itself, with markup a markdown preview shows as an edit, and wants Claude to
remove the markup once the rules are written, so none of it reaches a commit.

Source: README.md, under "Teaching it your style", and the update-prose-config
description.

- `markup-faults-named` (test): When markup breaks the grammar in
  `reference/tag-vocabulary.md`, the scanner reports each fault once, with its
  file and line.
- `code-markup-is-prose` (test): When a tag sits inside a code fence or a
  code span, the scanner reads it as prose.
- `bare-pair-is-replacement` (test): When a `<del>` is followed directly by an
  `<ins>`, the scanner and `evidence` read the pair as one replacement.
- `resolve-accepts-edits` (test): When `tags resolve` runs, `<ins>` text
  stays, `<del>` text goes, `<repl>` keeps its replacement, and every tag is
  removed.
- `resolve-tidies-cuts` (test): When a resolved cut removes whole paragraphs,
  one blank line is left where they were, none at either end of the file, and
  no newline is added to a file that had none.
- `resolve-list-warning` (test): When `tags resolve` removes a block-form tag
  inside a list, it warns with the tag's file and line.
- `resolve-refuses-bad-markup` (test): When a file's markup does not parse,
  `tags resolve` and `tags strip` write no file and name the fault.

## need answer-in-document: Answer questions in the document

When the author is not there to answer, they want Claude's questions written
into the documents, and the answers they write there read on the next run, so
a run can finish without them.

Source: update-prose-config's step 6 and its description, "to tag passages
for a style pass". The owner confirmed the need in the ruling on #132.

- `question-inserted` (test): When update-prose-config inserts a `<q>`, `tags
  insert` writes it on its own line before the line given, numbered one past
  the highest question id in scope.
- `question-not-in-structure` (test): When a `<q>` would land inside a code
  fence, a table, front matter or a blockquote, `tags insert` refuses it.
- `answers-read` (test): When an `<a>` follows a `<q>` before any other `<q>`,
  `evidence` reports it as that question's answer, and reports a `<q>` with
  none as open.
- `evidence-token` (test): When `evidence` finds no fault in the markup, it
  prints a token, as `data.token` and as its last line, and otherwise prints
  none.
- `insert-needs-token` (test): When the token passed to `tags insert` is not
  the one `evidence` would print for the tree as it is now, the command
  refuses the batch and writes nothing.
- `tags-one-batch` (step): When update-prose-config inserts markup, it passes
  every tag of the run to one `tags insert` call, with the token `evidence`
  printed.

## need abandon-a-run: Give up a run and get the documents back

When the author gives up a run partway, they want every tag removed and the
tagged edits reverted in one command, so the documents are as they were before
the run.

Source: update-prose-config's "Abandoning a run", and DESIGN.md, under "The
round trip". The owner confirmed the need in the ruling on #132.

- `strip-reverts` (test): When `tags strip` runs, every tag is removed,
  `<del>` text stays, `<ins>` text goes, and every blank line is kept.
- `insert-strip-round-trip` (test): When `tags strip` follows a `tags insert`
  batch, every file is byte-identical to what it was before the insert.

## need checkable-reports: Check a report against the rule it names

When Claude reports a passage that breaks a rule, the user wants the report to
name the rule by a short id that says what it means, so they can find the rule
and check the report themselves.

Source: README.md, under "What it adds to your project", and the
update-prose-config description.

- `finding-rule-defined` (test): When a finding names a rule `prose-style.md`
  does not define, `report` and `apply` refuse it.
- `pattern-rules-named` (test): When `report` runs, it names the rules it
  checked by pattern, and says every other rule was checked by reading.
- `one-rule-per-finding` (step): When a passage breaks two rules, apply-prose
  writes two findings, one for each rule.

## need approve-before-rewrite: Approve each rewrite before it is made

When the user asks Claude to apply the house style, they want a list of every
passage that breaks a rule, with its file, line, rule id and proposed rewrite,
and want nothing changed until they approve all of it or a part, so no
document changes in a way they did not see.

Source: README.md, under "Checking your documents", and the apply-prose
description.

- `finding-by-text` (test): When a finding gives its text, `report` and
  `apply` look for it among the places that start on its line, and refuse it
  when it starts at none of them, or at more than one and no `col_start` says
  which.
- `wrapped-finding` (test): When a finding's text holds a newline, `report`
  shows it whole and `apply` rewrites the span as one finding, keeping a
  newline its rewrite carries.
- `stale-finding-refused` (test): When a finding's text no longer matches its
  file, or its line or its file does not exist, `report` and `apply` refuse it
  and name it by its place in the batch.
- `report-reads-file` (test): When `report` prints a finding, it shows the
  text at the finding's place in the file as it is now, each line between `|`
  marks, with `(cut)` for an empty rewrite, and it writes no file.
- `approval-token` (test): When `report` exits 0, it prints a token as its
  last line, and otherwise prints none.
- `apply-needs-token` (test): When the token passed to `apply` is not the one
  `report` would print for the findings, the documents they name and
  `prose-style.md` as they are now, `apply` refuses the batch and writes
  nothing.
- `apply-writes-approved` (test): When `apply` runs with a current token, it
  writes each selected finding's rewrite in place, and reports the edits per
  file and per rule.
- `apply-filters` (test): When `apply` is given `--only`, `--file` or both, it
  writes only the findings that pass every filter given, and with none it
  writes every finding.
- `filter-matches-nothing` (test): When a filter given to `apply` matches no
  finding, alone or with the other filter, `apply` names it and writes
  nothing.
- `overlaps-named` (test): When two findings overlap, `report` and `apply`
  name both, and `apply` writes neither.
- `edits-one-snapshot` (test): When `apply` writes several findings to one
  file, it plans them against one snapshot of it, so the result does not
  depend on the order they came in.
- `unreadable-findings-stop` (test): When the findings file cannot be read,
  or is not JSON, `report` and `apply` name the fault and exit 2.
- `findings-help` (test): When `apply --help` runs, it describes every field
  of a finding, and where a rewrite may hold a newline.
- `pattern-lines-read` (test): When a rule carries `**Pattern.**` lines,
  `config` reads every one, fenced in one or two backticks, and lists them
  with the rule.
- `pattern-lint` (test): When a pattern cannot run, matches its rule's After
  example or finds nothing in its Before example, `config lint` names it and
  exits 1. A rule with no example leaves its patterns unchecked.
- `patterns-find-matches` (test): When a rule carries a pattern, `patterns`
  prints each place it matches in the segments' spans once, with its address,
  its rule and its text as a JSON string that `apply` accepts as a finding's
  `text`, including a match that wraps within a passage. It leaves out a
  match in a code span, and one made only of a line break.
- `patterns-refuse-unlinted` (test): When `prose-style.md` does not lint
  clean, `patterns` and `report` name the fault and exit 1 before reading any
  document.
- `uncovered-match-fails` (test): When a pattern matches text in a file in
  scope that no finding or dismissal of the same rule contains, `report`
  names the match and exits 1.
- `dismissal-kept` (test): When a finding carries `dismiss`, `report` prints
  its reason and `apply` leaves its text alone. A dismissal with no reason, or
  with a `replacement`, is refused.
- `patterns-judged` (step): When `patterns` prints a match, apply-prose makes
  it a finding or a dismissal, and never searches the prose with a command of
  its own.
- `report-shown-whole` (step): When `report` exits 0, apply-prose shows its
  output to the author as it stands, and takes one decision over the whole
  set, a set of rule ids or a set of files, with the side of each overlap that
  stays.

## need keep-the-meaning: Keep what a document says through a rewrite

When Claude rewrites a passage, the user wants its numbers, names, dates and
claims kept as they are, so a style pass changes how a sentence reads and never
what it says.

Source: README.md, under "Checking your documents".

- `facts-kept` (step): When apply-prose writes a finding, its rewrite changes
  how the sentence reads, and keeps its numbers, names, dates and claims.

## need leave-non-prose: Leave what is not prose alone

When the user applies the house style, they want only the document's own
prose checked and rewritten, never its code, front matter, comments, a table's
structure or someone else's words, so a style pass cannot break what is not
prose.

Source: the apply-prose description. The owner confirmed the need in the
ruling on #133.

- `segments-prose-only` (test): When `segments` or `patterns` reads a file,
  it gives headings and table cells, and leaves out front matter, fences,
  blockquotes, HTML comments and a table's delimiter row.
- `comment-cut-out` (test): When an HTML comment opens part way along a line
  of prose, `segments` gives the prose either side as separate segments. A
  comment that never closes is read as prose.
- `segment-lines` (test): When `segments` prints, it gives one line per
  segment, with its address, its kind and its text.
- `list-items-mapped` (test): When a line continues a list item, by its
  indent or lazily, `segments` reports it as the item's, and a paragraph after
  the list as a paragraph.
- `refuse-non-prose` (test): When a finding reaches a protected line, touches
  an HTML comment, or crosses a line that is not part of a paragraph or a list
  item, `report` and `apply` refuse it, with or without `--partial`.
- `structure-kept` (test): When a rewrite would put a `|` or a newline in a
  table cell, or a newline in a line it does not already cross outside a
  paragraph, `apply` refuses it.
- `list-item-indent` (test): When a rewrite in a list item holds a newline,
  `apply` indents each new line to the item's text, unless it is indented that
  far already.
- `cut-leaves-one-blank` (test): When findings cut whole lines, `apply`
  removes them with their newlines, leaves one blank line between the blocks
  either side and none at either end of the file, and keeps a line that also
  takes a rewrite.
- `read-segments-only` (step): When apply-prose judges whether prose
  conforms, it reads only what `segments` returns, never the raw file.

## need one-pass-at-a-time: Keep teaching and applying apart

When the user is partway through teaching the style, they want apply-prose to
wait, so rewrites to documents still being edited do not tangle the two sets
of changes.

Source: README.md, under "Checking your documents", and the apply-prose
description.

- `apply-waits-for-teaching` (step): When apply-prose starts, it runs
  `preflight --for apply`, and stops on markup in a governed file or an
  uncommitted governed document.

## need choose-checked-files: Decide which files are checked

When the user applies the house style, they want the `scope:` list in
`prose-style.md` to decide which files are checked, and Claude to explain why a
file was skipped, so the check covers the documents they meant.

Source: README.md, under "Checking your documents", and the apply-prose
description.

- `scope-by-default` (test): When `segments` or `patterns` is given no file,
  it reads every file in scope, and names a file given that does not exist.

## need start-from-defaults: Start a rules file without writing one

When the user first runs update-prose-config in a project, they want to start
the rules file from the default set the plugin ships, from another project's
rules or from an empty file, so the first rules need not be written from
nothing.

Source: README.md, under "Setting up".

- `shipped-patterns` (test): When a project starts from the shipped rules,
  they lint clean, and their patterns find a British spelling and a dash doing
  an em-dash's job, and leave a US spelling alone.

## need share-rules: Copy rules from another project

When the user wants another project's prose rules, they want the rules this
project lacks copied across, and the rules that collide on an id or say the
same thing under two ids shown side by side in one round, so they settle each
conflict once.

Source: README.md, under "Sharing rules between projects", and the adopt-prose
description. The 0.6 score at which two rules count as similar is the owner's,
in the ruling on #131.

- `classify-new` (test): When the target has no rule with a source rule's id,
  and no target rule scores 0.6 or more against it, `config classify` puts it
  in `new`.
- `classify-identical` (test): When a target rule has a source rule's id, and
  their bodies match once HTML comments are dropped and whitespace is
  collapsed, `config classify` puts the source rule in `identical`.
- `classify-colliding` (test): When a target rule has a source rule's id and
  the bodies differ, `config classify` puts the source rule in `colliding`.
- `classify-similar` (test): When the target has no rule with a source rule's
  id, and a target rule scores 0.6 or more against it, `config classify` puts
  it in `similar` and lists each such target rule as a candidate.
- `similarity-score` (test): When `config classify` scores two rules, the
  score is the higher of how alike their bodies are and how many words their
  names share.
- `classify-id-first` (test): When a target rule has a source rule's id,
  `config classify` settles it as identical or colliding and lists no
  candidates.
- `missing-file-stops` (test): When the file given to `--to` does not exist,
  `config classify` and `config adopt` name it and exit 2.
- `reread-new-rules` (step): When `config classify` puts a rule in `new`,
  adopt-prose reads it against the target and treats it as similar if it
  states a target rule's point in other words.
- `adopt-passes-new` (step): When rules remain in `new`, adopt-prose passes
  each to `config adopt` as its own `--rule`.
- `adopt-byte-for-byte` (test): When `config adopt` copies a rule, the target
  gets the rule's lines as the source has them, with only its metadata
  comment replaced.
- `adopt-placement` (test): When `config adopt` copies a rule, it puts it
  after the target's last rule from the same section, or failing that under
  the target's `##` heading matching the source's, or failing that at the end
  under a new copy of that heading.
- `adopt-source-order` (test): When `config adopt` puts several rules in one
  place, they keep the source's order.
- `adopt-lints-clean` (test): When `config adopt` writes, the target still
  lints clean.
- `adopt-refuses-collision` (test): When the target already has an id passed
  to `config adopt`, the command refuses it as a collision.
- `adopt-refuses-unknown` (test): When the source has no rule with an id
  passed to `config adopt`, or the id is passed twice, the command refuses
  it.
- `adopt-refuses-unlinted` (test): When the source or the target does not
  lint clean, `config adopt` names the lint command and exits 2.
- `conflicts-one-round` (step): When the classification leaves colliding or
  similar rules, adopt-prose puts every pair to the author in one round,
  with both bodies in full.
- `resolved-keeps-target-id` (step): When the author settles a pair with a
  combination or a rewrite, the resulting rule keeps the target's id.

## need promote-shipped-rule: Ship a rule with the plugin

When the owner finds a rule worth having in every project, they want to add it
to the rules prose-tuning ships, so every new `prose-style.md` starts with it.

Source: the adopt-prose description.

- `fill-marker-ignored` (test): When two rules differ only by a `FILL`
  marker, `config classify` treats their bodies as the same.
- `promote-obligations` (step): When the target is the shipped rules,
  adopt-prose bumps prose-tuning's version in both manifests, says that
  projects already started from the shipped rules now differ, and replaces a
  project's own example with a `FILL` marker.

## need review-then-commit: Commit each change the user's usual way

When a skill finishes, the user wants its changes left uncommitted, so they
review and commit them their usual way.

Source: README.md, under "What it adds to your project", and all three skill
descriptions.

- `learning-never-commits` (step): When update-prose-config finishes, it
  reports what changed and which files are dirty, and commits nothing.
- `apply-never-commits` (step): When apply-prose finishes, it shows `apply`'s
  output to the author and commits nothing.

## need works-in-cowork: Use the same skills in Cowork

When the user works in a Cowork Project, they want the skills they have in
Claude Code, installed from the same marketplace, so one house style serves
both.

Source: README.md, the opening section and "Setting up".

## constraint cowork-rules-partial: Cowork does not always load .claude/rules/

Cowork leaves `.claude/rules/` out of some parts of a conversation, so the
rules need a line in the project's Instructions field to reach every part.

Source: README.md, under "Setting up".

## constraint edits-in-git: The pending edits are read from git

The plugin finds the user's pending prose edits in git, as the staged and
uncommitted changes against the last commit, so a project has to be tracked by
git.

Source: the owner's review of #139, and README.md, under "When to use it".

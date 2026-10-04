# prose-tuning

This file records what the prose-tuning plugin is for. SPEC-METHODOLOGY.md, at
the repo root, has the grammar of this file and the steps that add its
requirements.

## Out of scope

- Writing outside the project repo a skill was invoked in.
- A single edit to a single document, which the user asks Claude for
  directly.
- Putting a project under git, which gitify-cowork-project does.
- Finding edits in a separate clone of the repo. Git lists only the worktrees
  that share one `.git`.

## need user-keeps-corrections: Keep a correction past the conversation

When the user keeps correcting the same things in what Claude writes in a
project, they want each correction kept as a written rule that every later
conversation there reads, so the next conversation does not repeat the
mistake.

Source: README.md, under "When to use it" and "What it adds to your project".

- `lint-cmd-refuses-paths-key` (test): When the front matter of
  `prose-style.md` carries a `paths:` key, `config lint` refuses it.
- `lint-cmd-accepts-any-source` (test): When a rule's `prose-rule` comment
  carries `source=` with any value, `config lint` accepts it.
- `lint-cmd-names-unknown-keys` (test): When a rule's `prose-rule` comment
  carries a key other than `origin` or `source`, `config lint` names it and
  exits 1.

## need user-teaches-by-editing: Teach the style by editing

When the user has edited documents the way they want them to read, they want
Claude to work out the rules behind the uncommitted edits and write them into
`prose-style.md`, so the user teaches the style by editing rather than by
writing rules.

Source: README.md, the opening section and "Teaching it your style", and the
update-prose-config description. The two occurrences that make a candidate a
rule are the owner's figure, in the ruling on #132.

- `evidence-cmd-reports-inferred-hunks` (test): When the author has edited
  a file in scope without markup, `evidence` reports each changed run of lines
  since the last commit as one inferred record, with its lines before and
  after.
- `evidence-cmd-diffs-without-markup` (test): When a file holds markup,
  `evidence` diffs it with the markup taken out, and numbers each hunk by its
  line in the working file.
- `evidence-cmd-reports-explicit-records` (test): When a file holds the
  author's `<ins>`, `<del>` or `<repl>`, `evidence` reports each as an
  explicit record with its old and new text, and the `why` and `<alt>` it
  carries.
- `evidence-cmd-marks-hunk-signals` (test): When an inferred hunk changed
  only numbers, only link targets or only whitespace, `evidence` marks it
  `numeric-only`, `link-only` or `whitespace-only`.
- `evidence-cmd-skips-comment-hunks` (test): When an inferred hunk changed
  only HTML comments, `evidence` leaves it out.
- `updateproseconfig-asks-about-signals` (step): When a hunk carries a signal,
  update-prose-config takes it to the interview and never straight into a
  rule.
- `updateproseconfig-makes-rules-at-threshold` (step): When a candidate occurs
  two or more times independently, carries a `why` or an `<alt>`, or is
  settled by an answered question, update-prose-config makes it a rule, and
  anything else a question.
- `reproduce-cmd-matches-changed-text` (test): When `reproduce` runs, it
  reports each edit since the last commit as reproduced when a rule's pattern,
  run over the file as it was at the last commit, matches text the edit
  changed. A pure insertion is never reproduced.
- `reproduce-cmd-skips-comment-edits` (test): When an edit changed only HTML
  comments, `reproduce` leaves it out.
- `reproduce-cmd-lists-unpatterned-rules` (test): When `reproduce` runs,
  it lists by id every rule with no pattern.
- `reproduce-cmd-refuses-unlinted-rules` (test): When `prose-style.md`
  does not lint clean, `reproduce` names the fault and exits 1 before reading
  any file.
- `updateproseconfig-fixes-the-rule` (step): When an edit is not reproduced by any
  pattern, and not accounted for by any unpatterned rule, update-prose-config fixes
  the rule rather than the document.
- `preflight-cmd-checks-before-teaching` (test): When `preflight --for
  config` runs, it exits 1 on markup that does not parse or a `prose-style.md`
  with errors.
- `list-cmd-gives-every-rule` (test): When `config list --json` runs, it
  gives every rule in `prose-style.md` with its id, its title and its worked
  example.
- `lint-cmd-checks-rule-shape` (test): When a rule has no body, half a
  worked example or the id of another rule, `config lint` names it and exits
  1, and it warns on a rule with no example.
- `updateproseconfig-writes-through-cmd` (step): When the author approves
  rules, update-prose-config hands them to `config write` in one batch and does
  not edit `prose-style.md` itself.
- `write-cmd-writes-from-data` (test): When `config write --batch` is given
  new rules and rewrites as JSON, it writes each in the format
  `prose-style.md` requires, or refuses the record and names it by its place
  and id.
- `write-cmd-lints-clean` (test): When `config write` writes rules,
  `prose-style.md` still lints clean. A record whose rule would not lint is
  refused, and a file that does not lint clean is not written to at all.
- `write-cmd-writes-all-or-none` (test): When `config write` refuses any
  record, it writes nothing unless `--partial` is passed. Given `--dry-run`,
  it reports what it would write and writes nothing.
- `write-cmd-places-by-section` (test): When `config write` adds a rule, it
  puts it after the last rule of its section. A rule in a section the file
  does not have goes at the end under the `##` heading its record gives, and
  without one it is refused.
- `write-cmd-keeps-unnamed-parts` (test): When `config write` rewrites a
  rule, it replaces the title, body, example or patterns the record gives and
  keeps the rest.
- `write-cmd-refuses-stale` (test): When a rewrite's `expect` is not the
  rule's body as the file holds it now, or the file has no rule with its id,
  `config write` refuses it.

## need user-answers-in-one-round: Answer every open question at once

When Claude cannot tell the reason for an edit, the user wants every such
question asked in one round, so learning the rules takes a single exchange.

Source: README.md, under "Teaching it your style", step 3, and the
update-prose-config description.

- `updateproseconfig-asks-in-one-batch` (step): When update-prose-config has
  open questions, it puts all of them to the author in one `AskUserQuestion`
  call, with every hunk that carries a signal asked as one question.

## need user-explains-edits-in-place: Say why an edit was made, in the document

When an edit needs explaining, the user wants to mark it in the document
itself, with markup a markdown preview shows as an edit, and wants Claude to
remove the markup once the rules are written, so none of it reaches a commit.

Source: README.md, under "Teaching it your style", and the update-prose-config
description.

- `scanner-names-markup-faults` (test): When markup breaks the grammar in
  `reference/tag-vocabulary.md`, the scanner reports each fault once, with its
  file and line.
- `scanner-ignores-tags-in-code` (test): When a tag sits inside a code fence
  or a code span, the scanner reads it as prose.
- `scanner-pairs-del-and-ins` (test): When a `<del>` is followed directly by an
  `<ins>`, the scanner and `evidence` read the pair as one replacement.
- `resolve-cmd-accepts-edits` (test): When `tags resolve` runs, `<ins>`
  text stays, `<del>` text goes, `<repl>` keeps its replacement, and every tag
  is removed.
- `resolve-cmd-tidies-cuts` (test): When a resolved cut removes whole
  paragraphs, one blank line is left where they were, none at either end of
  the file, and no newline is added to a file that had none.
- `resolve-cmd-warns-in-lists` (test): When `tags resolve` removes a
  block-form tag inside a list, it warns with the tag's file and line.
- `resolve-cmd-refuses-bad-markup` (test): When a file's markup does not
  parse, `tags resolve` and `tags strip` do not write a file, and name the fault.

## need user-answers-in-document: Answer questions in the document

When the author is not there to answer, they want Claude's questions written
into the documents, and the answers they write there read on the next run, so
a run can finish without them.

Source: update-prose-config's step 6 and its description, "to tag passages
for a style pass". The owner confirmed the need in the ruling on #132.

- `insert-cmd-places-questions` (test): When update-prose-config inserts a
  `<q>`, `tags insert` writes it on its own line before the line given,
  numbered one past the highest question id in scope.
- `insert-cmd-refuses-questions-in-structure` (test): When a `<q>` would
  land inside a code fence, a table, front matter or a blockquote, `tags
  insert` refuses it.
- `evidence-cmd-reads-answers` (test): When an `<a>` follows a `<q>`
  before any other `<q>`, `evidence` reports it as that question's answer, and
  reports a `<q>` with none as open.
- `evidence-cmd-prints-token` (test): When `evidence` does not find a fault in
  the markup, it prints a token, as `data.token` and as its last line, and
  otherwise prints none.
- `insert-cmd-requires-token` (test): When the token passed to `tags
  insert --token` is not the one `evidence` would print for the tree as it is
  now, the command refuses the batch and writes nothing.
- `updateproseconfig-inserts-in-one-batch` (step): When update-prose-config
  inserts markup, it passes every tag of the run to one `tags insert --batch`
  call, with the token `evidence` printed.

## need user-abandons-a-run: Give up a run and get the documents back

When the author gives up a run partway, they want every tag removed and the
tagged edits reverted in one command, so the documents are as they were before
the run.

Source: update-prose-config's "Abandoning a run", and DESIGN.md, under "The
round trip". The owner confirmed the need in the ruling on #132.

- `strip-cmd-reverts-tagged-edits` (test): When `tags strip` runs, every
  tag is removed, `<del>` text stays, `<ins>` text goes, and every blank line
  is kept.
- `strip-cmd-undoes-insert` (test): When `tags strip` follows a `tags
  insert` batch, every file is byte-identical to what it was before the
  insert.
- `restore-cmd-writes-last-commit` (test): When `restore --file` runs, it
  writes the file as it is at the last commit, and names a file the last
  commit does not hold.

## need user-checks-reports: Check a report against the rule it names

When Claude reports a passage that breaks a rule, the user wants the report to
name the rule by a short id that says what it means, so they can find the rule
and check the report themselves.

Source: README.md, under "What it adds to your project", and the
update-prose-config description.

- `report-cmd-refuses-undefined-rules` (test): When a finding names a rule
  `prose-style.md` does not define, `report` and `apply` refuse it.
- `report-cmd-names-pattern-rules` (test): When `report` runs, it names
  the rules it checked by pattern, and says every other rule was checked by
  reading.
- `applyprose-splits-findings-by-rule` (step): When a passage breaks two
  rules, apply-prose writes two findings, one for each rule.
- `lint-cmd-checks-id-grammar` (test): When a rule's id is not a
  lower-case section word and a name of one to four lower-case words, none
  starting with a digit, `config lint` names it once and exits 1. A name that
  repeats its section is a warning.
- `checkid-cmd-vets-new-ids` (test): When `config check-id` is given
  `--section` and `--name`, it prints the id when it is well formed and free,
  and otherwise names the fault and exits 1.
- `write-cmd-vets-new-names` (test): When a new rule given to `config write`
  has a malformed name or one already taken, the command refuses it.

## need user-approves-each-rewrite: Approve each rewrite before it is made

When the user asks Claude to apply the house style, they want a list of every
passage that breaks a rule, with its file, line, rule id and proposed rewrite,
and want nothing changed until they approve all of it or a part, so no
document changes in a way they did not see.

Source: README.md, under "Checking your documents", and the apply-prose
description.

- `report-cmd-locates-findings-by-text` (test): When a finding gives its
  text, `report` and `apply` look for it among the places that start on its
  line, and refuse it when it starts at none of them, or at more than one and
  no `col_start` says which.
- `apply-cmd-rewrites-wrapped-findings` (test): When a finding's text
  holds a newline, `report` shows it whole and `apply` rewrites the span as
  one finding, keeping a newline its rewrite carries.
- `report-cmd-refuses-stale-findings` (test): When a finding's text no
  longer matches its file, or its line or its file does not exist, `report`
  and `apply` refuse it and name it by its place in the batch.
- `report-cmd-shows-current-text` (test): When `report` prints a finding,
  it shows the text at the finding's place in the file as it is now, each line
  between `|` marks, with `(cut)` for an empty rewrite, and it does not write a file.
- `report-cmd-prints-approval-token` (test): When `report` exits 0, it
  prints a token as its last line, and otherwise prints none.
- `apply-cmd-requires-token` (test): When the token passed to `apply
  --token` is not the one `report` would print for the findings, the documents
  they name and `prose-style.md` as they are now, `apply` refuses the batch
  and writes nothing.
- `apply-cmd-writes-approved` (test): When `apply` runs with a current
  token, it writes each selected finding's rewrite in place, and reports the
  edits per file and per rule.
- `apply-cmd-obeys-filters` (test): When `apply` is given `--only`,
  `--file` or both, it writes only the findings that pass every filter given,
  and with none it writes every finding.
- `apply-cmd-names-empty-filters` (test): When a filter given to `apply`
  does not match any finding, alone or with the other filter, `apply` names it and
  writes nothing.
- `report-cmd-names-overlaps` (test): When two findings overlap, `report`
  and `apply` name both, and `apply` writes neither.
- `apply-cmd-plans-one-snapshot` (test): When `apply` writes several
  findings to one file, it plans them against one snapshot of it, so the
  result does not depend on the order they came in.
- `report-cmd-stops-on-unreadable-findings` (test): When the file given to
  `--findings` cannot be read, or is not JSON, `report` and `apply` name the
  fault and exit 2.
- `apply-cmd-describes-finding-fields` (test): When `apply --help` runs,
  it describes every field of a finding, and where a rewrite may hold a
  newline.
- `config-cmd-reads-pattern-lines` (test): When a rule carries
  `**Pattern.**` lines, `config` reads every one, fenced in one or two
  backticks, and lists them with the rule.
- `lint-cmd-checks-patterns` (test): When a pattern cannot run, matches
  its rule's After example or finds nothing in its Before example, `config
  lint` names it and exits 1. A rule with no example leaves its patterns
  unchecked.
- `patterns-cmd-prints-each-match` (test): When a rule carries a pattern,
  `patterns` prints each place it matches in the segments' spans once, with
  its address, its rule and its text as a JSON string that `apply` accepts as
  a finding's `text`, including a match that wraps within a passage. It leaves
  out a match in a code span, and one made only of a line break.
- `patterns-cmd-refuses-unlinted-rules` (test): When `prose-style.md` does
  not lint clean, `patterns` and `report` name the fault and exit 1 before
  reading any document.
- `report-cmd-fails-uncovered-matches` (test): When a pattern matches text
  in a file in scope that no finding or dismissal of the same rule contains,
  `report` names the match and exits 1.
- `apply-cmd-honors-dismissals` (test): When a finding carries `dismiss`,
  `report` prints its reason and `apply` leaves its text alone. A dismissal
  with no reason, or with a `replacement`, is refused.
- `applyprose-judges-each-match` (step): When `patterns` prints a match,
  apply-prose makes it a finding or a dismissal, and never searches the prose
  with a command of its own.
- `applyprose-shows-report-whole` (step): When `report` exits 0, apply-prose
  shows its output to the author as it stands, and takes one decision over the
  whole set, a set of rule ids or a set of files, with the side of each
  overlap that stays.

## need user-keeps-document-meaning: Keep what a document says through a rewrite

When Claude rewrites a passage, the user wants its numbers, names, dates and
claims kept as they are, so a style pass changes how a sentence reads and never
what it says.

Source: README.md, under "Checking your documents".

- `applyprose-keeps-facts` (step): When apply-prose writes a finding, its
  rewrite changes how the sentence reads, and keeps its numbers, names, dates
  and claims.

## need user-protects-non-prose: Leave what is not prose alone

When the user applies the house style, they want only the document's own
prose checked and rewritten, never its code, front matter, comments, a table's
structure or someone else's words, so a style pass cannot break what is not
prose.

Source: the apply-prose description. The owner confirmed the need in the
ruling on #133.

- `segments-cmd-gives-prose-only` (test): When `segments` or `patterns`
  reads a file, it gives headings and table cells, and leaves out front
  matter, fences, blockquotes, HTML comments and a table's delimiter row.
- `segments-cmd-cuts-out-comments` (test): When an HTML comment opens part
  way along a line of prose, `segments` gives the prose either side as
  separate segments. A comment that never closes is read as prose.
- `segments-cmd-prints-one-line-each` (test): When `segments` prints, it
  gives one line per segment, with its address, its kind and its text.
- `segments-cmd-maps-list-items` (test): When a line continues a list
  item, by its indent or lazily, `segments` reports it as the item's, and a
  paragraph after the list as a paragraph.
- `apply-cmd-refuses-non-prose` (test): When a finding reaches a protected
  line, touches an HTML comment, or crosses a line that is not part of a
  paragraph or a list item, `report` and `apply` refuse it, with or without
  `--partial`.
- `apply-cmd-keeps-table-structure` (test): When a rewrite would put a `|`
  or a newline in a table cell, or a newline in a line it does not already
  cross outside a paragraph, `apply` refuses it.
- `apply-cmd-indents-list-items` (test): When a rewrite in a list item
  holds a newline, `apply` indents each new line to the item's text, unless it
  is indented that far already.
- `apply-cmd-leaves-one-blank-line` (test): When findings cut whole lines,
  `apply` removes them with their newlines, leaves one blank line between the
  blocks either side and none at either end of the file, and keeps a line that
  also takes a rewrite.
- `applyprose-reads-segments-only` (step): When apply-prose judges whether
  prose conforms, it reads only what `segments` returns, never the raw file.
- `script-keeps-every-byte` (test): When the script reads a file into lines and
  writes it back, every byte (including line endings) comes back as it was.

## need user-finishes-teaching-first: Keep teaching and applying apart

When the user is partway through teaching the style, they want apply-prose to
wait, so rewrites to documents still being edited do not tangle the two sets
of changes.

Source: README.md, under "Checking your documents", and the apply-prose
description.

- `applyprose-waits-for-teaching` (step): When apply-prose starts, it runs
  `preflight --for apply`, and stops on markup in a governed file or an
  uncommitted governed document.
- `preflight-cmd-blocks-apply-mid-teaching` (test): When `preflight --for
  apply` runs, it exits 1 on markup in a file in scope or an uncommitted file
  in scope, and not on an uncommitted `prose-style.md`.

## need user-chooses-checked-files: Decide which files are checked

When the user applies the house style, they want the `scope:` list in
`prose-style.md` to decide which files are checked, and Claude to explain why a
file was skipped, so the check covers the documents they meant.

Source: README.md, under "Checking your documents", and the apply-prose
description.

- `segments-cmd-reads-scope-by-default` (test): When `segments` or
  `patterns` is not given a file, it reads every file in scope, and names a file
  given that does not exist.
- `lint-cmd-checks-front-matter` (test): When the front matter holds
  anything but `key: value` pairs and one `scope:` block of `include:` and
  `exclude:` lists, or is not opened and closed by `---`, `config lint` names
  the line and exits 1.
- `scope-cmd-honors-include-and-exclude` (test): When the front matter
  carries a `scope:` block, its `include` and `exclude` lists decide which
  markdown files are in scope.
- `glob-matches-whole-path` (test): When a scope pattern is matched, `**/`
  matches any number of folders, `**` anything, `*` anything within one
  folder and `?` one character, against the whole path from the project root.
- `scope-cmd-never-lists-rules-file` (test): When `scope` lists the files
  in scope, it leaves out `prose-style.md` whatever the scope says.
- `scope-cmd-explains-each-file` (test): When `scope --all` runs, it lists
  every markdown file with the pattern that included or excluded it.

## need user-starts-from-defaults: Start a rules file without writing one

When the user first runs update-prose-config in a project, they want to start
the rules file from the default set the plugin ships, from another project's
rules or from an empty file, so the first rules need not be written from
nothing.

Source: README.md, under "Setting up".

- `template-catches-spelling-and-dashes` (test): When a project starts from
  the shipped rules, they lint clean, and their patterns find a British
  spelling and a dash doing an em-dash's job, and leave a US spelling alone.
- `init-cmd-writes-shipped-rules` (test): When `config init` runs with no
  option, it writes the shipped rules to `.claude/rules/prose-style.md`,
  creating the folder, with the project's name where the rules leave a slot,
  and the file lints clean.
- `init-cmd-finds-project-name` (test): When `config init` names the
  project, it uses the folder of the main working tree from any worktree, and
  the name of a bare repository without its `.git`.
- `init-cmd-copies-or-starts-empty` (test): When `config init` is given
  `--from`, it copies that file, and given `--empty`, it writes a skeleton
  with no rules. It refuses both together, and names a `--from` file that does
  not exist.
- `init-cmd-never-overwrites` (test): When `.claude/rules/prose-style.md`
  exists, `config init` refuses and leaves it as it was.
- `preflight-cmd-points-to-init` (test): When a project has no
  `prose-style.md`, `preflight --for apply` and every `config` command but
  `init` stop and name `config init`.

## need user-shares-rules: Copy rules from another project

When the user wants another project's prose rules, they want the rules this
project lacks copied across, and the rules that collide on an id or say the
same thing under two ids shown side by side in one round, so they settle each
conflict once.

Source: README.md, under "Sharing rules between projects", and the adopt-prose
description. The 0.6 score at which two rules count as similar is the owner's,
in the ruling on #131.

- `classify-cmd-finds-new-rules` (test): When the target has no rule with
  a source rule's id, and no target rule scores 0.6 or more against it,
  `config classify` puts it in `new`.
- `classify-cmd-finds-identical-rules` (test): When a target rule has a
  source rule's id, and their bodies match once HTML comments are dropped and
  whitespace is collapsed, `config classify` puts the source rule in
  `identical`.
- `classify-cmd-finds-colliding-rules` (test): When a target rule has a
  source rule's id and the bodies differ, `config classify` puts the source
  rule in `colliding`.
- `classify-cmd-finds-similar-rules` (test): When the target has no rule
  with a source rule's id, and a target rule scores 0.6 or more against it,
  `config classify` puts it in `similar` and lists each such target rule as a
  candidate.
- `classify-cmd-scores-similarity` (test): When `config classify` scores
  two rules, the score is the higher of how alike their bodies are and how
  many words their names share.
- `classify-cmd-settles-ids-first` (test): When a target rule has a source
  rule's id, `config classify` settles it as identical or colliding and does not list
  any candidates.
- `classify-cmd-names-missing-target` (test): When the file given to
  `--to` does not exist, `config classify` and `config adopt` name it and exit
  2.
- `adoptprose-rereads-new-rules` (step): When `config classify` puts a rule in
  `new`, adopt-prose reads it against the target and treats it as similar if
  it states a target rule's point in other words.
- `adoptprose-passes-each-new-rule` (step): When rules remain in `new`,
  adopt-prose passes each to `config adopt` as its own `--rule`.
- `adopt-cmd-copies-byte-for-byte` (test): When `config adopt` copies a
  rule, the target gets the rule's lines as the source has them, less any
  `prose-rule` comment.
- `adopt-cmd-places-by-section` (test): When `config adopt` copies a rule,
  it puts it after the target's last rule from the same section, or failing
  that under the target's `##` heading matching the source's, or failing that
  at the end under a new copy of that heading.
- `adopt-cmd-keeps-source-order` (test): When `config adopt` puts several
  rules in one place, they keep the source's order.
- `adopt-cmd-lints-clean` (test): When `config adopt` writes, the target
  still lints clean.
- `adopt-cmd-refuses-collision` (test): When the target already has an id
  passed to `config adopt`, the command refuses it as a collision.
- `adopt-cmd-refuses-unknown` (test): When the source has no rule with an
  id passed to `config adopt`, or the id is passed twice, the command refuses
  it.
- `adopt-cmd-refuses-unlinted` (test): When the source or the target does
  not lint clean, `config adopt` names the lint command and exits 2.
- `adoptprose-shows-conflicts-once` (step): When the classification leaves
  colliding or similar rules, adopt-prose puts every pair to the author in one
  round, with both bodies in full.
- `adoptprose-keeps-target-id` (step): When the author settles a pair with a
  combination or a rewrite, the resulting rule keeps the target's id.

## need owner-ships-a-rule: Ship a rule with the plugin

When the owner finds a rule worth having in every project, they want to add it
to the rules prose-tuning ships, so every new `prose-style.md` starts with it.

Source: the adopt-prose description.

- `classify-cmd-ignores-fill-markers` (test): When two rules differ only
  by a `FILL` marker, `config classify` treats their bodies as the same.
- `adoptprose-bumps-shipped-version` (step): When the target is the shipped
  rules, adopt-prose bumps prose-tuning's version in both manifests, says that
  projects already started from the shipped rules now differ, and replaces a
  project's own example with a `FILL` marker.

## need user-reviews-then-commits: Commit each change the user's usual way

When a skill finishes, the user wants its changes left uncommitted, so they
review and commit them their usual way.

Source: README.md, under "What it adds to your project", and all three skill
descriptions.

- `adopt-cmd-gives-commit-note` (test): When `config adopt` writes, it
  gives a commit note naming the source's project, or its path outside a
  repository, and each id adopted.
- `adoptprose-never-commits` (step): When adopt-prose finishes, it reports what
  changed, gives the author `config adopt`'s commit note for their commit
  description, and commits nothing.
- `updateproseconfig-never-commits` (step): When update-prose-config finishes,
  it reports what changed and which files are dirty, and commits nothing.
- `applyprose-never-commits` (step): When apply-prose finishes, it shows
  `apply`'s output to the author and commits nothing.
- `setup-cmd-ignores-its-copy` (test): When `setup` or `stage` writes the
  copy of the script, a `.gitignore` of `*` beside it keeps the copy out of
  the project's commits, and `preflight` exits 1 on a copy git would commit.

## need user-works-in-cowork: Use the same skills in Cowork

When the user works in a Cowork Project, they want the skills they have in
Claude Code, installed from the same marketplace, so one house style serves
both.

Source: README.md, the opening section and "Setting up".

- `setup-cmd-names-its-surface` (test): When `setup` runs inside Cowork's
  container, it reports `cowork` and copies nothing, and anywhere else it
  reports `local`.
- `stage-cmd-copies-for-device` (test): When `stage` runs, it writes
  byte-identical copies of the script, its `.gitignore` and the shipped rules,
  and gives `device_commit_files` a path for each under the project folder.
- `stage-cmd-gives-checksum-command` (test): When `stage` runs, it gives a
  command that checks every staged file's checksum from the project's folder
  on the device, and a prefix that starts every device command there.
- `stage-cmd-checks-folder-paths` (test): When `--folder` or `--connected`
  is not an absolute path, or `--folder` sits outside `--connected`, `stage`
  names it and exits 2.
- `init-cmd-reads-staged-rules` (test): When the script runs from its copy
  in `.prose-tuning/`, `config init` starts from the rules staged beside it,
  and never from a `templates/` folder in the project.

## need user-teaches-from-own-branch: Teach from edits made in another checkout

When the user has edited on a branch of their own in one checkout of the repo,
and runs update-prose-config from a session opened in another, they want the
skill to find those edits and finish the run where the session is, so they can
edit wherever they edit and run the skill wherever the session opens.

Run in Claude Code from the checkout that holds the edits, the skill reads
them and writes the rules there.

Run in Claude Code from a worktree the desktop app made, whose tree does not hold
any pending edits while another checkout does, the skill names that checkout. On
the author's word it copies the edits into the session's tree and writes the
rules there. The originals stay in the other checkout for the user to discard.

Run in Cowork, the skill reads the edits in the connected project folder on
the device and writes the rules there. `evidence` and `carry` run on the
device too, and read git without writing to it, so another worktree on the
device is found and copied the same way.

Source: #301, and the owner's rulings while planning it, that the run carries
the edits into the session's tree and that the design and the build land
together.

- `evidence-cmd-names-other-worktrees` (test): When this tree does not hold
  any pending edit, markup or question in scope, and another worktree of the
  repo holds pending edits, `evidence` names each such worktree with its
  branch and files, and exits 1 naming `carry --from` with its path.
- `carry-cmd-copies-pending-files` (test): When `carry --from` runs, it copies
  byte for byte each file in that worktree's scope with a pending edit, and its
  `prose-style.md` when that has one, to the same path here, and names a
  worktree that does not hold any.
- `carry-cmd-refuses-different-base` (test): When a file to be carried differs
  between the last commits of the two trees, `carry` names it and writes
  nothing.
- `carry-cmd-refuses-dirty-target` (test): When a file `carry` would write has
  uncommitted changes here, `carry` names it and writes nothing.
- `carry-cmd-refuses-unknown-worktree` (test): When `--from` is not another
  worktree of this repo, `carry` names it and exits 2.
- `carry-cmd-honors-dry-run` (test): When `carry` is given `--dry-run`, it
  lists the files it would copy and writes nothing.
- `updateproseconfig-asks-which-checkout` (step): When `evidence` names
  another worktree, update-prose-config asks the author in one
  `AskUserQuestion` which worktree to carry from, if any, listing each one's
  path, branch and files. It asks even when only one worktree is named, runs
  `carry --from` with the one picked, and gathers the evidence again.
- `updateproseconfig-names-original-checkout` (step): When a run carried
  edits, update-prose-config's hand-off names the checkout and branch that
  still hold the original edits, and leaves discarding them to the user.

## need user-teaches-by-noting: Teach the style by noting a passage

When the author, or a skill acting for them, hands update-prose-config a note
on a passage, they want the note taken as a proposed rule for the passage, or,
when the author has rewritten the passage in place, as the reason for that
edit, so a style point noted during a review reaches prose-style.md.

Source: #316, which records the owner's rulings, and CLAUDE.md, under "A
plugin knows only itself", for the hand-off convention.

- `updateproseconfig-takes-handed-notes` (step): When update-prose-config is
  handed a note on a passage that has not changed since the last commit, it
  takes the note as it takes an `<alt>` on that passage, without writing
  markup into the document.
- `updateproseconfig-reads-notes-as-whys` (step): When update-prose-config is
  handed a note on a passage that has changed since the last commit, it takes
  the note as the `why` of those changes.
- `updateproseconfig-asks-about-vague-notes` (step): When a note on an
  unchanged passage does not state a rule, update-prose-config asks about it
  in the interview.
- `updateproseconfig-runs-on-notes-alone` (step): When update-prose-config is
  handed notes and `evidence` does not find a pending edit, it writes the
  rules the notes settle rather than stopping.
- `updateproseconfig-writes-note-examples` (step): When a rule comes from a
  note on an unchanged passage, update-prose-config writes its worked example
  from that passage.

## constraint shell-starts-fresh: Each shell call starts without the last one's variables

Each Bash call in Claude Code, and each `device_bash` call on Cowork, starts a
fresh shell. The plugin's install path runs past 200 characters, too long to
repeat in every command, so a skill reaches the script by a shorter path.

Source: CLAUDE.md, under "A shell variable lasts one command", and DESIGN.md,
under "Packaging". The owner confirmed the constraint in the ruling on #134.

- `setup-cmd-copies-locally` (test): When `setup` runs outside Cowork's
  container, it copies the script and the shipped rules byte for byte into
  `.prose-tuning/`, and gives the prefix `PROSE=.prose-tuning/prose.py`,
  which reaches the copy from the project root.

## constraint cowork-loads-rules-partly: Cowork does not always load .claude/rules/

Cowork leaves `.claude/rules/` out of some parts of a conversation, so the
rules need a line in the project's Instructions field to reach every part.

Source: README.md, under "Setting up".

## constraint git-holds-pending-edits: The pending edits are read from git

The plugin finds the user's pending prose edits in git, as the staged and
uncommitted changes against the last commit, so a project has to be tracked by
git.

Source: the owner's review of #139, and README.md, under "When to use it".

- `command-requires-a-repo` (test): When a command runs outside a git
  repository, or git is not installed, it names the cause and exits 2.

## constraint worktree-guards-shared-claude: A worktree session cannot edit another checkout's .claude/

Claude Code refuses an edit from a session in a worktree the desktop app made
to the `.claude/` folder of the repo's main checkout. So a run started in such
a worktree writes `prose-style.md` in the worktree's own tree, and only reads
the checkout that holds the edits.

Source: #301, which quotes the refusal. It comes from Claude Code itself, not
from a hook in the repo or in the user's settings.

- `carry-cmd-writes-only-this-tree` (test): When `carry` runs, the worktree it
  copies from is left byte for byte as it was, and git reports the same
  changes there.

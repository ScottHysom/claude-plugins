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
update-prose-config description.

## need one-question-round: Answer every open question at once

When Claude cannot tell the reason for an edit, the user wants every such
question asked in one round, so learning the rules takes a single exchange.

Source: README.md, under "Teaching it your style", step 3, and the
update-prose-config description.

## need explain-in-place: Say why an edit was made, in the document

When an edit needs explaining, the user wants to mark it in the document
itself, with markup a markdown preview shows as an edit, and wants Claude to
remove the markup once the rules are written, so none of it reaches a commit.

Source: README.md, under "Teaching it your style", and the update-prose-config
description.

## need checkable-reports: Check a report against the rule it names

When Claude reports a passage that breaks a rule, the user wants the report to
name the rule by a short id that says what it means, so they can find the rule
and check the report themselves.

Source: README.md, under "What it adds to your project", and the
update-prose-config description.

## need approve-before-rewrite: Approve each rewrite before it is made

When the user asks Claude to apply the house style, they want a list of every
passage that breaks a rule, with its file, line, rule id and proposed rewrite,
and want nothing changed until they approve all of it or a part, so no
document changes in a way they did not see.

Source: README.md, under "Checking your documents", and the apply-prose
description.

## need keep-the-meaning: Keep what a document says through a rewrite

When Claude rewrites a passage, the user wants its numbers, names, dates and
claims kept as they are, so a style pass changes how a sentence reads and never
what it says.

Source: README.md, under "Checking your documents".

## need one-pass-at-a-time: Keep teaching and applying apart

When the user is partway through teaching the style, they want apply-prose to
wait, so rewrites to documents still being edited do not tangle the two sets
of changes.

Source: README.md, under "Checking your documents", and the apply-prose
description.

## need choose-checked-files: Decide which files are checked

When the user applies the house style, they want the `scope:` list in
`prose-style.md` to decide which files are checked, and Claude to explain why a
file was skipped, so the check covers the documents they meant.

Source: README.md, under "Checking your documents", and the apply-prose
description.

## need start-from-defaults: Start a rules file without writing one

When the user first runs update-prose-config in a project, they want to start
the rules file from the default set the plugin ships, from another project's
rules or from an empty file, so the first rules need not be written from
nothing.

Source: README.md, under "Setting up".

## need move-old-rules: Find rules an earlier version left behind

When a project keeps `prose-style.md` at its top level from an earlier version
of the plugin, the user wants the skills to stop and offer to copy it into
`.claude/rules/`, so the rules are loaded again.

Source: README.md, under "Setting up".

## need share-rules: Copy rules from another project

When the user wants another project's prose rules, they want the rules this
project lacks copied across with a note of where each came from, and the rules
that collide on an id or say the same thing under two ids shown side by side in
one round, so they settle each conflict once.

Source: README.md, under "Sharing rules between projects", and the adopt-prose
description.

## need promote-shipped-rule: Ship a rule with the plugin

When the owner finds a rule worth having in every project, they want to add it
to the rules prose-tuning ships, so every new `prose-style.md` starts with it.

Source: the adopt-prose description.

## need review-then-commit: Commit each change the user's usual way

When a skill finishes, the user wants its changes left uncommitted, so they
review and commit them their usual way.

Source: README.md, under "What it adds to your project", and all three skill
descriptions.

## need works-in-cowork: Use the same skills in Cowork

When the user works in a Cowork Project, they want the skills they have in
Claude Code, installed from the same marketplace, so one house style serves
both.

Source: README.md, the opening section and "Setting up".

## constraint cowork-rules-partial: Cowork does not always load .claude/rules/

Cowork leaves `.claude/rules/` out of some parts of a conversation, so the
rules need a line in the project's Instructions field to reach every part.

Source: README.md, under "Setting up".

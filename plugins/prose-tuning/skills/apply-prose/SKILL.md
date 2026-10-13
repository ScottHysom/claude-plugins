---
name: apply-prose
description: Conform a project's markdown to the rules in its prose-style.md. Reports findings first - file, line, rule id, proposed rewrite - and changes nothing until the author approves. Uses scripts/prose.py to resolve scope, to skip code fences, mermaid blocks, indented code, HTML blocks, front matter, table structure and quoted material, to find the breaches a rule's pattern can, and to apply approved rewrites in place. Use when asked to apply the house style, conform documents to prose-style.md, run a style pass over the docs, check a document against the prose rules, or clean up the prose across a project. Resolves the author's own ins, del and repl markup first, once the author says update-prose-config has learned from it, then stops for the commit. Never commits.
---

# Conform the documents to prose-style.md

`update-prose-config` learns the rules. This skill applies them to everything
written before the rules existed.

**Report first. Change nothing until the author says so.** A style pass that
silently rewrites three hundred lines produces exactly the diff that nobody
reads. A reader can tell a rule being applied correctly from a rule being
misapplied only by seeing which rule was claimed.

## Locate the script

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"
PROSE="$ROOT/scripts/prose.py"
ls "$PROSE" || echo "prose-tuning is not installed as a plugin here"
python3 "$PROSE" setup --json
```

Run the block as one command, because the next command's shell will not have
`$PROSE`. Then follow `$ROOT/reference/setup.md`. It says where every command below
runs.

## Step 1: refuse early
<!-- spec: applyprose-waits-for-teaching, applyprose-resolves-author-markup -->
<!-- seam: judgment: the author says whether update-prose-config has learned from the markup -->

```sh
python3 "$PROSE" preflight --for apply
```

`preflight` exits 1 on either of two states:

- **markup present in any governed file.** It is the author's own: `<ins>`,
  `<del>` and `<repl>` marking edits, with `why` and `<alt>` saying why.
  `update-prose-config` learns from it and leaves it in place.
- **an uncommitted governed document.** The author is mid-edit, and a rewrite
  made over those edits could not be reviewed.

An uncommitted `prose-style.md` is not a blocker. It is the expected output of
the run whose rules this pass is about to check.

When `preflight` names markup, ask the author in one `AskUserQuestion` whether
`update-prose-config` has learned from it. On a no, stop and tell the author to
run it first. Resolving drops every `why` and `<alt>`, so they would never be
read. On a yes:

```sh
python3 "$PROSE" tags resolve
```

`resolve` keeps each `<ins>`, drops each `<del>`, keeps the replacement of
each `<repl>`, and removes every tag. Read its warnings. A block-form tag
resolved inside a list is the one case to read closely, because a tag between
two list items ends the list. Then stop. Tell the author to commit the
resolved files and run this skill again to conform them.

## Step 2: the rules, the prose and the pattern matches
<!-- spec: applyprose-passes-named-documents, applyprose-checks-named-rules, applyprose-judges-each-match, applyprose-reads-segments-only -->
<!-- seam: platform: the author asks why a file was skipped, and scope --all answers -->

```sh
python3 "$PROSE" pass
```

When the author named the documents to check, name the same files after
`pass` here, and after `report` and `apply` in the steps below, as in
`pass notes.md`. With no file, each of them reads every file in scope.
`apply` refuses the token unless it is given the files `report` was.

When the arguments name rule ids, such as the ones `update-prose-config` just
wrote, check the documents against those rules alone. Add `--rule` with each
id to `pass` here, and to `report` and `apply` in the steps below, as in
`pass --rule sentences-own-subject --rule headings-noun-phrase`. `pass` then
prints only those rules and their matches. `report` refuses a finding of any
other rule, and still checks each rewrite against every rule's pattern.
`apply` refuses the token unless it is given the same `--rule`s.

`pass` prints three parts, each under its own heading:

- `== rules ==`: every rule in `prose-style.md`, as the file words it.
- `== segments ==`: the prose a rule may touch, one span per line.
- `== matches ==`: every place a rule's pattern matches those spans, then
  the rules checked by pattern.

When the author asks why a file was skipped:

```sh
python3 "$PROSE" scope --all
```

which prints every markdown file with the pattern that included or excluded it.

### The segments

**Never read the raw file to judge conformance.** The segments are only the
spans a prose rule may touch, one per line:

```text
landscape.md:42:2-40  list-item  Able to state what is inside the file.
```

The line starts with the address `file:line:col_start-col_end`. Then come the
kind and the text, each after two spaces. The text runs to the end of the line.

| Kind | Is |
|---|---|
| `paragraph` | body prose, the usual case |
| `list-item` | the text after the bullet, not the bullet |
| `list-continuation` | a later line of a list item's text. A new line in its replacement is indented to stay in the item |
| `heading` | the text after the `#`s. Headings have rules too |
| `table-cell` | one cell's text, without its pipes |

A comment part way along a line is cut out, and
the prose either side of it comes back as separate segments.

### The matches

A rule can carry a regular expression that finds its breaches, such as a
spaced hyphen for `standing-no-em-dash`. `pass` runs every one over the
segments, and prints one line per match:

```text
notes.md:12:40-42  standing-no-em-dash  " -"
notes.md:30:61-31:4  register-plain-words  "in order\n  to"
```

The address is `file:line:col_start-col_end`, with `end_line:col_end` after
the dash when the match wraps onto the next line. Then come the rule id and
the matched text, as a JSON string that goes into a finding's `text` as it
stands. The last line names the rules checked by pattern.

When it says that none of the rules carries one, the project's rules were written before
rules could, and every rule is checked by reading. Tell the author that
`copy-prose` from the shipped rules brings in their patterns.

A pattern finds places to look, so judge each match. A spaced hyphen can be a
minus sign. Every match that breaks its rule becomes a finding in step 3,
usually with a longer `text` than the match, since the rewrite is of the
sentence. A match that stays as it is becomes a finding with `dismiss` and the
reason in place of `replacement`. A match that another rule's finding rewrites
does not stay, so it gets a finding of its own rule. `report` runs the patterns again, and fails
on a match that no finding or dismissal of its rule contains.

**Never search the prose with a command of your own,** such as `grep` over
the segments. A search written during a run finds a different set on
the next run, and the run does not record which rules it covered. A rule with no
pattern is checked by reading the segments. A break of a patterned rule that
reading turns up anyway is still a finding. Tell the author the pattern
missed it, since the pattern is theirs to extend.

## Step 3: produce findings
<!-- spec: applyprose-splits-findings-by-rule, applyprose-keeps-facts, applyprose-checks-own-rewrites -->

<!-- no-command: judgment. The model writes each finding, and step 4's report checks them. -->

Each finding is one JSON object in a findings file:

| Field | Content |
|---|---|
| `file`, `line` | where the text starts |
| `rule` | the id from `prose-style.md`, exactly one |
| `text` | the text as it stands |
| `replacement` | the rewrite |
| `dismiss` | in place of `replacement`, for a pattern's match that stays: one clause saying why |

**A finding names exactly one rule.** A passage breaking two rules is two
findings, because the author may accept one and reject the other. Write both
even when their texts overlap, and let `report` name the pair.

**Rewrite the prose, never the facts.** A rule is about how a sentence reads. A
proposed rewrite that changes a number, a name, a date or a claim is out of
scope for this skill no matter how badly the sentence reads.

**Read each rewrite against every rule.** A rewrite that fixes one rule can
break another. Read each replacement against the rules that do not carry a
pattern before step 4. `report` checks it against the rules that do.

Write the findings file outside the project, so the run does not leave a stray
file in it:

```sh
cat > "${TMPDIR:-/tmp}/prose-findings.json" <<'END'
[{"file":"landscape.md","line":42,"rule":"sentences-own-subject",
  "text":"<the current text, copied from the segment>",
  "replacement":"<the rewrite>"}]
END
```

`file` and `line` come from the segment's address, and `text` is copied
exactly from the segment's text. Leave the columns out: `apply` finds the text
on its line.
When it is refused because the text starts at more than one place on the line,
add the `col_start` the refusal lists. A sentence wrapped onto the next line is
one finding, with the newline and the next line's indent in `text`.

`python3 "$PROSE" apply --help` describes every field of a finding, and which
kinds of line a replacement may put a newline in.

A dismissal carries `text` as the match gives it, and never a
`replacement`. `apply` leaves its text alone.

To cut text, give `"replacement":""`. A line that the cuts cover whole goes
with its newline, and when a cut takes a whole block `apply` keeps one blank
line between the blocks either side.

## Step 4: one approval round
<!-- spec: applyprose-shows-report-whole, applyprose-revises-on-comment, applyprose-puts-rule-conflicts-to-author -->

```sh
python3 "$PROSE" report --findings "${TMPDIR:-/tmp}/prose-findings.json" --json
```

`report` reads each finding's current text from the file as it is now, and
writes the report to the markdown file at `data.report`: each finding with its
`file:line`, rule id, current text and proposed text, then the rules
checked by pattern in the files step 2 read. Each line of a text sits between
`|` marks, so a space at either end shows. `(cut)` stands for an empty
proposed text. A dismissal shows its reason in place of a proposed text.
When `report` exits 0, `data.token` is the approval token, and the file ends
with it. Step 5 takes the token from the report the author approved.

`report` exits 1 when a finding cannot apply. Each error names the finding
or match, and says what to do about it. Never drop a side of an overlap
yourself.

Publish the file at `data.report` as a private artifact with the Artifact
tool, as markdown, with the icon `checklist`. After every later run of
`report`, publish the same file path again, so the report keeps its address.
The author reads the report there, and nowhere else. Never retype the report
or a part of it into chat or a dialog, because the author would then approve a
text other than the one `apply` reads.

When an error says two rules refuse each other's rewrites, never rewrite
that finding again yourself. Only the author can say which rule gives way.

When the only errors left are overlaps and such conflicts, publish the report
with them, give the author its address, and ask them to comment on each one
and send the comment to Claude. Then end the turn. For an overlap, the comment
says which finding stays. For a conflict, it gives the wording to use, or
says to keep the current text. To keep it, drop the finding, or make it a
dismissal carrying the author's reason when its rule's pattern matches the
text. Tell the author that the two rules contradict each other,
and that `update-prose-config` can settle which one gives way.

Once `report` exits 0, put one `AskUserQuestion` to the author, naming the
artifact's address and `data.token`, with these options:

- apply every finding;
- apply some rule ids or some files, named in the answer;
- comment first, on the findings in the artifact;
- apply none of the findings.

On "comment first", end the turn. A comment the author sends to Claude starts
a new turn. Revise or dismiss the findings it names, or remove the side of an
overlap the author turned down. When that side covers a match of its rule's
pattern, make it a dismissal saying the author chose the other finding.
`report` shows that dismissal beside the finding the author chose. Then run
`report` again, publish the file
again, and answer in the comment's thread with `ArtifactComments`, saying
what changed. Ask the one question again, with the new token, once the
threads sent to Claude are answered.

When the Artifact tool is not available, or refuses to publish, read the file
at `data.report` and give it whole in your reply, as it stands, then end the
turn. The author's reply is the decision, and it names the token.

## Step 5: apply
<!-- spec: applyprose-applies-once -->

Hand the approval to `apply` as flags, with the token the author approved.
The flags select within the approved set and leave the token as it is.

| Approved | Flags |
|---|---|
| the whole set | none |
| by rule id | `--only sentences-own-subject,headings-noun-phrase` |
| by file | `--file landscape.md --file resources.md`, one per file |
| rule ids in some files | both; a finding must pass each |

Run it once. The report the author approved is the preview.

```sh
python3 "$PROSE" apply --findings "${TMPDIR:-/tmp}/prose-findings.json" \
  --token 3f9a1c0e7b2d4a68 --only sentences-own-subject --file landscape.md
```

The `--file` flags select from the approved findings. Any files the author
named in step 2 go after the flags, as they did for `report`, and so does
each `--rule` that step 2 passed.

A rule id or file that does not match any finding is an error rather than an
empty run.

## Step 6: report and stop
<!-- spec: applyprose-never-commits -->

<!-- no-command: hand-off to the author. The output of apply in step 5 is the report. -->

The output of `apply` in step 5 is the report of what changed: the edits per
file and per rule id. Show it to the author as it stands. Leave the working
tree dirty.
**Never commit.** The project's own maintenance skill owns that.

## What this skill does not do

This skill does not add rules. A passage that reads badly but does not break
any existing rule is a note to the author and a candidate for
`update-prose-config`. Leave it as it is, because a reader of the report or
the commit could not tell an edit to it from one a rule made.

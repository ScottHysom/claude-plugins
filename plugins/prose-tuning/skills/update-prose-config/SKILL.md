---
name: update-prose-config
description: Infer prose and style rules from the uncommitted markdown edits in a project repo and write them into that project's prose-style.md with stable rule ids. Reads explicit ins, del and repl markup and untagged diff hunks through scripts/prose.py, asks the author about anything ambiguous in one batch, and writes only prose-style.md, leaving the documents and their markup as the author left them. Use when asked to learn the house style from edits just made, to update or set up prose-style.md, to turn an editing pass into rules, to record why a passage was cut, or to take a note on how a passage reads, handed over by the author or another skill. Never commits and never writes outside the project repo.
---

# Learn the house prose style from edits already made

When the author edits documents by hand to tailor the prose, this skill reads those 
edits and works out what rule each one implies. It then writes the rules into `.claude/rules/prose-style.md`, which every later session in the project loads, so every agent applies them without being asked.

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

Read `$ROOT/reference/tag-vocabulary.md` for what the author's markup means.

## Step 1: refuse early
<!-- spec: updateproseconfig-offers-init -->
<!-- seam: judgment: the author decides whether to start a rules file with config init -->

```sh
python3 "$PROSE" preflight --for config
```

`preflight` exits 1 on a blocker: unbalanced markup, or a `prose-style.md`
that does not parse. Otherwise it reports whether `prose-style.md` exists and
the markup already in each file. The markup is what this skill reads, so
`preflight` does not block on it.

When `preflight` reports the rules file missing, offer `config init`. A project that has never
had one starts from the rules this plugin ships rather than from nothing:

```sh
python3 "$PROSE" config init
```

The shipped rules carry `<!-- FILL: ... -->` notes where a rule wants an
example or a name from this project. Tell the author they are there; the
evidence from this run is often what fills them. To start from another
project's rules instead, pass `--from <path to its .claude/rules/prose-style.md>`. To start
with no rules at all, pass `--empty`.

## Step 2: gather the evidence
<!-- spec: updateproseconfig-asks-about-signals, updateproseconfig-reads-named-checkout, updateproseconfig-asks-which-checkout, updateproseconfig-takes-handed-notes, updateproseconfig-reads-notes-as-whys, updateproseconfig-runs-on-notes-alone -->
<!-- seam: judgment: the author picks which checkout to learn from, when two or more hold edits -->

```sh
python3 "$PROSE" evidence --json
```

One command returns everything: explicit markup, untagged edits, and the
rules `prose-style.md` already holds. The explicit and inferred halves matter
differently.

**`rules`** gives each existing rule's `id`, `body` and `patterns`. Check
every candidate below against them before inferring anything. A run that does
not invents parallel rules that say the same thing in different words, and
neither can then be pointed at.

**When the author named a checkout,** by its folder or its branch, or the run
was handed one with its notes, add `--from "<that checkout>"` to `evidence`
here and to `reproduce` in step 7, and do not ask which checkout to read.

**When `data.other_worktrees` is not empty,** this tree does not hold any
edits and another checkout of the repo does. With one entry, read that one.
With two or more, put one `AskUserQuestion` to the author, with an option for
each entry giving its `root`, `branch` and `files`, and an option to read
none. Gather the evidence again from the one read, and pass the same `--from`
to `reproduce` in step 7:

```sh
python3 "$PROSE" evidence --from "<root>" --json
```

Tell the author which checkout the run reads, from `data.checkout`. The rules
still go into this tree's `prose-style.md`, and the other checkout is only
read. A warning that its `prose-style.md` has changes means the author edited
rules there that this run does not see. Say so.

If the author picks none and the run was not handed any notes, stop. This
tree has nothing to learn from.

**`explicit`** is markup the author wrote: an `<ins>`, `<del>` or `<repl>` with
its `why` and its `<alt>` proposals, or an `<alt>` tied to no passage, whose
record has kind `alt` and holds the proposal in `alt`. The author has already
said what they mean. Take it at face value.

**`inferred`** is an untagged diff hunk. Treat every one as a statement about
prose, not a factual correction. That is the working assumption of this whole
skill. The escape hatch is the `signal` field: a hunk marked `numeric-only`,
`link-only` or `whitespace-only` may be a fact that got fixed in passing. Those
go into the interview, never straight into a rule.

**A note handed to the run** comes from the author, or from another skill
through the Skill tool. Each one gives the note, and the passage it sat above:
its file, its lines, its text, and which of those lines changed since the last
commit. A note that does not say which lines changed takes them from the
`inferred` records whose `file`, `start` and `end` cover the passage.

- **On a passage that has not changed**, take the note as an `<alt>` on that
  passage: a proposed rule, with the passage as its evidence. Do not write it
  into the document as markup, and do not rewrite the passage. `apply-prose`
  rewrites it once the rule is written.
- **On a passage that has changed**, take the note as the `why` of the
  `inferred` records in its lines. The rule comes from what the diff changed,
  with the note as its commentary.

When `evidence` does not find any pending edit or markup, and the run was
handed notes, carry on with the notes alone.

**`evidence` computes a tag-neutral diff**, which is why it can tell the two
apart at all. A plain `git diff` on a tagged tree reports the tags themselves
as edits.

## Step 3: the threshold for calling something a rule
<!-- spec: updateproseconfig-makes-rules-at-threshold -->

<!-- no-command: judgment. The model weighs each candidate against the threshold. -->

A candidate becomes a rule when one of these holds:

- it occurs **two or more times** independently, or
- the author attached a `why` or an `<alt>` to it, which a note handed to the
  run counts as when it states a rule, or
- the author's answer in the interview settles it.

Anything else becomes a question, not a rule. A rule inferred from one sentence
with no commentary is a rule about one sentence, and it will fire on every
document in the project forever.

## Step 4: the interview, once
<!-- spec: updateproseconfig-asks-in-one-batch, updateproseconfig-asks-on-page, updateproseconfig-asks-about-vague-notes -->

**Budget: one round of questions, plus one approval at the end.** A second
round means the first asked the wrong things.

What always belongs in the round:

- every hunk with a `signal`, asked as one question, not one question each
- every single-occurrence candidate with no commentary
- every candidate that touches a subject an existing rule already covers
- every note on an unchanged passage that does not state a rule, such as one
  that says the passage reads badly without saying what makes it so

**With four questions or fewer,** put them in one `AskUserQuestion` call.

**With five or more,** write them to a page, as JSON on stdin:

```sh
python3 "$PROSE" questions --batch - --json <<'END'
[{"question":"Was \"in order to\" cut for style, or to fix this one sentence?",
  "options":[{"label":"Style","description":"Write to, not in order to."},
             {"label":"This sentence"}],
  "evidence":["guide.md:12\n- Run it in order to check.\n+ Run it to check."]}]
END
```

Each question gives `question`, its `options`, each with a `label` and
optionally a `description`, and `evidence`: the edits, passages or notes it
rests on, as a list of text. When `questions` exits 1, its errors name each
question it refused. Fix those and run it again.

Publish the file at `data.page` as a private artifact with the Artifact tool,
as markdown, with the icon `question`. Give the author its address, and tell
them to answer each question by commenting on it and sending the comment to
Claude. Then end the turn.

A comment sent to Claude starts a new turn. Read the threads with
`ArtifactComments`, and reply in each question's thread with the answer you
took from it. When a comment does not settle its question, reply asking what
it left open. Go on to step 5 once every question has an answer, and end the
turn until then.

When the Artifact tool is not available, or refuses to publish, ask in
`AskUserQuestion` calls of up to four questions each, in the order the
questions were written.

## Step 5: draft the rules for approval
<!-- spec: updateproseconfig-writes-note-examples, updateproseconfig-shows-rules-whole, updateproseconfig-revises-on-comment -->

Name each rule. The name is one to four words saying what the rule means, and
there is nothing to allocate. A name that reads as a near-duplicate of one
already in the file usually is one, and the fix is to rewrite that rule rather
than add a second under a name split finely enough to be free.

Every rule carries a worked before-and-after taken from the actual edit,
because that example is the rule's provenance as well as its explanation. A
rule from a note on an unchanged passage has no edit to take it from. Its
Before is a line of that passage as it stands, and its After is that line
rewritten to follow the rule, which the author approves with the rule.

**Decide whether the rule gets a pattern.** "When a rule gets a pattern", in
`$ROOT/reference/prose-style-format.md`, says which rules do. For each one
that does, write its patterns now, from the evidence behind the rule.
`apply-prose` runs them in every file, and a rule without one is checked only
by reading. The page the author approves shows each pattern beside its rule,
since a word list is a guess about scope that the author settles. When a rule already
in the file gains a new form in this run's evidence, extend its pattern rather
than adding a rule.

**When a new rule contradicts an existing one, rewrite the body of the existing
id.** Do not add a second rule, and do not mark the old one retired. The id is
the identity, the body is current truth, and
`git log -p .claude/rules/prose-style.md` holds what it used to say.

**The script cannot detect a contradiction** and does not try. That is why
every candidate is checked against `rules` from step 2, and why a candidate touching covered ground goes to the
author instead of into the file. Never reconcile two rules unilaterally.

Do not edit `prose-style.md` yourself. Write every new rule and rewrite to
one batch file:

```sh
cat > "${TMPDIR:-/tmp}/prose-rules.json" <<'END'
[{"section":"sentences","name":"no-in-order-to",
  "title":"Write to, not in order to",
  "body":"The two extra words carry nothing.",
  "example":{"before":"Run it in order to check.","after":"Run it to check."},
  "patterns":["\\bin order to\\b"]},
 {"id":"standing-us-spelling","expect":"<its body from evidence --json>",
  "patterns":["(?i)\\bcolour\\b","(?i)\\bwhilst\\b"]}]
END
```

A new rule gives:

| Field | Means |
|---|---|
| `section`, `name` | the id's two parts |
| `title` | the heading's text after the id, one line |
| `body` | the prose under the heading, with any `**Check.**` line, and no pattern or example |
| `example` | `{"before": ..., "after": ...}`, one line each |
| `patterns` | a list of Python regexes, written as the regex itself, not as a code span |
| `heading` | only for the first rule of a section the file does not have: the `##` heading to open it under |

A rewrite gives `id`, `expect` (the rule's `body` exactly as
`evidence --json` printed it in step 2), and only the parts that change, of
`title`, `body`, `example` and `patterns`. A part it gives replaces the old
one whole, so a pattern list carries the old patterns it keeps. `"example": null`
drops the example.

Then run the batch as a dry run:

```sh
python3 "$PROSE" config write --batch "${TMPDIR:-/tmp}/prose-rules.json" --dry-run --json
```

The script checks every name, and every rewrite against the file as it is now.
It refuses a record whose rule would not lint: for instance, a pattern that
misses its Before example or matches its After. On a refusal, fix what it
names, since the example is the evidence, and run the dry run again.

The dry run writes the rules to the markdown file at `data.rules`, each as
`prose-style.md` will hold it, and a rewrite with the rule it replaces above
it. When it exits 0, `data.token` is the approval token, and the file ends
with it. Step 6 takes the token from the page the author approved.

Publish the file at `data.rules` as a private artifact with the Artifact
tool, as markdown, with the icon `checklist`. After every later dry run,
publish the same file path again, so the page keeps its address. The author
reads the rules there, and nowhere else. Never retype a rule or a summary of
the batch into chat or a dialog, because the author then approves a text that
`config write` never sees.

Put one `AskUserQuestion` to the author, naming the artifact's address and
`data.token`, with these options:

- write every rule;
- comment first, on the rules in the artifact;
- write none.

On "comment first", end the turn. A comment the author sends to Claude starts
a new turn. Revise the batch file as the comment asks, run the dry run again,
publish the file again, and answer in the comment's thread with
`ArtifactComments`, saying what changed. Ask the one question again, with the
new token, once the threads sent to Claude are answered.

When the Artifact tool is not available, or refuses to publish, read the file
at `data.rules` and give it whole in your reply, as it stands, then end the
turn. The author's reply is the decision, and it names the token.

## Step 6: write the rules
<!-- spec: updateproseconfig-writes-through-cmd -->

Hand the batch the author approved to `config write`, with the token they
approved:

```sh
python3 "$PROSE" config write --batch "${TMPDIR:-/tmp}/prose-rules.json" --token 3f9a1c0e7b2d4a68 --json
```

`config write` writes all or none. It exits 1 and writes nothing when the
batch or `prose-style.md` changed since the dry run that printed the token.
Run the dry run again, publish it again and ask again before writing anything.

## Step 7: validate by reproduction
<!-- spec: updateproseconfig-fixes-the-rule -->

```sh
python3 "$PROSE" reproduce --json
```

Add the `--from` that step 2 used, if any. `reproduce` runs every rule's pattern over each file as it was at HEAD. It
reads the author's markup as resolved, and reports each edit made since HEAD
as one entry in `edits`:

- **`reproduced: true`** means a pattern matched what the edit changed. The
  entry's `matches` name the rule and the text at HEAD, with HEAD's line
  numbers.
- **`reproduced: false`** means that none of the patterns did. Check the edit by reading it
  against the rules listed in `unpatterned`, which a command cannot check. An
  edit the interview settled as a fact, not a style choice, does not need a rule.

An edit that no pattern reproduces and no unpatterned rule accounts for shows
a rule that is wrong or incomplete. Say which, and fix the rule rather than
the document: extend its pattern, or write the rule it is missing. Hand the fix
to the author and `config write` as steps 5 and 6 do, then run `reproduce`
again.

## Step 8: hand off
<!-- spec: updateproseconfig-never-commits, updateproseconfig-names-unreproduced-edits, updateproseconfig-never-writes-documents -->

<!-- no-command: hand-off to the author. The run ends with the working tree dirty. -->

Report what changed, which files are dirty, and stop. The only file the run
writes is `prose-style.md`. Never write markup into a document, and never run
`tags resolve`. The author's markup and edits stay as they left them, and
`apply-prose` resolves the markup once the author says the rules are learned.

List each edit that step 7 last reported with `reproduced: false`, by its
`file` and `start`. If the author discards their edits and runs `apply-prose`
instead, these are the edits it may not make again.
**Never commit.** The project's own maintenance skill owns commit types,
message format, and the bridge's lock-file workaround.

## Scope

This skill writes inside the project repo it was invoked in, and nowhere else.
`--from` reads another worktree of the same repo, and the run writes only this
tree.
Carrying a rule upstream into the rules this plugin ships is `adopt-prose`'s
job, and it is deliberate rather than automatic.

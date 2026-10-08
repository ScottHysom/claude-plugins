---
name: adopt-prose
description: Copy prose rules from one project's prose-style.md into another, or into the rules prose-tuning ships so every new prose-style.md starts with them. Rules the target lacks are added as-is, with a note naming where they came from for the commit description; rules that collide on the same id, and rules that state the same thing under two different ids, are shown side by side in one batch for the author to resolve. Use when asked to adopt another project's prose rules, to promote a rule into the shipped rules, to share a style rule between two projects, or to merge two prose-style.md files. Never commits.
---

# Move prose rules between projects

The target depends on what was asked:

- **"make this project sound like that one"**: the target is this project's
  `.claude/rules/prose-style.md`.
- **"promote this rule so new projects get it"**: the target is
  `plugins/prose-tuning/templates/prose-style.md` in the `claude-plugins` repo,
  the rules `config init` starts a project from.

The second is the only sanctioned route from a project back into the shipped
rules. `update-prose-config` deliberately cannot do it.

## Locate the script

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"
PROSE="$ROOT/scripts/prose.py"
ls "$PROSE" || echo "prose-tuning is not installed as a plugin here"
python3 "$PROSE" setup --json
```

Run the block as one command, because the next command's shell will not have
`$PROSE`. Then follow `$ROOT/reference/setup.md`. It says where every command below
runs. On Cowork, both files have to be in connected folders, and a `--file`
outside this project is given as
`"$HOME/mnt"/<folder>/.claude/rules/prose-style.md`, or the `prose-style.md` at
the folder's root for a project that has not moved its rules yet.
Promoting a rule into the shipped rules is repo work, done in Claude Code
against a checkout of `claude-plugins`.

## Step 1: classify
<!-- spec: classify-cmd-finds-new-rules, classify-cmd-finds-identical-rules, classify-cmd-finds-colliding-rules, classify-cmd-finds-similar-rules, classify-refuses-unlinted, classify-gives-bodies, adoptprose-rereads-new-rules -->

```sh
python3 "$PROSE" config classify --file <source> --to <target> --json
```

Every source rule comes back in `data.rules` with its `body`, one of four
buckets, and `target` naming the target rule it matched, with that rule's
`target_body`:

| Bucket | Meaning | Action |
|---|---|---|
| new | the target has no rule with that id, and none scored similar | step 2 |
| identical | same id, and the bodies match once comments and whitespace are set aside | skip silently |
| colliding | same id, different body | step 3 |
| similar | different id, and `candidates` lists the target rules that scored close | step 3 |

**The similar bucket is the one that matters.** Adopting a similar rule as new
leaves the target holding the same instruction twice under two names, and a
report can then cite only one of them.

**The script surfaces candidates; it never decides.** Every candidate goes to
the author in step 3 with both bodies in full. A score is a reason to look,
never a reason to merge.

The score is also a floor rather than a ceiling. Read each `new` rule against
the target yourself, and move any that states a target rule's point in other
words to step 3 as similar. Two rules can say the same thing with no words in
common. This is judgment, and it is the part of this step the script cannot do.
The identical and colliding buckets are exact, so leave them as they came.

## Step 2: adopt the new rules
<!-- spec: adoptprose-passes-each-new-rule, adopt-cmd-copies-byte-for-byte, adopt-cmd-places-by-section -->

```sh
python3 "$PROSE" config adopt --file <source> --to <target> --rule <id> --rule <id> --json
```

Pass every rule still in the new bucket after step 1, each as its own
`--rule`. Do not edit the copied rules by hand. The command copies each one
as the source has it and puts it under its section. Keep `data.commit_note`
for the hand-off.

The command exits 1 and writes nothing while any id is refused. An id refused
because the target already has it is a colliding rule: take it to step 3 and
run the command again without it.

## Step 3: the author's answers, in one batch
<!-- spec: adoptprose-shows-conflicts-once, adoptprose-keeps-target-id -->

Ask one `AskUserQuestion` set covering every colliding and every similar pair, each
showing both bodies in full. Take them from step 1's result: a rule's `body`
against its `target_body`, or against each candidate's `target_body`. Never
split them into two rounds: the author is deciding one thing, which is what
the target's rulebook should say.

A collision offers three options: take the source, keep the target, or write a
combination.

A similar pair offers three: keep both as distinct rules, rewrite the target's
rule to cover the source as well, or drop the source rule.

Then hand every answer to the command as one JSON list on stdin:

```sh
python3 "$PROSE" config resolve --file <source> --to <target> --answers - --json
```

Each answer is an object:

- `source` and `target`: the ids of the pair.
- `resolution`: `take-source`, `keep-target` or `combine` for a collision;
  `keep-both`, `combine` or `drop-source` for a similar pair. A rewrite of
  the target's rule is `combine`.
- `expect`: `{"source": ..., "target": ...}`, the rule's `body` and the
  matching `target_body` from step 1's result.
- For `combine` only, the parts the author's wording changes: `title`,
  `body`, `example` (`{"before": ..., "after": ...}`) and `patterns`, as
  `config write` takes them. The command writes the combination under the
  target's id.

Keep `data.commit_note` for the hand-off. The command exits 1 and writes
nothing while any answer is refused, and each refusal says why.

## Step 4: when the target is the shipped rules
<!-- spec: adoptprose-bumps-shipped-version -->

Promoting into them carries three extra obligations, because the shipped rules are part of the plugin:

```sh
python3 .github/scripts/check-manifest-consistency.py check
```

- **Bump `prose-tuning`** in both its `.claude-plugin/plugin.json` and the
  root `.claude-plugin/marketplace.json`. They must match or CI fails. A new
  rule is a minor bump; rewording one is a patch.
- **Say that projects already started from the shipped rules now differ.**
  They do not update themselves. Bringing one into line is this skill run
  again, with the shipped rules as the source and that project as the target,
  and it is the author's call, not this run's.
- **Keep the `FILL` markers.** A rule promoted out of a real project usually has
  that project's example baked into it. The shipped version needs the example
  replaced by a `FILL` telling the next project what to supply, or every project
  inherits a worked example about something it has never heard of.

## Step 5: hand off
<!-- spec: adoptprose-never-commits -->

<!-- no-command: hand-off to the author. Steps 2 and 3 hold the commit notes. -->

Report what changed, and give the author the `data.commit_note` of steps 2
and 3 as the lines for their commit description. Nothing in `prose-style.md` records where
a rule came from, so the commit is where that note lives. Leave the working
tree dirty. **Never commit.**

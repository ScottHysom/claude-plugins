---
name: adopt-prose
description: Copy prose rules from one project's prose-style.md into another, or into the rules prose-tuning ships so every new prose-style.md starts with them. Rules the target lacks are added as-is with their origin recorded; rules that collide on the same id, and rules that state the same thing under two different ids, are shown side by side in one batch for the author to resolve. Use when asked to adopt another project's prose rules, to promote a rule into the shipped rules, to share a style rule between two projects, or to merge two prose-style.md files. Never commits.
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

## Step 1: parse both files

```sh
python3 "$PROSE" config lint --file <source>
python3 "$PROSE" config lint --file <target>
python3 "$PROSE" config list --file <source> --json
python3 "$PROSE" config list --file <target> --json
python3 "$PROSE" config similar --file <source> --to <target> --json
```

**Lint both before merging either.** Merging a malformed file produces a
malformed file, and the errors then look like they came from the merge.

`similar` reports pairs of rules that hold across the two files under different
ids. Step 2 says what to do with them.

## Step 2: classify

Every rule lands in one of four buckets. The first three are computed by rule id, exactly:

| Bucket | Test | Action |
|---|---|---|
| new | no rule with that id, and nothing flagged similar | adopt as-is |
| identical | same id, same `body_key` | skip silently |
| colliding | same id, different `body_key` | one batched question |
| similar | different id, same subject | one batched question |

**Compare `body_key`, not `body`.** `config list --json` returns both.
`body_key` has HTML comments removed and whitespace collapsed, so two rules
differing only by a `FILL` marker or a line rewrap are recognized as the same
rule. Comparing raw bodies makes almost every shipped rule look like a
collision, and a batch of twenty false collisions is a batch nobody reads.

**The fourth bucket is the one that matters.** Two projects that wrote the same
rule in their own words give it two different names, so it is `new` by id in
both directions, and adopting it leaves the target holding the same instruction
twice under two names. Nothing downstream can then be pointed at: a report cites
one id, a conformance pass honors whichever it reads first, and a later run
tries to reconcile rules that were never meant to differ.

`config similar` finds the candidates. It scores every cross-file pair on the
normalized body and on the overlap between the two names, and prints the pairs
at or above a threshold. Two rules about the same subject usually get similar
names.

**The script surfaces candidates; it never decides.** Every pair it prints goes
to the author in step 4 with both bodies in full. A score is a reason to look,
never a reason to merge.

It is also a floor rather than a ceiling. Read the source rules against the
target yourself and add any pair the score missed; two rules can say the same
thing with no words in common. This is judgment, and it is the part of this
skill the script cannot do.

## Step 3: adopt the new rules

Copy the body verbatim, including the worked example. Record where it came from:

```markdown
### register-plain-in-headings: The register stays plain in headings
<!-- prose-rule: source=adopted origin=solo-game-research -->
```

`origin` matters here more than anywhere else. An adopted rule is the one most
likely to be wrong for its new home, and a year from now nothing else will
explain why the project has a rule nobody in it wrote. It is also the only mark
left on an adopted rule.

## Step 4: questions, one batch

<!-- no-command: judgment. The author resolves each colliding and similar pair. -->

Ask one `AskUserQuestion` set covering every colliding and every similar pair, each
showing both bodies in full. Never split them into two rounds: the author is
deciding one thing, which is what the target's rulebook should say.

A collision offers three options: take the source, keep the target, or write a
combination.

A similar pair offers three: keep both as distinct rules, rewrite the target's
rule to cover the source as well, or drop the source rule.

A combination or a rewrite is written by hand and **keeps the target's id**. The
id is what every existing report and cross-reference in the target already
names, and a similar pair that resolves into one rule is the case where losing
that id would be easiest and least noticed.

## Step 5: write and check

```sh
python3 "$PROSE" config lint --file <target>
```

The lint must pass.

## Step 6: when the target is the shipped rules

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

## Never commit

Leave the working tree dirty and report what changed.

---
name: adopt-prose
description: Copy prose rules from one project's prose-style.md into another, or into the cowork-project-scaffold plugin's templates/prose-style.md so newly scaffolded projects ship with them. Rules the target lacks are added as-is with their origin recorded; rules that collide on the same id are shown side by side in one batch for the author to pick source, target or a combination. Use when asked to adopt another project's prose rules, to promote a rule into the scaffold template, to share a style rule between two projects, or to merge two prose-style.md files. Never commits.
---

# Move prose rules between projects

Two uses, one flow:

- **"make this project sound like that one"** - target is this project's
  `prose-style.md`.
- **"promote this rule so new projects get it"** - target is
  `plugins/cowork-project-scaffold/skills/new-cowork-project/templates/prose-style.md`
  in the `claude-plugins` repo.

The second is the only sanctioned route from a project back into the shipped
default. `update-prose-config` deliberately cannot do it: a skill that writes
outside the repo it was invoked in is a skill whose blast radius depends on
which machine it ran on.

## Locate the script

```sh
PROSE="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}/scripts/prose.py"
ls "$PROSE" || echo "prose-tuning is not installed as a plugin here"
```

## Step 1: parse both files

```sh
python3 "$PROSE" config lint --file <source>
python3 "$PROSE" config lint --file <target>
python3 "$PROSE" config list --file <source> --json
python3 "$PROSE" config list --file <target> --json
```

**Lint both before merging either.** Merging a malformed file produces a
malformed file, and the errors then look like they came from the merge.

## Step 2: classify

Three buckets, computed **by rule id and section, never by prose similarity**:

| Bucket | Test | Action |
|---|---|---|
| new | the target has no rule with that id | adopt as-is |
| identical | same id, same `body_key` | skip silently |
| colliding | same id, different `body_key` | one batched question |

**Compare `body_key`, not `body`.** `config list --json` returns both.
`body_key` has HTML comments removed and whitespace collapsed, so two rules
differing only by a `FILL` marker or a line rewrap are recognised as the same
rule. Comparing raw bodies makes almost every shipped rule look like a
collision, and a batch of twenty false collisions is a batch nobody reads.

Similarity matching was considered and rejected. It produces confident wrong
pairings, and the author has no way to audit a pairing they never saw made.

A rule whose id is free in the target but whose subject is plainly covered by a
differently-numbered rule there is a collision in substance, not in id. Say so
and put it in the batch. This is judgement, and it is the one part of this skill
the script cannot do.

## Step 3: adopt the new rules

Copy the body verbatim, including the worked example. Record where it came from:

```markdown
### register-03: The register stays plain in headings
<!-- prose-rule: source=adopted origin=solo-game-research -->
```

`origin` matters here more than anywhere else. An adopted rule is the one most
likely to be wrong for its new home, and a year from now nothing else will
explain why the project has a rule nobody in it wrote.

## Step 4: collisions, one batch

One `AskUserQuestion` set covering every collision, each showing both bodies in
full. Three options per collision: take the source, keep the target, or write a
combination.

A combination is written by hand and **keeps the target's id**. The id is what
every existing report and cross-reference in the target already names.

## Step 5: write and check

```sh
python3 "$PROSE" config lint --file <target>
```

Must pass.

## Step 6: when the target is the scaffold template

Three extra obligations, because the template is shipped code:

```sh
python3 .github/scripts/check-manifest-consistency.py
```

- **Bump `cowork-project-scaffold`** in both `.claude-plugin/plugin.json` and
  the root `.claude-plugin/marketplace.json`. They must match or CI fails. A new
  rule is a minor bump; rewording one is a patch.
- **Say which already-scaffolded projects now differ.** They do not update
  themselves. Regenerating an existing project's files is a deliberate act that
  discards hand-tuning, and it is the author's call, not this skill's.
- **Keep the `FILL` markers.** A rule promoted out of a real project usually has
  that project's example baked into it. The template version needs the example
  replaced by a `FILL` telling the next project what to supply, or every project
  inherits a worked example about something it has never heard of.

## Never commit

Leave the working tree dirty and report what changed.

---
name: check-prose
description: Check a file that another skill hands over against the project's prose rules, and hand back what breaks them. Takes the file's path, the rules files and the checkout's root and branch in its arguments. Uses scripts/prose.py to run every rule's pattern over the file and to split the read of the rest into parts, and reports each pattern match as rule id, line and sentence, and each breach a read finds as rule id and sentence. Use when another skill has written a file, such as a draft in a temporary folder, and wants it checked against the prose rules before it acts on the result. Leaves the file as it is, asks nobody to approve anything, and never commits.
---

# Check a handed-over file against the prose rules

Another skill calls this one with the Skill tool, and acts on the reply
itself. Leave the file as it is, and do not ask the author anything: the
calling skill rewrites the file and calls again.

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

## Step 1: the matches and the parts
<!-- spec: checkprose-takes-handed-file, checkprose-names-trigger -->

The arguments name these:

- the file to check.
- the rules files, each in the format of `prose-style.md`.
- the checkout's root and branch.
- after a revision, the lines it changed. The read in step 2 covers every
  line, so treat these like any other line.

Run `check` on the file, with the checkout's root as `-C` and a `--rules`
for each rules file. With no rules file named, leave `--rules` out, and
`check` reads the project's `prose-style.md`:

```sh
python3 "$PROSE" check /var/folders/k2/T/pr-x8q1zv.md --rules .claude/rules/prose-style.md -C /path/to/checkout --json
```

`data.rules` holds an entry for each rules file, in the order given. Each has
its `path`, its `matches` and its `parts`. A match is a place where a rule's
pattern finds a likely breach, with its `rule`, its `line` and the
`sentence` it falls in. When `check` exits 2, its message names what to do.
Pass that message back to the calling skill as the reply.

## Step 2: read each part
<!-- spec: checkprose-reads-every-rule -->

A part is one section of a rules file over a run of the file's lines. Print
each part in `parts`, with the `path` of the rules file it was listed under:

```sh
python3 "$PROSE" check /var/folders/k2/T/pr-x8q1zv.md --rules .claude/rules/prose-style.md --part 'sentences@/var/folders/k2/T/pr-x8q1zv.md:1-12' -C /path/to/checkout
```

It prints the part's rules as the rules file words them, then the lines of
the file they cover. Read every line against every rule there. Note each
sentence that breaks a rule, with the rule's id. A match from step 1 is
judged as part of this read: keep it when the rule's own text shows that it
breaks the rule, and leave it out when that text shows the sentence follows
the rule.

## Step 3: reply
<!-- spec: checkprose-changes-nothing -->
<!-- no-command: hand-off. The reply goes back to the calling skill as text. -->

Reply in exactly this form, with every match kept and every breach the read
found, each under the rules file it came from:

```text
RULES: <the rules file's path>

MATCHES:
- <rule id>: line <line>: "<the sentence>"

BREACHES:
- <rule id>: "<the sentence, quoted>": <what breaks the rule>
```

Write "none" under a heading that lists nothing.

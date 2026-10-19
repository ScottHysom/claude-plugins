---
name: adopt
description: Bring a repository under the flywheel method, or re-assess one that adopted it, by level and principle id. Uses flywheel.py assess to report each of the method's controls with the evidence found or missing, asks the owner for the target level and for every field only the owner sets, writes the roles file and the review and merge policies with flywheel.py config init, writes the rules for agents into the project's CLAUDE.md, records the version and the controls held with flywheel.py record, and files each missing control as an issue of one plan. Claude Code only. Use when asked to adopt flywheel or the method, to bring a repository under the method, to assess which level a repository is at, or to find what changed since it adopted an earlier version.
---

# Adopt the method

The method the flywheel plugin follows sorts its **controls** (the rules,
files and checks a repository holds) into three levels, each a floor for the
next. The plugin's `docs/adoption.md` lists them, and `flywheel.py assess`
reports each one with the evidence the repository holds for it. Adopting means
choosing a target level, closing the gaps up to it one control per issue, and
recording which version of the method was adopted, so that a later run shows
only what changed.

Some things only the owner supplies: the target level, a need or a
constraint, a policy's terms and the model behind each role. Ask for each one,
and write nothing that depends on it until the owner answers. Each command
below runs from the root of the clone.

## Locate the script

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"
FLYWHEEL="$ROOT/scripts/flywheel.py"
ls "$FLYWHEEL" || echo "flywheel is not installed as a plugin here"
python3 "$FLYWHEEL" setup --json
```

Run the block as one command. If the `ls` fails, the plugin is not installed
here, so stop.

`setup` copies the script into the project at `.flywheel/`, which git
ignores. Each later command starts a fresh shell, so start every one with
`data.prefix` and `&&`, as the steps below do.

## Step 1: assess the repository
<!-- spec: assess-cmd-reports-gaps-by-id, record-cmd-writes-version-and-controls -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" assess --json
```

`data.levels` lists each level, whether the repository holds it, and the
`controls` the level introduces, each with its principle `ids`, whether it
is `held`, and its `evidence`. `data.level` is the highest level the
repository holds, with every level below it. When the repository has adopted
before, `data.recorded` gives the version and the target level it recorded,
and `data.changes` names each control whose state changed since, including a
control the method added after that version, as `new`.

Exit 1 means a control at or below the recorded level is missing. That is a
gap to file, not a reason to stop.

Show the owner each control with its evidence, grouped by level, and the
changes when there are any.

## Step 2: ask for the target level
<!-- spec: adopt-never-invents-owner-fields -->
<!-- no-command: the owner chooses the level, which a script cannot -->

Ask the owner which level to adopt, with one `AskUserQuestion`. Offer each
level with what `$ROOT/docs/adoption.md`, under "Choosing a level", says it
suits. When `data.recorded` gives a level, offer it first.

Never choose the level for the owner, and run nothing further until they
answer.

## Step 3: write the roles file, the policies and the test commands
<!-- spec: configinit-cmd-writes-roles-file, configinit-cmd-writes-policies, configinit-cmd-names-owner-fields, configinit-cmd-fills-pytest-test-commands, adopt-never-invents-owner-fields -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" config init --json
```

`config init` writes `.flywheel/roles.json`, `.flywheel/review-policy.md` and
`.flywheel/merge-policy.md`, and leaves each that exists as it is. It also
writes the commands that list the tests and run one under `tests` in
`.flywheel/gates.json`, filled in when the project runs pytest, and leaves
them as they are when the file gives them. Exit 1 means one existed already,
which is expected on a repository that adopted before.

Each entry of `data.files` names the `owner_fields` its file leaves unset.
Ask the owner for each field in a file whose control is at or below the
target level:

- the review policy and the gates file's test commands, from level 2.
- the roles file and the merge policy, at level 3.

Ask for the merge policy's terms, such as the paths it protects and the paths
each area covers, and for the model and the effort behind each role. For the
test commands, ask for the command that prints one test id per line, the
command that runs one test with `{id}` where its id goes, and the files and
directories that hold the tests. Write
each answer into its file as the owner gave it. Leave a field the owner
defers unset, and say so in step 7.

## Step 4: write the rules for agents
<!-- spec: adopt-writes-agent-rules -->
<!-- no-command: merging the rules into the project's own instructions is judgment -->

Read `$ROOT/templates/agent-rules.md`. Write its sections up to the target
level into the project's `CLAUDE.md`, or into `AGENTS.md` when the project
keeps its rules there and has no `CLAUDE.md`. Create `CLAUDE.md` when the
project has neither. Write it once, as a section of its own, and keep each
rule's `Source:` line, which is what `assess` reads.

Leave every rule the project already has as it is. When one of the
template's rules contradicts one of the project's, keep both, and name the
pair to the owner in step 7.

## Step 5: record the adoption
<!-- spec: record-cmd-writes-version-and-controls -->

Pass the target level the owner chose in step 2:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" record --level 2 --json
```

`record` writes `.flywheel/adoption.json` with the plugin's version, the
level and, under each level, each control's state. `data.gaps` lists each
level up to the target that has a control missing, with the `controls`
still missing and their evidence.

## Step 6: create the missing labels
<!-- spec: adopt-creates-missing-labels, labels-cmd-names-missing-labels -->
<!-- seam: judgment: the owner agrees to create the labels before the second command runs -->

When `data.gaps` is empty, skip to the report in step 7.

Otherwise name the labels the plan of gaps and the loop need that the
repository lacks:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" labels --json
```

Exit 0 means the repository has every label, so go on to step 7. Exit 1
means `data.missing` names each label it lacks. Show the owner those labels,
and ask with one `AskUserQuestion` whether to create them. Once the owner
agrees, create them:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" labels --create --json
```

`data.created` names each label it created. If the owner declines, file
nothing, and say in the report that file-issue refuses a plan whose labels
the repository lacks.

## Step 7: file the gaps
<!-- spec: adopt-files-gaps-as-plan -->
<!-- no-command: hand-off to the file-issue skill -->

When `data.gaps` is empty, skip to the report.

Otherwise hand the gaps to the plugin's file-issue skill as one plan, with
one issue per missing control, level by level in the order of `data.gaps`.
Each issue:

- is titled for the control the repository lacks, such as "Nothing runs the
  verify gate in CI".
- gives the control, the level that introduces it and its principle ids
  under "What's wrong",
  and the evidence `record` reported under "Evidence".
- says under "Done when" that `flywheel.py assess` reports the control held.
- for a missing spec, says the owner supplies each need and constraint, and
  that the agent drafts none of them.

The tracking issue's plan says the repository is adopting the method at the
target level, and that the issues come in the order of `docs/adoption.md`'s
tables.

Then tell the owner:

- the level the repository holds now and the level recorded.
- the files this run wrote, to review and commit: `.flywheel/adoption.json`,
  the roles file, the policies and the rules for agents.
- each field left unset, and each pair of contradicting rules from step 4.
- the plan file-issue filed, or that there was nothing to file.

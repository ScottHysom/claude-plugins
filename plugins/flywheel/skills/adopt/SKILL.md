---
name: adopt
description: Bring a repository under the Flywheel Playbook, or re-assess one that adopted it, by level and principle id. Uses flywheel.py assess to report each of the playbook's controls with the evidence found or missing, asks the owner for the target level and for every field only the owner sets, writes the roles file and the review and merge policies with flywheel.py config init, writes the rules for agents into the project's CLAUDE.md, records the version and the controls held with flywheel.py record, and files each missing control as an issue of one plan. Claude Code only. Use when asked to adopt flywheel or the playbook, to bring a repository under the playbook, to assess which level a repository is at, or to find what changed since it adopted an earlier version.
---

# Adopt the playbook

The playbook the flywheel plugin follows sorts its **controls** (the rules,
files and checks a repository holds) into three levels, each a floor for the
next. The plugin's `docs/adoption.md` lists them, and `flywheel.py assess`
reports each one with the evidence the repository holds for it. Adopting means
choosing a target level, closing the gaps up to it one control per issue, and
recording which version of the playbook was adopted, so that a later run shows
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
control the playbook added after that version, as `new`.

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

## Step 3: write the roles file, the policies, the gates and the test commands
<!-- spec: configinit-cmd-writes-roles-file, configinit-cmd-writes-policies, configinit-cmd-names-owner-fields, configinit-cmd-writes-gate-fields, configinit-cmd-fills-pytest-test-commands, adopt-never-invents-owner-fields, adopt-asks-roles-at-every-level -->

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" config init --json
```

`config init` writes `.flywheel/roles.json`, `.flywheel/review-policy.md` and
`.flywheel/merge-policy.md`, and leaves each that exists as it is. In
`.flywheel/gates.json`, it writes the gates `build`, `test`, `check` and
`verify` under `gates`, unset, and keeps each gate the file gives. It also
writes the commands that list the tests and run one under `tests`, filled in
when the project runs pytest, and leaves them as they are when the file gives
them. Exit 1 means one existed already, which is expected on a repository
that adopted before.

Each entry of `data.files` names the `owner_fields` its file leaves unset.
Ask the owner for each field in any of these:

- the gates and the roles file, whatever the target level, since every round
  the run skill starts reads each role's model and effort.
- the review policy and the gates file's test commands, from level 2.
- the merge policy, at level 3.

For each gate, offer the command the project already runs for it, from its
`CLAUDE.md`, a Makefile or a CI workflow, and ask the owner to confirm it.

Ask for the merge policy's terms, such as the paths it protects and the paths
each area covers, and for the model and the effort behind each role. For the
test commands, ask for the command that prints one test id per line, the
command that runs one test with `{id}` where its id goes, and the files and
directories that hold the tests. Write
each answer into its file as the owner gave it. Leave a field the owner
defers unset, and say so in step 7. Leave a gate unset when the project
lacks its command. `record` in step 5 then lists its control among the gaps,
and step 7 files it.

## Step 4: write the rules for agents
<!-- spec: adopt-writes-agent-rules, agentrules-names-requirements-section -->
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

## Step 6: set the issue and pull request rules and create the missing labels
<!-- spec: adopt-asks-role-labels, labels-cmd-sets-role, labels-cmd-flags-taken-claim-label, adopt-creates-missing-labels, labels-cmd-names-missing-labels, adopt-asks-issue-rules, labels-cmd-sets-kinds, issuetemplate-sets-headings, adopt-asks-pr-shape, prtemplate-sets-shape, adopt-asks-prose-rules, prtemplate-names-prose-rules, prtemplate-names-prose-check -->
<!-- seam: judgment: the owner names each role's label, the issue rules, the pull request shape and the prose rules, then agrees to create the missing labels -->

The loop acts on three labels by their role. Ask the owner, with one
`AskUserQuestion`, which label the repository already uses for each role,
offering the default first:

- `approval`, the label the owner adds to approve an issue: `approved`.
- `plan`, the label of a plan issue, which groups a plan's issues: `plan`.
- `claim`, the label a session adds to the issue it has claimed:
  `claimed`. Ask for a label that nothing else in the repository uses,
  since the loop adds it and takes it off.

Then ask the owner, with one more `AskUserQuestion`, for the rules each issue
that file-issue files follows and the shape of each pull request, offering
the default first:

- the kind labels, one of which each issue carries: GitHub's `bug`,
  `enhancement` and `documentation`, each with its description.
- the headings an issue's body holds, and what to write under each:
  `What's wrong` (what happens, and a command that shows it), `Evidence`
  (file and line, commit, pull request, output), `Done when` (what a fix
  has to make true) and `Requirements` (the ids in specs/ the issue adds,
  changes or removes).
- the shape of a pull request's description: its sections, in order, the
  subsections under each, and the section that names the requirement ids
  the pull request adds, changes or removes. The default is `Scenario` (who,
  by role, does what), with the subsections `Before` (what happened before
  the change) and `After` (what happens after it), then `Change` (what the
  pull request changes), `Requirements` (the section that names the ids)
  and `Test plan` (what ran).

When the owner gives headings other than the default, write them to
`.flywheel/issue-template.md`, each as `## <heading>` with what to write
under it on the lines below. Leave the file out when the answer is the
default.

When the owner gives a pull request shape other than the default, write it
to `.flywheel/pr-template.md`. Give each section as `## <heading>` and each
subsection under it as `### <heading>`, with what to write under each on the
lines below. Put `<!-- requirement-ids -->` on its own line under the heading
of the section that names the ids. Leave the file out when the answer is the
default.

Then ask the owner, with one more `AskUserQuestion`, for both of these:

- the files that hold the project's prose rules, if it keeps any, such as
  `.claude/rules/prose-style.md`. Offer each such file the repository has.
- the installed skill that checks a file it is handed against those rules,
  if there is one. Offer each skill of the session whose description says it
  checks a file against prose rules.

In the question, tell the owner that each rules file has to follow the
format that the skill reads. The skill refuses a file in another format, and
open-pr then gets a refusal in place of a check on every draft.

For each file, put a line `<!-- prose-rules: PATH -->` at the top of
`.flywheel/pr-template.md`, with the path from the project root. For the
skill, put a line `<!-- prose-check: SKILL -->` under them. When the template
does not exist yet, write the default shape under the lines: each section and
subsection above, with `<!-- requirement-ids -->` under `## Requirements`.
When the owner names no file, write neither line, and name no skill.

When step 6 wrote `.flywheel/pr-template.md`, check that every command that
reads it can:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" pr draft
```

Exit 0 means the template reads, and the path it prints is an empty file
that stays unused. Exit 2 means the template breaks a rule, such as a
`prose-rules` line that names a file the project does not have. The error
names the line and the remedy. Ask the owner for the right path, fix the
template, and run the command again.

Set each label answer that differs from the default and name the labels the
repository lacks. The command below sets `ready` as the approval label, and
the kinds `bug`, `feature` and `docs`. Give `--set` once for each role whose
answer differs, with the role and the owner's label. Give `--kind` once for
each kind, with its description, when that answer differs from the default.
Leave out an option whose answer is the default:

```sh
FLYWHEEL=.flywheel/flywheel.py && python3 "$FLYWHEEL" labels --set approval=ready --kind "bug=Something isn't working" --kind "feature=New behavior" --kind "docs=Documentation only" --json
```

`labels` writes each `--set` and `--kind` into `.flywheel/labels.json`.
`data.roles` gives the label for every role, and `data.kinds` gives the
kinds. Exit 0 means the repository has every label,
so go on to step 7. Exit 1 means at least one of these:

- `data.taken` names the claim label, which the repository already has with
  a description of its own. Ask the owner for another label, and run `labels`
  again with `--set claim=NAME`. The error names the other remedy, for a
  label that marks only flywheel's claims.
- `data.missing` names each label the repository lacks. Show the owner those
  labels, and ask with one `AskUserQuestion` whether to create them. Once the
  owner agrees, create them:

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
  under the heading that says what is wrong ("What's wrong" by default).
- gives the evidence `record` reported under the heading for evidence
  ("Evidence" by default).
- says under the heading for when the issue is done ("Done when" by
  default) that `flywheel.py assess` reports the control held.
- for a missing spec, says the owner supplies each need and constraint, and
  that the agent drafts none of them.

The plan issue's body says the repository is adopting the playbook at the
target level, and that the issues come in the order of `docs/adoption.md`'s
tables.

Then tell the owner:

- the level the repository holds now and the level recorded.
- the files this run wrote, to review and commit: `.flywheel/adoption.json`,
  the roles file, the policies, `.flywheel/gates.json`,
  `.flywheel/labels.json` when step 6 set a label,
  `.flywheel/issue-template.md` and `.flywheel/pr-template.md` when step 6
  wrote them, and the rules for agents.
- each field left unset, and each pair of contradicting rules from step 4.
- the plan file-issue filed, or that there was nothing to file.

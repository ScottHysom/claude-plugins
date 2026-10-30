# repo

This file records what the repository as a whole is for: its catalog, its
checks and the conventions every plugin script shares. SPEC-METHODOLOGY.md, at
the repo root, has the grammar of this file and the steps that add its
requirements.

## Out of scope

- Code shared between plugins. Each plugin installs on its own and cannot
  import another's.
- Packages outside the Python standard library in a plugin script.
- Editing this repo from Cowork, the Claude desktop app's mode for work on a
  user's own files. Contributors change it from Claude Code, and its plugins
  serve Cowork sessions in the user's own projects.

## need owner-keeps-model-at-seams: Keep the model to judgment and platform seams

When a skill runs script commands, the owner wants the model between two of
them only where it makes a judgment or calls a tool beyond a script's reach,
so a run does not spend context on work a script could do, or get that work
wrong.

Source: #126, and CLAUDE.md, under "Skills and scripts".

- `script-checks-every-answer` (test): When a script takes the model's answers
  as data, it checks every one, names each that fails, and writes nothing if
  any does.
- `steps-cmd-requires-seam-marker` (test): When a skill step runs more
  than one command, `check-skills.py steps` fails it unless a marker on its
  own line under the heading names a judgment or a platform seam and gives a
  reason.
- `steps-cmd-fails-stale-seam-marker` (test): When a step with a seam
  marker runs one command or none, `steps` fails the marker.
- `steps-cmd-warns-on-known-seams` (test): When a step listed in
  `KNOWN_SEAMS` (check-skills.py's list of the steps that ran more than one command before the seam rule) runs more than one command with no marker, `steps` passes it
  with a warning naming its issue, and fails the entry once the step runs one
  command, gains a marker or is gone.
- `ci-runs-steps-for-seams` (check): When a pull request is opened or updated,
  CI runs `steps`.

## need contributor-reads-shared-flags: Read every script's flags the same way

When a contributor runs or writes a repo script, they want each shared flag
to mean the same thing in every script that has it, so a skill can read any
result and preview or batch any change the same way. Every command takes
`--json` and `-C/--repo`. A command that writes takes `--dry-run` or
`--partial` only where a requirement names it for that command.

Source: CLAUDE.md, under "Script conventions".

- `command-never-writes-in-preview` (test): When a command that writes is given
  `--dry-run`, it reports what it would write and writes nothing.
- `command-splits-output-streams-without-json` (test): When a command runs
  without `--json`, it prints its result on stdout, and its warnings and
  errors on stderr.
- `command-applies-rest-if-partial` (test): When a command that writes a batch
  refuses part of it, it writes nothing and exits 1, and with `--partial` it
  writes the rest and still exits 1.
- `command-prints-json-envelope` (test): When a command is given `--json`, it
  prints one object on stdout with the keys `version`, `command`, `ok`,
  `errors`, `warnings` and `data`, and nothing on stderr, whether or not it
  found problems.

## need contributor-reads-exit-codes: Act on any repo script's exit code alone

When CI, a skill or a contributor runs a repo script, they want its exit code
to say whether it ran clean, found problems or could not run, and a stop to
say what to do next, so the caller can act without a table of remedies and a
test can drive any command through `main(argv)`.

Source: CLAUDE.md, under "Script conventions", and #24, "Importing the module
does nothing".

- `script-exits-2-when-unrunnable` (test): When a repo script cannot run, it writes its name and the cause to stderr and exits 2. It cannot run from any of these causes:
  - bad usage.
  - running outside a clone.
  - `-C` naming a missing directory.
  - a file it needs being missing or unreadable.
- `script-names-remedy-on-stop` (test): When a repo script stops, its message
  says what to do next.
- `script-does-nothing-on-import` (test): When a repo script is imported, it
  does nothing, and each `main(argv)` call starts without state from an
  earlier one.
- `script-ignores-closed-pipe` (test): When stdout closes before a repo script
  finishes printing, it exits 0 without a traceback.

## need user-installs-from-marketplace: Install any plugin from one marketplace

When the user wants one of the owner's plugins, they want to add the
marketplace once and install any
plugin listed in it, so each plugin does not need any setup of its own.

Source: README.md, under "Adding this marketplace".

- `ci-validates-manifests` (check): When a pull request is opened or
  updated, CI runs the latest `claude plugin validate --strict` on the
  catalog and on every plugin directory with a plugin.json, and fails when it
  does not find a plugin directory.
- `ci-prints-cli-version` (check): When CI validates the manifests, it prints
  the version of the Claude Code CLI it installed, so a failure that a new
  release brings can be traced to that release.
- `check-cmd-fails-uncataloged-plugin` (test): When a directory under
  `plugins/` holds a plugin.json and no catalog entry names it,
  `check-manifest-consistency.py check` fails it.

## need owner-ships-only-runtime-files: Install only what a plugin runs

When the user installs a plugin, the owner wants the install to hold only what
the user needs to run it, so a contributor-only file, such as a test or a
spec, never ships to a user.

Source: the owner's review of #139, and CLAUDE.md, under "Tests".

- `placement-cmd-fails-plugin-tests` (check): When a pull request adds a
  test file under `plugins/`, `check-tests.py placement` fails it.
- `placement-cmd-names-test-destination` (test): When a test file, a
  `conftest.py`, a file in a `tests/` directory, or a script importing pytest
  or hypothesis sits under `plugins/`, `placement` fails it, says it ships to
  every user, and names where it goes.
- `placement-cmd-reads-git` (test): When `placement` lists files, it reads
  every file git carries, tracked or not yet added, and skips what git
  ignores.

## need user-knows-plugin-surface: Know which surface a plugin needs before installing it

When the user chooses a plugin, they want its description to say whether it
needs Cowork, Claude Code or either, so a plugin installed on the wrong surface
does not fail confusingly.

Source: README.md, the opening section, and "Adding a plugin", step 3.

## need owner-approves-work: Work only on what the owner approved

When an issue is filed, the owner wants to decide whether it gets worked on,
so an agent posting under the owner's account cannot approve its own work.

Source: README.md, under "Issues" and "Keeping `approved` meaningful".

- `claim-cmd-refuses-unapproved-issues` (test): When `flywheel.py claim N`
  is given an issue that lacks `approved`, or is closed and so finished, it
  exits 1 and writes nothing.
- `checklinkedissues-cmd-requires-approved-issues` (test): When a pull
  request's title, body or a commit message closes an issue in this repository
  that lacks `approved`, check-linked-issues.py fails and says to re-run the
  job once it is labeled.
- `checklinkedissues-cmd-reads-closing-keywords` (test): When text names
  an issue with a closing keyword outside a code span, a fence or an HTML
  comment, check-linked-issues.py counts it as a link, and counts nothing
  else.
- `checklinkedissues-cmd-fails-non-issue-numbers` (test): When a closing
  keyword names a number that does not exist or is a pull request,
  check-linked-issues.py fails it.
- `checklinkedissues-cmd-fails-other-repo-issues` (test): When a closing
  keyword names another repository's issue, check-linked-issues.py fails it
  without looking it up.
- `checklinkedissues-cmd-passes-unlinked-requests` (test): When a pull
  request does not close an issue, check-linked-issues.py passes it from any branch.
- `checklinkedissues-cmd-stops-on-failed-listing` (test): When
  check-linked-issues.py cannot read a pull request's commits or the claim
  branches, it exits 2 before printing any links.
- `ci-runs-checklinkedissues` (check): When a pull request is opened, edited
  or updated, CI runs check-linked-issues.py.
- `changes-cmd-fails-post-approval-edits` (test): When an issue a pull
  request closes was edited after `approved` was last added to it, `changes`
  fails the pull request and says to re-add the label.
- `guard-blocks-approved-label` (test): When Claude Code runs a Bash command
  that names `approved` in one of the `gh` commands below, issue_guard.py
  exits 2 with the reason on stderr. The command counts bare, after a variable
  assignment, after `env` or `xargs`, inside `sh -c` or `bash -c`, and through
  a full path to `gh`. The `gh` commands it blocks are:
  - `gh issue create`, `gh issue edit`, `gh pr create` or `gh pr edit`, with
    `approved` in the value of `--label`, `-l` or `--add-label`.
  - `gh label edit` renaming a label to `approved`.
  - `gh api`, with an argument that mentions labels and one that names
    `approved`.
- `guard-allows-quoted-text` (test): When a command only quotes such a
  command, in an argument or a heredoc body, or reads, removes or creates the
  label, issue_guard.py exits 0 and prints nothing.
- `guard-scans-unparsed-input` (test): When the hook's input fails to parse as
  JSON, or its command cannot be split, issue_guard.py blocks it if the raw
  text names `gh`, a label flag and `approved`, and allows it otherwise.
- `settingsjson-registers-guard` (test): When Claude Code runs a Bash command
  in this repo, `.claude/settings.json` runs issue_guard.py first, with 10
  seconds to answer.

## need owner-keeps-claims-exclusive: Keep two agents off the same issue

When two agents are told to take the next issue at the same time, the owner
wants each to get a different one, so two agents never do the same work.

Source: README.md, under "Claiming an issue". specs/flywheel.md holds the
requirements the flywheel plugin meets under this need.

- `checklinkedissues-cmd-requires-claim-branch` (test): When a pull
  request closes #N and does not come from `issue/N` in this repository,
  check-linked-issues.py fails it.
- `checklinkedissues-cmd-fails-foreign-claims` (test): When a pull request
  also closes an issue that another `issue/M` branch holds,
  check-linked-issues.py fails it.

## need owner-sees-claim-outcome: Know at once whether a claim won

When an agent claims an issue, the owner wants to know at once whether the
claim won, so the owner can tell a working agent from a stuck one. A
command's output does not reliably reach the owner, under
`bash-hides-output`, so the agent says so in chat.

Source: #469. flywheel's `workissue-claims-first`, in specs/flywheel.md, is
the requirement that serves this need.

## need owner-sees-held-issues: See from the issue list which issues are held

When an agent or the owner looks at the issue list, they want a claimed issue
to show as claimed, and a label that disagrees with its branch to be reported,
so a reader never takes a stale label for a claim.

Source: README.md, under "Claiming an issue", and #33. specs/flywheel.md
holds the requirements the flywheel plugin meets under this need.

- `issueclosed-clears-claim-label` (check): When an issue carrying the
  claim label closes, issue-closed.yml removes the label. It reads the claim
  label from `.flywheel/labels.json`, and `claimed` when the file does not
  give one.

## need owner-sees-finished-plans-closed: See a finished plan closed

When the last issue of a plan closes, the owner wants the plan's tracking
issue closed with it, so an open tracking issue always means work remains.

Source: the owner's request on 2026-10-21, recorded in #732 and #733, with
#729 as the example. specs/flywheel.md holds the requirements the flywheel
plugin meets under this need.

- `issueclosed-closes-finished-plan` (check): When an issue closes,
  issue-closed.yml runs `flywheel.py plan close --sub-issue` on it, so the
  plan issue that holds it closes once every one of its sub-issues is closed.

## need owner-prevents-stale-branches: Keep finished branches from piling up

When a session's work has merged or was never started, the owner wants every
local branch it left removed without typing git commands, so the clone keeps
only live branches.

Source: #294, and README.md, under "Claiming an issue". specs/flywheel.md
holds the requirements the flywheel plugin meets under this need.

- `branchsweep-reports-deleted-branches` (test): When branch_sweep.py's sweep
  deletes branches, the hook names them on stdout in one line, and stays
  silent when it does not delete a branch.
- `branchsweep-never-blocks` (test): When `flywheel.py sweep` fails, does not
  print a result or runs past the hook's own time limit, branch_sweep.py exits 0 and
  prints one line saying why and naming the command to run by hand.
- `settingsjson-registers-branch-sweep` (test): When a Claude Code session
  starts in this repo, `.claude/settings.json` runs branch_sweep.py, with 30
  seconds to answer.

## need owner-runs-merged-flywheel: Run the merged flywheel in the next session

When a pull request that changes flywheel merges, the owner wants the next
session in this repository to run the merged flywheel, so a plan's later
issues are worked under its earlier fixes.

Source: #814. This repository enables flywheel from its own directory, and the
desktop app reads that directory from the main checkout and cuts each new
worktree from its local `main`. specs/flywheel.md holds the requirements the
flywheel plugin meets under this need.

## need contributor-catches-stale-commands: Catch a skill that names a missing command

When a contributor renames a script's subcommand or flag, they want CI to fail
every skill that still names the old one, so the failure shows in the pull
request rather than part way through a user's run.

Source: README.md, under "Adding a plugin", step 4.

- `commands-cmd-parses-invocations` (test): When a shell fence runs a
  plugin script, `check-skills.py commands` passes its arguments through that
  script's `build_parser()`, and fails what the parser rejects, naming the
  file and line.
- `commands-cmd-finds-named-script` (test): When an invocation names its
  script through a variable or a path, `commands` finds the script, and fails any of these:
  - an unassigned variable.
  - a variable naming two scripts.
  - a script that is missing, fails to import or has no parser.
- `commands-cmd-handles-fence-syntax` (test): When a fence writes a command with any of these parts, `commands` checks it as the model would run it, and reads only shell fences:
  - a placeholder.
  - an optional part.
  - a continuation.
  - a comment.
  - a heredoc.
  - a list indent.
- `commands-cmd-scans-something` (test): When `commands` does not find a shell
  fence that runs a script, it fails.
- `ci-runs-commands` (check): When a pull request is opened or updated, CI runs
  `commands`.

## need owner-knows-each-step-command: Know which command does each skill step's work

When a contributor writes a skill step, the owner wants it to name the command
that does its work, or say why it has no command, so every step that leaves
work to the model says so.

Source: CLAUDE.md, under "Skills and scripts", and #98.

- `steps-cmd-counts-step-commands` (test): When a `## Step` section runs
  an invocation `commands` accepts, `check-skills.py steps` counts it for that
  step, and otherwise fails the step unless it carries a no-command marker (a `<!-- no-command: <reason> -->` line saying why the step lacks a command).
- `steps-cmd-checks-no-command-markers` (test): When any of these holds of a no-command marker, `steps` fails it:
  - it has no reason.
  - it shares its line with other text.
  - it sits outside a step.
  - it sits on a step that runs a command.
- `steps-cmd-fails-stray-commands` (test): When a SKILL.md runs
  an invocation `commands` accepts outside every `## Step` section and outside
  "Locate the script", `steps` fails it.
- `steps-cmd-scans-something` (test): When `steps` does not find a SKILL.md
  with a step, it fails.
- `checkskills-cmd-reads-project-skills` (test): When a skill sits at
  `.claude/skills/<skill>/SKILL.md`, `check-skills.py commands`, `steps` and
  `fences` check it as they check a plugin's skill, and read a script path it
  names from the root of the clone. `repeats` and `descriptions` leave it
  out.
- `ci-runs-steps` (check): When a pull request is opened or updated, CI runs
  `steps`.

## need owner-keeps-computing-in-scripts: Keep a skill's shell blocks to running its script

When a contributor writes a shell block into a skill, the owner wants it to
run the plugin's script and nothing that computes beside it, so work that
should give the same answer on every run is done by the script.

Source: CLAUDE.md, under "Skills and scripts", and #97.

- `fences-cmd-rejects-other-commands` (test): When a shell fence in a
  skill runs anything but a script invocation, such as `python3 -c` or a stage
  of a pipeline, `check-skills.py fences` fails it and names the file, line
  and command.
- `fences-cmd-requires-info-strings` (test): When a fence has no info
  string, or is labeled `bash` or `shell` rather than `sh`, `fences` fails
  it.
- `fences-cmd-allows-setup-commands` (test): When a shell fence runs an
  allowed setup command where it may stand, `fences` passes it, and fails the
  same command anywhere else.
- `fences-cmd-scans-something` (test): When `fences` does not find a shell
  fence, it fails.
- `ci-runs-fences` (check): When a pull request is opened or updated, CI runs
  `fences`.

## need contributor-writes-shared-steps-once: Keep a step two skills share in one place

When two skills of one plugin need the same step, a contributor wants it
written once, in the plugin's `reference/`, and CI to fail a copy, so the two
copies cannot drift apart.

Source: CLAUDE.md, under "Skills in a plugin share instructions through one
file", README.md, under "Adding a plugin", step 2, and #54.

- `repeats-cmd-fails-copied-blocks` (test): When two SKILL.md files of one
  plugin share a paragraph, a table, a fenced block or a list item, whitespace
  aside, `check-skills.py repeats` fails and names each file and the line each
  copy starts on.
- `repeats-cmd-passes-exempt-blocks` (test): When the shared block is the
  section that locates the script, a heading or front matter, `repeats` passes
  it, and it checks a section under any other heading.
- `repeats-cmd-only-compares-sibling-skills` (test): When a block repeats
  across two plugins, or twice within one skill, `repeats` passes it.
- `repeats-cmd-skips-markers` (test): When two of a plugin's skills carry
  the same comment line, such as one spec marker, `repeats` does not report it
  as a copied block.
- `repeats-cmd-scans-something` (test): When `repeats` does not find a SKILL.md
  that yields a block, it fails.
- `ci-runs-repeats` (check): When a pull request is opened or updated, CI runs
  `repeats`.

## need contributor-keeps-skills-uploadable: Keep every skill uploadable to Cowork

When a contributor writes a skill's description, they want CI to fail one that
Cowork's `.plugin` upload would reject, so the user can install the plugin on
Cowork even though a marketplace install and `--strict` accept it.

Source: README.md, under "Adding a plugin", step 4.

- `descriptions-cmd-fails-named-tags` (test): When a description holds `<`
  or `</` followed by a name, on its first line or a continuation,
  `check-skills.py descriptions` fails and names the file, line and tag.
- `descriptions-cmd-passes-lone-less-than` (test): When a description
  holds a `<` that no name follows, `descriptions` passes it.
- `descriptions-cmd-reads-templates` (test): When a markdown file under
  `plugins/` other than SKILL.md has a description, such as a generated-skill
  template, `descriptions` checks it.
- `descriptions-cmd-only-checks-descriptions` (test): When a tag sits
  outside the description, in the body, in another front matter key or in
  markdown outside `plugins/`, `descriptions` passes it.
- `descriptions-cmd-scans-something` (test): When every file under `plugins/`
  lacks a description, `descriptions` fails.
- `ci-runs-descriptions` (check): When a pull request is opened or updated, CI
  runs `descriptions`.

## need contributor-validates-before-push: Run CI's checks before pushing

When a contributor changes the repo, they want to run CI's checks before
pushing and get CI's answer, or be told why a local run cannot give it. A
contributor adding a skill runs the skill checks before committing it, so the
checks read files git does not track yet.

Source: README.md, under "Adding a plugin", step 4: "Run the `verify`
gate, then push", and #284.

- `checkskills-cmd-reads-unignored-files` (test): When a skill file is
  committed, or new and not yet added, each check-skills.py command reads it,
  and skips a file git ignores.
- `floors-cmd-names-floor-version` (test): When the Python running
  `check-coverage.py floors` is not the version the floors (each script's lowest allowed test coverage) were measured on,
  `floors` exits 2 and names that version, rather than telling the
  contributor to add tests.

## need contributor-runs-one-gate-command: Run one command for each gate CI runs

When a contributor or an agent finishes a unit or readies a pull request, they
want one command for each gate that CI runs unchanged, so the local gate and
CI cannot drift and a green test run is never mistaken for a done unit.

Source: the playbook's `one-command-per-gate` and `checks-over-instructions`,
and #646.

- `build-cmd-builds-nothing` (test): When `gate.py build` runs, it says the
  repo has nothing to build and exits 0.
- `test-cmd-runs-suite-without-coverage` (test): When `gate.py test` runs, it
  runs the suite without coverage, and exits 1 when the suite fails.
- `check-cmd-runs-every-local-check` (test): When `gate.py check` runs, it
  runs the formatter and linter, the suite with coverage and every repo check
  that needs no network, and exits 1 when any does.
- `verify-cmd-runs-check-first` (test): When `gate.py verify` runs, it runs
  `check` and then the checks that read the base branch, given by
  `verify --base`, or the pull request, and prints its chain first.
- `gate-cmd-names-skipped-checks` (test): When a gate command meets a check
  that cannot give CI's answer on this machine, it skips the check and names
  it and the reason. `floors` off its Python version is one such check, and a
  check that reads the pull request outside a pull_request event is another.
- `gate-cmd-finds-tools-first` (test): When a tool a gate command's steps run
  is missing, the command names it and its install, and exits 2 before
  running any step.
- `ci-runs-verify` (check): When a pull request is opened or updated, CI runs
  `verify`.

## need contributor-keeps-manifests-in-step: Keep the two manifests in step

When a contributor bumps a plugin's version or edits its manifest, they want
CI to fail a catalog entry that disagrees with the plugin's own manifest, so
two files that each validate cannot drift apart.

Source: README.md, under "Adding a plugin", step 4.

- `check-cmd-fails-version-drift` (test): When a catalog entry's `version`
  differs from its plugin.json's, `check-manifest-consistency.py check` fails
  and names both.
- `check-cmd-fails-name-drift` (test): When plugin.json's `name`, or the
  source directory's name, differs from the entry's `name`, `check` fails it.
- `check-cmd-requires-source-manifest` (test): When a catalog entry's
  source directory does not hold a plugin.json, `check` fails it.
- `check-cmd-requires-entry-fields` (test): When a catalog entry lacks
  `name`, `source`, `description` or `version`, `check` names the field and
  fails.
- `check-cmd-requires-catalog` (test): When the catalog is missing or
  does not list any plugins, `check` fails.
- `ci-runs-manifest-check` (check): When a pull request is opened or updated,
  CI runs `check`.

## need owner-ships-every-rule-change: Ship each rule change made in this repo

When a contributor changes a rule in this repo's
`.claude/rules/prose-style.md`, the owner wants the same change in the rules
prose-tuning ships (`plugins/prose-tuning/templates/prose-style.md`), so every
new project starts from the voice the owner forms here.

Source: #621.

- `drift-cmd-fails-missing-rule` (test): When a rule id is in one of the two
  files and not the other, `check-prose-rules.py drift` fails and names the
  rule and the file that lacks it.
- `drift-cmd-fails-changed-rule` (test): When a rule's heading or text
  differs between the two files, `drift` fails and quotes where the two
  copies part.
- `drift-cmd-skips-project-text` (test): When the two copies of a rule differ only in any of these, `drift` passes the rule:
  - the worked examples, the `> **Before.**` and `> **After.**` lines.
  - text this repo's copy has where the shipped rules have a `FILL` marker.
  - line breaks and runs of spaces.
- `drift-cmd-names-copyprose` (test): When `drift` fails a rule, its message
  names copy-prose as the remedy.
- `drift-cmd-scans-something` (test): When either file does not hold any
  rule, `drift` fails.
- `ci-runs-drift` (check): When a pull request is opened or updated, CI runs
  `drift`.

## need owner-sees-every-line-tested: Know every plugin line runs under a test

When a contributor changes a plugin script, the owner wants CI to fail a
script whose coverage falls below its floor, or a new line that no test runs,
so the coverage check catches each line that the trace (`check-specs.py trace`, which ties each test to a requirement) would miss.

Source: #128, README.md, under "Coverage", and SPEC-METHODOLOGY.md, under
"The chain".

- `floors-cmd-fails-below-floor` (test): When a plugin script's branch
  coverage is below its floor in `.github/coverage-floors.json`,
  `check-coverage.py floors` fails and names the script, its figure and its
  floor.
- `floors-cmd-warns-to-raise-floor` (test): When a script's figure passes
  its floor, `floors` warns with the figure, to two decimals, to raise the
  floor to.
- `floors-cmd-fails-lowered-floor-with-base` (test): When a floor is lower
  than at `--base`, `floors` fails it.
- `floors-cmd-requires-new-script-floor` (test): When a plugin script has
  no floor, `floors` fails it and prints the figure to use.
- `floors-cmd-fails-stray-floor` (test): When the floors file holds a
  floor for a path that is not a plugin script, `floors` fails it, so the file
  lists exactly the plugin scripts.
- `floors-cmd-fails-unmeasured-script` (test): When the report leaves out
  a plugin script, `floors` fails the script and `diff` fails its added lines.
- `checkcoverage-cmd-requires-branch-report` (test): When the report was
  measured without branch coverage, check-coverage.py exits 2.
- `diff-cmd-fails-unrun-added-line` (test): When a pull request adds a
  plugin line that no test runs, `check-coverage.py diff` names it and fails,
  counting from the merge base, and every line of a new script counts as
  added.
- `pragmas-cmd-requires-reasons` (test): When a coverage exclusion, in any
  spelling coverage.py accepts, does not give a reason on its line,
  `check-coverage.py pragmas` fails it.
- `checkcoverage-cmd-scans-something` (test): When the clone does not hold a
  plugin script, each check-coverage.py command exits 2.
- `ci-runs-floors` (check): When a pull request is opened or updated, or main
  is pushed, CI runs `floors`, with `--base` set to a pull request's base.
- `ci-runs-diff` (check): When a pull request is opened or updated, CI runs
  `diff` against its base.
- `ci-runs-pragmas` (check): When a pull request is opened or updated, CI runs
  `pragmas`.
- `ci-runs-suite-under-coverage` (check): When a pull request is opened or
  updated, CI runs the whole suite under coverage, with pytest's config and
  markers checked, on Python 3.9 and 3.13, and lets each finish when the other
  fails.

## need contributor-knows-each-test-runs: Run every test the suite appears to have

When a contributor writes a test, they want CI to fail one that pytest would
not collect, by where it sits or by its name, so every test in the suite runs.

Source: README.md, under "Running the tests", CLAUDE.md, under "Tests", and
#22 and #26.

- `placement-cmd-fails-tests-outside-roots` (test): When a test file sits
  outside every `testpaths` root in pytest.ini, `check-tests.py placement`
  fails it.
- `naming-cmd-fails-old-test-names` (test): When a test file holds `def
  test_` or `class Test` at any indent, `check-tests.py naming` fails and
  names the file and line.
- `naming-cmd-scans-something` (test): When `naming` does not find a test file
  overall, or in any `testpaths` root that exists, it fails.
- `ci-runs-placement-and-naming` (check): When a pull request is opened or
  updated, CI runs `placement` and `naming`.

## need owner-trusts-each-new-test: Know each new test can fail

When an agent adds a test, the owner wants CI to fail a pull request whose
new test passes on the code before the change, unless the test says why.
This repo runs the flywheel plugin's check for it, at the cost of one run of
each new test at the branch and one on the base.

Source: the playbook's `agents-never-weaken-checks`, CLAUDE.md, under "Tests",
#669 and #682. specs/flywheel.md has the check's own requirements, under
`owner-checks-new-tests-fail`.

- `ci-runs-fails-on-base` (check): When a pull request is opened or updated,
  CI runs `flywheel.py fails-on-base` against its base, with the pytest
  commands in `.flywheel/gates.json`.

## need owner-keeps-one-code-style: Keep one code style, applied by tools

When anyone edits Python or shell in this repo, the owner wants formatting and
lint applied by tools and enforced in CI, so style is never argued about in
review.

Source: README.md, under "Formatting and linting" and "Shell scripts".

- `ruffhook-prefers-own-venv` (test): When the project has its own `.venv`
  holding ruff, the ruff hook uses it.
- `ruffhook-borrows-main-venv` (test): When the ruff hook runs in a worktree
  with no `.venv` of its own, it uses the main checkout's.
- `ruffhook-falls-back-to-path` (test): When ruff is not in any `.venv`, the
  ruff hook uses the ruff on PATH.
- `ruffhook-formats-edit` (test): When Claude Code writes or edits a `.py`
  file, the ruff hook sorts its imports and formats it, and leaves every other
  file alone.
- `ruffhook-reports-lint` (test): When lint problems remain after formatting,
  the ruff hook exits 2 with the findings on stderr.
- `ruffhook-reports-parse-error` (test): When ruff cannot format the file, the
  ruff hook exits 2 with ruff's error.
- `ruffhook-names-ruff-install` (test): When the ruff hook does not find ruff,
  it exits 2 and names the command that installs it.
- `settingsjson-registers-ruff-hook` (test): When Claude Code writes or edits
  a file in this repo, `.claude/settings.json` runs the ruff hook, with 30
  seconds to answer.
- `ci-checks-python-formatting` (check): When a pull request is opened or
  updated, CI checks the Python formatting.
- `ci-lints-python` (check): When a pull request is opened or updated, CI lints
  the Python.
- `ci-lints-shell` (check): When a pull request is opened or updated, CI
  checks each shell script parses and passes shellcheck, and fails when it
  does not find a shell script.

## need owner-traces-behavior-to-needs: Tie each behavior to the need behind it

When a contributor adds a behavior, the owner wants CI to tie each test and
skill step to a requirement in `specs/`, so every behavior arrives with a need
that asked for it, and every requirement keeps something that verifies it.

Source: #114, #129, and SPEC-METHODOLOGY.md, under "The chain".

- `trace-cmd-fails-uncited-tests-and-skills` (test): When a test or a skill
  step does not cite a requirement and is missing from `.github/untraced.json`,
  `check-specs.py trace` fails it.
- `trace-cmd-fails-unknown-ids` (test): When a test, a skill step or a
  workflow step cites an id its component's spec does not hold, `trace` fails
  the citation.
- `trace-cmd-fails-unverified-requirements` (test): When a
  requirement is not cited by anything of its kind, `trace` fails the
  requirement. Each kind is cited by:
  - `test`: a test.
  - `step`: a skill step.
  - `check`: a workflow step.
- `trace-cmd-warns-on-waiting-items` (test): When `.github/untraced.json`
  lists a test or a step that cites nothing, and the issue it waits on is
  open, `trace` passes it with a warning naming that issue.
- `trace-cmd-fails-closed-issue-entries` (test): When an entry in
  `.github/untraced.json`, or a step in check-skills.py's `KNOWN_SEAMS`, waits
  on an issue that has closed, `trace` fails the entry. It stops on an issue
  it cannot read, and without a token it warns that it skipped the lookup.
- `trace-cmd-fails-stale-list-entries` (test): When a listed test or step
  cites a requirement, or no longer exists, `trace` fails until its entry is
  removed.
- `trace-cmd-checks-spec-grammar` (test): When `trace` reads a spec file,
  it fails each of these it finds:
  - a requirement outside a need or a constraint.
  - a malformed requirement, at or below the section's `Source:` line or
    its first requirement.
  - a need, constraint or requirement id not in the form SPEC-METHODOLOGY.md
    gives under "Ids".
  - a duplicate id.
  - a kind that nothing in the repo verifies.
- `trace-cmd-scans-something` (test): When `trace` does not find any spec,
  test or skill step, it fails.
- `trace-cmd-reads-project-skills` (test): When a step of a skill under
  `.claude/skills/` cites a requirement, `trace` reads the citation against
  `specs/repo.md`.
- `ci-runs-trace` (check): When a pull request is opened or updated, CI runs
  `trace`.
- `inventory-cmd-lists-parser-surface` (test): When `check-specs.py
  inventory` lists a plugin, it gives every subcommand, option and `choices`
  value its script's `build_parser()` accepts, each with the skill text that
  names it. Skill text names an option or a value only when it gives the
  option's own command first.
- `inventory-cmd-lists-string-collections` (test): When `inventory` lists
  a plugin, it gives every module-level set, tuple or list of strings in its
  script.
- `inventory-cmd-lists-tests` (test): When `inventory` lists a plugin, it
  gives every test in `tests/<plugin>/`, with the script lines each one runs.
- `inventory-cmd-lists-skill-steps` (test): When `inventory` lists a
  plugin, it gives every step of its skills, with the commands each one runs.
- `inventory-cmd-lists-unrun-lines` (test): When `inventory` lists a
  plugin, it gives every line of its script that no test runs.
- `inventory-cmd-requires-per-test-report` (test): When the coverage
  report does not say which test ran each line, `inventory` stops and names
  the command that writes one that does.
- `inventory-cmd-refuses-unknown-coverage-schema` (test): When the
  coverage data file records a schema version other than the one
  `inventory` reads, `inventory` stops and names both versions.
- `surface-cmd-fails-unnamed-options` (test): When a subcommand, option or
  `choices` value of a plugin script or a repo script is not named in backticks by
  any requirement in its component's spec or in `specs/repo.md`,
  `check-specs.py surface` fails it.
- `surface-cmd-warns-on-listed-items` (test): When the `surface` section of
  `.github/untraced.json` lists an item that no requirement names, `surface`
  passes it with a warning naming its issue, and fails an entry whose item is
  named or gone.
- `surface-cmd-scans-something` (test): When `surface` does not find a script
  with a `build_parser()`, it fails.
- `ci-runs-surface` (check): When a pull request is opened or updated, CI runs
  `surface`.
- `changes-cmd-fails-unnamed-requirement-changes` (test): When a pull request
  adds, changes or removes a requirement, and its description does not name
  the id in backticks, `check-specs.py changes` fails it.
- `changes-cmd-requires-issue-for-section` (test): When a pull request
  adds a need or a constraint that no issue it closes names, `changes`
  fails it.
- `ci-runs-changes` (check): When a pull request is opened, edited or
  updated, CI runs `changes`.

## need owner-styles-specs-like-docs: Hold a spec's text to the house prose style

When a contributor runs a style pass over `specs/`, the owner wants a spec to
follow `.claude/rules/prose-style.md` as every other document does, so a style
pass never has to leave a rule's breach in place because the spec grammar
refuses its fix.

Source: #530, raised in the review of #527.

- `trace-cmd-reads-lists-in-text` (test): When a need's or a constraint's
  text holds a bulleted list above its `Source:` line and its first
  requirement, `trace` reads the list as text.

## need owner-reviews-from-description: Review a pull request from its scenario

When the owner reviews a pull request, the owner wants its description to
set up the scenario it changes, in terms the owner can read without the
plugin's code, so the review starts from what changes for whom.

Source: #566, #567, #717, and CLAUDE.md, under "Workflow".

- `ci-runs-description` (check): When a pull request is opened, edited or
  updated, CI runs `gate.py verify`, whose `description` step checks the
  description with the flywheel plugin's `pr check`, against the shape
  `.flywheel/pr-template.md` gives.
- `verify-cmd-checks-description-with-flywheel` (test): When `gate.py verify`
  runs on a pull_request event, it writes the pull request's description from
  `$GITHUB_EVENT_PATH` to a file of its own, and runs
  `flywheel.py pr check --body-file <file>` on it as its `description` step.
  When it cannot read the description from the event, it stops before any
  step and names the variable.
- `settings-enables-flywheel` (test): When a Claude Code session opens in this
  repository, `.claude/settings.json` names the repository as a directory
  marketplace and enables flywheel from it, so the session has flywheel's
  open-pr skill and its cold reader, the agent that reads a draft without the
  session's context.

## constraint marketplace-serves-repo-as-is: The marketplace is this repository as it stands

Claude reads the marketplace straight from this repository's GitHub address.
CI does not build a package in between, so an install copies a plugin's
directory whole, and a file stays out of an install only by sitting outside
`plugins/<plugin>/`.

Source: the owner's review of #139, and README.md, under "Adding this
marketplace" and "Layout".

## constraint bridge-cannot-delete: Cowork's device bridge cannot delete files

Cowork's **device bridge** is the set of tools, such as `device_bash`, that
reach the user's folder from Cowork's cloud container. A git write through the
bridge strands a `.git/*.lock` that blocks every
later write. The constraint binds every plugin script that runs on the user's
device through the bridge.

Source: CLAUDE.md, under "Script conventions", and COWORK.md.

## constraint proposeskills-takes-one-file: propose_skills takes a single SKILL.md

Cowork's `propose_skills` delivers one `SKILL.md` without any bundled files, so
a plugin that bundles a script cannot reach Cowork that way.

Source: README.md, under "Adding a plugin", step 2.

## constraint github-closes-keyword-named-issues: GitHub closes an issue named by a closing keyword

GitHub closes an issue when a merged pull request's title, body or commits
name it after close, fix or resolve, or one of their variants, as `#N` or
`owner/repo#N`.

Source: GitHub's "Linking a pull request to an issue", and #15.

## constraint github-ignores-name-case: GitHub reads label and repository names without case

GitHub finds a label or a repository whatever the case of the name it is
given, and refuses a second label whose name differs from one already there
only in case. So `Approved` on an issue is the `approved` label renamed, and
`scotthysom/Claude-Plugins` names this repository.

Source: the probe recorded in #227, where `gh api` returned `bug` for
`labels/BUG` and `labels/Bug`, and `ScottHysom/claude-plugins` for
`repos/SCOTTHYSOM/CLAUDE-PLUGINS`; and git-bug's report that GitHub refuses
the label `Bug` beside `bug` with "Name has already been taken".

- `checklinkedissues-cmd-ignores-name-case` (test): When an issue a pull
  request closes carries `approved` in another case, or a closing keyword
  names this repository in another case, check-linked-issues.py reads the
  label as `approved` and the issue as one in this repository.
- `claim-cmd-ignores-label-case` (test): When an issue carries `approved` in
  another case, `flywheel.py claim` claims it as it claims one labeled
  `approved`.
- `changes-cmd-ignores-label-case` (test): When an issue a pull request closes
  was given `approved` in another case, `changes` reads that as the time it
  was approved.

## constraint app-only-watches-own-opened-pr: The desktop app turns on Auto-fix only for a pull request the session's own command opened

The desktop app's **Auto-fix** wakes a session when CI fails on its pull
request. The app turns it on only for a pull request it saw the session open,
and it sees that when the session's own Bash command runs `gh pr create`.

Source: #830, and the probe in pull request #829, where `get_status` reported
the pull request as the session's and `set_monitor` turned Auto-fix on after
the session ran `gh pr create` itself.

- `fences-cmd-allows-pr-create-after-script` (test): When a shell fence runs
  `gh pr create --title <title> --body-file <path>` straight after a run of
  the script through `&&`, as the last command of the line, `fences` passes it,
  and fails `gh pr create` anywhere else and every other `gh` command.

## constraint hook-blocks-on-exit-2: A Claude Code hook that exits 2 blocks the call

A PreToolUse hook is a command that Claude Code runs before each tool call. One
that exits 2 stops the tool call, and Claude Code hands the hook's stderr back
to Claude.

Source: Claude Code's hooks documentation, and #15, which tried it live.

## constraint macos-ships-python-39: The Python on a user's machine may be 3.9

macOS ships Python 3.9 as its system Python, so a plugin script that runs
where it lands runs on 3.9.

Source: README.md, under "Running the tests", and CLAUDE.md, under "Script
conventions".

## constraint github-keeps-filed-issues: A filed issue cannot be counted on to come back

Deleting an issue takes admin rights on the repository, so a script cannot
count on undoing an issue it filed. For the same reason, a batch cannot be
filed all or nothing. This is the repo's own copy of the constraint in
`specs/todos.md`.

Source: GitHub's documentation, "Deleting an issue".

- `planfile-cmd-resumes-after-failed-call` (test): When a GitHub call fails,
  `plan file` stops, lists what it filed and exits 1, and a later run of the
  same plan files only what is missing. It refuses a plan it has finished
  filing.

## constraint bash-hides-output: A command's output does not reliably reach the user

Claude Code shows a Bash command's output to the model and not reliably to
the user, and an `AskUserQuestion` dialog covers the text above it. So a
report the owner must approve reaches them as a file or a page, not as a
command's output. This is the repo's own copy of the constraint in
`specs/todos.md`.

Source: Claude Code's Bash tool description, and the owner's report in #334.

- `planreport-cmd-writes-report-file` (test): When `plan report` runs, it
  writes the report it prints as markdown to `.flywheel/plan/report.md`,
  which git ignores. The file ends with the approval token, or holds the faults and
  no token.

## constraint bash-stops-waiting: The Bash tool stops waiting for a command after 120 seconds

Claude Code's Bash tool stops waiting for a command after 120 seconds, unless
the call sets a longer `timeout`, and after 600 seconds at most. So the whole
suite, run as README.md gives it, has to finish within 120 seconds for an agent
to see its result.

Source: Claude Code's Bash tool description, and #573 and #577.

- `suite-runs-across-cores` (check): When a pull request is opened or updated,
  CI runs the whole suite with the `-n auto` that pytest.ini gives every run,
  one pytest-xdist worker per core, as a contributor's `pytest` runs it.

## constraint github-breaks-body-lines: GitHub breaks a body's lines where a repository file joins them

GitHub renders a newline inside a paragraph or a list item of a pull request
or issue body as a line break, where a markdown file in the repository joins
the lines into one paragraph.

Source: #589, and the rendered body of #587, which holds a `<br>` for each
line its paragraphs were broken at.

- `planreport-cmd-refuses-split-lines` (test): When a plan's draft (an
  issue's body or the plan issue's body) continues a paragraph or a list
  item onto a second line, outside a code fence or an HTML comment,
  `flywheel.py plan report` refuses the draft and names each line.

## constraint artifact-sends-comments: A comment sent to Claude reaches the session

An artifact published from Claude Code is private by default. A comment its
owner sends to Claude reaches the session that published it, which can reply
in the thread. This is the repo's own copy of the constraint in
`specs/todos.md`, which records the probe.

Source: code.claude.com/docs/en/artifacts.md, under "Collect comments on an
artifact", and the probe recorded in #334.

- `fileissue-revises-on-comment` (step): When the owner sends a comment on the
  report's artifact to Claude, the file-issue skill revises the plan, runs
  `plan report` again, publishes the new report at the same address, and
  answers in the comment's thread.

## need owner-measures-loop: Measure the loop before changing a role

When the owner considers a change to how the loop runs (such as how a round
waits on CI) or to a role's model or effort, they want the loop's cost,
first-pass CI rate, review findings, CI's run time, the wait after CI and lead
time over a period, so the change is a trial against a baseline and not a
guess.

Source: #652. specs/flywheel.md holds the requirements the flywheel plugin
meets under this need.

- `ci-runs-stale-and-measure-on-schedule` (check): When the scheduled
  workflow runs, it runs `stale` and `measure` and records the result in one
  issue.

# repo

This file records what the repository as a whole is for: its catalog, its
checks and the conventions every plugin script shares. SPEC-METHODOLOGY.md, at
the repo root, has the grammar of this file and the steps that add its
requirements.

## Out of scope

- Code shared between plugins. Each plugin installs on its own and cannot
  import another's.
- Packages outside the Python standard library in a plugin script.
- Editing this repo from Cowork. Contributors change it from Claude Code, and
  its plugins serve Cowork sessions in the user's own projects.

## need owner-keeps-model-at-seams: Keep the model to judgment and platform seams

When a skill runs script commands, the owner wants the model between two of
them only where it makes a judgment or calls a tool no script can, so no run
spends context on work a script could do, or gets that work wrong.

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
  `KNOWN_SEAMS` runs more than one command with no marker, `steps` passes it
  with a warning naming its issue, and fails the entry once the step runs one
  command, gains a marker or is gone.
- `ci-runs-steps-for-seams` (check): When a pull request is opened or updated,
  CI runs `steps`.

## need contributor-reads-shared-flags: Read every script's flags the same way

When a contributor runs or writes a repo script, they want the flags every
command takes, `--json`, `-C/--repo`, `--dry-run` and `--partial`, to mean the
same thing in each script, so a skill can read any result and preview or batch
any change the same way.

Source: CLAUDE.md, under "Script conventions".

- `command-never-writes-in-preview` (test): When a command that writes is given
  `--dry-run`, it reports what it would write and writes nothing.
- `command-splits-output-streams` (test): When a command runs without
  `--json`, it prints its result on stdout, and its warnings and errors on
  stderr.
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
say what to do next, so the caller needs no table of remedies and a test can
drive any command through `main(argv)`.

Source: CLAUDE.md, under "Script conventions", and #24, "Importing the module
does nothing".

- `script-exits-2-when-unrunnable` (test): When a repo script cannot run, from
  bad usage, from running outside a clone, from `-C` naming a missing
  directory, or from a file it needs being missing or unreadable, it writes
  its name and the cause to stderr and exits 2.
- `script-names-remedy-on-stop` (test): When a repo script stops, its message
  says what to do next.
- `script-does-nothing-on-import` (test): When a repo script is imported, it
  does nothing, and each `main(argv)` call starts with no state from an
  earlier one.
- `script-ignores-closed-pipe` (test): When stdout closes before a repo script
  finishes printing, it exits 0 without a traceback.

## need user-installs-from-marketplace: Install any plugin from one marketplace

When the user wants one of the owner's plugins, they want to add the
marketplace once and install any plugin listed in it, so each plugin needs no
setup of its own.

Source: README.md, under "Adding this marketplace".

- `ci-validates-manifests` (check): When a pull request is opened or
  updated, CI runs the latest `claude plugin validate --strict` on the
  catalog and on every plugin directory with a plugin.json, and fails when it
  finds none.
- `ci-prints-cli-version` (check): When CI validates the manifests, it prints
  the version of the Claude Code CLI it installed, so a failure that a new
  release brings can be traced to that release.
- `check-cmd-fails-uncataloged-plugin` (test): When a directory under
  `plugins/` holds a plugin.json and no catalog entry names it,
  `check-manifest-consistency.py check` fails it.

## need owner-ships-only-runtime-files: Install only what a plugin runs

When the user installs a plugin, the owner wants the install to hold only what
the user needs to run it, so no contributor-only file, such as a test or a
spec, ships to every user.

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

- `claim-cmd-refuses-unapproved-issues` (test): When `issues.py claim N`
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
  request closes no issue, check-linked-issues.py passes it from any branch.
- `checklinkedissues-cmd-stops-on-failed-lookup` (test): When
  check-linked-issues.py cannot read a pull request's commits or the claim
  branches, it exits 2 and prints no links.
- `ci-runs-checklinkedissues` (check): When a pull request is opened, edited
  or updated, CI runs check-linked-issues.py.
- `changes-cmd-fails-post-approval-edits` (test): When an issue a pull
  request closes was edited after `approved` was last added to it, `changes`
  fails the pull request and says to re-add the label.
- `guard-blocks-approved-label` (test): When Claude Code runs a Bash command
  that would add `approved` through `gh`, issue_guard.py exits 2 with the
  reason on stderr. The command counts bare, after a variable assignment,
  after `env` or `xargs`, inside `sh -c` or `bash -c`, and through a full path
  to `gh`.
- `guard-allows-quoted-text` (test): When a command only quotes such a
  command, in an argument or a heredoc body, or reads or removes the label,
  issue_guard.py exits 0 and prints nothing.
- `guard-scans-unparsed-input` (test): When the hook's input is not JSON, or
  its command cannot be split, issue_guard.py blocks it if the raw text names
  `gh`, a label flag and `approved`, and allows it otherwise.
- `settingsjson-registers-guard` (test): When Claude Code runs a Bash command
  in this repo, `.claude/settings.json` runs issue_guard.py first, with 10
  seconds to answer.

## need owner-keeps-claims-exclusive: Keep two agents off the same issue

When two agents are told to take the next issue at the same time, the owner
wants each to get a different one, so no two agents do the same work.

Source: README.md, under "Claiming an issue".

- `next-cmd-offers-free-issue` (test): When `issues.py next` runs, it
  names the lowest-numbered open issue labeled `approved` that no `issue/N`
  branch holds, and exits 0 when none is free.
- `claim-cmd-picks-one-winner` (test): When two agents claim the same
  issue at once, `issues.py claim` lets exactly one create `issue/N`, and the
  other exits 1, names the holder and writes nothing.
- `claim-cmd-switches-to-issue-branch` (test): When `issues.py claim N`
  wins, it switches the clone to `issue/N`, and warns when the switch fails.
- `claim-cmd-stops-on-refused-push` (test): When the push fails and
  `issue/N` does not exist, `issues.py claim` exits 2 and writes nothing to
  the issue.
- `checklinkedissues-cmd-requires-claim-branch` (test): When a pull
  request closes #N and does not come from `issue/N` in this repository,
  check-linked-issues.py fails it.
- `checklinkedissues-cmd-fails-foreign-claims` (test): When a pull request
  also closes an issue that another `issue/M` branch holds,
  check-linked-issues.py fails it.

## need owner-sees-held-issues: See from the issue list which issues are held

When an agent or the owner looks at the issue list, they want a claimed issue
to show as claimed, and a label that disagrees with its branch to be reported,
so nobody reads a stale label as a claim.

Source: README.md, under "Claiming an issue", and #33.

- `claim-cmd-adds-in-progress-label` (test): When `issues.py claim` wins,
  it adds `in-progress` and a claim comment, and if either fails, it warns and
  still exits 0.
- `issueclosed-clears-label` (check): When an issue carrying `in-progress`
  closes, issue-closed.yml removes the label.
- `stale-cmd-reports-label-mismatch` (test): When a label has no branch, a
  closed issue keeps its label, or a closed issue keeps its branch, `issues.py
  stale` fails and names the remedy.

## need owner-frees-abandoned-claims: Free an abandoned claim without losing work

When an agent stops without opening a pull request, the owner wants its claim
freed for someone else, so the issue does not stay held, and wants no commit
on the claim branch lost in the freeing.

Source: README.md, under "Claiming an issue", and CLAUDE.md, under "Issues".

- `release-cmd-frees-unused-claim` (test): When `issues.py release N`
  finds `issue/N` with no commits off main, or only the `in-progress` label,
  it deletes the branch, removes the label and comments.
- `release-cmd-keeps-work` (test): When `issue/N` has commits off main, or
  changed after `release` checked it, `issues.py release` exits 1 and deletes
  nothing.
- `release-cmd-requires-held-claim` (test): When `issues.py release N`
  finds neither `issue/N` nor the `in-progress` label, it exits 1 and comments
  nothing, so no issue reads as released that was never held.

## need owner-clears-merged-claims: Clear a merged claim's local branch

When a pull request from `issue/N` has merged, the owner wants the local claim
branch removed without anyone typing git commands, so claim branches do not
pile up.

Source: #289, and README.md, under "Claiming an issue".

- `clear-cmd-deletes-merged-branch` (test): When `issues.py clear N` finds #N
  closed, and the local `issue/N` either inside the head of a merged pull
  request from it or holding no change `origin/main` lacks, it switches any
  worktree that has the branch checked out to a detached `origin/main`,
  removes no worktree, and deletes the branch.
- `clear-cmd-keeps-unmerged-work` (test): When #N is open, the local
  `issue/N` does not exist, or it holds a commit no merged pull request from
  it has and a change `origin/main` lacks, `issues.py clear` exits 1, says
  what to do next and deletes nothing.
- `clear-cmd-keeps-uncommitted-changes` (test): When a worktree that has
  `issue/N` checked out has uncommitted changes, `issues.py clear N` exits 1,
  names the worktree and says to commit or discard the changes, and moves no
  worktree and deletes nothing, with or without `--dry-run`.

## need owner-prevents-stale-branches: Keep finished branches from piling up

When a session's work has merged or was never started, the owner wants every
local branch it left removed without typing git commands, so stale branches do
not accumulate in the clone.

Source: #294, and README.md, under "Claiming an issue".

- `sweep-cmd-deletes-merged-branches` (test): When `issues.py sweep` runs, it
  deletes every local branch but `main` whose tip is inside the head of a
  merged pull request from that branch, or which holds no change `origin/main`
  lacks, as a branch with no commits of its own does.
- `sweep-cmd-keeps-live-branches` (test): When a local branch holds a change
  `origin/main` lacks, is checked out in any worktree, or still exists on
  `origin`, `issues.py sweep` keeps it and prints it with the reason.
- `branchsweep-reports-deleted-branches` (test): When branch_sweep.py's sweep
  deletes branches, the hook names them on stdout in one line, and prints
  nothing when it deletes none.
- `branchsweep-never-blocks` (test): When `issues.py sweep` fails, prints no
  result or runs past the hook's own time limit, branch_sweep.py exits 0 and
  prints one line saying why and naming the command to run by hand.
- `settingsjson-registers-branch-sweep` (test): When a Claude Code session
  starts in this repo, `.claude/settings.json` runs branch_sweep.py, with 30
  seconds to answer.

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
  script through a variable or a path, `commands` finds the script, and fails
  an unassigned variable, a variable naming two scripts, and a script that is
  missing, will not import or has no parser.
- `commands-cmd-handles-fence-syntax` (test): When a fence writes a
  command with a placeholder, an optional part, a continuation, a comment, a
  heredoc or a list indent, `commands` checks it as the model would run it,
  and reads only shell fences.
- `commands-cmd-scans-something` (test): When no shell fence runs a script,
  `commands` fails.
- `ci-runs-commands` (check): When a pull request is opened or updated, CI runs
  `commands`.

## need owner-knows-each-step-command: Know which command does each skill step's work

When a contributor writes a skill step, the owner wants it to name the command
that does its work, or say why it has none, so no step leaves work to the
model without saying so.

Source: CLAUDE.md, under "Skills and scripts", and #98.

- `steps-cmd-counts-step-commands` (test): When a `## Step` section runs
  an invocation `commands` accepts, `check-skills.py steps` counts it for that
  step, and otherwise fails the step unless it carries a no-command marker.
- `steps-cmd-checks-no-command-markers` (test): When a no-command marker
  has no reason, shares its line with other text, sits outside a step, or sits
  on a step that runs a command, `steps` fails it.
- `steps-cmd-scans-something` (test): When no SKILL.md has a step, `steps`
  fails.
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
  string, `fences` fails it.
- `fences-cmd-allows-setup-commands` (test): When a shell fence runs an
  allowed setup command where it may stand, `fences` passes it, and fails the
  same command anywhere else.
- `fences-cmd-scans-something` (test): When no shell fence exists, `fences`
  fails.
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
- `repeats-cmd-scans-something` (test): When no SKILL.md exists, or none
  yields a block, `repeats` fails.
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
- `descriptions-cmd-scans-something` (test): When no file under `plugins/`
  has a description, `descriptions` fails.
- `ci-runs-descriptions` (check): When a pull request is opened or updated, CI
  runs `descriptions`.

## need contributor-validates-before-push: Run CI's checks before pushing

When a contributor changes the repo, they want to run CI's checks before
pushing and get CI's answer, or be told why a local run cannot give it. A
contributor adding a skill runs the skill checks before committing it, so the
checks read files git does not track yet.

Source: README.md, under "Adding a plugin", step 4: "Validate, then push",
and #284.

- `checkskills-cmd-reads-worktree-files` (test): When a skill file is
  committed, or new and not yet added, each check-skills.py command reads it,
  and skips a file git ignores.
- `floors-cmd-names-floor-version` (test): When the Python running
  `check-coverage.py floors` is not the version the floors were measured on,
  `floors` exits 2 and names that version, rather than telling the
  contributor to add tests.

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
  source directory holds no plugin.json, `check` fails it.
- `check-cmd-requires-entry-fields` (test): When a catalog entry lacks
  `name`, `source`, `description` or `version`, `check` names the field and
  fails.
- `check-cmd-requires-catalog` (test): When the catalog is missing or
  lists no plugins, `check` fails.
- `ci-runs-manifest-check` (check): When a pull request is opened or updated,
  CI runs `check`.

## need owner-sees-every-line-tested: Know every plugin line runs under a test

When a contributor changes a plugin script, the owner wants CI to fail a
script whose coverage falls below its floor, or a new line no test runs, so a
line no test runs cannot also escape the trace.

Source: #128, README.md, under "Coverage", and SPEC-METHODOLOGY.md, under
"The chain".

- `floors-cmd-fails-below-floor` (test): When a plugin script's branch
  coverage is below its floor in `.github/coverage-floors.json`,
  `check-coverage.py floors` fails and names the script, its figure and its
  floor.
- `floors-cmd-warns-to-raise-floor` (test): When a script's figure passes
  its floor, `floors` warns with the figure, to two decimals, to raise the
  floor to.
- `floors-cmd-fails-lowered-floor` (test): When a floor is lower than at
  `--base`, `floors` fails it.
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
  spelling coverage.py accepts, gives no reason on its line,
  `check-coverage.py pragmas` fails it.
- `checkcoverage-cmd-scans-something` (test): When the clone holds no
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
not collect, by where it sits or by its name, so no test silently never runs.

Source: README.md, under "Running the tests", CLAUDE.md, under "Tests", and
#22 and #26.

- `placement-cmd-fails-tests-outside-roots` (test): When a test file sits
  outside every `testpaths` root in pytest.ini, `check-tests.py placement`
  fails it.
- `naming-cmd-fails-old-test-names` (test): When a test file holds `def
  test_` or `class Test` at any indent, `check-tests.py naming` fails and
  names the file and line.
- `naming-cmd-scans-something` (test): When `naming` finds no test file,
  or a `testpaths` root that exists holds none, it fails.
- `ci-runs-placement-and-naming` (check): When a pull request is opened or
  updated, CI runs `placement` and `naming`.

## need owner-keeps-one-code-style: Keep one code style, applied by tools

When anyone edits Python or shell in this repo, the owner wants formatting and
lint applied by tools and enforced in CI, so style is never argued about in
review.

Source: README.md, under "Formatting and linting" and "Shell scripts".

- `hook-prefers-own-venv` (test): When the project has its own `.venv` holding
  ruff, the ruff hook uses it.
- `hook-borrows-main-venv` (test): When the ruff hook runs in a worktree with
  no `.venv` of its own, it uses the main checkout's.
- `hook-falls-back-to-path` (test): When no `.venv` holds ruff, the ruff hook
  uses the ruff on PATH.
- `hook-formats-edit` (test): When Claude Code writes or edits a `.py` file,
  the ruff hook sorts its imports and formats it, and leaves every other file
  alone.
- `hook-reports-lint` (test): When lint problems remain after formatting, the
  ruff hook exits 2 with the findings on stderr.
- `hook-reports-parse-error` (test): When ruff cannot format the file, the
  ruff hook exits 2 with ruff's error.
- `hook-names-ruff-install` (test): When no ruff is found, the ruff hook exits
  2 and names the command that installs it.
- `settingsjson-registers-ruff-hook` (test): When Claude Code writes or edits
  a file in this repo, `.claude/settings.json` runs the ruff hook, with 30
  seconds to answer.
- `ci-checks-python-formatting` (check): When a pull request is opened or
  updated, CI checks the Python formatting.
- `ci-lints-python` (check): When a pull request is opened or updated, CI lints
  the Python.
- `ci-lints-shell` (check): When a pull request is opened or updated, CI
  checks each shell script parses and passes shellcheck.

## need owner-traces-behavior-to-needs: Tie each behavior to the need behind it

When a contributor adds a behavior, the owner wants CI to tie each test and
skill step to a requirement in `specs/`, so no behavior arrives that no need
asked for, and no requirement loses the last thing that verifies it.

Source: #114, #129, and SPEC-METHODOLOGY.md, under "The chain".

- `trace-cmd-fails-uncited-verifiers` (test): When a test or a skill step
  cites no requirement, and `.github/untraced.json` does not list it,
  `check-specs.py trace` fails it.
- `trace-cmd-fails-unknown-ids` (test): When a test, a skill step or a
  workflow step cites an id its component's spec does not hold, `trace` fails
  the citation.
- `trace-cmd-fails-unverified-requirements` (test): When nothing of a
  requirement's kind cites it, a test for `test`, a skill step for `step` and
  a workflow step for `check`, `trace` fails the requirement.
- `trace-cmd-warns-on-listed-items` (test): When `.github/untraced.json`
  lists a test or a step that cites nothing, and the issue it waits on is
  open, `trace` passes it with a warning naming that issue.
- `trace-cmd-fails-closed-issue-entries` (test): When an entry in
  `.github/untraced.json`, or a step in check-skills.py's `KNOWN_SEAMS`, waits
  on an issue that has closed, `trace` fails the entry. It stops on an issue
  it cannot read, and without a token it warns that it did not look.
- `trace-cmd-fails-stale-list-entries` (test): When a listed test or step
  cites a requirement, or no longer exists, `trace` fails until its entry is
  removed.
- `trace-cmd-checks-spec-grammar` (test): When a spec file has a
  requirement outside a need or a constraint, a malformed requirement, a need,
  constraint or requirement id not in the form SPEC-METHODOLOGY.md gives under
  "Ids", a duplicate id or a kind nothing in the repo verifies, `trace` fails
  it.
- `trace-cmd-scans-something` (test): When `trace` finds no spec, no test
  or no skill step, it fails.
- `ci-runs-trace` (check): When a pull request is opened or updated, CI runs
  `trace`.
- `inventory-cmd-lists-parser-surface` (test): When `check-specs.py
  inventory` lists a plugin, it gives every subcommand, option and `choices`
  value its script's `build_parser()` accepts, each with the skill text that
  names it.
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
- `surface-cmd-fails-unnamed-options` (test): When a subcommand, option or
  `choices` value of a plugin script or a repo script is named in backticks by
  no requirement in its component's spec or in `specs/repo.md`,
  `check-specs.py surface` fails it.
- `surface-cmd-warns-on-listed-items` (test): When the `surface` section of
  `.github/untraced.json` lists an item no requirement names, `surface`
  passes it with a warning naming its issue, and fails an entry whose item is
  named or gone.
- `surface-cmd-scans-something` (test): When `surface` finds no script
  with a `build_parser()`, it fails.
- `ci-runs-surface` (check): When a pull request is opened or updated, CI runs
  `surface`.
- `changes-cmd-lists-ids` (test): When a pull request adds, changes or
  removes a requirement, and its description does not name the id in
  backticks, `check-specs.py changes` fails it.
- `changes-cmd-requires-issue-for-section` (test): When a pull request
  adds a need or a constraint that no issue it closes names, `changes`
  fails it.
- `ci-runs-changes` (check): When a pull request is opened, edited or
  updated, CI runs `changes`.

## constraint marketplace-serves-repo-as-is: The marketplace is this repository as it stands

Claude reads the marketplace straight from this repository's GitHub address.
No CI step builds a package in between, so an install copies a plugin's
directory whole, and a file stays out of an install only by sitting outside
`plugins/<plugin>/`.

Source: the owner's review of #139, and README.md, under "Adding this
marketplace" and "Layout".

## constraint bridge-cannot-delete: Cowork's device bridge cannot delete files

A git write through the bridge strands a `.git/*.lock` that blocks every
later write. The constraint binds every plugin script that runs on the user's
device through the bridge.

Source: CLAUDE.md, under "Script conventions", and COWORK.md.

## constraint proposeskills-takes-one-file: propose_skills takes a single SKILL.md

Cowork's `propose_skills` delivers one `SKILL.md` and no bundled files, so a
plugin that bundles a script cannot reach Cowork that way.

Source: README.md, under "Adding a plugin", step 2.

## constraint github-closes-keyword-named-issues: GitHub closes an issue named by a closing keyword

GitHub closes an issue when a merged pull request's title, body or commits
name it after close, fix or resolve, or one of their variants, as `#N` or
`owner/repo#N`.

Source: GitHub's "Linking a pull request to an issue", and #15.

## constraint hook-blocks-on-exit-2: A Claude Code hook that exits 2 blocks the call

A PreToolUse hook that exits 2 stops the tool call, and Claude Code hands the
hook's stderr back to Claude.

Source: Claude Code's hooks documentation, and #15, which tried it live.

## constraint macos-ships-python-39: The Python on a user's machine may be 3.9

macOS ships Python 3.9 as its system Python, so a plugin script that runs
where it lands runs on 3.9.

Source: README.md, under "Running the tests", and CLAUDE.md, under "Script
conventions".

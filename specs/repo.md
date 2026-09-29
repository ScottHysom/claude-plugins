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

## need model-at-seams: Keep the model to judgment and platform seams

When a skill runs script commands, the owner wants the model between two of
them only where it makes a judgment or calls a tool no script can, so no run
spends context on work a script could do, or gets that work wrong.

Source: #126, and CLAUDE.md, under "Skills and scripts".

- `answers-checked` (test): When a script takes the model's answers as data,
  it checks every one, names each that fails, and writes nothing if any does.
- `seam-marker-required` (test): When a skill step runs more than one
  command, `check-skills.py steps` fails it unless a marker on its own line
  under the heading names a judgment or a platform seam and gives a reason.
- `seam-marker-stale` (test): When a step with a seam marker runs one command
  or none, `steps` fails the marker.
- `known-seams-warn` (test): When a step listed in `KNOWN_SEAMS` runs more
  than one command with no marker, `steps` passes it with a warning naming
  its issue, and fails the entry once the step runs one command, gains a
  marker or is gone.
- `seams-in-ci` (check): When a pull request is opened or updated, CI runs
  `steps`.

## need shared-flags: Read every script's flags the same way

When a contributor runs or writes a repo script, they want the flags every
command takes, `--json`, `-C/--repo`, `--dry-run` and `--partial`, to mean the
same thing in each script, so a skill can read any result and preview or batch
any change the same way.

Source: CLAUDE.md, under "Script conventions".

- `dry-run-writes-nothing` (test): When a command that writes is given
  `--dry-run`, it reports what it would write and writes nothing.
- `plain-output-streams` (test): When a command runs without `--json`, it
  prints its result on stdout, and its warnings and errors on stderr.
- `partial-applies-rest` (test): When a command that writes a batch refuses
  part of it, it writes nothing and exits 1, and with `--partial` it writes
  the rest and still exits 1.
- `json-envelope` (test): When a command is given `--json`, it prints one
  object on stdout with the keys `version`, `command`, `ok`, `errors`,
  `warnings` and `data`, and nothing on stderr, whether or not it found
  problems.

## need readable-exits: Act on any repo script's exit code alone

When CI, a skill or a contributor runs a repo script, they want its exit code
to say whether it ran clean, found problems or could not run, and a stop to
say what to do next, so the caller needs no table of remedies and a test can
drive any command through `main(argv)`.

Source: CLAUDE.md, under "Script conventions", and #24, "Importing the module
does nothing".

- `cannot-run-exits-2` (test): When a repo script cannot run, from bad usage,
  from running outside a clone, from `-C` naming a missing directory, or from
  a file it needs being missing or unreadable, it writes its name and the
  cause to stderr and exits 2.
- `stop-names-remedy` (test): When a repo script stops, its message says what
  to do next.
- `import-runs-nothing` (test): When a repo script is imported, it does
  nothing, and each `main(argv)` call starts with no state from an earlier
  one.
- `closed-pipe-exits-0` (test): When stdout closes before a repo script
  finishes printing, it exits 0 without a traceback.

## need install-from-marketplace: Install any plugin from one marketplace

When the user wants one of the owner's plugins, they want to add the
marketplace once and install any plugin listed in it, so each plugin needs no
setup of its own.

Source: README.md, under "Adding this marketplace".

- `manifests-validate-in-ci` (check): When a pull request is opened or
  updated, CI runs the latest `claude plugin validate --strict` on the
  catalog and on every plugin directory with a plugin.json, and fails when it
  finds none.
- `cli-version-shown` (check): When CI validates the manifests, it prints the
  version of the Claude Code CLI it installed, so a failure that a new release
  brings can be traced to that release.
- `manifest-uncataloged` (test): When a directory under `plugins/` holds a
  plugin.json and no catalog entry names it, `check-manifest-consistency.py
  check` fails it.

## need install-holds-runtime-only: Install only what a plugin runs

When the user installs a plugin, the owner wants the install to hold only what
the user needs to run it, so no contributor-only file, such as a test or a
spec, ships to every user.

Source: the owner's review of #139, and CLAUDE.md, under "Tests".

- `tests-outside-plugins` (check): When a pull request adds a test file under
  `plugins/`, `check-tests.py placement` fails it.
- `stray-names-destination` (test): When a test file, a `conftest.py`, a file
  in a `tests/` directory, or a script importing pytest or hypothesis sits
  under `plugins/`, `placement` fails it, says it ships to every user, and
  names where it goes.
- `placement-reads-git` (test): When `placement` lists files, it reads every
  file git carries, tracked or not yet added, and skips what git ignores.

## need surface-stated: Know which surface a plugin needs before installing it

When the user chooses a plugin, they want its description to say whether it
needs Cowork, Claude Code or either, so a plugin installed on the wrong surface
does not fail confusingly.

Source: README.md, the opening section, and "Adding a plugin", step 3.

## need owner-approves-work: Work only on what the owner approved

When an issue is filed, the owner wants to decide whether it gets worked on,
so an agent posting under the owner's account cannot approve its own work.

Source: README.md, under "Issues" and "Keeping `approved` meaningful".

- `claim-needs-approved` (test): When `issues.py claim N` is given an issue
  that lacks `approved`, or is closed and so finished, it exits 1 and writes
  nothing.
- `linked-needs-approved` (test): When a pull request's title, body or a
  commit message closes an issue in this repository that lacks `approved`,
  check-linked-issues.py fails and says to re-run the job once it is labeled.
- `linked-keywords` (test): When text names an issue with a closing keyword
  outside a code span, a fence or an HTML comment, check-linked-issues.py
  counts it as a link, and counts nothing else.
- `linked-not-an-issue` (test): When a closing keyword names a number that
  does not exist or is a pull request, check-linked-issues.py fails it.
- `linked-other-repo` (test): When a closing keyword names another
  repository's issue, check-linked-issues.py fails it without looking it up.
- `linked-none-passes` (test): When a pull request closes no issue,
  check-linked-issues.py passes it from any branch.
- `linked-lookup-fails-closed` (test): When check-linked-issues.py cannot read
  a pull request's commits or the claim branches, it exits 2 and prints no
  links.
- `linked-in-ci` (check): When a pull request is opened, edited or updated,
  CI runs check-linked-issues.py.
- `disclosed-edited-after-approval` (test): When an issue a pull request
  closes was edited after `approved` was last added to it, `disclosed` fails
  the pull request and says to re-add the label.
- `guard-blocks-approve` (test): When Claude Code runs a Bash command that
  would add `approved` through `gh`, issue_guard.py exits 2 with the reason on
  stderr. The command counts bare, after a variable assignment, after `env` or
  `xargs`, inside `sh -c` or `bash -c`, and through a full path to `gh`.
- `guard-passes-text` (test): When a command only quotes such a command, in
  an argument or a heredoc body, or reads or removes the label, issue_guard.py
  exits 0 and prints nothing.
- `guard-unparsed` (test): When the hook's input is not JSON, or its command
  cannot be split, issue_guard.py blocks it if the raw text names `gh`, a
  label flag and `approved`, and allows it otherwise.
- `guard-registered` (test): When Claude Code runs a Bash command in this
  repo, `.claude/settings.json` runs issue_guard.py first, with 10 seconds to
  answer.

## need one-claim-per-issue: Keep two agents off the same issue

When two agents are told to take the next issue at the same time, the owner
wants each to get a different one, so no two agents do the same work.

Source: README.md, under "Claiming an issue".

- `next-offers-free` (test): When `issues.py next` runs, it names the
  lowest-numbered open issue labeled `approved` that no `issue/N` branch
  holds, and exits 0 when none is free.
- `claim-one-winner` (test): When two agents claim the same issue at once,
  `issues.py claim` lets exactly one create `issue/N`, and the other exits 1,
  names the holder and writes nothing.
- `claim-switches` (test): When `issues.py claim N` wins, it switches the
  clone to `issue/N`, and warns when the switch fails.
- `claim-push-refused` (test): When the push fails and `issue/N` does not
  exist, `issues.py claim` exits 2 and writes nothing to the issue.
- `linked-from-claim-branch` (test): When a pull request closes #N and does
  not come from `issue/N` in this repository, check-linked-issues.py fails
  it.
- `linked-others-claim` (test): When a pull request also closes an issue that
  another `issue/M` branch holds, check-linked-issues.py fails it.

## need claim-shows: See from the issue list which issues are held

When an agent or the owner looks at the issue list, they want a claimed issue
to show as claimed, and a label that disagrees with its branch to be reported,
so nobody reads a stale label as a claim.

Source: README.md, under "Claiming an issue", and #33.

- `claim-labels` (test): When `issues.py claim` wins, it adds `in-progress`
  and a claim comment, and if either fails, it warns and still exits 0.
- `closed-clears-label` (check): When an issue carrying `in-progress` closes,
  issue-closed.yml removes the label.
- `stale-disagreement` (test): When a label has no branch, a closed issue
  keeps its label, or a closed issue keeps its branch, `issues.py stale` fails
  and names the remedy.

## need claim-given-up: Free an abandoned claim without losing work

When an agent stops without opening a pull request, the owner wants its claim
freed for someone else, so the issue does not stay held, and wants no commit
on the claim branch lost in the freeing.

Source: README.md, under "Claiming an issue", and CLAUDE.md, under "Issues".

- `release-frees` (test): When `issues.py release N` finds `issue/N` with no
  commits off main, or only the `in-progress` label, it deletes the branch,
  removes the label and comments.
- `release-keeps-work` (test): When `issue/N` has commits off main, or
  changed after `release` checked it, `issues.py release` exits 1 and deletes
  nothing.
- `release-needs-claim` (test): When `issues.py release N` finds neither
  `issue/N` nor the `in-progress` label, it exits 1 and comments nothing, so
  no issue reads as released that was never held.

## need skills-match-scripts: Catch a skill that names a missing command

When a contributor renames a script's subcommand or flag, they want CI to fail
every skill that still names the old one, so the failure shows in the pull
request rather than part way through a user's run.

Source: README.md, under "Adding a plugin", step 4.

- `commands-parsed` (test): When a shell fence runs a plugin script,
  `check-skills.py commands` passes its arguments through that script's
  `build_parser()`, and fails what the parser rejects, naming the file and
  line.
- `commands-resolve-script` (test): When an invocation names its script
  through a variable or a path, `commands` finds the script, and fails an
  unassigned variable, a variable naming two scripts, and a script that is
  missing, will not import or has no parser.
- `commands-fence-forms` (test): When a fence writes a command with a
  placeholder, an optional part, a continuation, a comment, a heredoc or a
  list indent, `commands` checks it as the model would run it, and reads only
  shell fences.
- `commands-scans-something` (test): When no shell fence runs a script,
  `commands` fails.
- `commands-in-ci` (check): When a pull request is opened or updated, CI runs
  `commands`.

## need step-names-command: Know which command does each skill step's work

When a contributor writes a skill step, the owner wants it to name the command
that does its work, or say why it has none, so no step leaves work to the
model without saying so.

Source: CLAUDE.md, under "Skills and scripts", and #98.

- `step-command-counted` (test): When a `## Step` section runs an invocation
  `commands` accepts, `check-skills.py steps` counts it for that step, and
  otherwise fails the step unless it carries a no-command marker.
- `no-command-marker-form` (test): When a no-command marker has no reason,
  shares its line with other text, sits outside a step, or sits on a step
  that runs a command, `steps` fails it.
- `steps-scans-something` (test): When no SKILL.md has a step, `steps` fails.
- `steps-in-ci` (check): When a pull request is opened or updated, CI runs
  `steps`.

## need script-computes: Keep a skill's shell blocks to running its script

When a contributor writes a shell block into a skill, the owner wants it to
run the plugin's script and nothing that computes beside it, so work that
should give the same answer on every run is done by the script.

Source: CLAUDE.md, under "Skills and scripts", and #97.

- `fences-reject-other-commands` (test): When a shell fence in a skill runs
  anything but a script invocation, such as `python3 -c` or a stage of a
  pipeline, `check-skills.py fences` fails it and names the file, line and
  command.
- `fences-labeled` (test): When a fence has no info string, `fences` fails
  it.
- `fences-allow-setup` (test): When a shell fence runs an allowed setup
  command where it may stand, `fences` passes it, and fails the same command
  anywhere else.
- `fences-scans-something` (test): When no shell fence exists, `fences`
  fails.
- `fences-in-ci` (check): When a pull request is opened or updated, CI runs
  `fences`.

## need skills-share-steps: Keep a step two skills share in one place

When two skills of one plugin need the same step, a contributor wants it
written once, in the plugin's `reference/`, and CI to fail a copy, so the two
copies cannot drift apart.

Source: CLAUDE.md, under "Skills in a plugin share instructions through one
file", README.md, under "Adding a plugin", step 2, and #54.

- `repeats-names-copies` (test): When two SKILL.md files of one plugin share a
  paragraph, a table, a fenced block or a list item, whitespace aside,
  `check-skills.py repeats` fails and names each file and the line each copy
  starts on.
- `repeats-exemptions` (test): When the shared block is the section that
  locates the script, a heading or front matter, `repeats` passes it, and it
  checks a section under any other heading.
- `repeats-within-plugin` (test): When a block repeats across two plugins, or
  twice within one skill, `repeats` passes it.
- `repeats-skips-markers` (test): When two of a plugin's skills carry the same
  comment line, such as one spec marker, `repeats` does not report it as a
  copied block.
- `repeats-scans-something` (test): When no SKILL.md exists, or none yields a
  block, `repeats` fails.
- `repeats-in-ci` (check): When a pull request is opened or updated, CI runs
  `repeats`.

## need cowork-accepts-description: Keep every skill uploadable to Cowork

When a contributor writes a skill's description, they want CI to fail one that
Cowork's `.plugin` upload would reject, so the user can install the plugin on
Cowork even though a marketplace install and `--strict` accept it.

Source: README.md, under "Adding a plugin", step 4.

- `description-tag-named` (test): When a description holds `<` or `</`
  followed by a name, on its first line or a continuation,
  `check-skills.py descriptions` fails and names the file, line and tag.
- `description-lone-less-than` (test): When a description holds a `<` that no
  name follows, `descriptions` passes it.
- `description-templates-read` (test): When a markdown file under `plugins/`
  other than SKILL.md has a description, such as a generated-skill template,
  `descriptions` checks it.
- `description-only` (test): When a tag sits outside the description, in the
  body, in another front matter key or in markdown outside `plugins/`,
  `descriptions` passes it.
- `descriptions-scans-something` (test): When no file under `plugins/` has a
  description, `descriptions` fails.
- `descriptions-in-ci` (check): When a pull request is opened or updated, CI
  runs `descriptions`.

## need validate-before-push: Run CI's checks before pushing

When a contributor adds a skill, they want to run CI's skill checks before
committing it, so the checks read files git does not track yet.

Source: README.md, under "Adding a plugin", step 4: "Validate, then push".

- `skill-checks-read-worktree` (test): When a skill file is committed, or new
  and not yet added, each check-skills.py command reads it, and skips a file
  git ignores.

## need manifests-agree: Keep the two manifests in step

When a contributor bumps a plugin's version or edits its manifest, they want
CI to fail a catalog entry that disagrees with the plugin's own manifest, so
two files that each validate cannot drift apart.

Source: README.md, under "Adding a plugin", step 4.

- `manifest-version-drift` (test): When a catalog entry's `version` differs
  from its plugin.json's, `check-manifest-consistency.py check` fails and
  names both.
- `manifest-name-drift` (test): When plugin.json's `name`, or the source
  directory's name, differs from the entry's `name`, `check` fails it.
- `manifest-entry-resolves` (test): When a catalog entry's source directory
  holds no plugin.json, `check` fails it.
- `manifest-entry-complete` (test): When a catalog entry lacks `name`,
  `source`, `description` or `version`, `check` names the field and fails.
- `manifest-catalog-present` (test): When the catalog is missing or lists no
  plugins, `check` fails.
- `manifests-agree-in-ci` (check): When a pull request is opened or updated,
  CI runs `check`.

## need covered-lines: Know every plugin line runs under a test

When a contributor changes a plugin script, the owner wants CI to fail a
script whose coverage falls below its floor, or a new line no test runs, so a
line no test runs cannot also escape the trace.

Source: #128, README.md, under "Coverage", and SPEC-METHODOLOGY.md, under
"The chain".

- `floor-holds` (test): When a plugin script's branch coverage is below its
  floor in `.github/coverage-floors.json`, `check-coverage.py floors` fails
  and names the script, its figure and its floor.
- `floor-rises` (test): When a script's figure passes its floor, `floors`
  warns with the figure, to two decimals, to raise the floor to.
- `floor-never-lowered` (test): When a floor is lower than at `--base`,
  `floors` fails it.
- `floor-for-new-script` (test): When a plugin script has no floor, `floors`
  fails it and prints the figure to use.
- `floors-list-scripts` (test): When the floors file holds a floor for a path
  that is not a plugin script, `floors` fails it, so the file lists exactly
  the plugin scripts.
- `unmeasured-script-fails` (test): When the report leaves out a plugin
  script, `floors` fails the script and `diff` fails its added lines.
- `branch-report-required` (test): When the report was measured without
  branch coverage, check-coverage.py exits 2.
- `added-line-unrun` (test): When a pull request adds a plugin line that no
  test runs, `check-coverage.py diff` names it and fails, counting from the
  merge base, and every line of a new script counts as added.
- `pragma-reason` (test): When a coverage exclusion, in any spelling
  coverage.py accepts, gives no reason on its line,
  `check-coverage.py pragmas` fails it.
- `coverage-scans-something` (test): When the clone holds no plugin script,
  each check-coverage.py command exits 2.
- `floors-in-ci` (check): When a pull request is opened or updated, or main
  is pushed, CI runs `floors`, with `--base` set to a pull request's base.
- `diff-in-ci` (check): When a pull request is opened or updated, CI runs
  `diff` against its base.
- `pragmas-in-ci` (check): When a pull request is opened or updated, CI runs
  `pragmas`.
- `suite-in-ci` (check): When a pull request is opened or updated, CI runs
  the whole suite under coverage, with pytest's config and markers checked,
  on Python 3.9 and 3.13, and lets each finish when the other fails.

## need every-test-runs: Run every test the suite appears to have

When a contributor writes a test, they want CI to fail one that pytest would
not collect, by where it sits or by its name, so no test silently never runs.

Source: README.md, under "Running the tests", CLAUDE.md, under "Tests", and
#22 and #26.

- `test-outside-roots` (test): When a test file sits outside every
  `testpaths` root in pytest.ini, `check-tests.py placement` fails it.
- `old-test-names` (test): When a test file holds `def test_` or
  `class Test` at any indent, `check-tests.py naming` fails and names the file
  and line.
- `naming-scans-something` (test): When `naming` finds no test file, or a
  `testpaths` root that exists holds none, it fails.
- `tests-collected` (check): When a pull request is opened or updated, CI
  runs `placement` and `naming`.

## need one-code-style: Keep one code style, applied by tools

When anyone edits Python or shell in this repo, the owner wants formatting and
lint applied by tools and enforced in CI, so style is never argued about in
review.

Source: README.md, under "Formatting and linting" and "Shell scripts".

- `hook-own-venv-first` (test): When the project has its own `.venv` holding
  ruff, the ruff hook uses it.
- `hook-main-venv` (test): When the ruff hook runs in a worktree with no
  `.venv` of its own, it uses the main checkout's.
- `hook-path-fallback` (test): When no `.venv` holds ruff, the ruff hook uses
  the ruff on PATH.
- `hook-formats-edit` (test): When Claude Code writes or edits a `.py` file,
  the ruff hook sorts its imports and formats it, and leaves every other file
  alone.
- `hook-reports-lint` (test): When lint problems remain after formatting, the
  ruff hook exits 2 with the findings on stderr.
- `hook-reports-parse-error` (test): When ruff cannot format the file, the
  ruff hook exits 2 with ruff's error.
- `hook-ruff-missing` (test): When no ruff is found, the ruff hook exits 2
  and names the command that installs it.
- `hook-registered` (test): When Claude Code writes or edits a file in this
  repo, `.claude/settings.json` runs the ruff hook, with 30 seconds to
  answer.
- `format-in-ci` (check): When a pull request is opened or updated, CI checks
  the Python formatting.
- `lint-in-ci` (check): When a pull request is opened or updated, CI lints
  the Python.
- `shell-lint-in-ci` (check): When a pull request is opened or updated, CI
  checks each shell script parses and passes shellcheck.

## need traced-behavior: Tie each behavior to the need behind it

When a contributor adds a behavior, the owner wants CI to tie each test and
skill step to a requirement in `specs/`, so no behavior arrives that no need
asked for, and no requirement loses the last thing that verifies it.

Source: #114, #129, and SPEC-METHODOLOGY.md, under "The chain".

- `trace-uncited` (test): When a test or a skill step cites no requirement,
  and `.github/untraced.json` does not list it, `check-specs.py trace` fails
  it.
- `trace-unknown-id` (test): When a test, a skill step or a workflow step
  cites an id its component's spec does not hold, `trace` fails the citation.
- `trace-unverified` (test): When nothing of a requirement's kind cites it, a
  test for `test`, a skill step for `step` and a workflow step for `check`,
  `trace` fails the requirement.
- `trace-listed-warns` (test): When `.github/untraced.json` lists a test or a
  step that cites nothing, and the issue it waits on is open, `trace` passes
  it with a warning naming that issue.
- `trace-closed-issue` (test): When an entry in `.github/untraced.json`, or a
  step in check-skills.py's `KNOWN_SEAMS`, waits on an issue that has closed,
  `trace` fails the entry. It stops on an issue it cannot read, and without
  a token it warns that it did not look.
- `trace-list-shrinks` (test): When a listed test or step cites a requirement,
  or no longer exists, `trace` fails until its entry is removed.
- `trace-spec-grammar` (test): When a spec file has a requirement outside a
  need or a constraint, a malformed requirement, an id of more than six
  words, a duplicate id or a kind nothing in the repo verifies, `trace` fails
  it.
- `trace-scans-something` (test): When `trace` finds no spec, no test or no
  skill step, it fails.
- `trace-in-ci` (check): When a pull request is opened or updated, CI runs
  `trace`.
- `inventory-surface` (test): When `check-specs.py inventory` lists a plugin,
  it gives every subcommand, option and `choices` value its script's
  `build_parser()` accepts, each with the skill text that names it.
- `inventory-collections` (test): When `inventory` lists a plugin, it gives
  every module-level set, tuple or list of strings in its script.
- `inventory-tests` (test): When `inventory` lists a plugin, it gives every
  test in `tests/<plugin>/`, with the script lines each one runs.
- `inventory-steps` (test): When `inventory` lists a plugin, it gives every
  step of its skills, with the commands each one runs.
- `inventory-unrun` (test): When `inventory` lists a plugin, it gives every
  line of its script that no test runs.
- `inventory-per-test-report` (test): When the coverage report does not say
  which test ran each line, `inventory` stops and names the command that
  writes one that does.
- `surface-unnamed` (test): When a subcommand, option or `choices` value of a
  plugin script or a repo script is named in backticks by no requirement in
  its component's spec or in `specs/repo.md`, `check-specs.py surface` fails
  it.
- `surface-listed-warns` (test): When the `surface` section of
  `.github/untraced.json` lists an item no requirement names, `surface`
  passes it with a warning naming its issue, and fails an entry whose item is
  named or gone.
- `surface-scans-something` (test): When `surface` finds no script with a
  `build_parser()`, it fails.
- `surface-in-ci` (check): When a pull request is opened or updated, CI runs
  `surface`.
- `disclosed-lists-ids` (test): When a pull request adds, changes or removes a
  requirement, and its description does not name the id in backticks,
  `check-specs.py disclosed` fails it.
- `disclosed-new-need` (test): When a pull request adds a need that no issue
  it closes names, `disclosed` fails it.
- `disclosed-checks-new-ids` (test): When a pull request adds a need, a
  constraint or a requirement whose id is not in the form SPEC-METHODOLOGY.md
  gives under "Ids", `disclosed` fails it.
- `disclosed-in-ci` (check): When a pull request is opened, edited or
  updated, CI runs `disclosed`.

## constraint marketplace-from-repo: The marketplace is this repository as it stands

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

## constraint propose-skills-one-file: propose_skills takes a single SKILL.md

Cowork's `propose_skills` delivers one `SKILL.md` and no bundled files, so a
plugin that bundles a script cannot reach Cowork that way.

Source: README.md, under "Adding a plugin", step 2.

## constraint closing-keywords: GitHub closes an issue named by a closing keyword

GitHub closes an issue when a merged pull request's title, body or commits
name it after close, fix or resolve, or one of their variants, as `#N` or
`owner/repo#N`.

Source: GitHub's "Linking a pull request to an issue", and #15.

## constraint hook-exit-2: A Claude Code hook that exits 2 blocks the call

A PreToolUse hook that exits 2 stops the tool call, and Claude Code hands the
hook's stderr back to Claude.

Source: Claude Code's hooks documentation, and #15, which tried it live.

## constraint system-python-39: The Python on a user's machine may be 3.9

macOS ships Python 3.9 as its system Python, so a plugin script that runs
where it lands runs on 3.9.

Source: README.md, under "Running the tests", and CLAUDE.md, under "Script
conventions".

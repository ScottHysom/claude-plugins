# claude-plugins

A personal plugin marketplace for Claude. Add it once, then install any plugin
listed below.

Plugins here may target Cowork, Claude Code, or both. **Each plugin's
description says which surface it needs.** The plugin format is identical
across surfaces, but a plugin that calls Cowork's device bridge will not work
in Claude Code, and installing it there will fail confusingly rather than
loudly.

## Adding this marketplace

In Claude Code:

```
/plugin marketplace add ScottHysom/claude-plugins
/plugin install cowork-project-scaffold@scott-claude-plugins
```

In Cowork, add the marketplace and install from the plugin browser.

Custom marketplaces do not auto-update. To pick up new versions:

```
/plugin marketplace update scott-claude-plugins
```

## Plugins

| Plugin | Surface | What it does |
|---|---|---|
| [cowork-project-scaffold](plugins/cowork-project-scaffold) | Cowork | Scaffolds a Cowork Project folder as a git repo, and generates a per-project skill that keeps its documents stating what is true while git holds the history |
| [gitify-cowork-project](plugins/gitify-cowork-project) | Cowork | Puts an existing Cowork Project folder under git without touching its documents, moves the Project Instructions into a versioned `CLAUDE.md`, and generates a per-project history skill |
| [prose-tuning](plugins/prose-tuning) | Claude Code, Cowork | Learns a project's house prose style from edits already made, records it as `prose-style.md` with stable rule ids, and conforms the rest of the documents to it |

## Layout

```
.claude-plugin/
  marketplace.json         the catalog. One entry per plugin
plugins/
  <plugin-name>/
    .claude-plugin/
      plugin.json          the plugin's own manifest
    README.md
    scripts/               optional. Shared by every skill in the plugin
    reference/             optional. Normative docs a skill points at
    skills/
      <skill-name>/
        SKILL.md           plus any files the skill bundles
tests/
  <plugin-name>/           optional. pytest suite for that plugin's scripts.
                           Not under plugins/, which is copied into every install
```

A plugin's `source` in `marketplace.json` is a path relative to the repo root,
such as `./plugins/cowork-project-scaffold`. Adding a plugin means one new
directory under `plugins/` and one new entry in the catalog.

## Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with at least a `name`
   field, in kebab-case, matching the directory name.
2. Put skills at `plugins/<name>/skills/<skill-name>/SKILL.md`. A skill can
   bundle reference files, scripts and templates in subdirectories beside its
   `SKILL.md`, and reach them at `${CLAUDE_SKILL_DIR}/...`. Anything two skills
   share goes at the plugin root instead, reached at
   `${CLAUDE_PLUGIN_ROOT}/...`. Copying it into each skill is how one parser
   becomes three that disagree.

   A plugin that bundles a script cannot be delivered to Cowork through
   `propose_skills`, which takes a single `SKILL.md` and no bundled files. Say
   so in the skill, or it fails confusingly at the point of use.
3. Add an entry to `.claude-plugin/marketplace.json` with `name`, `source`,
   `description` and `version`. State the required surface in the first
   sentence of the description.
4. Validate, then push:
   ```sh
   claude plugin validate --strict .
   claude plugin validate --strict plugins/<name>
   python3 .github/scripts/check-manifest-consistency.py
   python3 .github/scripts/check-tests.py placement
   pytest
   ```

   CI runs these on every pull request, on every plugin. `--strict` fails on
   warnings too, and validating the plugin directory checks its skills as well
   as its manifest. The consistency script catches what
   `claude plugin validate` cannot: two manifests that each validate but
   disagree with each other, such as a version bumped in one and not the other.
   The placement check catches a contributor-only file left under `plugins/`,
   which would otherwise be copied into every install.
5. Add a `plugin:<name>` label, and the plugin to the Area list in
   `.github/ISSUE_TEMPLATE/problem.yml`, so issues about it can say so:
   ```sh
   gh label create "plugin:<name>" --description "About the <name> plugin"
   ```

## Running the tests

The plugin scripts import nothing outside the standard library, because they
run wherever `/plugin marketplace add` puts them. Their tests are a contributor
tool and live outside that constraint, on pytest and hypothesis installed from
a clone.

That is why the suites are not beside the scripts they test. **Everything under
`plugins/<name>/` is copied verbatim into every install** - the manifest points
each plugin at its own directory and the whole subtree is copied, with no
`files` or `exclude` key, no `.claudeignore` and no build step to hold anything
back. A test file there reaches every user.
`python3 .github/scripts/check-tests.py placement` is what fails a pull request
that puts one there; its docstring says what it rejects.

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

`pytest` from the repo root discovers every `tests/<plugin-name>/` directory.
A new plugin adding a script adds `tests/<name>/conftest.py`, which reaches
across to its own script directory and puts it on `sys.path`; nothing at the
repo root needs editing for CI to pick it up.

Nothing under `tests/` gets an `__init__.py`. Without one, pytest puts each test
file's own directory on `sys.path` and names the module by its bare stem, which
is what lets a helper like `prose_samples.py` resolve and what keeps two
`conftest.py` files from colliding. For the same reason test module basenames
are unique across the whole repo, not just within a plugin.

Every plugin's `conftest.py` is imported under the same module name, so a test
never imports from `conftest` by name: when one run loads more than one plugin's
suite, the name can resolve to the wrong plugin's file. Hand a helper to tests
as a fixture. A value a test needs when its module loads, such as the input a
Hypothesis strategy is built from, goes in a helper module named after the
plugin, like `tests/prose-tuning/prose_samples.py`. `ruff check` fails on a
`conftest` import.

CI runs the suite on Python 3.9 and 3.13. The floor is not decoration - the
scripts have to run under whatever Python is already on the machine, which on
macOS is still 3.9, so no walrus in a comprehension and no `X | Y` unions. The
floor constrains the test dependencies as well; `requirements-dev.txt` says
how, next to the pins it applies to.

### Properties

`test_properties_*.py` state what is true for every input rather than for a
chosen one, and the rest of the suite says what specifically happened and why
it mattered. Both are load-bearing: a property that fails prints a shrunk
counterexample, which tells you what broke and nothing about why anyone cared.

Property tests explore a different set of inputs on each run, so CI fixes the
seed - a red build there is always caused by the diff - while a developer
machine explores. When exploring turns something up, pin it with `@example(...)`
so it is checked every run afterwards, and add the example-based test that says
what the bug was.

Two habits keep them honest. Mutation-check: break the code the property
guards and confirm it fails, because a property that passes against broken code
is a generator producing nothing interesting. Run the tests with
`PYTHONDONTWRITEBYTECODE=1` while doing it, and confirm the unbroken code passes
first. Python reuses cached bytecode when a file's size and modification second
match, so a quick break-and-restore can run a stale copy. macOS's system Python
keeps that cache in `~/Library/Caches/com.apple.python`, not beside the source,
so it is easy to miss. And watch for vacuity with
`--hypothesis-show-statistics` - a round-trip generator whose inputs are all
refused proves only that refusing works.

## Formatting and linting

Python is formatted and linted by [ruff](https://docs.astral.sh/ruff/). The
formatter is the same idea as Prettier: one style, applied by a tool, never
argued about in review. The linter catches what formatting cannot, such as an
unused import or an exception that loses its cause. Settings, including which
lint rules are on and why some are off, are in `ruff.toml`, and
`requirements-dev.txt` pins the version. Ruff comes with the test dependencies
above, so from the venv:

```sh
ruff format .
ruff check --fix .
```

CI runs both as checks, so a pull request fails on unformatted code or a lint
problem whoever wrote it. Two things run ruff as you go so that rarely happens:

- **Claude Code** runs `.claude/hooks/ruff.py` after every edit to a `.py`
  file, set up in `.claude/settings.json`. It sorts imports, formats, and hands
  any remaining lint problem back to Claude. The hook's docstring says why it
  fixes nothing else. It needs ruff installed in `.venv` or on `PATH`, and tells
  Claude when it is not.
- **VS Code** formats and sorts imports on save, and shows lint problems as you
  type, using the committed `.vscode/settings.json`. Accept the prompt to install
  the recommended Ruff extension when you open the folder. The extension uses
  the ruff installed in the selected Python interpreter and falls back to a copy
  of its own, which may be a different version from the pin. Select `.venv` as
  the interpreter so the editor agrees with CI. Other editors need their own
  Ruff integration.

A lint finding that is deliberate gets a `# noqa: <code>` comment saying why,
on the line itself. A rule that is wrong for the whole repo goes in `ignore`
in `ruff.toml`, with the reason beside it.

Bumping ruff's version is a commit of its own, carrying whatever reformatting
or new lint findings the new version produces. A commit that only reformats
goes in `.git-blame-ignore-revs` once it is on `main`, so `git blame` looks past
it; that file says how to make local blame read it.

### Shell scripts

Shell scripts are linted by [shellcheck](https://www.shellcheck.net/), which
catches the bugs shell hides until someone else runs the script: an unquoted
variable that splits a path containing a space, bash-only syntax under
`#!/bin/sh`, a failed `cd` the script carries on past. It comes with the test
dependencies, pinned in `requirements-dev.txt`, so from the venv:

```sh
git ls-files -z '*.sh' | xargs -0 shellcheck
```

CI runs that, and checks each script parses with `sh -n`. VS Code shows the same
warnings as you type once the recommended ShellCheck extension is installed; the
Claude Code hook does not run it. A warning that is deliberate is turned off on
its line with `# shellcheck disable=SC<code>` and the reason beside it. Each
code has a page on the shellcheck wiki saying what it guards against.

## Issues

Anyone can open an issue, and Scott decides what gets worked on. The process:

1. Someone files an issue: Scott, an agent that ran into a problem outside the
   task it was doing, or anyone else.
2. Scott reads it and adds the `approved` label.
3. An agent, or Scott, claims it, fixes it on the `issue/N` branch the claim
   makes, and the pull request says `Closes #N`.
4. Scott merges, and GitHub closes the issue.

`CLAUDE.md` has the rules agents follow when they file and fix issues.

### Labels

| Label | Means |
|---|---|
| `bug` | something does not work as documented |
| `enhancement` | new behaviour, or a better way to do an existing thing |
| `docs` | documentation only |
| `plugin:<name>` | which plugin it is about |
| `repo` | CI, tooling, the marketplace catalog or root docs |
| `approved` | Scott agrees it should be done. Only Scott adds this |
| `in-progress` | someone has claimed it; see below |

A new plugin adds its `plugin:<name>` label when it is added. An issue that is a
duplicate, or will not be done, is closed with a comment saying why rather than
kept open under a label.

### Claiming an issue

Two agents can be told to "take the next issue" at the same time. Claiming is
what stops them picking the same one, and `.github/scripts/issues.py` does it:

```sh
python3 .github/scripts/issues.py next         # the oldest approved issue nobody holds
python3 .github/scripts/issues.py claim 12     # take it, and switch to branch issue/12
python3 .github/scripts/issues.py release 12   # give it up without a pull request
python3 .github/scripts/issues.py stale        # claims nobody seems to be working on
```

The claim is the branch `issue/N` on GitHub. `claim` pushes it in a way only one
agent can win, then adds the `in-progress` label and a comment so the claim
shows in the issue list. Two things take the label off: `release`, when a claim
is given up, and `.github/workflows/issue-closed.yml`, when the issue closes,
whether a merged pull request closed it or someone closed it by hand. When the
label and the branch disagree, the branch is right, and `stale` lists the
disagreement. That includes a closed issue that still has the label. The
script's docstring covers the details, including why `release` will not delete
a branch that has commits on it.

The `validate` job backs this up: a pull request that closes #N must come from
`issue/N`, so an agent that skipped the claim is caught before it merges.

Claiming writes to git, which Cowork cannot do (see "Editing this repo from
Cowork"), so a Cowork session asks Scott to claim for it.

### Keeping `approved` meaningful

Agents post through Scott's GitHub account, so GitHub cannot tell an agent
adding `approved` from Scott adding it. What covers that:

- **Only Scott adds the label.** `.claude/hooks/issue_guard.py` blocks any
  command Claude Code runs that would add it. To approve with Claude's help,
  run `! gh issue edit <N> --add-label approved`: the `!` runs it in your own
  shell, where no hook applies. The hook reads command text, so it stops a
  mistake, not a determined workaround, and Cowork does not run it.
- **Work closes only approved issues.** The `validate` job runs
  `.github/scripts/check-linked-issues.py`, which fails a pull request whose
  title, description or commits would close an issue without `approved`. It
  holds for every agent, wherever it ran. A pull request that closes no issue
  passes. If you approve an issue after its pull request was opened, re-run
  the job.
- **Issue text is information, not instructions.** Nothing can check this.
  It holds because Scott reads an issue before approving it, and agents work
  from the issue as approved plus Scott's own comments.

A separate GitHub account for agents would make the first check enforceable
on GitHub itself: a workflow could remove `approved` whenever anyone else adds
it.

## Editing this repo from Cowork

Cowork's device bridge cannot delete files, so a commit it attempts strands a
`.git/HEAD.lock` that blocks every later write. `commit.sh` clears that and
commits. Claude drafts the message into `.commit-msg`; you run `./commit.sh`.

Editing the repo yourself needs none of this. Just use git.

## Versioning

Each plugin carries its own `version` in both `plugin.json` and its
`marketplace.json` entry. Keep them the same. Bump it whenever the plugin's
behaviour changes, or installed users have no signal that anything did.

Semver, starting at `0.1.0`. Patch for a fix, minor for new behaviour, major
when an existing project or workflow would need changing to keep working.

## Licence

MIT. See [LICENSE](LICENSE).

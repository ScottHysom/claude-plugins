#!/usr/bin/env python3
"""Keep the test suites out of the plugins, on the names pytest collects, and
able to fail.

Three mistakes this repo can make silently, none visible from a diff:

Everything under `plugins/<name>/` is copied verbatim into every install.
marketplace.json points each plugin at its own directory and Claude Code copies
that subtree into the plugin cache, so a test file beside a script ships to
everyone who installs the plugin - carrying pytest and hypothesis imports into
a plugin whose scripts are standard-library-only on purpose. `placement` is
what notices.

pytest.ini replaces pytest's default `python_functions` and `python_classes`
rather than adding to them, so a test left as `def test_x` matches nothing: it
is not run, and not reported either, and the suite stays green one test
lighter. `naming` is what notices.

A new test that passes on the code before the change it tests would pass
without that change, so it shows nothing about it. `fails-on-base` is what
notices.

Run from anywhere in the clone:

    python3 .github/scripts/check-tests.py placement
    python3 .github/scripts/check-tests.py naming
    python3 .github/scripts/check-tests.py fails-on-base --base origin/main

Commands:

  placement      every test file sits under a root pytest.ini collects, and
                 none sits under plugins/
  naming         no test is on pytest's default prefixes
  fails-on-base  no test the branch adds since its merge base with --base
                 passes on the merge base's code, unless it carries
                 @pytest.mark.passes_on_base("<reason>")

Every command takes --json and -C/--repo.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Things that look like bugs and are not:

- It asks git for the file list rather than walking the tree. __pycache__, the
  venv and the hypothesis cache are ignored by git, so they are never strays,
  and no exclusion list here has to be kept in step with .gitignore.
- The list includes untracked files git is not ignoring, so a test file written
  but not yet `git add`ed is checked too. CI checks out a clean tree, where the
  two sets are the same, so CI and a working copy agree.
- `naming` fails when it matches nothing. That is the failure this script
  exists for. The grep it replaced used the pathspec '*/tests/test_*.py', which
  matches no file once a suite sits at tests/<plugin>/, and `if git grep ...;
  then fail; fi` passes when nothing matched. A check that scans nothing is not
  a passing check, so scanning nothing is an error rather than a clean run.
- The roots come from pytest.ini rather than from a list here, so adding a test
  root is one edit and the two cannot drift.
- It only reads, and the only thing it reads through is git, so it is safe to
  run anywhere - including Cowork's device bridge, where a git write would
  strand a lock file. `fails-on-base` writes too, but only under a temporary
  directory: the merge base's tree, from `git archive`, with the branch's
  test roots and pytest.ini copied over it.
- `fails-on-base` finds the new tests by collecting the suite at the branch
  and at the merge base, and runs only those, in one pytest run with
  outcomes_plugin.py loaded. A test passes there only when its setup, call
  and teardown all pass, so one that errors, such as by importing a name the
  base does not have, or is skipped there counts as failing.
- A conftest.py that fails to load stops a pytest run outright, as one does
  when a new plugin's suite loads a script the base does not have.
  `fails-on-base` then fails the new tests under it and runs the rest again.
- A test that is renamed or moved has a new id, so it counts as new. Mark its
  module with `pytestmark = pytest.mark.passes_on_base("moved from ...")`.
"""

import argparse
import configparser
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

import closed_pipe

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-tests.py"
PYTEST_INI = "pytest.ini"
TESTPATHS = "testpaths"
PLUGINS = "plugins"
SUITES = "tests"

# A test file by name, wherever it sits.
TEST_FILE_RE = re.compile(r"^(test_.+|.+_test)\.py$")
# pytest-only files that are not test files themselves.
SUPPORT_FILES = ("conftest.py",)
# The names pytest.ini no longer collects. POSIX-ish rather than \s so a form
# feed inside a docstring cannot look like an indent.
OLD_NAME_RE = re.compile(r"^[ \t]*(def test_|class Test)")
# A plugin script has no business importing either of these.
CONTRIBUTOR_IMPORT_RE = re.compile(r"^[ \t]*(?:import|from)[ \t]+(pytest|hypothesis)\b", re.M)

WHERE = 'README.md, under "Running the tests", says where tests go and why.'

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
# outcomes_plugin.py, beside this script, and the environment it reads.
OUTCOMES_PLUGIN = "outcomes_plugin"
OUTCOMES_ENV = "CHECK_TESTS_OUTCOMES"
SELECT_ENV = "CHECK_TESTS_SELECT"
MARKER = "passes_on_base"
DEFAULT_BASE = "origin/main"
# pytest's exit codes for a run that ran: all passed, some failed, none ran.
PYTEST_RAN = (0, 1, 5)
# What pytest prints when a conftest.py fails to load, which stops the run.
CONFTEST_FAILED_RE = re.compile(r"ImportError while loading conftest '([^']+)'")
FAILS_ON_BASE_WHY = (
    'CLAUDE.md, under "Tests": a new test is not finished until it has failed. Source: the '
    "method's `agents-never-weaken-checks`."
)


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def envelope(command, data, errors=None, warnings=None):
    errors = errors or []
    return {
        "version": ENVELOPE_VERSION,
        "command": command,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings or [],
        "data": data,
    }


def emit(args, command, data, errors=None, warnings=None, human=None, where=WHERE):
    """Print JSON or human output, and return the exit code."""
    errors = errors or []
    warnings = warnings or []
    if args.json:
        print(json.dumps(envelope(command, data, errors, warnings), indent=2, sort_keys=True))
    else:
        if human:
            human()
        for w in warnings:
            sys.stderr.write("warning: %s\n" % w)
        for e in errors:
            sys.stderr.write("%s\n" % e)
        if errors:
            sys.stderr.write("%s\n" % where)
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# the clone
# --------------------------------------------------------------------------


def run(repo, cmd):
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    except OSError as exc:
        raise Fatal("cannot run %s: %s" % (cmd[0], exc)) from exc
    if proc.returncode != 0:
        raise Fatal("`%s` failed: %s" % (" ".join(cmd), proc.stderr.strip()))
    return proc


def toplevel(repo):
    if not os.path.isdir(repo):
        raise Fatal("no such directory: %s" % repo)
    return run(repo, ["git", "rev-parse", "--show-toplevel"]).stdout.strip()


def repo_files(root):
    """Every file git would carry: tracked, plus untracked it is not ignoring."""
    out = run(root, ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]).stdout
    return sorted(set(p for p in out.split("\0") if p))


def test_roots(root):
    """The directories pytest.ini collects, so this script and pytest agree."""
    path = os.path.join(root, PYTEST_INI)
    if not os.path.isfile(path):
        raise Fatal("no %s at %s" % (PYTEST_INI, root))
    parser = configparser.ConfigParser()
    parser.read(path)
    if not parser.has_option("pytest", TESTPATHS):
        raise Fatal("%s has no %s to read the test roots from" % (PYTEST_INI, TESTPATHS))
    roots = parser.get("pytest", TESTPATHS).split()
    if not roots:
        raise Fatal("%s sets %s to nothing" % (PYTEST_INI, TESTPATHS))
    return roots


# --------------------------------------------------------------------------
# the base
# --------------------------------------------------------------------------


def merge_base(root, ref):
    proc = subprocess.run(
        ["git", "merge-base", ref, "HEAD"], cwd=root, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise Fatal(
            "cannot find where HEAD left %s: %s. Pass --base the ref the branch merges into, "
            "such as origin/main." % (ref, proc.stderr.strip() or "no common commit")
        )
    return proc.stdout.strip()


def extract(root, commit, dest):
    """Write the tree at `commit` into `dest`, reading git and writing nothing to it."""
    proc = subprocess.run(["git", "archive", "--format=tar", commit], cwd=root, capture_output=True)
    if proc.returncode != 0:
        raise Fatal("`git archive %s` failed: %s" % (commit, proc.stderr.decode().strip()))
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        # The data filter is the default from Python 3.14, and older versions
        # warn without it. 3.9 has no filter at all.
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:  # pragma: no cover - only Python before 3.12 lacks the filter
            tar.extractall(dest)


def overlay(root, dest, roots):
    """Replace the test roots and pytest.ini in `dest` with the branch's."""
    for name in roots:
        shutil.rmtree(os.path.join(dest, name), ignore_errors=True)
    for path in repo_files(root):
        if path != PYTEST_INI and not any(under(path, name) for name in roots):
            continue
        source = os.path.join(root, path)
        if not os.path.isfile(source):
            continue
        target = os.path.join(dest, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)


def pytest_run(cwd, scratch, argv, select=None):
    """Run pytest with outcomes_plugin: (what it wrote, or None, exit code, stderr)."""
    out = os.path.join(scratch, "outcomes.json")
    if os.path.exists(out):
        os.remove(out)
    env = dict(os.environ)
    env[OUTCOMES_ENV] = out
    env["PYTHONPATH"] = os.pathsep.join(p for p in (SCRIPTS, env.get("PYTHONPATH")) if p)
    env.pop(SELECT_ENV, None)
    if select is not None:
        chosen = os.path.join(scratch, "select.json")
        with open(chosen, "w") as fh:
            json.dump(select, fh)
        env[SELECT_ENV] = chosen
    cmd = [sys.executable, "-m", "pytest", "-p", OUTCOMES_PLUGIN, "-p", "no:cacheprovider"]
    cmd += ["-n", "0", "-q", "--no-header", *argv]
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    except OSError as exc:  # pragma: no cover - this Python is running
        raise Fatal("cannot run pytest: %s" % exc) from exc
    result = None
    if os.path.isfile(out):
        with open(out) as fh:
            result = json.load(fh)
    return result, proc.returncode, proc.stdout + proc.stderr


def collect(cwd, scratch, where):
    """Every test id pytest collects in `cwd`, mapped to its marker's reason."""
    result, code, output = pytest_run(cwd, scratch, ["--collect-only"])
    if result is None or code not in PYTEST_RAN or result["errors"]:
        raise Fatal(
            "pytest cannot collect the suite at %s, so the new tests are unknown. Fix what "
            "it reports:\n%s" % (where, output.strip()[-2000:])
        )
    return result["collected"]


def run_on_base(dest, scratch, new):
    """How each new test ends in `dest`, in one pytest run, and every test that ran.

    A conftest.py that fails to load stops the whole run, as one does when a
    new suite loads a script the base does not have. Each new test under that
    conftest's directory then cannot run on the base, so it is failed and the
    run starts again without it.
    """
    outcomes, ran = {}, []
    left = list(new)
    while left:
        files = sorted(set(nodeid.split("::")[0] for nodeid in left))
        argv = ["--continue-on-collection-errors", *files]
        result, code, output = pytest_run(dest, scratch, argv, select=left)
        broken = CONFTEST_FAILED_RE.search(output)
        if result is None and broken:
            # pytest names the conftest by its real path, and a temporary
            # directory can sit behind a symlink, as /var does on macOS.
            conftest = os.path.realpath(broken.group(1))
            directory = os.path.relpath(os.path.dirname(conftest), os.path.realpath(dest))
            directory = directory.replace(os.sep, "/")
            stuck = [n for n in left if directory == "." or under(n.split("::")[0], directory)]
            if not stuck:
                raise Fatal("pytest cannot load %s on the base:\n%s" % (broken.group(1), output))
            for nodeid in stuck:
                outcomes[nodeid] = "error"
            left = [n for n in left if n not in stuck]
            continue
        if result is None or code not in PYTEST_RAN:
            raise Fatal(
                "pytest stopped running the new tests on the base, exiting %d:\n%s"
                % (code, output.strip()[-2000:])
            )
        for nodeid in left:
            outcomes[nodeid] = result["outcomes"].get(nodeid, "error")
        ran = sorted(result["outcomes"])
        break
    return outcomes, ran


# --------------------------------------------------------------------------
# classifying a path
# --------------------------------------------------------------------------


def under(path, directory):
    return path == directory or path.startswith(directory + "/")


def is_test_file(path):
    return bool(TEST_FILE_RE.match(os.path.basename(path)))


def is_test_artifact(path):
    """A file that exists for pytest: a test, a conftest, or anything in tests/."""
    name = os.path.basename(path)
    return is_test_file(path) or name in SUPPORT_FILES or SUITES in path.split("/")[:-1]


def imports_contributor_dep(root, path):
    if not path.endswith(".py"):
        return False
    try:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
            return bool(CONTRIBUTOR_IMPORT_RE.search(fh.read()))
    except OSError:
        return False


def destination(path):
    """Where a stray under plugins/<name>/ should have gone."""
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != PLUGINS:
        return None
    return "%s/%s/%s" % (SUITES, parts[1], os.path.basename(path))


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_placement(args, root):
    roots = test_roots(root)
    files = repo_files(root)
    strays = []

    for path in files:
        in_plugins = under(path, PLUGINS)
        artifact = is_test_artifact(path)
        if in_plugins and not artifact and imports_contributor_dep(root, path):
            artifact = True
        if not artifact:
            continue
        if in_plugins:
            strays.append({"path": path, "destination": destination(path), "reason": "ships"})
        elif not any(under(path, r) for r in roots):
            strays.append({"path": path, "destination": None, "reason": "not-collected"})

    errors = []
    for stray in strays:
        if stray["reason"] == "ships":
            errors.append(
                "%s is a test file under %s/. Everything under %s/<name>/ is copied into "
                "every install, so this ships to every user. Move it to %s"
                % (stray["path"], PLUGINS, PLUGINS, stray["destination"])
            )
        else:
            errors.append(
                "%s is a test file outside every root pytest collects (%s), so nothing runs "
                "it and nothing reports it missing. Move it under one of those, or delete it."
                % (stray["path"], ", ".join(roots))
            )

    warnings = []
    suites = set(p.split("/")[1] for p in files if under(p, SUITES) and len(p.split("/")) > 2)
    plugins = set(p.split("/")[1] for p in files if under(p, PLUGINS) and len(p.split("/")) > 2)
    for name in sorted(suites - plugins):
        warnings.append("%s/%s is a suite for a plugin that does not exist" % (SUITES, name))
    scripted = set(
        p.split("/")[1]
        for p in files
        if under(p, PLUGINS) and "/scripts/" in p and p.endswith(".py")
    )
    for name in sorted(scripted - suites):
        warnings.append("%s/%s has a script but no suite at %s/%s" % (PLUGINS, name, SUITES, name))

    def human():
        if not strays:
            print(
                "No test file under %s/. %d files checked against %d roots."
                % (PLUGINS, len(files), len(roots))
            )

    data = {"roots": roots, "checked": len(files), "strays": strays}
    return emit(args, "placement", data, errors, warnings, human)


def cmd_naming(args, root):
    roots = test_roots(root)
    files = repo_files(root)
    scanned, offenses = [], []

    for path in files:
        if not is_test_file(path):
            continue
        scanned.append(path)
        try:
            with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError as exc:
            raise Fatal("cannot read %s: %s" % (path, exc)) from exc
        for number, line in enumerate(lines, 1):
            if OLD_NAME_RE.match(line):
                offenses.append({"path": path, "line": number, "text": line.strip()})

    errors = [
        "%s:%d: `%s` is a name pytest does not collect. Name it it_<does x> in a "
        "Describe<Subject> class; CLAUDE.md, Tests" % (o["path"], o["line"], o["text"])
        for o in offenses
    ]

    # A check that scanned nothing is the failure this command exists for.
    if not scanned:
        errors.append(
            "no file matched %s anywhere in the clone. This check is scanning nothing, "
            "which is exactly how a misnamed test gets through." % TEST_FILE_RE.pattern
        )
    else:
        for name in roots:
            if not os.path.isdir(os.path.join(root, name)):
                continue
            if not any(under(p, name) for p in scanned):
                errors.append(
                    "%s is a root pytest collects but no test file under it matched %s; "
                    "the check has gone blind there." % (name, TEST_FILE_RE.pattern)
                )

    def human():
        if not errors:
            print("%d test files, all on the names pytest collects." % len(scanned))

    data = {"roots": roots, "scanned": scanned, "offenses": offenses}
    return emit(args, "naming", data, errors, None, human)


def cmd_fails_on_base(args, root):
    roots = test_roots(root)
    base = merge_base(root, args.base)
    with tempfile.TemporaryDirectory() as scratch:
        dest = os.path.join(scratch, "base")
        os.mkdir(dest)
        extract(root, base, dest)
        branch = collect(root, scratch, "the branch")
        before = collect(dest, scratch, "the merge base %s" % base[:12])
        new = sorted(set(branch) - set(before))
        outcomes, ran = {}, []
        if new:
            overlay(root, dest, roots)
            outcomes, ran = run_on_base(dest, scratch, new)

    errors, warnings, excused = [], [], {}
    for nodeid in new:
        if outcomes[nodeid] != "passed":
            continue
        reason = branch[nodeid]
        if reason is None:
            errors.append(
                "%s passes against the code at the merge base with %s, so it would pass "
                "without the change it tests. Make it fail there first. If it pins "
                'behavior the change keeps, mark it @pytest.mark.%s("<why>").'
                % (nodeid, args.base, MARKER)
            )
        elif not reason.strip():
            errors.append(
                "%s carries %s without a reason. Say why it passes before the change, as "
                '@pytest.mark.%s("<why>").' % (nodeid, MARKER, MARKER)
            )
        else:
            excused[nodeid] = reason
            warnings.append("%s passes on the base, excused: %s" % (nodeid, reason))

    def human():
        if not errors:
            print(
                "%d new test(s) against the merge base %s, none passing there unexcused."
                % (len(new), base[:12])
            )

    data = {"base": base, "new": new, "ran": ran, "outcomes": outcomes, "excused": excused}
    return emit(args, "fails-on-base", data, errors, warnings, human, where=FAILS_ON_BASE_WHY)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Keep test files out of the plugins and on the house names."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "placement", parents=[common], help="no test file ships, or goes uncollected"
    )
    p.set_defaults(func=cmd_placement)

    p = sub.add_parser("naming", parents=[common], help="no test on pytest's default prefixes")
    p.set_defaults(func=cmd_naming)

    p = sub.add_parser(
        "fails-on-base", parents=[common], help="no new test passes on the code before the change"
    )
    p.add_argument(
        "--base",
        metavar="REF",
        default=DEFAULT_BASE,
        help="the ref the branch merges into (default: %(default)s)",
    )
    p.set_defaults(func=cmd_fails_on_base)

    return ap


@closed_pipe.exits_ok
def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, toplevel(args.repo))
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN


if __name__ == "__main__":
    sys.exit(main())

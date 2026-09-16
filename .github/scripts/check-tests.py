#!/usr/bin/env python3
"""Keep the test suites out of the plugins, and on the names pytest collects.

Two mistakes this repo can make silently, neither visible from a diff:

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

Run from anywhere in the clone:

    python3 .github/scripts/check-tests.py placement
    python3 .github/scripts/check-tests.py naming

Commands:

  placement  every test file sits under a root pytest.ini collects, and none
             sits under plugins/
  naming     no test is on pytest's default prefixes

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
  strand a lock file.
"""

import argparse
import configparser
import json
import os
import re
import subprocess
import sys

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


def emit(args, command, data, errors=None, warnings=None, human=None):
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
            sys.stderr.write("%s\n" % WHERE)
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
# classifying a path
# --------------------------------------------------------------------------


def under(path, directory):
    return path == directory or path.startswith(directory + "/")


def is_test_file(path):
    return bool(TEST_FILE_RE.match(os.path.basename(path)))


def is_test_artefact(path):
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
        artefact = is_test_artefact(path)
        if in_plugins and not artefact and imports_contributor_dep(root, path):
            artefact = True
        if not artefact:
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
    scanned, offences = [], []

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
                offences.append({"path": path, "line": number, "text": line.strip()})

    errors = [
        "%s:%d: `%s` is a name pytest does not collect. Name it it_<does x> in a "
        "Describe<Subject> class; CLAUDE.md, Tests" % (o["path"], o["line"], o["text"])
        for o in offences
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

    data = {"roots": roots, "scanned": scanned, "offences": offences}
    return emit(args, "naming", data, errors, None, human)


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

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, toplevel(args.repo))
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN
    except BrokenPipeError:
        return OK


if __name__ == "__main__":
    sys.exit(main())

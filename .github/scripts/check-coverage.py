#!/usr/bin/env python3
"""Hold each plugin script's test coverage where it is, and let it only rise.

CLAUDE.md asks for a pytest suite for every script, and a suite can pass while
whole branches of its script never run. A spec traced through the tests cannot
see a line no test runs. This reads the JSON report coverage.py writes and
fails a pull request that lets a plugin script's coverage fall, or that adds a
line to one that no test runs.

Run from the clone, after the suite has run under coverage:

    pytest --cov --cov-report=json:coverage.json
    python3 .github/scripts/check-coverage.py floors --base origin/main
    python3 .github/scripts/check-coverage.py diff --base origin/main
    python3 .github/scripts/check-coverage.py pragmas

Commands:

  floors   every plugin script's branch coverage is at or above its floor in
           .github/coverage-floors.json, every script has a floor, and with
           --base no floor is lower than it is at that ref
  diff     no line a plugin script adds since its merge base with --base is a
           line coverage says no test ran
  pragmas  every `# pragma: no cover` in a plugin script gives its reason on
           the same line, as `# pragma: no cover - <reason>`

Every command takes --json and -C/--repo.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Things that look like bugs and are not:

- The plugin scripts come from git, not from the report. A script no test
  imports is then still a script, and one the report leaves out fails rather
  than passing unseen. .coveragerc's `source` has coverage report such a
  script at 0% as well.
- The coverage figure is coverage.py's own `percent_covered`, which counts
  branches as well as statements when the run measured branches. A report
  measured without branches stops the run, because its figures are not
  comparable with the floors.
- `floors` warns, rather than fails, when a script is above its floor. The
  warning prints the figure to raise the floor to, which is how a floor rises.
- CI measures on one Python version only. Branch arcs differ between Python
  versions, so the floors are that version's figures, and a local run on
  another version can land a little either side of them.
- `diff` compares the merge base with the working tree, not with HEAD, so
  locally it covers uncommitted edits too, as the report does. CI checks out a
  clean tree, where the two are the same. A script that did not exist at the
  merge base counts every line as added, tracked or not.
- A line the report does not list as missing is a line that ran, or one
  coverage does not count: a blank line, a comment, or one a pragma excludes.
  So `diff` flags only statements.
- `pragmas` finds the pragma with coverage.py's default exclusion pattern, so
  it sees exactly the lines coverage skips.
- It only reads, and the only thing it reads through is git, so it is safe to
  run anywhere, including Cowork's device bridge.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-coverage.py"
FLOORS_FILE = ".github/coverage-floors.json"
DEFAULT_REPORT = "coverage.json"

# A plugin's script, as CLAUDE.md places it: plugins/<plugin>/scripts/<name>.py.
PLUGIN_SCRIPT_RE = re.compile(r"^plugins/[^/]+/scripts/[^/]+\.py$")
# coverage.py's default exclusion pattern, so this sees the lines coverage skips.
PRAGMA_RE = re.compile(r"#\s*(?:pragma|PRAGMA)[:\s]?\s*(?:no|NO)\s*(?:cover|COVER)")
# What must follow the pragma on its line: a dash and a reason.
REASON_RE = re.compile(r"^\s*-\s*\S")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# Floors are kept to this many decimals, rounded down so a floor never sits
# above the figure it was taken from.
FLOOR_DECIMALS = 2

WHERE = 'README.md, under "Coverage", says how coverage is checked.'


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


def git(repo, *argv, check=True):
    cmd = ["git", *argv]
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    except OSError as exc:
        raise Fatal("cannot run git: %s" % exc) from exc
    if check and proc.returncode != 0:
        raise Fatal("`%s` failed: %s" % (" ".join(cmd), proc.stderr.strip()))
    return proc


def toplevel(repo):
    if not os.path.isdir(repo):
        raise Fatal("no such directory: %s" % repo)
    return git(repo, "rev-parse", "--show-toplevel").stdout.strip()


def plugin_scripts(root):
    """Every plugin script git would carry: tracked, plus untracked it is not ignoring."""
    out = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout
    scripts = sorted(set(p for p in out.split("\0") if PLUGIN_SCRIPT_RE.match(p)))
    if not scripts:
        raise Fatal(
            "no file matched %s in the clone, so there is nothing to check. "
            "A check that scans nothing is not a passing check." % PLUGIN_SCRIPT_RE.pattern
        )
    return scripts


def read_lines(root, path):
    try:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError as exc:
        raise Fatal("cannot read %s: %s" % (path, exc)) from exc


def resolve(root, ref):
    """The commit a ref names, or stop with what to do about it."""
    proc = git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False)
    if proc.returncode != 0:
        raise Fatal(
            "%s is not a commit in this clone. Fetch it first, for example "
            "`git fetch origin main`, or pass --base a ref that exists." % ref
        )
    return proc.stdout.strip()


def exists_at(root, commit, path):
    return git(root, "cat-file", "-e", "%s:%s" % (commit, path), check=False).returncode == 0


# --------------------------------------------------------------------------
# the report and the floors
# --------------------------------------------------------------------------


def load_report(root, path):
    """coverage.py's JSON report, keyed by path relative to the clone."""
    full = os.path.join(root, path)
    if not os.path.isfile(full):
        raise Fatal(
            "no coverage report at %s. Run `pytest --cov --cov-report=json:%s` "
            "from the clone first." % (path, DEFAULT_REPORT)
        )
    try:
        with open(full, encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Fatal("cannot read the coverage report %s: %s" % (path, exc)) from exc
    if not report.get("meta", {}).get("branch_coverage"):
        raise Fatal(
            "%s was measured without branch coverage, so its figures cannot be compared "
            "with the floors. .coveragerc sets `branch = True`; run pytest from the clone "
            "so it is read." % path
        )
    files = {}
    for name, entry in report.get("files", {}).items():
        if os.path.isabs(name):
            name = os.path.relpath(name, root)
        files[name.replace(os.sep, "/")] = entry
    return files


def parse_floors(text, where):
    try:
        floors = json.loads(text)
    except ValueError as exc:
        raise Fatal("%s is not valid JSON: %s" % (where, exc)) from exc
    if not isinstance(floors, dict) or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in floors.values()
    ):
        raise Fatal("%s must map each script's path to a number" % where)
    return floors


def load_floors(root):
    path = os.path.join(root, FLOORS_FILE)
    if not os.path.isfile(path):
        raise Fatal("no %s. It holds each plugin script's coverage floor." % FLOORS_FILE)
    with open(path, encoding="utf-8") as fh:
        return parse_floors(fh.read(), FLOORS_FILE)


def floor_of(percent):
    """The floor a figure sets: rounded down, so it never sits above the figure."""
    scale = 10**FLOOR_DECIMALS
    return math.floor(percent * scale) / scale


# --------------------------------------------------------------------------
# the diff
# --------------------------------------------------------------------------


def added_lines(root, base, path):
    """Line numbers in the working tree that the merge base does not have."""
    if not exists_at(root, base, path):
        return list(range(1, len(read_lines(root, path)) + 1))
    out = git(root, "diff", "-U0", "--no-color", "--no-ext-diff", base, "--", path).stdout
    added = []
    number = 0
    for line in out.splitlines():
        match = HUNK_RE.match(line)
        if match:
            number = int(match.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            added.append(number)
            number += 1
    return added


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_floors(args, root):
    scripts = plugin_scripts(root)
    report = load_report(root, args.report)
    floors = load_floors(root)
    errors, warnings, measured = [], [], {}

    for path in scripts:
        entry = report.get(path)
        if entry is None:
            errors.append(
                "%s is not in the coverage report, so nothing measured it. Run the whole "
                "suite with --cov from the clone, and give the script a suite if it has none."
                % path
            )
            continue
        percent = entry["summary"]["percent_covered"]
        measured[path] = percent
        if path not in floors:
            errors.append(
                "%s has no floor in %s. Add it at %.*f, its figure now."
                % (path, FLOORS_FILE, FLOOR_DECIMALS, floor_of(percent))
            )
        elif percent < floors[path]:
            errors.append(
                "%s is covered %.2f%%, below its floor of %.2f%%. Add tests that run the "
                "lines and branches the report lists as missing." % (path, percent, floors[path])
            )
        elif floor_of(percent) > floors[path]:
            warnings.append(
                "%s is covered %.2f%%, above its floor of %.2f%%. Raise the floor in %s to %.*f."
                % (path, percent, floors[path], FLOORS_FILE, FLOOR_DECIMALS, floor_of(percent))
            )

    for path in sorted(set(floors) - set(scripts)):
        errors.append(
            "%s has a floor in %s but is not a plugin script. Remove the floor."
            % (path, FLOORS_FILE)
        )

    lowered = []
    if args.base:
        commit = resolve(root, args.base)
        if exists_at(root, commit, FLOORS_FILE):
            text = git(root, "show", "%s:%s" % (commit, FLOORS_FILE)).stdout
            before = parse_floors(text, "%s at %s" % (FLOORS_FILE, args.base))
            for path in sorted(set(before) & set(floors)):
                if floors[path] < before[path]:
                    lowered.append(path)
                    errors.append(
                        "%s's floor fell from %.2f to %.2f against %s. A floor only rises; "
                        "add tests instead of lowering it."
                        % (path, before[path], floors[path], args.base)
                    )

    def human():
        if not errors:
            for path in scripts:
                print("%s %.2f%% (floor %.2f%%)" % (path, measured[path], floors[path]))

    data = {"measured": measured, "floors": floors, "lowered": lowered}
    return emit(args, "floors", data, errors, warnings, human)


def cmd_diff(args, root):
    scripts = plugin_scripts(root)
    report = load_report(root, args.report)
    base = git(root, "merge-base", resolve(root, args.base), "HEAD").stdout.strip()
    errors, unrun, checked = [], [], 0

    for path in scripts:
        added = added_lines(root, base, path)
        if not added:
            continue
        checked += len(added)
        entry = report.get(path)
        if entry is None:
            errors.append(
                "%s adds %d lines and is not in the coverage report, so no test ran any of "
                "them. Give it a suite under tests/, and run the whole suite with --cov."
                % (path, len(added))
            )
            continue
        missing = set(entry.get("missing_lines", []))
        text = read_lines(root, path)
        for number in added:
            if number in missing:
                unrun.append({"path": path, "line": number})
                errors.append(
                    "%s:%d: no test runs this new line: `%s`. Add a test that does, or mark "
                    "it `# pragma: no cover - <reason>`." % (path, number, text[number - 1].strip())
                )

    def human():
        if not errors:
            print("%d added lines in plugin scripts; every one runs under the suite." % checked)

    data = {"base": base, "checked": checked, "unrun": unrun}
    return emit(args, "diff", data, errors, None, human)


def cmd_pragmas(args, root):
    scripts = plugin_scripts(root)
    errors, found = [], []

    for path in scripts:
        for number, line in enumerate(read_lines(root, path), 1):
            match = PRAGMA_RE.search(line)
            if not match:
                continue
            reasoned = bool(REASON_RE.match(line[match.end() :]))
            found.append({"path": path, "line": number, "reasoned": reasoned})
            if not reasoned:
                errors.append(
                    "%s:%d: `%s` excludes the line from coverage without saying why. "
                    "Write it as `# pragma: no cover - <reason>`." % (path, number, line.strip())
                )

    def human():
        if not errors:
            print(
                "%d pragmas in %d plugin scripts, each with its reason."
                % (len(found), len(scripts))
            )

    data = {"scripts": scripts, "pragmas": found}
    return emit(args, "pragmas", data, errors, None, human)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    reported = argparse.ArgumentParser(add_help=False)
    reported.add_argument(
        "--report",
        metavar="PATH",
        default=DEFAULT_REPORT,
        help="coverage.py's JSON report, relative to the clone (default: %(default)s)",
    )

    ap = argparse.ArgumentParser(
        prog=PROG, description="Hold each plugin script's test coverage at its floor."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "floors", parents=[common, reported], help="no plugin script falls below its floor"
    )
    p.add_argument("--base", metavar="REF", help="also fail a floor lowered since this ref")
    p.set_defaults(func=cmd_floors)

    p = sub.add_parser(
        "diff", parents=[common, reported], help="no added plugin line goes unrun by the suite"
    )
    p.add_argument("--base", metavar="REF", required=True, help="the branch being merged into")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("pragmas", parents=[common], help="every no-cover pragma gives its reason")
    p.set_defaults(func=cmd_pragmas)

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

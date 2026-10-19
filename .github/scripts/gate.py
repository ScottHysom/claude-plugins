#!/usr/bin/env python3
"""Run each of the repo's gates as one command, the same one CI runs.

A unit of work is done when `check` passes, and a pull request is ready when
`verify` passes. CLAUDE.md says so. Before this script, a contributor ran the
formatter, the linter, the suite and each `check-*.py` command by hand from a
list in README.md, and CI ran its own list of named steps. The two lists could
drift, and a green `pytest` passed for a done unit. CI now runs `verify`
through this script, so the local gate and CI's are the same list.

Each gate runs the one before it:

  build   nothing. The repo ships its scripts as source.
  test    the suite, without coverage.
  check   lint, then the suite under coverage, then every repo check that
          reads only the clone.
  verify  check, then the checks that read the base branch or the pull
          request. One of those, the flywheel plugin's `fails-on-base`,
          runs each test the branch adds against the base branch's code,
          with the test commands in .flywheel/gates.json.

Run from anywhere in the clone, with the Python of the venv that holds
requirements-dev.txt:

    python3 .github/scripts/gate.py build
    python3 .github/scripts/gate.py test
    python3 .github/scripts/gate.py check
    python3 .github/scripts/gate.py verify --base origin/main

Commands:

  build   say there is nothing to build
  test    run the suite
  check   run lint, the suite under coverage and the local checks
  verify  run check, then the base-branch and pull request checks

Every command takes --json and -C/--repo. `verify` also takes --base, the ref
the branch merges into, origin/main by default.

Exit codes: 0 clean, 1 a step failed, 2 could not run, including a step that
itself exited 2.

Things that look like bugs and are not:

- Each command prints its chain to stderr before it runs a step, so a reader
  sees what "passed" covered. With --json, the chain is in `data` instead,
  and each step's output is captured there rather than streamed.
- The first failing step stops the run. The steps after it read what the
  earlier ones made, such as coverage.json, so their answer would mean
  nothing.
- Some checks cannot give CI's answer on this machine. They are skipped and
  named, with the reason, as warnings:
  - `floors` off the Python version its floors were measured on, which
    check-coverage.py's FLOORS_PYTHON names. It would exit 2 there.
  - the checks that read the pull request, outside a pull_request event:
    check-linked-issues.py, `check-pr.py description` and
    `check-specs.py changes`. `check-pr.py description --body-file` checks a
    drafted description before the pull request exists.
- The tools run from the venv of the Python running this script. Its
  directory goes first on the steps' PATH, so `python3 .venv/bin/...` and an
  activated venv find the same ruff and shellcheck. A tool it cannot find
  stops the run before any step, and names the install.
- It writes only what its steps write: coverage.json and .coverage, which git
  ignores.
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys

import closed_pipe

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "gate.py"
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
# The flywheel plugin's script, which runs each new test against the base.
FLYWHEEL = os.path.join(
    os.path.dirname(os.path.dirname(SCRIPTS)), "plugins", "flywheel", "scripts", "flywheel.py"
)
CHECK_COVERAGE = os.path.join(SCRIPTS, "check-coverage.py")
DEFAULT_BASE = "origin/main"
PLUGINS = "plugins"
PLUGIN_MANIFEST = os.path.join(".claude-plugin", "plugin.json")
EVENT_NAME_ENV = "GITHUB_EVENT_NAME"
PULL_REQUEST_EVENT = "pull_request"

# The tools the steps run. A module runs as `python -m <module>`, so it comes
# from the same Python as this script, and so does coverage.json's version.
MODULES = ("pytest", "pytest_cov", "xdist", "ruff")
DEV_INSTALL = (
    "install the contributor tools with `pip install -r requirements-dev.txt` in a "
    "venv, and run gate.py with that venv's python3"
)
CLAUDE_INSTALL = "install Claude Code, whose `claude` CLI validates the plugin manifests"
EXECUTABLES = {"shellcheck": DEV_INSTALL, "claude": CLAUDE_INSTALL}

COVERAGE_REPORT = "--cov-report=json:coverage.json"
SUITE = ["-m", "pytest"]
SUITE_UNDER_COVERAGE = [*SUITE, "--cov", COVERAGE_REPORT, "--cov-report=term-missing:skip-covered"]


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


def emit(args, command, data, errors=None, warnings=None, human=None, code=None):
    """Print JSON or human output, and return the exit code."""
    errors = errors or []
    warnings = warnings or []
    if args.json:
        print(json.dumps(envelope(command, data, errors, warnings), indent=2, sort_keys=True))
    else:
        for w in warnings:
            sys.stderr.write("warning: %s\n" % w)
        for e in errors:
            sys.stderr.write("%s\n" % e)
        if human and not errors:
            human()
    if code is not None:
        return code
    return PROBLEMS if errors else OK


def progress(args, text):
    if not args.json:
        sys.stderr.write("%s\n" % text)
        sys.stderr.flush()


# --------------------------------------------------------------------------
# the machine
# --------------------------------------------------------------------------


def execute(argv, cwd, env, capture):
    """Run one command: (exit code, stdout, stderr). Tests replace this."""
    try:
        proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=capture, text=True)
    except OSError as exc:
        raise Fatal("cannot run %s: %s" % (argv[0], exc)) from exc
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def have_module(name):
    """Whether this Python can import `name`. Tests replace this."""
    return importlib.util.find_spec(name) is not None


def find_executable(name, path):
    """The full path of `name` on `path`, or None. Tests replace this."""
    return shutil.which(name, path=path)


def toplevel(repo):
    if not os.path.isdir(repo):
        raise Fatal("no such directory: %s. Pass -C a directory in the clone." % repo)
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True
        )
    except OSError as exc:  # pragma: no cover - git is installed wherever this runs
        raise Fatal("cannot run git: %s" % exc) from exc
    if proc.returncode != 0:
        raise Fatal("%s is not in a git clone. Run gate.py from the clone, or pass -C." % repo)
    return proc.stdout.strip()


def floors_python():
    """check-coverage.py's FLOORS_PYTHON, so the two cannot disagree."""
    spec = importlib.util.spec_from_file_location("gate_check_coverage", CHECK_COVERAGE)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError) as exc:
        raise Fatal("cannot load %s: %s" % (CHECK_COVERAGE, exc)) from exc
    return module.FLOORS_PYTHON


class Machine:
    """Where the steps run: the clone, the environment and the tools."""

    def __init__(self, root, environ):
        self.root = root
        self.environ = dict(environ)
        bindir = os.path.dirname(sys.executable)
        self.environ["PATH"] = os.pathsep.join(
            p for p in (bindir, self.environ.get("PATH", "")) if p
        )
        self.tools = {}

    def require(self, modules, executables):
        """Find every tool the steps need, or stop before running any."""
        missing = []
        for name in modules:
            if not have_module(name):
                missing.append("the Python module %s: %s" % (name, DEV_INSTALL))
        for name in executables:
            found = find_executable(name, self.environ["PATH"])
            if found is None:
                missing.append("%s: %s" % (name, EXECUTABLES[name]))
            self.tools[name] = found
        if missing:
            raise Fatal(
                "%s cannot find what its steps run, with %s:\n  %s"
                % (PROG, sys.executable, "\n  ".join(missing))
            )

    def tracked(self, pattern):
        code, out, err = execute(
            ["git", "ls-files", "-z", pattern], self.root, self.environ, capture=True
        )
        if code != 0:
            raise Fatal("`git ls-files %s` failed: %s" % (pattern, err.strip()))
        return [p for p in out.split("\0") if p]

    def pull_request(self):
        return self.environ.get(EVENT_NAME_ENV) == PULL_REQUEST_EVENT


# --------------------------------------------------------------------------
# the steps
# --------------------------------------------------------------------------


class Step:
    """One named step: the commands it runs, or why it fails or is skipped."""

    def __init__(self, name, commands=None, problem=None, skipped=None):
        self.name = name
        self.commands = commands or []
        self.problem = problem
        self.skipped = skipped


def script(name, *argv):
    return [sys.executable, os.path.join(SCRIPTS, name), *list(argv)]


def lint_steps(machine):
    ruff = [sys.executable, "-m", "ruff"]
    shells = machine.tracked("*.sh")
    if shells:
        shell = Step(
            "shell",
            [["sh", "-n", path] for path in shells] + [[machine.tools["shellcheck"], *shells]],
        )
    else:
        shell = Step(
            "shell", problem="`git ls-files '*.sh'` found no shell script to lint, so it is blind."
        )
    return [
        Step("format", [[*ruff, "format", "--check", "--diff", "."]]),
        Step("ruff", [[*ruff, "check", "."]]),
        shell,
    ]


def manifests_step(machine):
    claude = machine.tools["claude"]
    plugins = sorted(
        os.path.join(PLUGINS, name)
        for name in os.listdir(os.path.join(machine.root, PLUGINS))
        if os.path.isfile(os.path.join(machine.root, PLUGINS, name, PLUGIN_MANIFEST))
    )
    if not plugins:
        return Step(
            "manifests",
            problem="found no plugin manifest under %s/. Expected at least one." % PLUGINS,
        )
    return Step(
        "manifests",
        [[claude, "--version"], [claude, "plugin", "validate", "--strict", "."]]
        + [[claude, "plugin", "validate", "--strict", p] for p in plugins],
    )


def floors_step(base):
    running = tuple(sys.version_info[:2])
    wanted = floors_python()
    if running != wanted:
        return Step(
            "floors",
            skipped="the floors are Python %s's figures and this is Python %s. CI checks them."
            % (".".join(map(str, wanted)), ".".join(map(str, running))),
        )
    argv = ["floors"] + (["--base", base] if base else [])
    return Step("floors", [script("check-coverage.py", *argv)])


def check_steps(machine, base=None):
    return {
        "lint": lint_steps(machine),
        "test": [Step("suite", [[sys.executable, *SUITE_UNDER_COVERAGE]])],
        "checks": [
            manifests_step(machine),
            Step("consistency", [script("check-manifest-consistency.py", "check")]),
            Step("drift", [script("check-prose-rules.py", "drift")]),
            Step("descriptions", [script("check-skills.py", "descriptions")]),
            Step("repeats", [script("check-skills.py", "repeats")]),
            Step("commands", [script("check-skills.py", "commands")]),
            Step("steps", [script("check-skills.py", "steps")]),
            Step("fences", [script("check-skills.py", "fences")]),
            Step("placement", [script("check-tests.py", "placement")]),
            Step("naming", [script("check-tests.py", "naming")]),
            Step("pragmas", [script("check-coverage.py", "pragmas")]),
            floors_step(base),
            Step("trace", [script("check-specs.py", "trace")]),
            Step("surface", [script("check-specs.py", "surface")]),
        ],
    }


def pull_request_steps(machine, base):
    steps = [
        Step("linked-issues", [script("check-linked-issues.py")]),
        Step("description", [script("check-pr.py", "description")]),
        Step("changes", [script("check-specs.py", "changes", "--base", base)]),
    ]
    if machine.pull_request():
        return steps
    reason = (
        "it reads the pull request, which only a %s event gives. CI runs it." % PULL_REQUEST_EVENT
    )
    return [Step(s.name, skipped=reason) for s in steps]


def chain_line(command, groups, then=None):
    parts = ", ".join("%s (%s)" % (g, ", ".join(s.name for s in steps)) for g, steps in groups)
    if then:
        parts += ", then " + ", ".join(s.name for s in then)
    return "%s: %s" % (command, parts)


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------


def run_steps(args, machine, command, chain, steps):
    """Run each step in order, stopping at the first that fails."""
    progress(args, chain)
    ran, skipped, warnings = [], [], []
    for step in steps:
        if step.skipped:
            skipped.append({"name": step.name, "reason": step.skipped})
            warnings.append("skipped %s: %s" % (step.name, step.skipped))
            continue
        record = {"name": step.name, "commands": [], "exit": OK}
        ran.append(record)
        if step.problem:
            record["exit"] = PROBLEMS
            record["problem"] = step.problem
        for argv in step.commands:
            if record["exit"] != OK:
                break
            progress(args, "%s: %s: %s" % (command, step.name, " ".join(argv)))
            code, out, err = execute(argv, machine.root, machine.environ, capture=args.json)
            record["commands"].append({"argv": argv, "exit": code, "stdout": out, "stderr": err})
            record["exit"] = code
        if record["exit"] != OK:
            failed = CANNOT_RUN if record["exit"] == CANNOT_RUN else PROBLEMS
            why = record.get("problem") or "it exited %d" % record["exit"]
            error = "%s stopped at %s: %s. Fix what it reported, and run `%s %s` again." % (
                command,
                step.name,
                why,
                PROG,
                command,
            )
            data = {"chain": chain, "steps": ran, "skipped": skipped}
            return emit(args, command, data, [error], warnings, code=failed)

    def human():
        print("%s passed: %s" % (command, ", ".join(r["name"] for r in ran)))

    data = {"chain": chain, "steps": ran, "skipped": skipped}
    return emit(args, command, data, None, warnings, human)


def check_tools(machine):
    machine.require(MODULES, ["shellcheck", "claude"])


def flatten(groups):
    return [step for _, steps in groups for step in steps]


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_build(args, machine):
    def human():
        print("build: nothing to build. The repo ships its scripts as source.")

    return emit(
        args, "build", {"chain": "build: nothing", "steps": [], "skipped": []}, None, None, human
    )


def cmd_test(args, machine):
    machine.require(["pytest", "xdist"], [])
    steps = [Step("suite", [[sys.executable, *SUITE]])]
    chain = chain_line("test", [("test", steps)])
    return run_steps(args, machine, "test", chain, steps)


def cmd_check(args, machine):
    check_tools(machine)
    groups = list(check_steps(machine).items())
    chain = chain_line("check", groups)
    return run_steps(args, machine, "check", chain, flatten(groups))


def cmd_verify(args, machine):
    check_tools(machine)
    groups = list(check_steps(machine, args.base).items())
    then = [
        Step("diff", [script("check-coverage.py", "diff", "--base", args.base)]),
        Step("fails-on-base", [[sys.executable, FLYWHEEL, "fails-on-base", "--base", args.base]]),
    ]
    then += pull_request_steps(machine, args.base)
    chain = "verify: check (%s), then %s. %s" % (
        ", ".join(g for g, _ in groups),
        ", ".join(s.name for s in then),
        chain_line("check", groups),
    )
    return run_steps(args, machine, "verify", chain, flatten(groups) + then)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Run each of the repo's gates as one command."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", parents=[common], help="say there is nothing to build")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("test", parents=[common], help="run the suite")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser(
        "check", parents=[common], help="run lint, the suite under coverage and the local checks"
    )
    p.set_defaults(func=cmd_check)

    p = sub.add_parser(
        "verify", parents=[common], help="run check, then the base-branch and pull request checks"
    )
    p.add_argument(
        "--base",
        metavar="REF",
        default=DEFAULT_BASE,
        help="the ref the branch merges into (default: %(default)s)",
    )
    p.set_defaults(func=cmd_verify)

    return ap


@closed_pipe.exits_ok
def main(argv=None, environ=None):
    args = build_parser().parse_args(argv)
    environ = os.environ if environ is None else environ
    try:
        return args.func(args, Machine(toplevel(args.repo), environ))
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN


if __name__ == "__main__":
    sys.exit(main())

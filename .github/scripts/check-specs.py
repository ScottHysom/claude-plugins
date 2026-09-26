#!/usr/bin/env python3
"""Tie each test and skill step to a requirement in specs/, and list what needs tying.

specs/ records what each plugin, and the repo as a whole, is for.
SPEC-METHODOLOGY.md has the grammar of a spec file and the chain this checks:
a need or a constraint, then a requirement, then the test or step that
verifies it, then the code. Without a check, a test can verify a behavior no
requirement asks for, and a requirement can lose its last test, and CI passes
either way.

`trace` fails a test or a skill step that cites no requirement, a citation of
an id its component's spec lacks, and a requirement nothing verifies the way
its kind says. The kinds, and what verifies each:

  test   a test marked `@pytest.mark.spec("<id>")`, on the test or its class
  step   a `## Step` of a SKILL.md with `<!-- spec: <id>, <id> -->` on a line
         of its own inside it
  check  a step of a workflow in .github/workflows/ with `# spec: <id>` in the
         comment lines directly above its `- name:`

A plugin's test, under tests/<plugin>/, and a plugin's skill step cite that
plugin's specs/<plugin>.md. Every other test, and every workflow step, cites
specs/repo.md. Any of them can name a repo requirement as `repo:<id>`.

The tests and steps that were there before the check are listed in
.github/untraced.json, each keyed to the backfill issue that will trace it:

    {"tests": {"<file>::<class>::<test>": <issue>},
     "steps": {"<SKILL.md path>::<step number>": <issue>}}

A listed item that cites nothing passes with a warning naming its issue. The
list only shrinks: an entry whose item now cites a requirement, or is gone,
fails until it is removed.

`inventory` lists what needs tracing in one plugin, as the input to its
backfill: every subcommand, option and `choices` value its script's
build_parser() accepts, with the skill text that names each; every module-level
set, tuple or list of strings; every test, with the script lines it runs;
every skill step, with the commands it runs; and every script line no test
runs. The lines each test runs come from a coverage report measured per test:

    pytest --cov --cov-context=test --cov-report=json:coverage.json

.coveragerc has the report carry each line's tests.

Run from anywhere in the clone:

    python3 .github/scripts/check-specs.py trace
    python3 .github/scripts/check-specs.py inventory prose-tuning

Commands:

  trace      every test and skill step cites a requirement its spec holds, or
             is listed in .github/untraced.json; every requirement is verified
             the way its kind says
  inventory  what needs tracing in one plugin

Every command takes --json and -C/--repo.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Things that look like bugs and are not:

- The tests are found by reading their source, not by running pytest, so the
  check needs nothing outside the standard library. It reads the files under
  pytest.ini's `testpaths` with pytest's default file names, and in them the
  `Describe*` classes and `it_*` functions that pytest.ini collects. A test is
  one entry however many parameters it runs with.
- A marker on a class cites for every test in it.
- A spec file is parsed only as far as tracing needs: its need and constraint
  headings and the requirement bullets under them. A requirement bullet
  anywhere else, a malformed one, a duplicate id and an unknown kind are
  errors, since the check cannot trace what it cannot read. `eval` is a kind
  SPEC-METHODOLOGY.md names, and nothing in this repo runs an eval yet, so a
  requirement of that kind fails.
- A citation of a requirement of another kind is allowed. A test may cite a
  `step` requirement it also exercises; what `trace` holds a requirement to is
  that its own kind cites it.
- `inventory` counts text as naming a command, an option or a value in two
  places: a script invocation in a skill's shell fence whose arguments hold
  it, and a backticked span in a skill's prose that starts with the command's
  words or holds the option. It lists both, and leaves to the backfill what a
  mention in prose counts for.
- `inventory` reads the parser through argparse's own attributes, `_actions`
  and the subparsers' `choices`, since argparse has no public way to list a
  parser's options.
- Steps and script invocations are read by check-skills.py, loaded by path
  from beside this script, so a step here is the step `check-skills.py steps`
  checks.
- It fails when it has scanned nothing: no spec, no test or no step. A check
  whose file pattern has gone blind passes every pull request.
- It only reads. `trace` reads through git and nothing else. `inventory` also
  imports the plugin's script, from the working tree, to call its
  build_parser(); the script runs main() only under `if __name__ ==
  "__main__":`, so importing it runs no command.
"""

import argparse
import ast
import configparser
import fnmatch
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-specs.py"
SPECS = "specs"
REPO = "repo"
PLUGINS = "plugins"
TESTS = "tests"
SCRIPTS = "scripts"
MARKDOWN = ".md"
UNTRACED_FILE = ".github/untraced.json"
WORKFLOWS = ".github/workflows/"
WORKFLOW_SUFFIXES = (".yml", ".yaml")
PYTEST_INI = "pytest.ini"
DEFAULT_REPORT = "coverage.json"
# check-skills.py, beside this script, reads the steps and the invocations.
CHECK_SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check-skills.py")

# pytest's default test file names; pytest.ini does not change them.
TEST_FILES = ("test_*.py", "*_test.py")
# What pytest.ini collects in those files.
TEST_CLASS_PREFIX = "Describe"
TEST_FUNCTION_PREFIX = "it_"
MARKER = "pytest.mark.spec"
NODE_SEPARATOR = "::"

# A spec file's grammar, from SPEC-METHODOLOGY.md, under "The spec files".
SECTION_RE = re.compile(r"^##[ \t]")
HEADING_RE = re.compile(r"^## (need|constraint) (\S+?):[ \t]+\S")
BULLET_RE = re.compile(r"^[-*+][ \t]")
# A bullet that means to be a requirement: an id in backticks, then a kind.
REQUIREMENT_START_RE = re.compile(r"^- `[^`]*` \(")
REQUIREMENT_RE = re.compile(r"^- `([^`]+)` \(([^)]*)\): \S")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){0,3}$")
TEST, STEP, CHECK, EVAL = "test", "step", "check", "eval"
KINDS = (TEST, STEP, CHECK)

# A citation: an id, or `repo:<id>` for a requirement in specs/repo.md.
CITATION_RE = re.compile(r"^(?:(%s):)?(\S+)$" % REPO)
# A step's citation, as it must be written: alone on its line.
STEP_MARKER_RE = re.compile(r"<!--\s*spec\b")
STEP_MARKER_LINE_RE = re.compile(r"^[ \t]*<!--[ \t]*spec:(.*?)-->[ \t]*$")
STEP_MARKER_FORM = "<!-- spec: <id>, <id> -->"
# A workflow step's citation, and the line it sits above.
CHECK_MARKER_RE = re.compile(r"^[ \t]*#[ \t]*spec:(.*)$")
COMMENT_RE = re.compile(r"^[ \t]*#")
WORKFLOW_STEP_RE = re.compile(r"^[ \t]*- name:[ \t]*(.*?)[ \t]*$")

# inventory: a backticked span in a skill's prose.
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
# The suffix pytest-cov adds to a test's context: |setup, |run or |teardown.
CONTEXT_PHASE_RE = re.compile(r"\|\w+$")
# A parametrized test's id, [param], which inventory folds into its test.
CONTEXT_PARAMS_RE = re.compile(r"\[.*\]$")
COLLECTION_CALLS = ("frozenset", "set", "tuple")

WHERE = 'SPEC-METHODOLOGY.md, under "Citing requirements", says how a test or a step cites one.'


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


def git(repo, *argv):
    cmd = ["git", *argv]
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    except OSError as exc:
        raise Fatal("cannot run git: %s" % exc) from exc
    if proc.returncode != 0:
        raise Fatal("`%s` failed: %s" % (" ".join(cmd), proc.stderr.strip()))
    return proc


def toplevel(repo):
    if not os.path.isdir(repo):
        raise Fatal("no such directory: %s" % repo)
    return git(repo, "rev-parse", "--show-toplevel").stdout.strip()


def repo_files(root):
    """Every file git would carry: tracked, plus untracked it is not ignoring."""
    out = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout
    return sorted(set(p for p in out.split("\0") if p))


def read(root, path):
    try:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError as exc:
        raise Fatal("cannot read %s: %s" % (path, exc)) from exc


def load_check_skills():
    """check-skills.py as a module. Its main() runs only from a shell."""
    spec = importlib.util.spec_from_file_location("check_specs_check_skills", CHECK_SKILLS)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError) as exc:
        raise Fatal("cannot load %s: %s" % (CHECK_SKILLS, exc)) from exc
    return module


def ranges(numbers):
    """[1, 2, 3, 5] as ["1-3", "5"]."""
    out = []
    for n in sorted(set(numbers)):
        if out and out[-1][1] == n - 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return ["%d" % a if a == b else "%d-%d" % (a, b) for a, b in out]


# --------------------------------------------------------------------------
# the specs
# --------------------------------------------------------------------------


def spec_path(component):
    return "%s/%s%s" % (SPECS, component, MARKDOWN)


def parse_spec(path, text, errors):
    """The requirements of one spec file, as {id: {"kind", "line", "under"}}."""
    requirements = {}
    under = None
    for number, line in enumerate(text.splitlines(), 1):
        where = "%s:%d" % (path, number)
        if SECTION_RE.match(line):
            heading = HEADING_RE.match(line)
            under = heading.group(2) if heading else None
            continue
        if under is None:
            if REQUIREMENT_START_RE.match(line):
                errors.append(
                    "%s: a requirement sits outside any need or constraint. Move it under "
                    "the `## need` or `## constraint` it serves." % where
                )
            continue
        if not BULLET_RE.match(line):
            continue
        m = REQUIREMENT_RE.match(line)
        if not m:
            errors.append(
                "%s: a bullet under need or constraint `%s` is not a requirement. Write it as "
                "- `<id>` (<kind>): <sentence>." % (where, under)
            )
            continue
        rid, kind = m.group(1), m.group(2)
        if not ID_RE.match(rid):
            errors.append(
                "%s: `%s` is not an id. An id is one to four lower-case words joined by "
                "hyphens." % (where, rid)
            )
            continue
        if rid in requirements:
            errors.append(
                "%s: `%s` is already the id of the requirement at line %d. Ids are unique "
                "within a file." % (where, rid, requirements[rid]["line"])
            )
            continue
        if kind == EVAL:
            errors.append(
                "%s: `%s` is verified by an eval, and nothing in this repo runs one yet. "
                "Make it a %s requirement." % (where, rid, " or ".join(KINDS))
            )
        elif kind not in KINDS:
            errors.append(
                "%s: `%s` names the kind `%s`. A requirement is verified by %s."
                % (where, rid, kind, ", ".join(KINDS))
            )
        requirements[rid] = {"kind": kind, "line": number, "under": under}
    return requirements


def load_specs(root, files, errors):
    """{component: {id: requirement}}, for each specs/<component>.md."""
    specs = {}
    for path in files:
        parts = path.split("/")
        if len(parts) == 2 and parts[0] == SPECS and parts[1].endswith(MARKDOWN):
            component = parts[1][: -len(MARKDOWN)]
            specs[component] = parse_spec(path, read(root, path), errors)
    return specs


def resolve(citation, component, specs, where, errors):
    """(component, id) a citation names, or None after an error saying why."""
    m = CITATION_RE.match(citation)
    if not m or not ID_RE.match(m.group(2)):
        errors.append(
            "%s: `%s` is not a requirement id. Cite `<id>`, or `%s:<id>` for one in %s."
            % (where, citation, REPO, spec_path(REPO))
        )
        return None
    target = REPO if m.group(1) else component
    rid = m.group(2)
    if target not in specs:
        errors.append(
            "%s: cites `%s`, and there is no %s to hold it. Add the spec file, with the "
            "need and the requirement." % (where, citation, spec_path(target))
        )
        return None
    if rid not in specs[target]:
        errors.append(
            "%s: cites `%s`, which %s does not hold. Cite an id it holds, or propose the "
            'requirement as CLAUDE.md, under "Specs", says.' % (where, citation, spec_path(target))
        )
        return None
    return (target, rid)


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------


def test_roots(root):
    """pytest.ini's testpaths."""
    parser = configparser.ConfigParser()
    try:
        parser.read_string(read(root, PYTEST_INI))
        return parser.get("pytest", "testpaths").split()
    except (configparser.Error, Fatal) as exc:
        raise Fatal("cannot read testpaths from %s: %s" % (PYTEST_INI, exc)) from exc


def test_component(path):
    """tests/<plugin>/... is that plugin's; every other suite is the repo's."""
    parts = path.split("/")
    if len(parts) > 2 and parts[0] == TESTS:
        return parts[1]
    return REPO


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        inner = dotted(node.value)
        return inner + "." + node.attr if inner else None
    return None


def citations_of(node, where, errors):
    """The ids a node's @pytest.mark.spec(...) decorators cite."""
    out = []
    for decorator in node.decorator_list:
        if not (isinstance(decorator, ast.Call) and dotted(decorator.func) == MARKER):
            continue
        for arg in decorator.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.append(arg.value)
            else:
                errors.append(
                    "%s:%d: @%s takes requirement ids as string literals, so the check can "
                    "read them without running the test." % (where, decorator.lineno, MARKER)
                )
        if decorator.keywords or not decorator.args:
            errors.append(
                '%s:%d: @%s names no id. Write @%s("<id>").'
                % (where, decorator.lineno, MARKER, MARKER)
            )
    return out


def find_tests(root, files, errors):
    """Every test pytest.ini collects, as [{"id", "path", "line", "component", "cites"}]."""
    roots = [r.rstrip("/") + "/" for r in test_roots(root)]
    tests = []
    for path in files:
        if not any(path.startswith(r) for r in roots):
            continue
        name = path.rsplit("/", 1)[-1]
        if not any(fnmatch.fnmatch(name, pattern) for pattern in TEST_FILES):
            continue
        try:
            tree = ast.parse(read(root, path), filename=path)
        except SyntaxError as exc:
            raise Fatal("cannot parse %s: %s" % (path, exc)) from exc
        component = test_component(path)
        functions = (ast.FunctionDef, ast.AsyncFunctionDef)
        found = []
        for node in tree.body:
            if isinstance(node, functions) and node.name.startswith(TEST_FUNCTION_PREFIX):
                found.append((node, [], []))
            elif isinstance(node, ast.ClassDef) and node.name.startswith(TEST_CLASS_PREFIX):
                inherited = citations_of(node, path, errors)
                for item in node.body:
                    if isinstance(item, functions) and item.name.startswith(TEST_FUNCTION_PREFIX):
                        found.append((item, [node.name], inherited))
        for node, prefix, inherited in found:
            tests.append(
                {
                    "id": NODE_SEPARATOR.join([path, *prefix, node.name]),
                    "path": path,
                    "line": node.lineno,
                    "component": component,
                    "cites": inherited + citations_of(node, path, errors),
                }
            )
    return tests


# --------------------------------------------------------------------------
# skill steps
# --------------------------------------------------------------------------


def find_steps(root, cs, files, errors):
    """Every `## Step` of a SKILL.md, as [{"id", "path", "line", "end", "heading",
    "number", "component", "cites"}]."""
    steps = []
    for component, paths in sorted(cs.skill_files(files).items()):
        for path in sorted(paths):
            text = read(root, path)
            sections, _ = cs.step_sections(text)
            mine = []
            for s in sections:
                entry = dict(s)
                entry.update(
                    {
                        "id": "%s%s%d" % (path, NODE_SEPARATOR, s["number"]),
                        "path": path,
                        "component": component,
                        "cites": [],
                    }
                )
                mine.append(entry)
            lines = text.splitlines()
            i = 0
            while i < len(lines):
                line = lines[i]
                fence = cs.FENCE_RE.match(line)
                if fence:
                    i = cs.fence_end(lines, i, fence.group("marker")) + 1
                    continue
                number = i + 1
                i += 1
                if not STEP_MARKER_RE.search(line):
                    continue
                where = "%s:%d" % (path, number)
                step = next((s for s in mine if s["line"] < number <= s["end"]), None)
                m = STEP_MARKER_LINE_RE.match(line)
                if step is None:
                    errors.append(
                        "%s: a spec marker sits outside any step. Put it under the heading "
                        "of the step it cites for." % where
                    )
                elif not m:
                    errors.append(
                        "%s: a spec marker must be a line of its own, as `%s`, or Cowork does "
                        "not strip it." % (where, STEP_MARKER_FORM)
                    )
                else:
                    ids = [c.strip() for c in m.group(1).split(",") if c.strip()]
                    if not ids:
                        errors.append("%s: a spec marker names no id." % where)
                    step["cites"].extend((c, number) for c in ids)
            steps.extend(mine)
    return steps


# --------------------------------------------------------------------------
# workflow steps
# --------------------------------------------------------------------------


def find_checks(root, files, errors):
    """Every `# spec:` above a workflow step, as [{"path", "line", "name", "cites"}]."""
    checks = []
    for path in files:
        if not (path.startswith(WORKFLOWS) and path.endswith(WORKFLOW_SUFFIXES)):
            continue
        lines = read(root, path).splitlines()
        for i, line in enumerate(lines):
            m = CHECK_MARKER_RE.match(line)
            if not m:
                continue
            j = i + 1
            while j < len(lines) and COMMENT_RE.match(lines[j]):
                j += 1
            step = WORKFLOW_STEP_RE.match(lines[j]) if j < len(lines) else None
            where = "%s:%d" % (path, i + 1)
            if not step:
                errors.append(
                    "%s: a spec comment must sit in the comment lines directly above a "
                    "step's `- name:`." % where
                )
                continue
            ids = [c.strip() for c in m.group(1).split(",") if c.strip()]
            if not ids:
                errors.append("%s: a spec comment names no id." % where)
            checks.append({"path": path, "line": i + 1, "name": step.group(1), "cites": ids})
    return checks


# --------------------------------------------------------------------------
# the untraced list
# --------------------------------------------------------------------------


def load_untraced(root):
    """{"tests": {id: issue}, "steps": {id: issue}}. No file is an empty list."""
    path = os.path.join(root, UNTRACED_FILE)
    if not os.path.isfile(path):
        return {"tests": {}, "steps": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Fatal("cannot read %s: %s" % (UNTRACED_FILE, exc)) from exc
    shape_ok = isinstance(data, dict) and set(data) <= {"tests", "steps"}
    if shape_ok:
        for entries in data.values():
            if not isinstance(entries, dict) or not all(
                isinstance(v, int) and not isinstance(v, bool) for v in entries.values()
            ):
                shape_ok = False
    if not shape_ok:
        raise Fatal(
            '%s must be {"tests": {id: issue}, "steps": {id: issue}}, each issue a number.'
            % UNTRACED_FILE
        )
    return {"tests": data.get("tests", {}), "steps": data.get("steps", {})}


# --------------------------------------------------------------------------
# trace
# --------------------------------------------------------------------------


def cmd_trace(args, root):
    files = repo_files(root)
    cs = load_check_skills()
    errors, warnings = [], []
    specs = load_specs(root, files, errors)
    tests = find_tests(root, files, errors)
    steps = find_steps(root, cs, files, errors)
    checks = find_checks(root, files, errors)
    untraced = load_untraced(root)

    for what, found in (("spec file under %s/" % SPECS, specs), ("test", tests), ("step", steps)):
        if not found:
            errors.append("found no %s; a check that scanned nothing has not passed" % what)

    verified = {TEST: set(), STEP: set(), CHECK: set()}
    waiting = {}

    def trace_items(items, kind, listed, remedy):
        for item in items:
            where = "%s:%d" % (item["path"], item["line"])
            cites = item["cites"]
            for cite in cites:
                citation, at = cite if isinstance(cite, tuple) else (cite, item["line"])
                target = resolve(
                    citation,
                    item["component"],
                    specs,
                    "%s:%d" % (item["path"], at),
                    errors,
                )
                if target:
                    verified[kind].add(target)
            issue = listed.get(item["id"])
            if cites and issue is not None:
                errors.append(
                    "%s: %s now cites a requirement. Remove its entry from %s, which "
                    "waited on #%d." % (where, item["id"], UNTRACED_FILE, issue)
                )
            elif not cites and issue is not None:
                waiting.setdefault(issue, {TEST: 0, STEP: 0})[kind] += 1
            elif not cites:
                label = (
                    '"%s"' % item["heading"]
                    if kind == STEP
                    else item["id"].split(NODE_SEPARATOR, 1)[1]
                )
                errors.append("%s: %s cites no requirement. %s" % (where, label, remedy))

    trace_items(
        tests,
        TEST,
        untraced["tests"],
        'Mark it @%s("<id>") with the requirement it verifies.' % MARKER,
    )
    trace_items(
        steps,
        STEP,
        untraced["steps"],
        "Put `%s` under its heading, naming the requirements it serves." % STEP_MARKER_FORM,
    )
    for c in checks:
        for citation in c["cites"]:
            target = resolve(citation, REPO, specs, "%s:%d" % (c["path"], c["line"]), errors)
            if target:
                verified[CHECK].add(target)

    for kind, items in ((TEST, tests), (STEP, steps)):
        present = set(i["id"] for i in items)
        listed = untraced["tests" if kind == TEST else "steps"]
        for item_id, issue in sorted(listed.items()):
            if item_id not in present:
                errors.append(
                    "%s lists %s for #%d, and there is no such %s. Remove its entry."
                    % (UNTRACED_FILE, item_id, issue, kind)
                )

    how = {
        TEST: 'Mark the test that verifies it @%s("%%s").' % MARKER,
        STEP: "Put `<!-- spec: %s -->` under the heading of the step that serves it.",
        CHECK: "Put `# spec: %s` directly above the `- name:` of the workflow step that "
        "runs the check.",
    }
    requirements = []
    for component in sorted(specs):
        for rid, req in sorted(specs[component].items(), key=lambda kv: kv[1]["line"]):
            kind = req["kind"]
            ok = (component, rid) in verified.get(kind, ())
            requirements.append({"component": component, "id": rid, "kind": kind, "verified": ok})
            if kind in KINDS and not ok:
                errors.append(
                    "%s:%d: `%s` (%s) is verified by nothing of its kind. %s"
                    % (spec_path(component), req["line"], rid, kind, how[kind] % rid)
                )

    for issue in sorted(waiting):
        counts = waiting[issue]
        what = " and ".join(
            "%d %s(s)" % (counts[kind], kind) for kind in (TEST, STEP) if counts[kind]
        )
        warnings.append("%s cite no requirement yet; #%d will trace them." % (what, issue))

    def human():
        if not errors:
            print(
                "%d requirement(s) verified; %d test(s) and %d step(s) cite one."
                % (
                    len(requirements),
                    sum(1 for t in tests if t["cites"]),
                    sum(1 for s in steps if s["cites"]),
                )
            )

    def brief(item):
        cites = [c[0] if isinstance(c, tuple) else c for c in item["cites"]]
        return {"id": item["id"], "component": item["component"], "cites": cites}

    data = {
        "requirements": requirements,
        "tests": [brief(t) for t in tests],
        "steps": [brief(s) for s in steps],
        "checks": checks,
    }
    return emit(args, "trace", data, errors, warnings, human)


# --------------------------------------------------------------------------
# inventory
# --------------------------------------------------------------------------


def parser_surface(build):
    """Every subcommand, option and choices value, as a flat list in parser order."""
    out = []
    seen = set()

    def walk(parser, path):
        if id(parser) in seen:
            return
        seen.add(id(parser))
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    out.append({"kind": "command", "command": " ".join([*path, name])})
                    walk(sub, [*path, name])
                continue
            if isinstance(action, argparse._HelpAction):
                continue
            command = " ".join(path)
            label = "/".join(action.option_strings) or action.dest
            if action.option_strings:
                out.append(
                    {
                        "kind": "option",
                        "command": command,
                        "option": label,
                        "strings": list(action.option_strings),
                    }
                )
            for value in action.choices or ():
                out.append(
                    {
                        "kind": "choice",
                        "command": command,
                        "option": label,
                        "strings": list(action.option_strings),
                        "value": str(value),
                    }
                )

    walk(build(), [])
    return out


def names(item, words):
    """Whether these words name the surface item: the command's words first,
    then the option, then the value."""
    command = item["command"].split()
    if item["kind"] == "command":
        return words[: len(command)] == command
    strings = item.get("strings") or []
    if strings:
        at = [
            i
            for i, w in enumerate(words)
            if w in strings or any(w.startswith(s + "=") for s in strings)
        ]
        if not at:
            return False
        if item["kind"] == "option":
            return True
        value = item["value"]
        for i in at:
            if words[i] in strings and i + 1 < len(words) and words[i + 1] == value:
                return True
            if words[i] != value and words[i].split("=", 1)[-1] == value:
                return True
        return False
    return words[: len(command)] == command and item["value"] in words[len(command) :]


def span_words(span):
    try:
        return shlex.split(span)
    except ValueError:
        return span.split()


def prose_spans(root, cs, paths):
    """Every backticked span outside a fence in these files, as [(path, line, text)]."""
    out = []
    for path in paths:
        lines = read(root, path).splitlines()
        i = 0
        while i < len(lines):
            fence = cs.FENCE_RE.match(lines[i])
            if fence:
                i = cs.fence_end(lines, i, fence.group("marker")) + 1
                continue
            for m in CODE_SPAN_RE.finditer(lines[i]):
                out.append((path, i + 1, m.group(1)))
            i += 1
    return out


def string_collections(path, text):
    """Module-level sets, frozensets, tuples and lists whose items are all strings."""
    tree = ast.parse(text, filename=path)
    constants = {}
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        name, value = targets[0].id, node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            constants[name] = value.value
            continue
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in COLLECTION_CALLS
            and len(value.args) == 1
        ):
            value = value.args[0]
        if not isinstance(value, (ast.Set, ast.Tuple, ast.List)) or not value.elts:
            continue
        items = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                items.append(elt.value)
            elif isinstance(elt, ast.Name) and elt.id in constants:
                items.append(constants[elt.id])
            else:
                items = None
                break
        if items is not None:
            out.append({"path": path, "line": node.lineno, "name": name, "items": items})
    return out


def load_report(root, path):
    """coverage.py's JSON report measured per test, keyed by path in the clone."""
    full = os.path.join(root, path)
    remedy = (
        "Run `pytest --cov --cov-context=test --cov-report=json:%s` from the clone first; "
        ".coveragerc has the report carry each line's tests." % DEFAULT_REPORT
    )
    if not os.path.isfile(full):
        raise Fatal("no coverage report at %s. %s" % (path, remedy))
    try:
        with open(full, encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Fatal("cannot read the coverage report %s: %s" % (path, exc)) from exc
    files = {}
    per_test = False
    for name, entry in report.get("files", {}).items():
        if os.path.isabs(name):
            name = os.path.relpath(name, root)
        files[name.replace(os.sep, "/")] = entry
        for tests in entry.get("contexts", {}).values():
            per_test = per_test or any(NODE_SEPARATOR in t for t in tests)
    if not per_test:
        raise Fatal("%s does not say which test ran each line. %s" % (path, remedy))
    return files


def test_of(context):
    """The test a pytest-cov context names, without its phase or parameters."""
    return CONTEXT_PARAMS_RE.sub("", CONTEXT_PHASE_RE.sub("", context))


def cmd_inventory(args, root):
    plugin = args.plugin
    files = repo_files(root)
    cs = load_check_skills()
    errors = []

    prefix = "%s/%s/%s/" % (PLUGINS, plugin, SCRIPTS)
    scripts = [p for p in files if p.startswith(prefix) and p.count("/") == 3 and p.endswith(".py")]
    if not scripts:
        raise Fatal(
            "no script under %s. Name a plugin that has one: %s."
            % (
                prefix,
                ", ".join(
                    sorted(set(p.split("/")[1] for p in files if p.startswith(PLUGINS + "/")))
                ),
            )
        )
    report = load_report(root, args.report)

    instructions = sorted(cs.instruction_files(files).get(plugin, []))
    _, invocations, _ = cs.find_invocations(root, {plugin: instructions})
    spans = prose_spans(root, cs, instructions)

    surface, collections = [], []
    cache = {}
    for script in scripts:
        build = cs.load_parser(root, script, cache)
        if isinstance(build, str):
            raise Fatal(build)
        for item in parser_surface(build):
            named = [
                {"path": inv["path"], "line": inv["line"], "text": " ".join(inv["argv"])}
                for inv in invocations
                if inv["script"] == script and names(item, inv["argv"])
            ]
            named += [
                {"path": path, "line": line, "text": text}
                for path, line, text in spans
                if names(item, span_words(text))
                or (
                    item["kind"] == "option"
                    and span_words(text)[:1] in [[s] for s in item["strings"]]
                )
            ]
            entry = {k: v for k, v in item.items() if k != "strings"}
            entry.update({"script": script, "named_by": named})
            surface.append(entry)
        collections.extend(string_collections(script, read(root, script)))

    runs = {}
    for script in scripts:
        for line, contexts in report.get(script, {}).get("contexts", {}).items():
            for context in contexts:
                if NODE_SEPARATOR in context:
                    runs.setdefault(test_of(context), {}).setdefault(script, set()).add(int(line))

    tests = []
    for t in find_tests(root, files, errors):
        if t["component"] != plugin:
            continue
        ran = runs.get(t["id"], {})
        tests.append(
            {
                "id": t["id"],
                "line": t["line"],
                "cites": t["cites"],
                "runs": {s: ranges(lines) for s, lines in sorted(ran.items())},
            }
        )

    steps = []
    for s in find_steps(root, cs, files, errors):
        if s["component"] != plugin:
            continue
        commands = [
            {"line": inv["line"], "script": inv["script"], "argv": inv["argv"]}
            for inv in invocations
            if inv["path"] == s["path"] and s["line"] < inv["line"] <= s["end"]
        ]
        steps.append(
            {
                "id": s["id"],
                "heading": s["heading"],
                "cites": [c for c, _ in s["cites"]],
                "commands": commands,
            }
        )

    unrun = {s: ranges(report.get(s, {}).get("missing_lines", [])) for s in scripts}

    def human():
        print("## Surface")
        for item in surface:
            label = item["command"]
            if item["kind"] != "command":
                label += " " + item["option"]
            if item["kind"] == "choice":
                label += " " + item["value"]
            where = ", ".join("%s:%d" % (n["path"], n["line"]) for n in item["named_by"])
            print("%s %s: %s" % (item["kind"], label, where or "named by no skill text"))
        print("\n## Collections")
        for c in collections:
            print("%s:%d %s: %s" % (c["path"], c["line"], c["name"], ", ".join(c["items"])))
        print("\n## Tests")
        for t in tests:
            lines = "; ".join("%s %s" % (s, ", ".join(r)) for s, r in t["runs"].items())
            print("%s: %s" % (t["id"], lines or "runs no script line"))
        print("\n## Steps")
        for s in steps:
            commands = "; ".join(" ".join(c["argv"]) for c in s["commands"])
            print("%s %s: %s" % (s["id"], s["heading"], commands or "runs no command"))
        print("\n## Lines no test runs")
        for script, r in unrun.items():
            print("%s: %s" % (script, ", ".join(r) or "none"))

    data = {
        "plugin": plugin,
        "scripts": scripts,
        "surface": surface,
        "collections": collections,
        "tests": tests,
        "steps": steps,
        "unrun": unrun,
    }
    return emit(args, "inventory", data, errors, None, human)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Tie each test and skill step to a requirement in specs/."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "trace", parents=[common], help="every test and step cites a requirement its spec holds"
    )
    p.set_defaults(func=cmd_trace)

    p = sub.add_parser("inventory", parents=[common], help="what needs tracing in one plugin")
    p.add_argument("plugin", help="the plugin's directory name under plugins/")
    p.add_argument(
        "--report",
        metavar="PATH",
        default=DEFAULT_REPORT,
        help="coverage.py's JSON report measured per test, relative to the clone "
        "(default: %(default)s)",
    )
    p.set_defaults(func=cmd_inventory)

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

#!/usr/bin/env python3
"""Fail a pull request whose description does not open with its scenario.

CLAUDE.md, under "Workflow", says what a pull request description covers, and
that it opens with `## Scenario`: who meets the change, what happened before
it and what happens after it. The owner reviews from that section. Agents
post under the owner's account, so a description in another shape reaches
the owner as though the owner had written it, unless CI fails it first.

`description` fails a pull request when either holds:

  - the description's first heading is not `## Scenario`, or it has no
    heading.
  - its Scenario section, up to the next heading of level 1 or 2, holds
    nothing but blank lines and HTML comments.

It reads the pull request from $GITHUB_EVENT_PATH, so it runs in CI on a
pull_request event. The validate workflow runs it on `edited` as well, so a
corrected description clears the failure.

    python3 .github/scripts/check-pr.py description

Commands:

  description  the description opens with a `## Scenario` section that says
               something

Every command takes --json.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Things that look like bugs and are not:

- It takes no -C/--repo, since it reads nothing from a clone.
- Only ATX headings, the ones that open with `#`, are read. A heading in a
  fenced code block or an HTML comment is not a heading, as GitHub does not
  render one, so a description that quotes CLAUDE.md's example passes or
  fails on its own headings.
- Text before the first heading is allowed. The check holds the description
  to its first heading, which is what CLAUDE.md names.
"""

import argparse
import json
import os
import re
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-pr.py"
EVENT_ENV = "GITHUB_EVENT_PATH"
SCENARIO = "Scenario"
SCENARIO_LEVEL = 2
SCENARIO_HEADING = "%s %s" % ("#" * SCENARIO_LEVEL, SCENARIO)
WHERE = 'CLAUDE.md, under "Workflow", says what a pull request description covers.'

# An ATX heading: up to three spaces, one to six #, then a space or the end.
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
# The closing run of # that an ATX heading may end with.
CLOSING_HASHES_RE = re.compile(r"(?:^|[ \t]+)#+$")
# A code fence's opening line: its character and its length.
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


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
# the description
# --------------------------------------------------------------------------


def load_event(environ):
    path = environ.get(EVENT_ENV)
    if not path:
        raise Fatal(
            "%s is not set. `description` reads the pull request from the event GitHub "
            "Actions writes, so it runs in CI on a pull_request event." % EVENT_ENV
        )
    try:
        with open(path, encoding="utf-8") as fh:
            event = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Fatal("cannot read the event at %s: %s" % (path, exc)) from exc
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        raise Fatal("the event at %s is not a pull request's." % path)
    return pr


def lines_outside_fences(text):
    """Each line of `text` that is not in a fenced code block, with its index.

    A fence's own opening and closing lines are left out too.
    """
    fence = None
    for i, line in enumerate(text.splitlines()):
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                continue
            yield i, line
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
            if not line.strip().strip(fence[0]):
                fence = None


def headings(text):
    """(index, level, title) for each heading in `text`, in order."""
    out = []
    for i, line in lines_outside_fences(text):
        m = HEADING_RE.match(line)
        if m:
            title = CLOSING_HASHES_RE.sub("", m.group(2) or "").strip()
            out.append((i, len(m.group(1)), title))
    return out


def scenario_problems(body):
    """The first heading, the Scenario section's text, and what is wrong."""
    text = COMMENT_RE.sub("", body)
    found = headings(text)
    if not found:
        return (
            None,
            None,
            ["the description has no heading. It opens with `%s`." % SCENARIO_HEADING],
        )
    start, level, title = found[0]
    first = "%s %s" % ("#" * level, title)
    if (level, title) != (SCENARIO_LEVEL, SCENARIO):
        return (
            first,
            None,
            [
                "the description's first heading is `%s`. It opens with `%s` instead."
                % (first, SCENARIO_HEADING)
            ],
        )
    end = next((i for i, lvl, _ in found[1:] if lvl <= SCENARIO_LEVEL), None)
    section = "\n".join(text.splitlines()[start + 1 : end]).strip()
    if not section:
        return (
            first,
            section,
            [
                "the description's `%s` section is empty. It says who meets the change, "
                "what happened before it and what happens after it." % SCENARIO_HEADING
            ],
        )
    return first, section, []


def cmd_description(args):
    pr = load_event(args.environ)
    first, section, errors = scenario_problems(pr.get("body") or "")

    def human():
        if not errors:
            print("The description opens with `%s`." % SCENARIO_HEADING)

    data = {"first_heading": first, "scenario": section}
    return emit(args, "description", data, errors, None, human)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")

    ap = argparse.ArgumentParser(prog=PROG, description="Check a pull request's description.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "description",
        parents=[common],
        help="the description opens with a Scenario section that says something",
    )
    p.set_defaults(func=cmd_description)

    return ap


def main(argv=None, environ=None):
    args = build_parser().parse_args(argv)
    args.environ = os.environ if environ is None else environ
    try:
        return args.func(args)
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN
    except BrokenPipeError:
        return OK


if __name__ == "__main__":
    sys.exit(main())

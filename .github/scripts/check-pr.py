#!/usr/bin/env python3
"""Check a pull request's description, and open one from a checked draft.

CLAUDE.md, under "Workflow", says what a pull request description covers, and
that it opens with `## Scenario`: who meets the change, what happened before
it and what happens after it. The owner reviews from that section. Agents
post under the owner's account, so a description in another shape reaches
the owner as though the owner had written it, unless CI fails it first.

`description` fails a description when any of these holds:

  - the description's first heading is not `## Scenario`, or it has no
    heading.
  - its Scenario section, up to the next heading of level 1 or 2, holds
    nothing but blank lines and HTML comments.
  - the Scenario section lacks a `### Before` or a `### After` subsection
    with text under it, or puts `### After` first.
  - outside a code fence or an HTML comment, a paragraph or a list item
    continues onto a second line. GitHub renders that newline in a pull
    request body as a line break, where a markdown file in the repository
    joins the lines, so the paragraph reads as a ragged column. Each such
    line is named by its number in the description.

It reads the pull request from $GITHUB_EVENT_PATH, so it runs in CI on a
pull_request event. The validate workflow runs it on `edited` as well, so a
corrected description clears the failure. Given --body-file, it reads a
drafted description from that file instead, so the open-pr skill can check a
draft before anyone reads it.

`draft` makes an empty file in the temporary directory for the open-pr skill
to write its draft to, and prints its path. Every Claude Code session on a
machine shares that directory, so a fixed name there lets one session's
draft replace another's, and the pull request would open with the other
session's description. The path it prints is literal, because a session that
Claude Code isolates in a worktree refuses a command that expands
${TMPDIR:-/tmp} as too complex to verify.

`open` makes the same check on a drafted description, and refuses it the same
way. When the draft passes, it pushes the current branch and opens a pull
request against main, with the file as its description. The open-pr skill, at
.claude/skills/open-pr/SKILL.md, opens every agent's pull request through it.

    python3 .github/scripts/check-pr.py draft
    python3 .github/scripts/check-pr.py description
    python3 .github/scripts/check-pr.py description --body-file pr.md
    python3 .github/scripts/check-pr.py open --title "fix(repo): ..." --body-file pr.md

Commands:

  draft        make an empty file for a drafted description, named so that
               no other run gets it, and print its path
  description  the description opens with a `## Scenario` section that gives
               its before and its after, and writes each paragraph and list
               item on one line
  open         open a pull request from a drafted description that passes
               `description`

Every command takes --json. `open` also takes -C/--repo, for the clone whose
branch it pushes.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Things that look like bugs and are not:

- `description` and `draft` take no -C/--repo, since they read nothing from
  a clone.
- Only ATX headings, the ones that open with `#`, are read. A heading in a
  fenced code block or an HTML comment is not a heading, as GitHub does not
  render one, so a description that quotes CLAUDE.md's example passes or
  fails on its own headings.
- A line that opens a list item, a table row, a blockquote line, an HTML
  block, a thematic break or an indented code block is not a continuation,
  even straight under a paragraph. A line with a trailing hard break (two
  spaces or a backslash) is still one: the description puts each paragraph
  on one line.
- Text before the first heading is allowed. The check holds the description
  to its first heading, which is what CLAUDE.md names.
- `open` pushes before it opens, because `gh pr create` run without a
  terminal stops on a branch the remote does not have yet.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import closed_pipe

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-pr.py"
EVENT_ENV = "GITHUB_EVENT_PATH"
BASE = "main"
REMOTE = "origin"
SCENARIO = "Scenario"
SCENARIO_LEVEL = 2
SCENARIO_HEADING = "%s %s" % ("#" * SCENARIO_LEVEL, SCENARIO)
# The Scenario section's subsections, in the order they come.
BEFORE, AFTER = "Before", "After"
SUBSECTION_LEVEL = 3
# `draft`: the name of the file a run of the open-pr skill writes its draft to.
DRAFT_PREFIX, DRAFT_SUFFIX = "pr-", ".md"
WHERE = 'CLAUDE.md, under "Workflow", says what a pull request description covers.'

# An ATX heading: up to three spaces, one to six #, then a space or the end.
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
# The closing run of # that an ATX heading may end with.
CLOSING_HASHES_RE = re.compile(r"(?:^|[ \t]+)#+$")
# A code fence's opening line: its character and its length.
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# A line that opens a list item: a bullet, or a number and its delimiter.
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
# A line indented far enough to be code, when it opens an indented block.
INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)")
# A line that is not paragraph text: a table row, a blockquote, an HTML
# block, or a thematic break or setext underline.
NOT_TEXT_RE = re.compile(r"^\s*(?:\||>|<|(?:[-*_=][ \t]*){3,}$|=+[ \t]*$)")


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


def blank_comments(body):
    """`body` with each HTML comment emptied, keeping its line breaks.

    Every line keeps its number, so a fault names the line the author wrote.
    """
    return COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), body)


def split_line_problems(body):
    """A fault for each line that continues a paragraph or a list item."""
    text = blank_comments(body)
    errors = []
    previous = None
    code = False
    for i, line in lines_outside_fences(text):
        # An indented code block opens after a line that is not text, and
        # runs while its lines stay indented or blank.
        indented = INDENTED_CODE_RE.match(line) is not None
        if code:
            code = indented or not line.strip()
        else:
            code = indented and previous != i - 1
        is_text = (
            bool(line.strip())
            and not code
            and not HEADING_RE.match(line)
            and not NOT_TEXT_RE.match(line)
        )
        if is_text and previous == i - 1 and not LIST_ITEM_RE.match(line):
            errors.append(
                "line %d continues the paragraph or list item above it. GitHub renders the "
                "newline as a line break, so join the line to the one above." % (i + 1)
            )
        previous = i if is_text else None
    return errors


def subsection_problems(text, found, start, end):
    """What is wrong with the Before and After subsections of the Scenario.

    `found` is every heading in `text`, and the section runs from line
    `start` up to line `end`.
    """
    lines = text.splitlines()
    inside = [h for h in found if h[0] > start and (end is None or h[0] < end)]
    at = {}
    for n, (i, level, title) in enumerate(inside):
        if level != SUBSECTION_LEVEL or title not in (BEFORE, AFTER):
            continue
        stop = next((j for j, lvl, _ in inside[n + 1 :] if lvl <= SUBSECTION_LEVEL), end)
        at[title] = (i, any(line.strip() for line in lines[i + 1 : stop]))
    errors = []
    before, after = ("%s %s" % ("#" * SUBSECTION_LEVEL, t) for t in (BEFORE, AFTER))
    for title, says in (
        (BEFORE, "what happened before the change"),
        (AFTER, "what happens after it"),
    ):
        heading = "%s %s" % ("#" * SUBSECTION_LEVEL, title)
        if title not in at:
            errors.append(
                "the `%s` section has no `%s` subsection. Give %s under `%s`."
                % (SCENARIO_HEADING, heading, says, heading)
            )
        elif not at[title][1]:
            errors.append("the `%s` subsection is empty. Give %s under it." % (heading, says))
    if BEFORE in at and AFTER in at and at[AFTER][0] < at[BEFORE][0]:
        errors.append(
            "the `%s` section puts `%s` before `%s`. Move `%s` and its text first."
            % (SCENARIO_HEADING, after, before, before)
        )
    return errors


def scenario_problems(body):
    """The first heading, the Scenario section's text, and what is wrong."""
    text = blank_comments(body)
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
    return first, section, subsection_problems(text, found, start, end)


def description_problems(body):
    """The first heading, the Scenario section's text, and every fault."""
    first, section, errors = scenario_problems(body)
    return first, section, errors + split_line_problems(body)


def cmd_draft(args):
    try:
        fd, path = tempfile.mkstemp(prefix=DRAFT_PREFIX, suffix=DRAFT_SUFFIX)
    except OSError as exc:
        raise Fatal(
            "cannot make a file for the draft in %s: %s. Set TMPDIR to a directory you can "
            "write and run this again." % (tempfile.gettempdir(), exc)
        ) from exc
    os.close(fd)

    def human():
        print(path)

    return emit(args, "draft", {"path": path}, None, None, human)


def read_body_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise Fatal(
            "cannot read the description at %s: %s. Write the draft there and run "
            "this again." % (path, exc)
        ) from exc


def cmd_description(args):
    if args.body_file:
        body = read_body_file(args.body_file)
    else:
        body = load_event(args.environ).get("body") or ""
    first, section, errors = description_problems(body)

    def human():
        if not errors:
            print("The description opens with `%s`." % SCENARIO_HEADING)

    data = {"first_heading": first, "scenario": section}
    return emit(args, "description", data, errors, None, human)


# --------------------------------------------------------------------------
# opening a pull request
# --------------------------------------------------------------------------


def run(repo, cmd):
    """Run git or gh in `repo` and return its stdout. Tests replace this."""
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    except OSError as exc:
        raise Fatal("cannot run %s in %s: %s" % (cmd[0], repo, exc)) from exc
    if proc.returncode != 0:
        raise Fatal(
            "`%s` failed: %s. Fix what it names and run `open` again."
            % (" ".join(cmd), proc.stderr.strip())
        )
    return proc.stdout


def cmd_open(args):
    body = read_body_file(args.body_file)
    first, section, errors = description_problems(body)
    data = {"first_heading": first, "scenario": section, "branch": None, "url": None}
    if not errors:
        repo = args.repo
        data["branch"] = run(repo, ["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
        run(repo, ["git", "push", "-u", REMOTE, "HEAD"])
        out = run(
            repo,
            [
                "gh",
                "pr",
                "create",
                "--base",
                BASE,
                "--title",
                args.title,
                "--body-file",
                os.path.abspath(args.body_file),
            ],
        )
        data["url"] = out.strip().splitlines()[-1] if out.strip() else None

    def human():
        if data["url"]:
            print(data["url"])

    return emit(args, "open", data, errors, None, human)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Check a pull request's description, and open one."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "draft",
        parents=[common],
        help="make an empty file for a draft that no other run is given, and print its path",
    )
    p.set_defaults(func=cmd_draft)

    p = sub.add_parser(
        "description",
        parents=[common],
        help="the Scenario has a Before and an After, and each paragraph is on one line",
    )
    p.add_argument(
        "--body-file",
        metavar="FILE",
        help="check a drafted description in FILE, in place of the pull request event",
    )
    p.set_defaults(func=cmd_description)

    p = sub.add_parser(
        "open",
        parents=[common],
        help="push the branch and open a pull request from a description that passes",
    )
    p.add_argument("--title", required=True, help="the pull request's title")
    p.add_argument("--body-file", metavar="FILE", required=True, help="the drafted description")
    p.add_argument(
        "-C", "--repo", metavar="DIR", default=".", help="a directory in the clone to push from"
    )
    p.set_defaults(func=cmd_open)

    return ap


@closed_pipe.exits_ok
def main(argv=None, environ=None):
    args = build_parser().parse_args(argv)
    args.environ = os.environ if environ is None else environ
    try:
        return args.func(args)
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN


if __name__ == "__main__":
    sys.exit(main())

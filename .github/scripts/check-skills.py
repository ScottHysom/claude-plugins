#!/usr/bin/env python3
"""Check skill front matter for what Cowork's plugin upload rejects.

Uploading a .plugin file to Cowork rejects a skill whose `description` holds
anything that looks like an XML tag ("SKILL.md description cannot contain XML
tags"). A marketplace install accepts the same skill, and so does
`claude plugin validate --strict`, so CI stayed green while the upload failed.
COWORK.md, under "How skills load", records the difference.

Run from anywhere in the clone:

    python3 .github/scripts/check-skills.py descriptions

Commands:

  descriptions  no description in the front matter of a markdown file under
                plugins/ holds a `<` followed by a tag-like name

Every command takes --json and -C/--repo.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Things that look like bugs and are not:

- It reads every markdown file under plugins/ whose front matter has a
  description, not only SKILL.md. The generated-skill templates in
  cowork-project-scaffold and gitify-cowork-project are skills too, once
  rendered. Their description is a placeholder the plugin script fills in and
  checks at runtime; this check keeps the template itself clean.
- A `<` on its own, as in `a < b` or `<3`, passes. Only `<` directly followed
  by a letter, or by `/` and a letter, reads as a tag.
- It fails when it finds no descriptions at all. A check that scanned nothing
  has not passed; the file selection has broken.
- It asks git for the file list rather than walking the tree, and includes
  untracked files git is not ignoring, as check-tests.py does.
- It only reads, and the only thing it asks git is the file list, so it is safe
  to run anywhere - including Cowork's device bridge, where a git write would
  strand a lock file.
"""

import argparse
import json
import os
import re
import subprocess
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-skills.py"
PLUGINS = "plugins"
MARKDOWN = ".md"
FENCE = "---"

DESCRIPTION_RE = re.compile(r"^description:(.*)$")
# A continuation line of a folded or multi-line YAML value is indented.
CONTINUATION_RE = re.compile(r"^[ \t]+\S")
# A `<` directly followed by a tag-like name: <ins>, </del>, <br/>. Not `a < b`.
TAG_RE = re.compile(r"</?[A-Za-z][\w:.-]*")

WHERE = 'COWORK.md, under "How skills load", says why an upload rejects this.'


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


def plugin_markdown(root):
    """Markdown under plugins/ that git would carry: tracked, plus untracked not ignored."""
    cmd = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", PLUGINS]
    out = run(root, cmd).stdout
    return sorted(set(p for p in out.split("\0") if p.endswith(MARKDOWN)))


def read_lines(root, path):
    try:
        with open(os.path.join(root, path), encoding="utf-8") as fh:
            return fh.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise Fatal("cannot read %s: %s" % (path, exc)) from exc


# --------------------------------------------------------------------------
# front matter
# --------------------------------------------------------------------------


def description_lines(lines):
    """The description's lines as (line number, text), or None if there is none.

    Only the front matter is read: the lines between a first line of `---` and
    the next `---`. The value is the rest of the `description:` line plus the
    indented lines after it.
    """
    if not lines or lines[0] != FENCE:
        return None
    found = None
    for i, line in enumerate(lines[1:], start=2):
        if line == FENCE:
            break
        if found is None:
            m = DESCRIPTION_RE.match(line)
            if m:
                found = [(i, m.group(1))]
        elif CONTINUATION_RE.match(line):
            found.append((i, line))
        else:
            break
    return found


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_descriptions(args, root):
    """No skill description holds something Cowork's upload reads as a tag."""
    errors, checked = [], []

    def human():
        if not errors:
            print("%d skill description(s) clear of XML-like tags." % len(checked))

    for path in plugin_markdown(root):
        found = description_lines(read_lines(root, path))
        if found is None:
            continue
        checked.append(path)
        for number, text in found:
            for tag in TAG_RE.findall(text):
                errors.append(
                    "%s:%d: description contains an XML-like tag `%s`; "
                    "Cowork's .plugin upload rejects it" % (path, number, tag)
                )

    if not checked:
        errors.append(
            "found no markdown under %s/ with a description in its front matter; "
            "a check that scanned nothing has not passed" % PLUGINS
        )

    return emit(args, "descriptions", {"checked": checked}, errors, human=human)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Check skill front matter for what Cowork's upload rejects."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "descriptions", parents=[common], help="no skill description holds an XML-like tag"
    )
    p.set_defaults(func=cmd_descriptions)

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

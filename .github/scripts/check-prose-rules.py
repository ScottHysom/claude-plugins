#!/usr/bin/env python3
"""Keep the prose rules prose-tuning ships in step with this repo's own.

prose-tuning ships a starting set of prose rules (the shipped rules) in
plugins/prose-tuning/templates/prose-style.md, and `prose.py config init`
copies them into a new project. The owner forms those rules in this repo's
.claude/rules/prose-style.md first. A pull request can change a rule here and
leave the shipped copy as it was, and every other check passes. This one
fails it.

Run from anywhere in the clone:

    python3 .github/scripts/check-prose-rules.py drift

Commands:

  drift  every rule (a `### <id>: <title>` heading and the text under it) is
         in both files, and its text is the same in both

The comparison sets aside:

  - the worked examples, the `> **Before.**` and `> **After.**` lines, which
    each project writes from its own documents.
  - each `FILL` marker in the shipped rules (an HTML comment telling a
    project's author what to write there). The marker matches whatever this
    repo's copy has in its place, including nothing.
  - line breaks and runs of spaces, so rewrapping a paragraph is not drift.
  - everything outside a rule: front matter, the title and the text a section
    opens with, which name the project.

Every command takes --json and -C/--repo.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Things that look like bugs and are not:

- The order of the rules is not compared. The two files already list some of
  a section's rules in different orders, and still say the same thing.
- Text this repo's copy has where the shipped rules have a `FILL` marker is
  never drift, however long it is. That is where the repo's own terms, roles
  and examples go.
- It only reads, and the only thing it asks git is where the clone's root is.
"""

import argparse
import json
import os
import re
import subprocess
import sys

import closed_pipe

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-prose-rules.py"
REPO_RULES = os.path.join(".claude", "rules", "prose-style.md")
SHIPPED_RULES = os.path.join("plugins", "prose-tuning", "templates", "prose-style.md")
RULE_RE = re.compile(r"^###\s+([A-Za-z0-9-]+):")
HEADING_RE = re.compile(r"^#{1,6}\s")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
EXAMPLE_RE = re.compile(r"^>\s*\*\*(?:Before|After)\.\*\*")
FILL_RE = re.compile(r"<!--\s*FILL:.*?-->", re.S)
# How many words of each side a difference quotes.
EXCERPT_WORDS = 8
REMEDY = (
    "Carry the change across with copy-prose (prose-tuning's skill that copies "
    "rules from one rules file into another), with %s as the source" % REPO_RULES
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
            sys.stderr.write("  - %s\n" % e)
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------


def run(repo, cmd):
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    except OSError as exc:
        raise Fatal("cannot run %s: %s" % (cmd[0], exc)) from exc
    if proc.returncode != 0:
        raise Fatal(
            "`%s` failed: %s. Run it from a clone of this repo, or name one with -C."
            % (" ".join(cmd), proc.stderr.strip())
        )
    return proc


def toplevel(repo):
    if not os.path.isdir(repo):
        raise Fatal("no such directory: %s. Name a directory in the clone with -C." % repo)
    return run(repo, ["git", "rev-parse", "--show-toplevel"]).stdout.strip()


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise Fatal(
            "cannot read %s: %s. Restore it from main, or name another clone with -C." % (rel, exc)
        ) from exc


def rules(text):
    """{rule id: its heading and text, with the worked examples left out}."""
    out, current, fenced = {}, None, False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
        elif not fenced and HEADING_RE.match(line):
            m = RULE_RE.match(line)
            current = m.group(1) if m else None
            if current:
                out[current] = []
        if current and not EXAMPLE_RE.match(line):
            out[current].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


# --------------------------------------------------------------------------
# comparing
# --------------------------------------------------------------------------


def excerpt(words):
    shown = " ".join(words[:EXCERPT_WORDS])
    return shown + (" ..." if len(words) > EXCERPT_WORDS else "")


def find(words, chunk, start):
    """The first index at or after start where chunk occurs in words, or -1."""
    for i in range(start, len(words) - len(chunk) + 1):
        if words[i : i + len(chunk)] == chunk:
            return i
    return -1


def anchored(chunk, words):
    """How chunk and the start of words differ, or None when words opens with it."""
    for k, word in enumerate(chunk):
        if k >= len(words) or words[k] != word:
            return "the shipped rules have %r where %s has %r" % (
                excerpt(chunk[k:]),
                REPO_RULES,
                excerpt(words[k:]),
            )
    return None


def difference(shipped, repo):
    """How the repo's copy of a rule differs from the shipped one, or None.

    The shipped text splits at its FILL markers into chunks of words. The
    first chunk opens the repo's copy, the last closes it, and the rest occur
    in order between them. A marker matches any words in between, including
    none.
    """
    chunks = [c.split() for c in FILL_RE.split(shipped)]
    words = repo.split()
    if len(chunks) == 1:
        found = anchored(chunks[0], words)
        if found is None and len(words) > len(chunks[0]):
            found = "%s adds %r" % (REPO_RULES, excerpt(words[len(chunks[0]) :]))
        return found
    found = anchored(chunks[0], words)
    if found is not None:
        return found
    pos = len(chunks[0])
    for chunk in chunks[1:-1]:
        at = find(words, chunk, pos)
        if at < 0:
            return "%s lacks %r" % (REPO_RULES, excerpt(chunk))
        pos = at + len(chunk)
    last = chunks[-1]
    if not last:
        return None
    at = find(words, last, pos)
    if at < 0:
        return "%s lacks %r" % (REPO_RULES, excerpt(last))
    while find(words, last, at + 1) >= 0:
        at = find(words, last, at + 1)
    if at + len(last) < len(words):
        return "%s adds %r" % (REPO_RULES, excerpt(words[at + len(last) :]))
    return None


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_drift(args, root):
    """Every rule is in both files, with the same text."""
    here = rules(read(root, REPO_RULES))
    shipped = rules(read(root, SHIPPED_RULES))
    errors, matching = [], []

    for rel, found in ((REPO_RULES, here), (SHIPPED_RULES, shipped)):
        if not found:
            errors.append(
                "%s does not hold any rule. A rule opens with a `### <id>: <title>` "
                "heading; restore the file from main." % rel
            )
    if errors:
        return emit(args, "drift", {"matching": matching}, errors)

    for rule in sorted(set(here) | set(shipped)):
        if rule not in shipped:
            errors.append(
                "%s: in %s and not in %s. %s." % (rule, REPO_RULES, SHIPPED_RULES, REMEDY)
            )
        elif rule not in here:
            errors.append(
                "%s: in %s and not in %s. Remove it from the shipped rules too, or "
                "copy it here with copy-prose." % (rule, SHIPPED_RULES, REPO_RULES)
            )
        else:
            found = difference(shipped[rule], here[rule])
            if found is None:
                matching.append(rule)
            else:
                errors.append("%s: %s. %s." % (rule, found, REMEDY))

    def human():
        if not errors:
            print("All %d rule(s) match the shipped rules." % len(matching))

    return emit(args, "drift", {"matching": matching}, errors, human=human)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Check the shipped prose rules match this repo's."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("drift", parents=[common], help="the two rules files hold the same rules")
    p.set_defaults(func=cmd_drift)

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

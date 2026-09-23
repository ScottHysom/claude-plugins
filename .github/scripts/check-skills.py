#!/usr/bin/env python3
"""Keep a plugin's skills sharing a step rather than each carrying a copy.

When two skills in one plugin need the same instructions, CLAUDE.md puts them
once in the plugin's reference/ and has each SKILL.md point there. A copy
pasted into a second SKILL.md reads fine in either file, and the two drift
apart the first time someone edits one of them. No diff shows the copy unless
the reviewer happens to have both files open. `repeats` is what notices.

Run from anywhere in the clone:

    python3 .github/scripts/check-skills.py repeats

Commands:

  repeats  no block of text appears in two SKILL.md files of the same plugin

Every command takes --json and -C/--repo.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

What counts as a block: a paragraph, a table, a fenced code block (blank lines
and all), or a single list item without its bullet or number. Whitespace is
collapsed before comparing, so rewrapping a copied paragraph does not hide it.

Things that look like bugs and are not:

- The "Locate the script" section is skipped entirely. Every SKILL.md must carry
  it, because Cowork fills in ${CLAUDE_SKILL_DIR} only in SKILL.md itself, and
  reference/setup.md names that step as the one every skill starts from - so
  the pointer to setup.md at the end of it repeats by design, not only the
  fence that sets ROOT. The section's heading is the named exception,
  LOCATE_SECTION below.
- Headings are skipped. "## Step 1: refuse early" in two skills is two skills
  with the same shape, not a copied instruction.
- Each list item is its own block. Comparing whole lists would miss one bullet
  copied into a list that otherwise differs.
- Skills are compared only within a plugin. Each plugin installs on its own and
  cannot point at another's reference/, so text shared across plugins has
  nowhere to go.
- A paragraph repeated inside one SKILL.md is not reported. That is a matter of
  editing the one file, and has no reference/ to move to.
- It fails when it has scanned nothing: no SKILL.md at all, or one that yields
  no blocks. A check whose file pattern or parser has gone blind passes every
  pull request, so scanning nothing is an error rather than a clean run.
- It only reads, and the only thing it reads through is git, so it is safe to
  run anywhere - including Cowork's device bridge, where a git write would
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
SKILLS = "skills"
SKILL_FILE = "SKILL.md"
REFERENCE = "reference"
LOCATE_SECTION = "Locate the script"

FRONT_MATTER = "---"
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.*?)[ \t#]*$")
LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
# How much of a repeated block an error quotes.
QUOTE_CHARS = 72

WHERE = (
    'CLAUDE.md, under "Skills and scripts", says why a step shared by two skills '
    "lives once in the plugin's %s/." % REFERENCE
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


def skill_files(files):
    """plugins/<plugin>/skills/<skill>/SKILL.md, as {plugin: [path, ...]}."""
    found = {}
    for path in files:
        parts = path.split("/")
        if len(parts) == 5 and parts[0] == PLUGINS and parts[2] == SKILLS:
            if parts[4] == SKILL_FILE:
                found.setdefault(parts[1], []).append(path)
    return found


# --------------------------------------------------------------------------
# splitting a SKILL.md into blocks
# --------------------------------------------------------------------------


def normalise(text):
    return " ".join(text.split())


def blocks(text):
    """The comparable blocks of a SKILL.md, as [(line, normalised text)].

    Front matter, headings and the LOCATE_SECTION section are left out.
    """
    lines = text.splitlines()
    out = []
    current, start = [], 0
    exempt = False

    def flush():
        if current and not exempt:
            out.append((start, normalise("\n".join(current))))
        del current[:]

    i = 0
    if lines and lines[0].strip() == FRONT_MATTER:
        for j in range(1, len(lines)):
            if lines[j].strip() == FRONT_MATTER:
                i = j + 1
                break

    while i < len(lines):
        line = lines[i]
        number = i + 1
        fence = FENCE_RE.match(line)
        heading = HEADING_RE.match(line)
        if fence:
            flush()
            marker = fence.group(1)
            current.append(line)
            start = number
            i += 1
            while i < len(lines):
                current.append(lines[i])
                if lines[i].strip().startswith(marker):
                    break
                i += 1
            flush()
        elif heading:
            flush()
            exempt = heading.group(1).strip() == LOCATE_SECTION
        elif not line.strip():
            flush()
        elif LIST_ITEM_RE.match(line):
            flush()
            # Without its marker, so a bullet copied into a numbered list matches.
            current.append(LIST_ITEM_RE.sub("", line, count=1))
            start = number
        else:
            if not current:
                start = number
            current.append(line)
        i += 1
    flush()
    return out


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def skill_name(path):
    return path.split("/")[3]


def cmd_repeats(args, root):
    found = skill_files(repo_files(root))
    scanned, repeats, errors = [], [], []

    if not found:
        errors.append(
            "no file matched %s/*/%s/*/%s anywhere in the clone. This check is scanning "
            "nothing, which is exactly how a copied step gets through."
            % (PLUGINS, SKILLS, SKILL_FILE)
        )

    for plugin in sorted(found):
        places = {}
        for path in sorted(found[plugin]):
            try:
                with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
                    parsed = blocks(fh.read())
            except OSError as exc:
                raise Fatal("cannot read %s: %s" % (path, exc)) from exc
            scanned.append(path)
            if not parsed:
                errors.append(
                    "%s yielded no blocks to compare; the check has gone blind there." % path
                )
            for line, text in parsed:
                places.setdefault(text, []).append({"path": path, "line": line})
        for text, where in places.items():
            if len(set(skill_name(w["path"]) for w in where)) > 1:
                repeats.append({"plugin": plugin, "text": text, "places": where})

    for r in repeats:
        quote = r["text"]
        if len(quote) > QUOTE_CHARS:
            quote = quote[:QUOTE_CHARS] + "..."
        errors.append(
            "%s share a block: %r. Move it to %s/%s/%s/ and point to it from each skill."
            % (
                " and ".join("%s:%d" % (w["path"], w["line"]) for w in r["places"]),
                quote,
                PLUGINS,
                r["plugin"],
                REFERENCE,
            )
        )

    def human():
        if not errors:
            print(
                "%d %s files in %d plugins, no block repeated within a plugin."
                % (len(scanned), SKILL_FILE, len(found))
            )

    data = {"scanned": scanned, "repeats": repeats}
    return emit(args, "repeats", data, errors, None, human)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Keep a plugin's skills sharing steps rather than copying them."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "repeats", parents=[common], help="no block in two SKILL.md files of one plugin"
    )
    p.set_defaults(func=cmd_repeats)

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

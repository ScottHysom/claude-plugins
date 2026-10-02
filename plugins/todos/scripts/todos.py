#!/usr/bin/env python3
"""Deterministic half of the do-todos skill.

A TODO is a note the user leaves in a file while reviewing it, for the skill
to file as an issue. This script finds them. The model does what needs
judgment: drafting each issue, and asking the user when a TODO says too
little.

Usage:
    python3 todos.py <command> [options]
    python3 todos.py --help

Commands:
    scan    list the TODOs in the working tree's changes since the last commit

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

What a TODO is. A line of a text file that opens, after its indent and an
optional comment marker, with `TODO:` or `TODO(<kind>):`. The rest of the line
is the title. The comment marker is the run of characters before `TODO` that
are not letters, digits or spaces, such as `#`, `//`, `<!--`, or nothing. It
is read off the TODO's own line, so there is no table of comment syntax by
file type, and nothing checks that a marker suits its file. specs/todos.md, in
the claude-plugins repo, has the full rules. Two forms:

- Line form. A marker that is not empty and not a list or quote mark
  (TITLE_ONLY_MARKERS) carries detail: the added lines directly below that
  open with the same marker at the same indent, up to a blank line or the
  next TODO.
- Block form. A marker holding an opener in BLOCK_COMMENTS runs to its closer,
  and the rest of the comment is the detail. Every line up to the closer has
  to be new since the last commit, so filing the TODO never removes a
  committed line.

Only lines added since the last commit count. git decides what changed, what
is binary and what is ignored. The last commit's side of a file is read with
`git cat-file --filters`, so autocrlf and eol attributes do not make every
line look changed. Lines are compared without their line endings.

Things that look like bugs and are not:

1. A `TODO:` part way along a line draws a warning and is not read. A TODO
   at the end of a line of code is a later addition (issue #314), and until
   then the warning is what keeps it from going unnoticed.

2. In a markdown file (MARKDOWN_SUFFIXES), a TODO in a code fence or a code
   span is ignored without a warning, so a document can show the syntax. As a
   simplification, a fence is found only at the left margin (not inside a
   list or a quote), and a code span only within one line.

3. Text is read as bytes and decoded only for output, with undecodable bytes
   replaced. Any encoding that spells `TODO` in ASCII is read.

4. The line a TODO sits above is the next line that is neither blank nor part
   of a TODO, so a run of TODOs all point at the code below them.

Nothing here writes to the working tree or to git, and every git call passes
--no-optional-locks so that even git's own index refresh is skipped.

Python 3.9 is the floor. No match statements, no X | Y unions.
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "todos.py"

# The kinds a TODO can name in `TODO(<kind>):`.
KINDS = ("bug", "fix", "change", "design", "docs", "prose")

MARKDOWN_SUFFIXES = (".md", ".markdown")

# Markers that open a list item, a quote or a table row rather than a comment.
# A TODO behind one has a title only, so it cannot swallow the author's lines.
TITLE_ONLY_MARKERS = (b"-", b"*", b"+", b">", b"|")

# (opener, closer). The only comment syntax the script knows.
BLOCK_COMMENTS = ((b"<!--", b"-->"), (b"/*", b"*/"))

# What git prints in place of line counts for a binary file.
BINARY_NUMSTAT = b"-\t-\t"

NULL_PATH = "/dev/null"

# A TODO: indent, marker, then `TODO:` or `TODO(<kind>):`.
TODO_RE = re.compile(rb"^([ \t]*)([^A-Za-z0-9\s]*)[ \t]*TODO(?:\(([^()]*)\))?:")
# A line that opens with TODO, after its indent and marker, read or not.
OPENS_RE = re.compile(rb"^[ \t]*[^A-Za-z0-9\s]*[ \t]*TODO")
# A line that holds the start of a TODO anywhere along it.
HOLDS_RE = re.compile(rb"TODO[:(]")
# The indent and marker of any line.
MARKER_RE = re.compile(rb"^([ \t]*)([^A-Za-z0-9\s]*)")

FENCE_RE = re.compile(rb"^ {0,3}(`{3,}|~{3,})(.*)$")
BACKTICKS_RE = re.compile(rb"`+")
# What a code span's bytes are masked with: a letter, so it never reads as a
# marker or as `TODO`.
MASK = b"x"

ABBREV = 7


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def envelope(command, data, errors, warnings):
    return {
        "version": ENVELOPE_VERSION,
        "command": command,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "data": data,
    }


def emit(args, command, data, errors=None, warnings=None, human=None):
    """Print JSON or human output, and return the exit code."""
    errors = errors or []
    warnings = warnings or []
    if args.json:
        print(json.dumps(envelope(command, data, errors, warnings), indent=2, sort_keys=True))
    else:
        human()
        sys.stderr.write("".join("warning: %s\n" % w for w in warnings))
        sys.stderr.write("".join("%s\n" % e for e in errors))
    return PROBLEMS if errors else OK


def decode(raw):
    return raw.decode("utf-8", "replace")


# --------------------------------------------------------------------------
# git, read-only
# --------------------------------------------------------------------------


class Repo:
    """A git working tree with at least one commit."""

    def __init__(self, start):
        start = os.path.abspath(start)
        if not os.path.isdir(start):
            raise Fatal("%s is not a directory. Name a clone with -C." % start)
        try:
            out = subprocess.run(
                ["git", "-C", start, "rev-parse", "--show-toplevel"],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise Fatal(
                "git is not installed, or not on PATH. Install git, then run again."
            ) from exc
        if out.returncode != 0:
            raise Fatal(
                "%s is not inside a git working tree. Run from inside a clone, or name one"
                " with -C." % start
            )
        self.root = os.fsdecode(out.stdout.rstrip(b"\n"))
        code, head, _ = self.run("rev-parse", "--verify", "--quiet", "HEAD^{commit}")
        if code != 0:
            raise Fatal(
                "%s has no commit yet. TODOs are read from the changes since the last commit,"
                " so commit the project first." % self.root
            )
        self.head = decode(head.strip())

    def run(self, *args):
        """(exit code, stdout as bytes, stderr as bytes)."""
        out = subprocess.run(
            ["git", "--no-optional-locks", "-C", self.root, *args],
            capture_output=True,
            check=False,
        )
        return out.returncode, out.stdout, out.stderr

    def git(self, *args, codes=(0,)):
        """stdout as bytes, or Fatal when git exits with a code not in codes."""
        code, stdout, stderr = self.run(*args)
        if code not in codes:
            raise Fatal(
                "git %s failed: %s. Run `git status` in %s to see what git reports."
                % (" ".join(args), decode(stderr).strip(), self.root)
            )
        return stdout

    def on_remote(self):
        """Whether a remote-tracking branch holds the last commit."""
        out = self.git("for-each-ref", "--contains", "HEAD", "--format=%(refname)", "refs/remotes")
        return bool(out.strip())

    def base(self, path):
        """The file at the last commit, as checkout would write it, or None."""
        code, out, _ = self.run("cat-file", "--filters", "HEAD:%s" % path)
        return out if code == 0 else None

    def changed(self):
        """[(path, path at the last commit, binary)] for each tracked change.

        numstat names a rename's old and new paths, and prints `-` for the
        counts of a binary file. A deleted file is listed too; the caller
        skips anything that is not a regular file now.
        """
        tokens = self.git("diff", "-z", "--numstat", "-M", "HEAD").split(b"\0")
        out = []
        i = 0
        while i < len(tokens) - 1:
            entry = tokens[i]
            binary = entry.startswith(BINARY_NUMSTAT)
            path = entry.split(b"\t", 2)[2]
            if path:
                out.append((os.fsdecode(path), os.fsdecode(path), binary))
                i += 1
            else:
                # A rename: the old and new paths follow as tokens of their own.
                out.append((os.fsdecode(tokens[i + 2]), os.fsdecode(tokens[i + 1]), binary))
                i += 3
        return out

    def untracked(self):
        """Every file git neither tracks nor ignores."""
        out = self.git("ls-files", "-z", "--others", "--exclude-standard")
        return [os.fsdecode(p) for p in out.split(b"\0") if p]

    def binary(self, path):
        """Whether git reads an untracked file as binary."""
        out = self.git("diff", "--no-index", "-z", "--numstat", "--", NULL_PATH, path, codes=(0, 1))
        return out.startswith(BINARY_NUMSTAT)


# --------------------------------------------------------------------------
# lines
# --------------------------------------------------------------------------


def split_lines(raw):
    """A file's lines, without their endings."""
    lines = raw.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    return [ln[:-1] if ln.endswith(b"\r") else ln for ln in lines]


def compare(base_lines, lines):
    """(added, base_of): the indexes of lines new since the base, and a map
    from the index of each line kept from the base to its 1-based number
    there."""
    added, base_of = set(), {}
    sm = difflib.SequenceMatcher(None, base_lines, lines, autojunk=False)
    for tag, i1, _i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                base_of[j1 + k] = i1 + k + 1
        elif tag != "delete":
            added.update(range(j1, j2))
    return added, base_of


def fenced(lines):
    """The indexes of the lines in a markdown code fence, delimiters included."""
    out, fence = set(), None
    for i, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if fence is None:
            if m and not (m.group(1)[:1] == b"`" and b"`" in m.group(2)):
                fence = m.group(1)
                out.add(i)
        else:
            out.add(i)
            run = m.group(1) if m else b""
            if run[:1] == fence[:1] and len(run) >= len(fence) and not m.group(2).strip():
                fence = None
    return out


def mask_code_spans(line):
    """The line with each markdown code span's bytes masked, length kept."""
    out = bytearray(line)
    pos = 0
    while True:
        m = BACKTICKS_RE.search(line, pos)
        if not m:
            return bytes(out)
        run = m.group(0)
        close = re.compile(rb"(?<!`)" + run + rb"(?!`)").search(line, m.end())
        if not close:
            pos = m.end()
            continue
        out[m.start() : close.end()] = MASK * (close.end() - m.start())
        pos = close.end()


# --------------------------------------------------------------------------
# scan
# --------------------------------------------------------------------------


class FileScan:
    """The TODOs and warnings in one file's added lines."""

    def __init__(self, path, lines, added, base_of):
        self.path = path
        self.lines = lines
        self.added = added
        self.base_of = base_of
        markdown = path.lower().endswith(MARKDOWN_SUFFIXES)
        self.skip = fenced(lines) if markdown else set()
        self.masked = [mask_code_spans(ln) for ln in lines] if markdown else lines
        self.todos = []
        self.warnings = []
        self.spans = set()
        self._scan()
        for todo in self.todos:
            todo["above"] = self._above(todo["last"])

    def warn(self, i, reason):
        self.warnings.append("%s:%d: %s" % (self.path, i + 1, reason))

    def _scan(self):
        i = 0
        while i < len(self.lines):
            if i not in self.added or i in self.skip:
                i += 1
                continue
            line = self.masked[i]
            m = TODO_RE.match(line)
            if m:
                last = self._read(i, m)
                if last is not None:
                    self.spans.update(range(i, last + 1))
                    i = last + 1
                    continue
            elif OPENS_RE.match(line):
                self.warn(i, "the line opens with TODO but not with `TODO:` or `TODO(<kind>):`")
            elif HOLDS_RE.search(line):
                self.warn(
                    i,
                    "a TODO is read only at the start of its line, after its indent and"
                    " comment marker",
                )
            i += 1

    def _read(self, i, m):
        """Read the TODO opening line i. Its last line's index, or None when
        it cannot be read, with a warning saying why."""
        indent, marker, word = m.group(1), m.group(2), m.group(3)
        rest = self.lines[i][m.end() :]
        closer = next((c for o, c in BLOCK_COMMENTS if o in marker), None)
        if closer is not None:
            got = self._block(i, rest, closer)
            if got is None:
                return None
            title, detail, last = got
            if marker.endswith(b"/*"):
                detail = [d.strip().lstrip(b"*") for d in detail]
        elif marker and marker not in TITLE_ONLY_MARKERS:
            title, detail, last = rest, [], i
            j = i + 1
            while j in self.added and self.lines[j].strip():
                if TODO_RE.match(self.masked[j]):
                    break
                lm = MARKER_RE.match(self.lines[j])
                if lm.group(1) != indent or lm.group(2) != marker:
                    break
                detail.append(self.lines[j][lm.end() :])
                last = j
                j += 1
        else:
            title, detail, last = rest, [], i
        kind = None
        if word is not None:
            if decode(word) in KINDS:
                kind = decode(word)
            else:
                self.warn(
                    i,
                    "`%s` is not a kind, so the TODO is read without one. The kinds are %s"
                    % (decode(word), ", ".join(KINDS)),
                )
        self.todos.append(
            {
                "file": self.path,
                "first": i + 1,
                "last": last + 1,
                "kind": kind,
                "marker": decode(marker),
                "title": decode(title.strip()),
                "detail": decode(b"\n".join(d.strip() for d in detail).strip()),
            }
        )
        return last

    def _block(self, i, rest, closer):
        """(title, detail lines, last index) for a block comment, or None."""
        at = rest.find(closer)
        if at >= 0:
            title, detail, last, tail = rest[:at], [], i, rest[at + len(closer) :]
        else:
            title, detail = rest, []
            j = i + 1
            while True:
                if j >= len(self.lines):
                    self.warn(i, "the comment does not close with `%s`" % decode(closer))
                    return None
                if j not in self.added:
                    self.warn(
                        i,
                        "the comment runs on to line %d, which was there at the last commit"
                        % (j + 1),
                    )
                    return None
                at = self.lines[j].find(closer)
                if at >= 0:
                    detail.append(self.lines[j][:at])
                    last, tail = j, self.lines[j][at + len(closer) :]
                    break
                detail.append(self.lines[j])
                j += 1
        if tail.strip():
            self.warn(last, "text follows the comment's `%s`" % decode(closer))
            return None
        return title, detail, last

    def _above(self, last):
        """The line below a TODO's 1-based last line, past blank lines and
        other TODOs, or None at the end of the file."""
        for k in range(last, len(self.lines)):
            if k in self.spans or not self.lines[k].strip():
                continue
            return {"line": k + 1, "text": decode(self.lines[k]), "base_line": self.base_of.get(k)}
        return None


def read_file(repo, path):
    """The file's bytes, or None with a warning when it cannot be read."""
    try:
        with open(os.path.join(repo.root, path), "rb") as fh:
            return fh.read(), None
    except OSError as exc:
        return None, "%s: cannot read, so it was skipped: %s" % (path, exc.strerror)


def regular(repo, path):
    full = os.path.join(repo.root, path)
    return os.path.isfile(full) and not os.path.islink(full)


def scan(repo):
    """(todos, warnings) for every pending file, in path order."""
    files = repo.changed() + [(path, None, None) for path in repo.untracked()]
    todos, warnings = [], []
    for path, base_path, binary in sorted(files):
        if not regular(repo, path):
            continue
        raw, problem = read_file(repo, path)
        if problem:
            warnings.append(problem)
            continue
        if binary is None:
            binary = repo.binary(path)
        if binary:
            continue
        lines = split_lines(raw)
        base = repo.base(base_path) if base_path is not None else None
        added, base_of = compare(split_lines(base) if base is not None else [], lines)
        found = FileScan(path, lines, added, base_of)
        todos.extend(found.todos)
        warnings.extend(found.warnings)
    return todos, warnings


def cmd_scan(args):
    repo = Repo(args.repo)
    todos, warnings = scan(repo)
    commit = {"hash": repo.head, "on_remote": repo.on_remote()}

    def human():
        short = commit["hash"][:ABBREV]
        if not todos:
            print("No pending TODOs in the changes since %s." % short)
            return
        for t in todos:
            where = "%d" % t["first"]
            if t["last"] != t["first"]:
                where += "-%d" % t["last"]
            kind = "(%s) " % t["kind"] if t["kind"] else ""
            print("%s:%s: %s%s" % (t["file"], where, kind, t["title"]))
            for d in t["detail"].split("\n") if t["detail"] else []:
                print(("    %s" % d).rstrip())
            above = t["above"]
            if above:
                was = "line %d at %s" % (above["base_line"], short) if above["base_line"] else "new"
                print("    above line %d (%s): %s" % (above["line"], was, above["text"].strip()))
        print(
            "Last commit %s, %s."
            % (short, "on a remote branch" if commit["on_remote"] else "not on any remote branch")
        )

    return emit(args, "scan", {"commit": commit, "todos": todos}, warnings=warnings, human=human)


# --------------------------------------------------------------------------
# entry
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument(
        "-C", "--repo", metavar="DIR", default=".", help="the clone to read (default: here)"
    )

    ap = argparse.ArgumentParser(prog=PROG, description="Deterministic half of the do-todos skill.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "scan", parents=[common], help="list the TODOs in the changes since the last commit"
    )
    p.set_defaults(func=cmd_scan)

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN
    except BrokenPipeError:
        return OK


if __name__ == "__main__":
    sys.exit(main())

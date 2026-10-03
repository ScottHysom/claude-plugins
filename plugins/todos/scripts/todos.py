#!/usr/bin/env python3
"""Deterministic half of the do-todos skill.

A TODO is a note the user leaves in a file while reviewing it, for the skill
to file as an issue. This script finds them, checks the model's drafts, files
them through GitHub's command-line tool, gh, and takes each TODO out of its
file. The model does what needs judgment: drafting each issue, and asking the
user when a TODO says too little.

Usage:
    python3 todos.py <command> [options]
    python3 todos.py --help

Commands:
    setup   copy this script into the project's .todos/, which git ignores
    scan    list the TODOs in the working tree's changes since the last
            commit, and the labels of the repository they would be filed in
    report  check the model's drafts against the files as they are now, and
            print them whole, ending with an approval token
    file    file each draft that report showed, and remove its TODO

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Drafts. `--drafts` names a file holding a JSON array, one object per TODO to
file. `file`, `line` and `text` name the TODO: its path, its first line's
number and that line's text, all as `scan` gave them. `route` says where it
goes. The only route is `issue`, which takes `title`, `body` and `labels`.
`python3 todos.py report --help` shows an example.

The token. `report` ends with a token that hashes the drafts file, the
repository gh resolves for the clone, the last commit and every file a draft
names. `file` refuses a token that does not match them as they are now, so
what it files is what the author approved, in the repository the report
named. Every later gh call passes that repository as --repo, so a fork cannot
send issues to its upstream.

Filing. A filed issue cannot be counted on to come back, since deleting one
takes admin rights, so `file` checks everything it can before its first gh
call: the token, every draft, and that it can open each file it would change
for writing. It then files the drafts file by file, from the last TODO in each
to the first, and removes each TODO as soon as its issue exists. A run cut
short leaves every TODO whose issue does not exist, and none whose issue does.
It stops at the first gh call that fails.

Removing a TODO takes its lines and tidies the blank lines around it:
- Added blank lines go, and committed ones stay.
- One added blank line stays where the run holds no committed one, reaches
  neither end of the file, and borders a line added since the last commit,
  so new code keeps its spacing.
- When the removal reaches the end of the file, the line left last gets back
  the ending it had at the last commit, if it was the last line then too.
So a tracked file whose only changes were TODOs, with blank lines around
them, goes back to its last commit byte for byte. A blank line added away
from every TODO is the author's, and stays. A byte-order mark is kept, and a
file left empty is not deleted.

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

5. `scan` leaves out .todos/, where `setup` puts this script, even when git
   does not ignore it, since a copy of this file holds `TODO:` in its
   strings.

6. A byte-order mark at the start of a file is not part of its first line,
   so it is not read as a comment marker.

Only `setup` and `file` write, and only in the working tree: `setup` its copy
in .todos/, and `file` the files whose TODOs it removes. Nothing writes to
git, and every git call passes --no-optional-locks so that even git's own
index refresh is skipped.

Python 3.9 is the floor. No match statements, no X | Y unions.
"""

import argparse
import difflib
import hashlib
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

# Edits past which a file is compared with its last commit by difflib, since
# a shortest edit script keeps memory that grows with their square.
MAX_EDITS = 1000

BOM = b"\xef\xbb\xbf"
# A line and its ending, if it has one.
LINE_RE = re.compile(rb"[^\n]*\n|[^\n]+$")
ENDING_RE = re.compile(rb"\r?\n$")

# Where setup copies this script, and the prefix every later command takes.
SCRIPT_PATH = os.path.abspath(__file__)
COPY_DIR = ".todos"
COPY_SCRIPT = COPY_DIR + "/todos.py"
COPY_IGNORE = COPY_DIR + "/.gitignore"
COPY_IGNORE_TEXT = b"*\n"
COPY_PREFIX = "TODOS=" + COPY_SCRIPT

# Every gh call times out, and none prompts or checks for gh's own updates.
GH_TIMEOUT = 60
GH_ENV = {"GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1"}
# gh label list stops at 30 without --limit.
LABEL_LIMIT = 10000
ISSUE_URL_RE = re.compile(r"/issues/(\d+)$")
GH_MISSING = (
    "gh, GitHub's command-line tool, is not installed or not on PATH. Install it from"
    " https://cli.github.com, run `gh auth login`, then run again."
)

ROUTE_ISSUE = "issue"
# The keys a draft holds, by route.
DRAFT_KEYS = {ROUTE_ISSUE: ("file", "line", "text", "route", "title", "body", "labels")}
# Only the owner adds it, so no draft may carry it, in any case.
APPROVED_LABEL = "approved"
DRAFTS_HELP = """\
A draft is one JSON object, and --drafts names a file holding an array of them.
file, line and text name the TODO as scan gave it: its path, its first line's
number, and that line's text. route is "issue", which takes title, body and
labels. Every label must be one scan lists.

example:
  [{"file": "src/run.py", "line": 12, "text": "# TODO(bug): run() waits forever",
    "route": "issue", "title": "run() waits forever on a stalled gh",
    "body": "subprocess.run has no timeout.", "labels": ["bug"]}]
"""

TOKEN_LENGTH = 16
TOKEN_LABEL = "approval token: "
TOKEN_STALE = (
    "the token does not match the drafts, the files they name, the last commit or the"
    " repository as they are now, so nothing was filed or written. Run report again, show"
    " it to the author, and file with its token"
)


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


class GhFailed(Exception):
    """A gh call that ran and failed."""


class GhTimedOut(GhFailed):
    """A gh call that did not finish in time, which says nothing of signing in."""


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
# gh
# --------------------------------------------------------------------------


def gh(root, *args, stdin=None):
    """Run gh in the clone and return its stdout. Tests replace this."""
    try:
        proc = subprocess.run(
            ["gh", *args],
            cwd=root,
            input=stdin,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT,
            env=dict(os.environ, **GH_ENV),
            check=False,
        )
    except FileNotFoundError as exc:
        raise Fatal(GH_MISSING) from exc
    except subprocess.TimeoutExpired as exc:
        raise GhTimedOut(
            "`gh %s` did not finish within %s seconds" % (" ".join(args[:2]), GH_TIMEOUT)
        ) from exc
    if proc.returncode != 0:
        raise GhFailed("`gh %s` failed: %s" % (" ".join(args[:2]), proc.stderr.strip()))
    return proc.stdout


def gh_json(root, *args):
    out = gh(root, *args)
    try:
        return json.loads(out)
    except ValueError as exc:
        raise Fatal(
            "`gh %s` did not print JSON: %s. Run it yourself to see what it prints."
            % (" ".join(args[:2]), exc)
        ) from exc


class GitHub:
    """The repository gh resolves for the clone, and the calls made to it."""

    def __init__(self, repo):
        self.root = repo.root
        try:
            got = gh_json(self.root, "repo", "view", "--json", "nameWithOwner,url")
        except GhFailed as exc:
            raise self.cannot_resolve(exc) from exc
        self.name = got["nameWithOwner"]
        self.url = got["url"]

    def cannot_resolve(self, exc):
        """The Fatal for a clone gh cannot name a repository for."""
        if isinstance(exc, GhTimedOut):
            return Fatal("%s. Check that GitHub can be reached, then run again." % exc)
        try:
            gh(self.root, "auth", "status")
        except GhFailed as auth:
            return Fatal("gh is not signed in. %s. Run `gh auth login`, then run again." % auth)
        return Fatal(
            "%s. Add a GitHub remote, or choose one with `gh repo set-default`, then run again."
            % exc
        )

    def labels(self):
        """Every label of the repository, as {name, description}."""
        try:
            got = gh_json(
                self.root,
                "label",
                "list",
                "--repo",
                self.name,
                "--limit",
                str(LABEL_LIMIT),
                "--json",
                "name,description",
            )
        except GhFailed as exc:
            raise Fatal("%s. Run it yourself to see what gh reports." % exc) from exc
        return [{"name": g["name"], "description": g["description"]} for g in got]

    def create(self, title, body, labels):
        """(number, address) of a new issue. GhFailed when it was not filed."""
        args = ["issue", "create", "--repo", self.name, "--title", title, "--body-file", "-"]
        for label in labels:
            args += ["--label", label]
        out = gh(self.root, *args, stdin=body).strip()
        url = out.splitlines()[-1] if out else ""
        m = ISSUE_URL_RE.search(url)
        if not m:
            raise GhFailed(
                "`gh issue create` did not print an issue's address, but printed %r. Look in"
                " %s for the issue before filing again" % (out, self.url)
            )
        return int(m.group(1)), url


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
    base_of = dict((j, i + 1) for i, j in kept_lines(base_lines, lines))
    return set(range(len(lines))) - set(base_of), base_of


def kept_lines(a, b):
    """(i, j) for each line a[i] that b keeps as b[j], in order.

    A shortest edit script keeps every line a change only added to, so no
    committed line reads as added, even among repeated lines. Past MAX_EDITS
    edits, difflib takes over, which is faster and not always shortest.
    """
    pre = 0
    while pre < min(len(a), len(b)) and a[pre] == b[pre]:
        pre += 1
    suf = 0
    while suf < min(len(a), len(b)) - pre and a[-1 - suf] == b[-1 - suf]:
        suf += 1
    middle = shortest_edit(a[pre : len(a) - suf], b[pre : len(b) - suf])
    if middle is None:
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        return [(i + k, j + k) for i, j, size in sm.get_matching_blocks() for k in range(size)]
    out = [(k, k) for k in range(pre)]
    out += [(i + pre, j + pre) for i, j in middle]
    out += [(len(a) - suf + k, len(b) - suf + k) for k in range(suf)]
    return out


def shortest_edit(a, b):
    """The (i, j) pairs a shortest edit script from a to b keeps, or None
    past MAX_EDITS edits. Myers' greedy algorithm, which keeps each round's
    furthest reach on every diagonal so the path can be traced back."""
    if not a or not b:
        return []
    n, m = len(a), len(b)
    reach = {1: 0}
    rounds = []
    for d in range(min(n + m, MAX_EDITS) + 1):
        rounds.append(dict(reach))
        for k in range(-d, d + 1, 2):
            down = k == -d or (k != d and reach[k - 1] < reach[k + 1])
            x = reach[k + 1] if down else reach[k - 1] + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x, y = x + 1, y + 1
            reach[k] = x
            if x >= n and y >= m:
                return trace_back(rounds, n, m)
    return None


def trace_back(rounds, x, y):
    """The kept pairs of the path shortest_edit found, from its end."""
    pairs = []
    for d in range(len(rounds) - 1, -1, -1):
        reach = rounds[d]
        k = x - y
        down = k == -d or (k != d and reach[k - 1] < reach[k + 1])
        prev_x = reach[k + 1] if down else reach[k - 1]
        prev_y = prev_x - (k + 1 if down else k - 1)
        while x > prev_x and y > prev_y:
            x, y = x - 1, y - 1
            pairs.append((x, y))
        x, y = prev_x, prev_y
    return pairs[::-1]


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
                "text": decode(self.lines[i]),
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


class Pending:
    """One file's bytes and lines, against its last commit, and its TODOs."""

    def __init__(self, path, raw, base):
        self.path = path
        self.bom = raw.startswith(BOM)
        self.raw = raw[len(BOM) :] if self.bom else raw
        if base is not None and base.startswith(BOM):
            base = base[len(BOM) :]
        base_lines = split_lines(base) if base is not None else []
        self.base_count = len(base_lines)
        # Whether the last commit's last line had no ending.
        self.base_open_end = bool(base) and not base.endswith(b"\n")
        lines = split_lines(self.raw)
        added, base_of = compare(base_lines, lines)
        self.added = added
        self.base_of = base_of
        self.found = FileScan(path, lines, added, base_of)


class Scan:
    """Every pending file's TODOs and warnings, in path order."""

    def __init__(self, repo):
        self.files = {}
        self.todos, self.warnings = [], []
        changed = repo.changed() + [(path, None, None) for path in repo.untracked()]
        for path, base_path, binary in sorted(changed):
            if path.startswith(COPY_DIR + "/") or not regular(repo, path):
                continue
            raw, problem = read_file(repo, path)
            if problem:
                self.warnings.append(problem)
                continue
            if binary is None:
                binary = repo.binary(path)
            if binary:
                continue
            base = repo.base(base_path) if base_path is not None else None
            pending = Pending(path, raw, base)
            self.files[path] = pending
            self.todos.extend(pending.found.todos)
            self.warnings.extend(pending.found.warnings)


def print_labels(github, labels):
    print("Labels in %s:" % github.name)
    for label in labels:
        print(("  %s  %s" % (label["name"], label["description"])).rstrip())


def cmd_scan(args):
    repo = Repo(args.repo)
    found = Scan(repo)
    todos = found.todos
    github = GitHub(repo)
    labels = github.labels()
    commit = {"hash": repo.head, "on_remote": repo.on_remote()}

    def human():
        print_labels(github, labels)
        print()
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

    data = {"commit": commit, "repository": github.name, "labels": labels, "todos": todos}
    return emit(args, "scan", data, warnings=found.warnings, human=human)


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------


def cmd_setup(args):
    """Copy this script into the project, since each shell call starts
    without the last one's variables, and the plugin's own path is too long
    to repeat."""
    repo = Repo(args.repo)
    with open(SCRIPT_PATH, "rb") as fh:
        script = fh.read()
    files = []
    for rel, content in ((COPY_SCRIPT, script), (COPY_IGNORE, COPY_IGNORE_TEXT)):
        path = os.path.join(repo.root, rel)
        if not args.dry_run:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(content)
        files.append({"file": rel, "sha256": hashlib.sha256(content).hexdigest()})
    data = {"repo": repo.root, "files": files, "prefix": COPY_PREFIX, "dry_run": args.dry_run}

    def human():
        verb = "would write" if args.dry_run else "wrote"
        for f in files:
            print("%s %s" % (verb, f["file"]))
        print("\nfrom %s, start every command with:\n%s && " % (repo.root, COPY_PREFIX))

    return emit(args, "setup", data, human=human)


# --------------------------------------------------------------------------
# drafts
# --------------------------------------------------------------------------


def read_drafts(path):
    """(raw bytes, drafts) from the file --drafts names."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise Fatal(
            "cannot read the drafts in %s: %s. Write them there, then run again."
            % (path, exc.strerror)
        ) from exc
    try:
        drafts = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise Fatal("%s is not JSON: %s. Fix it, then run again." % (path, exc)) from exc
    if not isinstance(drafts, list):
        raise Fatal("%s holds JSON, but not an array of drafts. Fix it, then run again." % path)
    return raw, drafts


def is_text(value):
    return isinstance(value, str)


def draft_problems(draft, github, label_names):
    """What is wrong with one draft's own fields, as a list of reasons."""
    if not isinstance(draft, dict):
        return ["is not a JSON object"]
    route = draft.get("route")
    if route not in DRAFT_KEYS:
        return ["has route %s, and the only route is `%s`" % (json.dumps(route), ROUTE_ISSUE)]
    keys = DRAFT_KEYS[route]
    out = ["lacks `%s`" % k for k in keys if k not in draft]
    out += ["has `%s`, which a draft does not take" % k for k in sorted(draft) if k not in keys]
    if out:
        return out
    line = draft["line"]
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        out.append("has a `line` that is not a line number")
    for key in ("file", "text", "body"):
        if not is_text(draft[key]):
            out.append("has a `%s` that is not a string" % key)
    if not is_text(draft["title"]) or not draft["title"].strip():
        out.append("has a `title` that is not a string with words in it")
    labels = draft["labels"]
    if not isinstance(labels, list) or not all(is_text(x) for x in labels):
        out.append("has `labels` that are not an array of strings")
        return out
    for label in labels:
        if label.lower() == APPROVED_LABEL:
            out.append("carries the label `%s`, which only the owner adds. Take it off" % label)
        elif label not in label_names:
            out.append(
                "names the label `%s`, which %s does not have. Use one scan lists"
                % (label, github.name)
            )
    return out


def check_drafts(drafts, found, github, labels):
    """(rows, refused): a row for each draft that names a pending TODO and
    passes every check, and a reason for each that does not."""
    todos = dict(((t["file"], t["first"]), t) for t in found.todos)
    label_names = set(label["name"] for label in labels)
    rows, refused, claims = [], [], {}
    for n, draft in enumerate(drafts, 1):
        problems = draft_problems(draft, github, label_names)
        if problems:
            refused.extend("draft %d %s" % (n, p) for p in problems)
            continue
        place = (draft["file"], draft["line"])
        todo = todos.get(place)
        if todo is None or todo["text"] != draft["text"]:
            refused.append(
                "draft %d: %s:%d does not hold a pending TODO whose first line is %s. Run scan"
                " again and redraft it" % (n, place[0], place[1], json.dumps(draft["text"]))
            )
            continue
        claims.setdefault(place, []).append(n)
        rows.append(
            {
                "draft": n,
                "file": todo["file"],
                "first": todo["first"],
                "last": todo["last"],
                "route": draft["route"],
                "title": draft["title"],
                "body": draft["body"],
                "labels": draft["labels"],
            }
        )
    for place, numbers in sorted(claims.items()):
        if len(numbers) > 1:
            refused.append(
                "drafts %s name one TODO, %s:%d. Keep one of them"
                % (", ".join(str(n) for n in numbers), place[0], place[1])
            )
            rows = [r for r in rows if r["draft"] not in numbers]
    return rows, refused


def where(row):
    """A TODO's file and lines, as `a.py:3` or `a.py:3-5`."""
    span = "%d" % row["first"]
    if row["last"] != row["first"]:
        span += "-%d" % row["last"]
    return "%s:%s" % (row["file"], span)


class TokenHash:
    """The sha256 behind a token, fed one part at a time.

    Every part carries its length, so bytes cannot move from one part to the
    next and hash the same.
    """

    def __init__(self):
        self.digest = hashlib.sha256()

    def part(self, data):
        self.digest.update(b"%d:" % len(data))
        self.digest.update(data)

    def document(self, path):
        # A leading byte tells a missing file from an empty one.
        if not os.path.isfile(path):
            self.digest.update(b"-")
            return
        self.digest.update(b"+")
        with open(path, "rb") as fh:
            self.part(fh.read())

    def token(self):
        return self.digest.hexdigest()[:TOKEN_LENGTH]


def approval_token(repo, github, raw, drafts):
    """The token report prints and file requires, for this batch as it is now.

    A sha256 over the drafts' bytes, the repository's name, the last commit,
    and the path and bytes of every file a draft names.
    """
    digest = TokenHash()
    digest.part(raw)
    digest.part(github.name.encode("utf-8"))
    digest.part(repo.head.encode("utf-8"))
    names = set(d["file"] for d in drafts if isinstance(d, dict) and is_text(d.get("file")))
    for rel in sorted(names):
        digest.part(rel.encode("utf-8"))
        digest.document(os.path.join(repo.root, rel))
    return digest.token()


def print_draft(row):
    print("draft %d  %s  %s" % (row["draft"], where(row), row["route"]))
    print("  title   %s" % row["title"])
    print("  labels  %s" % (", ".join(row["labels"]) or "(none)"))
    print("  body")
    for line in row["body"].split("\n"):
        print(("    | %s" % line).rstrip())
    print()


def cmd_report(args):
    """The drafts as the author approves them, read against the files now."""
    repo = Repo(args.repo)
    raw, drafts = read_drafts(args.drafts)
    github = GitHub(repo)
    labels = github.labels()
    found = Scan(repo)
    rows, refused = check_drafts(drafts, found, github, labels)
    drafted = set((r["file"], r["first"]) for r in rows)
    left = [t for t in found.todos if (t["file"], t["first"]) not in drafted]
    # No token for a report that failed: the author cannot approve a batch
    # file would refuse.
    token = None if refused else approval_token(repo, github, raw, drafts)
    data = {
        "repository": github.name,
        "url": github.url,
        "drafts": rows,
        "left": left,
        "scan_warnings": found.warnings,
        "token": token,
    }

    def human():
        print("Filing in %s (%s).\n" % (github.name, github.url))
        for row in rows:
            print_draft(row)
        print("%d draft(s)." % len(rows))
        if left:
            print("\nLeft in place, with no draft:")
            for t in left:
                print("  %s  %s" % (where(t), t["title"]))
        if found.warnings:
            print("\nWarnings from scan:")
            for w in found.warnings:
                print("  %s" % w)
        if token:
            print("\n" + TOKEN_LABEL + token)

    return emit(args, "report", data, errors=refused, human=human)


# --------------------------------------------------------------------------
# removing a TODO
# --------------------------------------------------------------------------


class Entry:
    """One line of a file being edited, with its ending."""

    def __init__(self, text, added, base_line):
        self.text = text
        self.added = added
        self.base_line = base_line

    def blank(self):
        return not self.text.strip()


class Removal:
    """A file's lines, from which TODOs are removed from the bottom up.

    Each removal leaves the lines above it where they were, so the line
    numbers scan gave for the TODOs above stay right.
    """

    def __init__(self, path, pending):
        self.path = path
        self.pending = pending
        self.entries = [
            Entry(text, i in pending.added, pending.base_of.get(i))
            for i, text in enumerate(LINE_RE.findall(pending.raw))
        ]

    def remove(self, first, last):
        """Take out lines first to last, 1-based, and tidy the blank lines
        around them, as the module docstring says."""
        e = self.entries
        del e[first - 1 : last]
        lo = hi = first - 1
        while lo > 0 and e[lo - 1].blank():
            lo -= 1
        while hi < len(e) and e[hi].blank():
            hi += 1
        run = e[lo:hi]
        committed = [x for x in run if not x.added]
        inside = lo > 0 and hi < len(e)
        borders_added = inside and (e[lo - 1].added or e[hi].added)
        keep = committed or (run[:1] if inside and borders_added else [])
        e[lo:hi] = keep
        at_end = lo + len(keep) == len(e)
        p = self.pending
        if at_end and e and p.base_open_end and e[-1].base_line == p.base_count:
            e[-1].text = ENDING_RE.sub(b"", e[-1].text)

    def content(self):
        return (BOM if self.pending.bom else b"") + b"".join(x.text for x in self.entries)

    def write(self):
        with open(self.path, "wb") as fh:
            fh.write(self.content())


# --------------------------------------------------------------------------
# file
# --------------------------------------------------------------------------


def writable(repo, rel):
    """Fatal unless the file can be opened for writing. Writes nothing."""
    try:
        with open(os.path.join(repo.root, rel), "r+b"):
            pass
    except OSError as exc:
        raise Fatal(
            "cannot open %s for writing: %s. Make it writable, then run file again; nothing"
            " was filed" % (rel, exc.strerror)
        ) from exc


def cmd_file(args):
    repo = Repo(args.repo)
    raw, drafts = read_drafts(args.drafts)
    github = GitHub(repo)
    data = {"repository": github.name, "filed": [], "left": [], "dry_run": args.dry_run}
    if args.token != approval_token(repo, github, raw, drafts):
        return emit(args, "file", data, errors=[TOKEN_STALE])
    found = Scan(repo)
    rows, refused = check_drafts(drafts, found, github, github.labels())
    if refused:
        refused.append("nothing was filed or written")
        return emit(args, "file", data, errors=refused)

    rows.sort(key=lambda r: (r["file"], -r["first"]))
    removals = {}
    for rel in sorted(set(r["file"] for r in rows)):
        writable(repo, rel)
        removals[rel] = Removal(os.path.join(repo.root, rel), found.files[rel])

    errors = []
    for i, row in enumerate(rows):
        if args.dry_run:
            data["filed"].append(dict(row, number=None, url=None))
            continue
        try:
            number, url = github.create(row["title"], row["body"], row["labels"])
        except GhFailed as exc:
            errors.append(
                "draft %d (%s): %s. Filing stopped there, and the TODOs of the drafts not"
                " filed are still in their files" % (row["draft"], where(row), exc)
            )
            data["left"] = rows[i:]
            break
        removal = removals[row["file"]]
        removal.remove(row["first"], row["last"])
        removal.write()
        data["filed"].append(dict(row, number=number, url=url))

    def human():
        for r in data["filed"]:
            if args.dry_run:
                print(
                    "would file in %s: %s  [%s]"
                    % (github.name, r["title"], ", ".join(r["labels"]) or "no labels")
                )
                print("  and remove %s" % where(r))
            else:
                print("filed #%d %s" % (r["number"], r["url"]))
                print("  and removed %s" % where(r))
        for r in data["left"]:
            print("not filed: draft %d, %s, left in place" % (r["draft"], where(r)))

    return emit(args, "file", data, errors=errors, human=human)


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

    dry_run = argparse.ArgumentParser(add_help=False)
    dry_run.add_argument(
        "--dry-run", action="store_true", help="say what would be done, and do none of it"
    )
    drafts = argparse.ArgumentParser(add_help=False)
    drafts.add_argument(
        "--drafts", required=True, metavar="FILE", help="the JSON file of drafts to check"
    )

    p = sub.add_parser(
        "setup",
        parents=[common, dry_run],
        help="copy this script into %s/, which git ignores" % COPY_DIR,
    )
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser(
        "scan",
        parents=[common],
        help="list the TODOs in the changes since the last commit, and the repository's labels",
    )
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser(
        "report",
        parents=[common, drafts],
        help="check the drafts against the files now, and print them with an approval token",
        epilog=DRAFTS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.set_defaults(func=cmd_report)

    p = sub.add_parser(
        "file",
        parents=[common, drafts, dry_run],
        help="file each draft report showed, and remove its TODO",
        epilog=DRAFTS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--token", required=True, help="the approval token report printed")
    p.set_defaults(func=cmd_file)

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

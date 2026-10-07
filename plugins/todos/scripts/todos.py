#!/usr/bin/env python3
"""Deterministic half of the do-todos skill.

A TODO is a note the user leaves in a file while reviewing it, for the skill
to file as an issue. This script finds them, checks the model's drafts, files
them through GitHub's command-line tool, gh, and marks each TODO handled where
it was left. The model does what needs judgment: drafting each issue, and asking the
user when a TODO says too little.

Usage:
    python3 todos.py <command> [options]
    python3 todos.py --help

Commands:
    setup   copy this script into the project's .todos/, which git ignores
    scan    list the TODOs in the working tree's changes since the last
            commit, the open issues like each, and the labels of the
            repository they would be filed in
    report  check the model's drafts against the files as they are now, and
            print them whole, ending with an approval token, and write them
            as markdown to .todos/report.md
    file    file or post each draft that report showed, mark its TODO
            handled, and print the hand-off for each draft routed to a skill
    questions
            write the questions about TODOs that say too little to
            .todos/questions.md, for the author to answer on a page

scan, report, file and questions take --from with another worktree of the repository,
named by its folder or by the branch it has checked out, and read that
worktree's TODOs instead of this tree's. file then marks them there, and each
hand-off names that worktree's root and branch. --from naming this tree reads
as no --from, so the skill can pass on whichever checkout the author named.
When this tree does not hold a pending TODO and another worktree does, scan
names each such worktree and exits 1, so a session opened in a fresh worktree
still finds the TODOs left in the checkout where the author reviews.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Drafts. `--drafts` names a file holding a JSON array, one object per TODO to
file. `file`, `line` and `text` name the TODO: its path, its first line's
number and that line's text, all as `scan` gave them. `route` says where it
goes. The route `issue` takes `title`, `body` and `labels`, for a new issue.
The route `comment` takes `issue` and `body`, for a comment on an open issue
that already covers the TODO. The route `skill` takes `skill`, the name the
Skill tool takes, for an installed skill made for the work the TODO asks for.
`python3 todos.py report --help` shows an example.

Hand-offs. A draft routed to `skill` does not reach GitHub. `file` marks its
TODO like any other, then prints a hand-off for each skill, holding every TODO
routed to it: the TODO's title and detail, and the passage it sat above. The
passage is the run of lines that are neither blank nor a TODO's, marked or
not, around the line `scan` gave as `above`, with any trailing TODO taken off.
Marking never moves a line, so its line numbers are the ones the receiving
skill sees, and `changed` lists those added since the last commit. A TODO at the end of the
file does not sit above anything, and its passage is null. The script cannot
see which skills are installed, so it does not check the name; the model
takes it from the skills the session lists.

Open issues like a TODO. `scan` lists, for each TODO, the first SIMILAR_LIMIT
open issues GitHub's search returns for its title. GitHub's REST search allows
a signed-in client 30 requests a minute, so every title goes in one GraphQL
query, with an aliased `search` per title. A word of the title holding a colon
is quoted, so a title such as "is:closed in config" cannot act as a search
qualifier and widen the search past this repository's open issues.

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
to the first, and marks each TODO as soon as its issue or comment exists. A
run cut short leaves unmarked every TODO whose issue or comment does not
exist, and none whose does. It stops at the first gh call that fails.

A comment draft is checked against its issue twice, by `report` and again by
`file`, since the token covers the drafts and not the issue, which may close
in between.

Marking a TODO handled puts `TODO-HANDLED(<target>)` in place of its word,
`TODO` or `TODO(<kind>)`, and keeps its text and comment syntax. The target is
`#<n>` for an issue, `#<n> comment` for a comment on one, and the skill's name
for a hand-off. A search for TODO then finds the handled TODOs and the missed
ones alike, and the author deletes the markers when committing, or keeps them.
In a markdown file, a TODO that is not already in an HTML comment is wrapped
in one, from after its indent, or for a trailing TODO from its marker, to the
end of its last line, so it does not render. No other byte changes, and no
line is added or removed. `scan` reads a marked TODO, with its detail, only
so that it neither reports it, nor warns about it, nor reads it as another
TODO's detail or as the line a TODO sits above.

What a TODO is. A line of a text file that opens, after its indent and an
optional comment marker, with `TODO:` or `TODO(<kind>):`, or the end of a
line, in the trailing form below. The rest of the line
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
  to be new since the last commit, so a TODO never takes in a committed
  line.
- Trailing form. Text at the end of a line, from the space before its marker,
  where the line without it is a line of the last commit, such as
  `x = 3  # TODO: allow 5`. It has a title only. A block comment's closer has
  to end the line, and is not part of the title. The file is compared with
  the last commit as if the text were already gone, so the line counts as
  committed, and its `above` is the line itself as committed.

Only lines added since the last commit count. git decides what changed, what
is binary and what is ignored. The last commit's side of a file is read with
`git cat-file --filters`, so autocrlf and eol attributes do not make every
line look changed. Lines are compared without their line endings.

Things that look like bugs and are not:

1. A `TODO:` part way along a line is read only when it and the text after it
   are all that sets the line apart from a line of the last commit, and
   otherwise draws a warning. scan compares the line without the TODO with
   the last commit, so on a line whose code changed too it could not tell
   the TODO from the change, and the hand-off's passage would not show which
   lines changed.

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

7. In markdown, a marked TODO whose text holds `-->` ends its wrapping
   comment early, and what follows renders. As a simplification, the wrap
   does not escape it, and the HTML comment a TODO already sits in is found
   by pairing each `<!--` with the next `-->`, outside the fences and code
   spans of item 2, with no other markdown rule applied.

The report file. Claude Code shows a command's output to the model, and not
reliably to the author, so `report` also writes the report as markdown to
.todos/report.md, for the skill to publish where the author reads it whole.
It goes in the -C tree even under --from, since that is the tree the session
can publish from. A report that refuses a draft writes the refusals and no
token, so a stale token never reaches the author.

The questions file. One dialog holds only a few questions, and a later one
covers the one before, so `questions` writes a round too long for one dialog
to .todos/questions.md, for the skill to publish as a page. Each question
names the TODOs it asks about by file and first line, and the script takes
each title from its own scan, so a question about a TODO that is not pending
is refused. Like the report, the file goes in the -C tree, and a batch with a
refused question writes the refusals and no question.

Only `setup`, `report`, `questions` and `file` write, and only in a working
tree: `setup` its copy in .todos/, `report` .todos/report.md, `questions`
.todos/questions.md, and `file` the files whose TODOs it marks, in the
worktree --from names when it is given. `setup`, `report` and `questions` also
write .todos/.gitignore, so git ignores what they leave there. `report` and
`questions` do not take --dry-run, because nothing reads a preview of the
scratch they write, which their next run replaces. Nothing writes to
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
import shlex
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

# The lines of `git worktree list --porcelain` that the script reads.
WORKTREE_LINE = "worktree "
BRANCH_LINE = "branch refs/heads/"
BARE_LINE = "bare"
# The command scan names when another worktree holds the pending TODOs.
FROM_COMMAND = "scan --from %s"

# A TODO: indent, marker, then `TODO:` or `TODO(<kind>):`. The third group
# is the word `file` replaces when it marks the TODO handled.
TODO_RE = re.compile(rb"^([ \t]*)([^A-Za-z0-9\s]*)[ \t]*(TODO(?:\(([^()]*)\))?):")
# A line that opens with TODO, after its indent and marker, read or not.
OPENS_RE = re.compile(rb"^[ \t]*[^A-Za-z0-9\s]*[ \t]*TODO")
# A TODO that `file` marked handled: indent, then everything before the word,
# such as the marker and the comment that wraps it in markdown.
HANDLED_RE = re.compile(rb"^([ \t]*)([^A-Za-z0-9]*?)TODO-HANDLED\([^()]*\):")
# What `file` puts in place of a finished TODO's word, around its target.
HANDLED = b"TODO-HANDLED(%s)"
# The HTML comment that keeps a marked TODO in markdown from rendering.
HTML_OPEN, HTML_CLOSE = b"<!--", b"-->"
WRAP_OPEN, WRAP_CLOSE = HTML_OPEN + b" ", b" " + HTML_CLOSE
# A line that holds the start of a TODO anywhere along it.
HOLDS_RE = re.compile(rb"TODO[:(]")
# A TODO part way along a line: the space and marker before it, then `TODO:`
# or `TODO(<kind>):`.
TRAILING_RE = re.compile(rb"[ \t]*([^A-Za-z0-9\s]*)[ \t]*(TODO(?:\(([^()]*)\))?):")
# The warning for a TODO part way along a line that is not read.
UNREAD_PART_WAY = (
    "a TODO is read at the start of its line, after its indent and comment marker, or at"
    " its end when the line without it is as the last commit has it"
)
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
# Where report writes the report as markdown, for the author to read whole.
REPORT_FILE = COPY_DIR + "/report.md"
# Where questions writes the questions, for the author to answer on a page.
QUESTIONS_FILE = COPY_DIR + "/questions.md"
# What --batch takes in place of a path to read from stdin.
STDIN_PATH = "-"

# Every gh call times out, and none prompts or checks for gh's own updates.
GH_TIMEOUT = 60
GH_ENV = {"GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1"}
# gh label list stops at 30 without --limit.
LABEL_LIMIT = 10000
ISSUE_URL_RE = re.compile(r"/issues/(\d+)$")
COMMENT_URL_RE = re.compile(r"/issues/\d+#issuecomment-\d+$")
# How many open issues scan lists for each TODO, as the owner set in #313.
SIMILAR_LIMIT = 5
# The GraphQL error a lookup of a missing issue gives, and an open issue's state.
NOT_FOUND = "NOT_FOUND"
OPEN_STATE = "OPEN"
GH_MISSING = (
    "gh, GitHub's command-line tool, is not installed or not on PATH. Install it from"
    " https://cli.github.com, run `gh auth login`, then run again."
)

ROUTE_ISSUE = "issue"
ROUTE_COMMENT = "comment"
ROUTE_SKILL = "skill"
# The target a marked TODO names, for an issue and for a comment on one. A
# hand-off names its skill.
ISSUE_TARGET = "#%d"
COMMENT_TARGET = "#%d comment"
# The keys a draft holds, by route.
DRAFT_KEYS = {
    ROUTE_ISSUE: ("file", "line", "text", "route", "title", "body", "labels"),
    ROUTE_COMMENT: ("file", "line", "text", "route", "issue", "body"),
    ROUTE_SKILL: ("file", "line", "text", "route", "skill"),
}
# Only the owner adds it, so no draft may carry it, in any case.
APPROVED_LABEL = "approved"
DRAFTS_HELP = """\
A draft is one JSON object, and --drafts names a file holding an array of them.
file, line and text name the TODO as scan gave it: its path, its first line's
number, and that line's text. route is "issue", which takes title, body and
labels, "comment", which takes issue, the number of an open issue, and body, or
"skill", which takes skill, the name of an installed skill as the Skill tool
takes it. Every label must be one scan lists.

example:
  [{"file": "src/run.py", "line": 12, "text": "# TODO(bug): run() waits forever",
    "route": "issue", "title": "run() waits forever on a stalled gh",
    "body": "subprocess.run has no timeout.", "labels": ["bug"]},
   {"file": "src/run.py", "line": 30, "text": "# TODO: retry on 502",
    "route": "comment", "issue": 7, "body": "run() gives up on a 502 too."},
   {"file": "README.md", "line": 4, "text": "<!-- TODO(prose): too long -->",
    "route": "skill", "skill": "example:learn-prose-rules"}]
"""

TOKEN_LENGTH = 16
TOKEN_LABEL = "approval token: "
TOKEN_STALE = (
    "the token does not match the drafts, the files they name, the last commit or the"
    " repository as they are now, so nothing was filed, posted or written. Run report again,"
    " show it to the author, and file with its token"
)


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


class GhFailed(Exception):
    """A gh call that ran and failed, with what it printed on stdout."""

    def __init__(self, message, stdout=""):
        super().__init__(message)
        self.stdout = stdout


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

    def trees(self):
        """[(root, branch)] for every worktree of this repository, this one too.

        branch is None for a detached HEAD. A bare repository has no tree,
        and a worktree whose folder is gone has nothing to read, so neither
        is listed.
        """
        trees = []
        for line in os.fsdecode(self.git("worktree", "list", "--porcelain")).splitlines():
            if line.startswith(WORKTREE_LINE):
                trees.append({"root": line[len(WORKTREE_LINE) :], "branch": None, "bare": False})
            elif trees and line.startswith(BRANCH_LINE):
                trees[-1]["branch"] = line[len(BRANCH_LINE) :]
            elif trees and line == BARE_LINE:
                trees[-1]["bare"] = True
        return [
            (t["root"], t["branch"]) for t in trees if not t["bare"] and os.path.isdir(t["root"])
        ]

    def worktrees(self):
        """[(root, branch)] for every other worktree of this repository."""
        here = os.path.realpath(self.root)
        return [(root, branch) for root, branch in self.trees() if os.path.realpath(root) != here]


def open_tree(args, repo=None):
    """(the tree a command reads, its checkout): this tree, or the one --from names.

    --from names a worktree by its folder, or by the branch it has checked
    out, tried in that order. The checkout is None when the tree read is this
    one, so --from naming this tree reads as no --from, and is otherwise
    {root, branch} for the hand-offs to carry. repo is this tree, when the
    caller has opened it already.
    """
    repo = repo or Repo(args.repo)
    if args.source is None:
        return repo, None
    here = os.path.realpath(repo.root)
    trees = repo.trees()
    source = os.path.realpath(args.source)
    named = [t for t in trees if os.path.realpath(t[0]) == source]
    named = named or [t for t in trees if t[1] == args.source]
    if not named:
        listed = "; ".join(
            "%s %s%s"
            % (
                root,
                "on %s" % branch if branch else "(detached)",
                " (this tree)" if os.path.realpath(root) == here else "",
            )
            for root, branch in trees
        )
        raise Fatal(
            "%s is neither a worktree of this repository nor a branch one has checked out."
            " Pass --from one of these worktrees, or its branch: %s" % (args.source, listed)
        )
    root, branch = named[0]
    if os.path.realpath(root) == here:
        return repo, None
    return Repo(root), {"root": root, "branch": branch}


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
        raise GhFailed(
            "`gh %s` failed: %s" % (" ".join(args[:2]), proc.stderr.strip()), proc.stdout
        )
    return proc.stdout


def gh_json(root, *args):
    return parse_json(gh(root, *args), args)


def parse_json(out, args):
    try:
        return json.loads(out)
    except ValueError as exc:
        raise Fatal(
            "`gh %s` did not print JSON: %s. Run it yourself to see what it prints."
            % (" ".join(args[:2]), exc)
        ) from exc


def search_query(repository, title):
    """GitHub's search for the open issues of a repository like a title.

    A word holding a colon is quoted, so it is searched for rather than read
    as a qualifier, and a double quote is dropped, so it cannot open a phrase.
    """
    words = ['"%s"' % w if ":" in w else w for w in title.replace('"', " ").split()]
    return " ".join(["repo:" + repository, "is:issue", "is:open", *words])


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

    def graphql(self, query, missing_ok=False):
        """The data of a GraphQL query. With missing_ok, a query whose only
        errors are lookups of things that do not exist gives its data, with
        null in their place, although gh exits 1 for it."""
        args = ("api", "graphql", "--input", "-")
        try:
            out = gh(self.root, *args, stdin=json.dumps({"query": query}))
        except GhFailed as exc:
            got = parse_json(exc.stdout, args) if missing_ok and exc.stdout.strip() else {}
            errors = got.get("errors") or [{}]
            if got.get("data") is None or any(e.get("type") != NOT_FOUND for e in errors):
                raise
            return got["data"]
        return parse_json(out, args)["data"]

    def similar(self, titles):
        """For each title, the first SIMILAR_LIMIT open issues GitHub's search
        returns for it, as {number, title, url}, all in one query."""
        if not titles:
            return []
        searches = " ".join(
            "s%d: search(query: %s, type: ISSUE, first: %d) { nodes { ... on Issue"
            " { number title url } } }" % (i, json.dumps(search_query(self.name, t)), SIMILAR_LIMIT)
            for i, t in enumerate(titles)
        )
        try:
            data = self.graphql("query { %s }" % searches)
        except GhFailed as exc:
            raise Fatal("%s. Run it yourself to see what gh reports." % exc) from exc
        return [
            [
                {"number": n["number"], "title": n["title"], "url": n["url"]}
                for n in data["s%d" % i]["nodes"]
                if n
            ]
            for i in range(len(titles))
        ]

    def issues(self, numbers):
        """{number: {number, title, state, url}, or None when the repository
        does not have that issue}, all in one query."""
        if not numbers:
            return {}
        owner, _, name = self.name.partition("/")
        aliases = " ".join(
            "i%d: issue(number: %d) { number title state url }" % (n, n) for n in numbers
        )
        query = "query { repository(owner: %s, name: %s) { %s } }" % (
            json.dumps(owner),
            json.dumps(name),
            aliases,
        )
        try:
            data = self.graphql(query, missing_ok=True)
        except GhFailed as exc:
            raise Fatal("%s. Run it yourself to see what gh reports." % exc) from exc
        repo = data.get("repository") or {}
        return dict((n, repo.get("i%d" % n)) for n in numbers)

    def comment(self, number, body):
        """The address of a new comment on an issue. GhFailed when it was not
        posted."""
        args = ["issue", "comment", str(number), "--repo", self.name, "--body-file", "-"]
        out = gh(self.root, *args, stdin=body).strip()
        url = out.splitlines()[-1] if out else ""
        if not COMMENT_URL_RE.search(url):
            raise GhFailed(
                "`gh issue comment` did not print a comment's address, but printed %r. Look"
                " on %s/issues/%d for the comment before posting again" % (out, self.url, number)
            )
        return url

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


def html_comment_open(is_open, text):
    """Whether an HTML comment is open after text, given whether one was
    open before it."""
    pos = 0
    while True:
        at = text.find(HTML_CLOSE if is_open else HTML_OPEN, pos)
        if at < 0:
            return is_open
        pos = at + len(HTML_CLOSE if is_open else HTML_OPEN)
        is_open = not is_open


def commented(lines, skip):
    """For each line, whether an HTML comment is open where it starts. The
    lines in skip, which are in a code fence, do not open or close one."""
    out, is_open = [], False
    for i, line in enumerate(lines):
        out.append(is_open)
        if i not in skip:
            is_open = html_comment_open(is_open, line)
    return out


# --------------------------------------------------------------------------
# scan
# --------------------------------------------------------------------------


class FileScan:
    """The TODOs and warnings in one file's added lines.

    `added` and `base_of` are as compare() gives them for the file with each
    trailing TODO taken off, and `cuts` maps the index of each such line to
    where its TODO starts. `spans` holds the index of every line of a TODO,
    and of a TODO marked handled. `marks` maps the index of each TODO's first
    line to (start, end, wrap): where its word is, and where the HTML comment
    that keeps it from rendering opens, or None when it needs none.
    """

    def __init__(self, path, lines, base_lines):
        self.path = path
        self.lines = lines
        self.markdown = path.lower().endswith(MARKDOWN_SUFFIXES)
        self.skip = fenced(lines) if self.markdown else set()
        self.masked = [mask_code_spans(ln) for ln in lines] if self.markdown else lines
        self.open = commented(self.masked, self.skip) if self.markdown else None
        self.todos = []
        self.warnings = []
        self.spans = set()
        self.marks = {}
        self.added, self.base_of = compare(base_lines, lines)
        self.cuts = {}
        # Why a line holding a TODO part way along was not read, where the
        # general reason would not say.
        self.unread = {}
        self._trailing(base_lines)
        self._scan()
        for todo in self.todos:
            if todo["first"] - 1 in self.cuts:
                todo["above"] = self._own(todo["first"] - 1)
            else:
                todo["above"] = self._above(todo["last"])

    def warn(self, i, reason):
        self.warnings.append("%s:%d: %s" % (self.path, i + 1, reason))

    def _trailing(self, base_lines):
        """Find the trailing TODOs, and compare the file with the last commit
        as if they were gone."""
        committed = set(base_lines)
        cuts = {}
        for i in sorted(self.added - self.skip):
            line = self.masked[i]
            m = TRAILING_RE.search(line)
            if OPENS_RE.match(line) or not m:
                continue
            closer = next((c for o, c in BLOCK_COMMENTS if o in m.group(1)), None)
            if closer is not None and not line.rstrip().endswith(closer):
                self.unread[i] = "a comment holding a TODO at the end of a line has to end it"
                continue
            cut = next(
                (k for k in range(m.start(2), m.start() - 1, -1) if self.lines[i][:k] in committed),
                None,
            )
            if cut is not None:
                cuts[i] = cut
        if not cuts:
            return
        bare = [ln[: cuts[i]] if i in cuts else ln for i, ln in enumerate(self.lines)]
        self.added, self.base_of = compare(base_lines, bare)
        self.cuts = dict((i, cut) for i, cut in cuts.items() if i not in self.added)

    def _scan(self):
        i = 0
        while i < len(self.lines):
            if i in self.cuts:
                self._read_trailing(i)
                i += 1
                continue
            if i not in self.added or i in self.skip:
                i += 1
                continue
            line = self.masked[i]
            handled = HANDLED_RE.match(line)
            if handled:
                last = self._handled(i, handled)
                self.spans.update(range(i, last + 1))
                i = last + 1
                continue
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
                self.warn(i, self.unread.get(i, UNREAD_PART_WAY))
            i += 1

    def _read(self, i, m):
        """Read the TODO opening line i. Its last line's index, or None when
        it cannot be read, with a warning saying why."""
        indent, marker, word = m.group(1), m.group(2), m.group(4)
        rest = self.lines[i][m.end() :]
        closer = next((c for o, c in BLOCK_COMMENTS if o in marker), None)
        if closer is not None:
            got = self._block(i, rest, closer)
            if got is None:
                return None
            title, detail, last = got
            if marker.endswith(b"/*"):
                detail = [d.strip().lstrip(b"*") for d in detail]
        else:
            last = self._detail_end(i, indent, marker)
            title = rest
            detail = [
                self.lines[j][MARKER_RE.match(self.lines[j]).end() :]
                for j in range(i + 1, last + 1)
            ]
        self._add(i, last, marker, word, title, detail, m.span(3), m.end(1))
        return last

    def _detail_end(self, i, indent, marker):
        """The index of the last detail line of a line-form TODO opening line
        i: the added lines below it that open with its marker at its indent,
        up to a blank line or the next TODO, marked handled or not."""
        if not marker or marker in TITLE_ONLY_MARKERS:
            return i
        j = i
        while j + 1 in self.added and self.lines[j + 1].strip():
            line = self.masked[j + 1]
            if TODO_RE.match(line) or HANDLED_RE.match(line):
                break
            lm = MARKER_RE.match(self.lines[j + 1])
            if lm.group(1) != indent or lm.group(2) != marker:
                break
            j += 1
        return j

    def _handled(self, i, m):
        """The index of the last line of the TODO marked handled on line i.
        It is read as `_read` reads a TODO, without a title or a warning."""
        indent, before = m.group(1), m.group(2)
        closer = next((c for o, c in BLOCK_COMMENTS if o in before), None)
        if closer is None:
            return self._detail_end(i, indent, before.rstrip())
        j, text = i, self.masked[i][m.end() :]
        while closer not in text:
            j += 1
            if j not in self.added:
                return i
            text = self.masked[j]
        return j

    def _read_trailing(self, i):
        """Read the TODO at the end of line i, whose closer, if it has one,
        _trailing found ending the line."""
        m = TRAILING_RE.match(self.masked[i], self.cuts[i])
        marker, word, rest = m.group(1), m.group(3), self.lines[i][m.end() :]
        closer = next((c for o, c in BLOCK_COMMENTS if o in marker), None)
        if closer is not None:
            rest = rest.rstrip()[: -len(closer)]
        self._add(i, i, marker, word, rest, [], m.span(2), m.start(1))

    def _add(self, i, last, marker, word, title, detail, span, wrap):
        """Record the TODO opening line i, whose word is at span. In markdown,
        an HTML comment opening at wrap keeps it from rendering once marked,
        unless it is in one already."""
        if not self.markdown or HTML_OPEN in marker:
            wrap = None
        elif html_comment_open(self.open[i], self.masked[i][:wrap]):
            wrap = None
        self.marks[i] = (span[0], span[1], wrap)
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

    def _own(self, i):
        """A line, with any trailing TODO taken off, as {line, text, base_line}."""
        text = decode(self.lines[i][: self.cuts.get(i)])
        return {"line": i + 1, "text": text, "base_line": self.base_of.get(i)}

    def passage(self, line):
        """The passage around a 1-based line, as {first, last, changed, text}:
        the lines that are neither blank nor a TODO's, with any trailing TODO
        taken off."""
        lo = hi = line - 1
        while lo > 0 and self._in_passage(lo - 1):
            lo -= 1
        while hi + 1 < len(self.lines) and self._in_passage(hi + 1):
            hi += 1
        return {
            "first": lo + 1,
            "last": hi + 1,
            "changed": [k + 1 for k in range(lo, hi + 1) if k in self.added],
            "text": "\n".join(self._own(k)["text"] for k in range(lo, hi + 1)),
        }

    def _in_passage(self, k):
        return bool(self.lines[k].strip()) and k not in self.spans

    def _above(self, last):
        """The line below a TODO's 1-based last line, past blank lines and
        other TODOs, or None at the end of the file."""
        for k in range(last, len(self.lines)):
            if k in self.spans or not self.lines[k].strip():
                continue
            return self._own(k)
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
        self.found = FileScan(path, split_lines(self.raw), base_lines)


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


def other_pending(repo):
    """[{root, branch, files}] for each other worktree holding pending TODOs."""
    out = []
    for root, branch in repo.worktrees():
        files = sorted(set(t["file"] for t in Scan(Repo(root)).todos))
        if files:
            out.append({"root": root, "branch": branch, "files": files})
    return out


def cmd_scan(args):
    repo, checkout = open_tree(args)
    found = Scan(repo)
    todos = found.todos
    # A tree without a TODO may be a fresh worktree, opened while the
    # author's TODOs sit in another checkout of the same repository.
    elsewhere = other_pending(repo) if not todos and checkout is None else []
    errors = [
        "this tree does not hold any pending TODO, and %s%s holds TODOs in %s. Ask the author"
        " whether to collect them, then run `%s`, and pass the same --from to report and file"
        % (
            tree["root"],
            ", on %s," % tree["branch"] if tree["branch"] else "",
            ", ".join(tree["files"]),
            FROM_COMMAND % shlex.quote(tree["root"]),
        )
        for tree in elsewhere
    ]
    github = GitHub(repo)
    labels = github.labels()
    for todo, similar in zip(todos, github.similar([t["title"] for t in todos])):
        todo["similar"] = similar
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
                place = "at the end of" if above["line"] == t["first"] else "above"
                print(
                    "    %s line %d (%s): %s" % (place, above["line"], was, above["text"].strip())
                )
            if t["similar"]:
                print("    open issues like it:")
                for issue in t["similar"]:
                    print("      #%d  %s" % (issue["number"], issue["title"]))
        print(
            "Last commit %s, %s."
            % (short, "on a remote branch" if commit["on_remote"] else "not on any remote branch")
        )

    data = {
        "commit": commit,
        "repository": github.name,
        "labels": labels,
        "todos": todos,
        "other_worktrees": elsewhere,
    }
    return emit(args, "scan", data, errors=errors, warnings=found.warnings, human=human)


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


def is_number(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def draft_problems(draft, github, label_names):
    """What is wrong with one draft's own fields, as a list of reasons."""
    if not isinstance(draft, dict):
        return ["is not a JSON object"]
    route = draft.get("route")
    if route not in DRAFT_KEYS:
        return [
            "has route %s, and the routes are `%s`, `%s` and `%s`"
            % (json.dumps(route), ROUTE_ISSUE, ROUTE_COMMENT, ROUTE_SKILL)
        ]
    keys = DRAFT_KEYS[route]
    out = ["lacks `%s`" % k for k in keys if k not in draft]
    out += ["has `%s`, which a draft does not take" % k for k in sorted(draft) if k not in keys]
    if out:
        return out
    if not is_number(draft["line"]):
        out.append("has a `line` that is not a line number")
    for key in ("file", "text", "body"):
        if key in keys and not is_text(draft[key]):
            out.append("has a `%s` that is not a string" % key)
    if route == ROUTE_SKILL:
        if not is_text(draft["skill"]) or not draft["skill"].strip():
            out.append("has a `skill` that is not a string with words in it")
        return out
    if route == ROUTE_COMMENT:
        if not is_number(draft["issue"]):
            out.append("has an `issue` that is not an issue number")
        if is_text(draft["body"]) and not draft["body"].strip():
            out.append("has a `body` with no words in it, which a comment needs")
        return out
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


def target_problems(draft, targets, github):
    """Why a comment draft's issue cannot take it, as a list of reasons."""
    if draft["route"] != ROUTE_COMMENT:
        return []
    number = draft["issue"]
    target = targets[number]
    if target is None:
        return [
            "names issue #%d, which %s does not have. Name an open issue scan lists, or route"
            " the draft to `%s`" % (number, github.name, ROUTE_ISSUE)
        ]
    if target["state"] != OPEN_STATE:
        return [
            "names issue #%d, which is closed. Name an open issue scan lists, or route the"
            " draft to `%s`" % (number, ROUTE_ISSUE)
        ]
    return []


def check_drafts(drafts, found, github, labels):
    """(rows, refused): a row for each draft that names a pending TODO and
    passes every check, and a reason for each that does not."""
    todos = dict(((t["file"], t["first"]), t) for t in found.todos)
    label_names = set(label["name"] for label in labels)
    checked = [(n, d, draft_problems(d, github, label_names)) for n, d in enumerate(drafts, 1)]
    numbers = sorted(
        set(d["issue"] for _, d, p in checked if not p and d["route"] == ROUTE_COMMENT)
    )
    targets = github.issues(numbers)
    rows, refused, claims = [], [], {}
    for n, draft, problems in checked:
        problems = problems or target_problems(draft, targets, github)
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
        row = {
            "draft": n,
            "file": todo["file"],
            "first": todo["first"],
            "last": todo["last"],
            "route": draft["route"],
        }
        if draft["route"] == ROUTE_COMMENT:
            target = targets[draft["issue"]]
            row["issue"] = dict((k, target[k]) for k in ("number", "title", "url"))
            row["body"] = draft["body"]
        elif draft["route"] == ROUTE_SKILL:
            row.update(skill=draft["skill"], title=todo["title"], detail=todo["detail"])
            row["above"] = todo["above"]["line"] if todo["above"] else None
        else:
            row.update(title=draft["title"], body=draft["body"], labels=draft["labels"])
        rows.append(row)
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


def print_block(heading, text):
    print("  %s" % heading)
    for line in text.split("\n"):
        print(("    | %s" % line).rstrip())


def print_draft(row):
    print("draft %d  %s  %s" % (row["draft"], where(row), row["route"]))
    if row["route"] == ROUTE_SKILL:
        print("  to      %s" % row["skill"])
        print("  title   %s" % row["title"])
        if row["detail"]:
            print_block("detail", row["detail"])
        print()
        return
    if row["route"] == ROUTE_COMMENT:
        print("  on      #%d  %s" % (row["issue"]["number"], row["issue"]["title"]))
    else:
        print("  title   %s" % row["title"])
        print("  labels  %s" % (", ".join(row["labels"]) or "(none)"))
    print_block("body", row["body"])
    print()


def quoted(text):
    """text as a markdown quote, so a body's own headings stay inside it."""
    return "\n".join(("> " + line).rstrip() for line in text.split("\n"))


def report_markdown(data, refused):
    """The report as markdown: what the author reads whole, and approves."""
    out = ["# TODO report", ""]
    out.append("Filing in [%s](%s)." % (data["repository"], data["url"]))
    if refused:
        out += ["", "## Refused", "", "Fix these drafts and run report again:", ""]
        out += ["- %s" % e for e in refused]
    for row in data["drafts"]:
        heading = "## Draft %d: `%s`, %s" % (row["draft"], where(row), row["route"])
        out += ["", heading, ""]
        if row["route"] == ROUTE_SKILL:
            out += ["- **To:** `%s`" % row["skill"], "- **Title:** %s" % row["title"]]
            if row["detail"]:
                out += ["", quoted(row["detail"])]
            continue
        if row["route"] == ROUTE_COMMENT:
            out.append("- **On:** #%d %s" % (row["issue"]["number"], row["issue"]["title"]))
        else:
            out.append("- **Title:** %s" % row["title"])
            out.append("- **Labels:** %s" % (", ".join(row["labels"]) or "(none)"))
        out += ["", quoted(row["body"])]
    out += ["", "%d draft(s)." % len(data["drafts"])]
    if data["left"]:
        out += ["", "## Left in place", ""]
        out += ["- `%s` %s" % (where(t), t["title"]) for t in data["left"]]
    if data["scan_warnings"]:
        out += ["", "## Warnings from scan", ""]
        out += ["- %s" % w for w in data["scan_warnings"]]
    if data["token"]:
        out += ["", "%s`%s`" % (TOKEN_LABEL.capitalize(), data["token"])]
    return "\n".join(out) + "\n"


def write_page(repo, rel, text):
    """Write text to rel in repo's .todos/, beside the ignore file, and
    return its path."""
    ignore = os.path.join(repo.root, COPY_IGNORE)
    os.makedirs(os.path.dirname(ignore), exist_ok=True)
    if not os.path.isfile(ignore):
        with open(ignore, "wb") as fh:
            fh.write(COPY_IGNORE_TEXT)
    path = os.path.join(repo.root, rel)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def write_report(repo, data, refused):
    """Write the report into repo's .todos/, and return its path."""
    return write_page(repo, REPORT_FILE, report_markdown(data, refused))


def cmd_report(args):
    """The drafts as the author approves them, read against the files now."""
    here = Repo(args.repo)
    repo, _ = open_tree(args, here)
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
    # In this session's tree even under --from, where the session can read
    # and publish it.
    data["report"] = write_report(here, data, refused)

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
# questions
# --------------------------------------------------------------------------


def read_questions(path):
    """The questions from the file --batch names, or from stdin given -."""
    try:
        if path == STDIN_PATH:
            raw = sys.stdin.read()
        else:
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
    except OSError as exc:
        raise Fatal(
            "cannot read the questions in %s: %s. Write them there, then run again."
            % (path, exc.strerror)
        ) from exc
    try:
        questions = json.loads(raw)
    except ValueError as exc:
        raise Fatal("the questions are not JSON: %s. Fix them, then run again." % exc) from exc
    if not isinstance(questions, list) or not questions:
        raise Fatal(
            "the questions are not a JSON array of at least one question. Fix them, then run again."
        )
    return questions


def question_problems(n, q, todos):
    """(reasons question n cannot go on the page, the TODOs it names)."""
    if not isinstance(q, dict):
        return ["question %d is not a JSON object" % n], []
    reasons, named = [], []
    if not is_text(q.get("question")) or not q["question"].strip():
        reasons.append("question %d has no question text" % n)
    options = q.get("options")
    if not isinstance(options, list) or not options:
        reasons.append("question %d has no options" % n)
    else:
        for i, o in enumerate(options, 1):
            if not isinstance(o, dict) or not is_text(o.get("label")) or not o["label"].strip():
                reasons.append("question %d, option %d has no label" % (n, i))
            elif not is_text(o.get("description", "")):
                reasons.append("question %d, option %d has a description that is not text" % (n, i))
    asked = q.get("todos")
    if not isinstance(asked, list) or not asked:
        reasons.append("question %d does not name a TODO" % n)
        return reasons, named
    for i, t in enumerate(asked, 1):
        if not isinstance(t, dict) or not is_text(t.get("file")) or not is_number(t.get("line")):
            reasons.append("question %d, TODO %d does not give a `file` and a `line`" % (n, i))
            continue
        todo = todos.get((t["file"], t["line"]))
        if todo is None:
            reasons.append(
                "question %d, TODO %d: %s:%d does not hold a pending TODO. Run scan again and"
                " name the TODO by its file and first line" % (n, i, t["file"], t["line"])
            )
            continue
        named.append(todo)
    return reasons, named


def questions_markdown(asked, refused):
    """The questions as the author reads them whole, or the refusals instead."""
    out = ["# Questions from do-todos", ""]
    if refused:
        out += ["Fix these questions and run questions again:", ""]
        out += ["- %s" % r for r in refused]
        return "\n".join(out) + "\n"
    out.append(
        "Answer each question by commenting on it and sending the comment to Claude."
        " Pick an option, or say what you mean in your own words."
    )
    for n, (q, named) in enumerate(asked, 1):
        out += ["", "## Question %d" % n, ""]
        out += ["- `%s:%d` %s" % (t["file"], t["first"], t["title"]) for t in named]
        out += ["", q["question"].strip(), "", "Options:", ""]
        for o in q["options"]:
            line = "- **%s**" % o["label"]
            if o.get("description"):
                line += ": %s" % o["description"]
            out.append(line)
    return "\n".join(out) + "\n"


def cmd_questions(args):
    """Write the questions to .todos/questions.md, for the author to answer
    on a page when one dialog cannot hold them."""
    here = Repo(args.repo)
    repo, _ = open_tree(args, here)
    questions = read_questions(args.batch)
    todos = dict(((t["file"], t["first"]), t) for t in Scan(repo).todos)
    asked, refused = [], []
    for n, q in enumerate(questions, 1):
        reasons, named = question_problems(n, q, todos)
        refused += reasons
        asked.append((q, named))
    # In this session's tree even under --from, as report's file is.
    path = write_page(here, QUESTIONS_FILE, questions_markdown(asked, refused))
    data = {"page": path, "questions": 0 if refused else len(asked)}
    return emit(args, "questions", data, errors=refused, human=lambda: print("wrote %s" % path))


# --------------------------------------------------------------------------
# marking a TODO handled
# --------------------------------------------------------------------------


class Marking:
    """A file's lines, in which finished TODOs are marked handled.

    Marking changes bytes inside a TODO's first and last lines and never adds
    or removes a line, so the line numbers scan gave stay right.
    """

    def __init__(self, path, pending):
        self.path = path
        self.pending = pending
        self.lines = LINE_RE.findall(pending.raw)

    def mark(self, first, last, target):
        """Put `TODO-HANDLED(<target>)` in place of the word of the TODO on
        lines first to last, 1-based, and wrap it in an HTML comment where
        scan found it needs one."""
        start, end, wrap = self.pending.found.marks[first - 1]
        line = self.lines[first - 1]
        line = line[:start] + HANDLED % target.encode("utf-8") + line[end:]
        if wrap is not None:
            line = line[:wrap] + WRAP_OPEN + line[wrap:]
        self.lines[first - 1] = line
        if wrap is not None:
            text = self.lines[last - 1]
            body = ENDING_RE.sub(b"", text)
            self.lines[last - 1] = body + WRAP_CLOSE + text[len(body) :]

    def content(self):
        return (BOM if self.pending.bom else b"") + b"".join(self.lines)

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
            " was filed or posted" % (rel, exc.strerror)
        ) from exc


def cmd_file(args):
    repo, checkout = open_tree(args)
    raw, drafts = read_drafts(args.drafts)
    github = GitHub(repo)
    data = {
        "repository": github.name,
        "filed": [],
        "left": [],
        "handoffs": [],
        "dry_run": args.dry_run,
    }
    if args.token != approval_token(repo, github, raw, drafts):
        return emit(args, "file", data, errors=[TOKEN_STALE])
    found = Scan(repo)
    rows, refused = check_drafts(drafts, found, github, github.labels())
    if refused:
        refused.append("nothing was filed, posted or written")
        return emit(args, "file", data, errors=refused)

    rows.sort(key=lambda r: (r["file"], -r["first"]))
    markings = {}
    for rel in sorted(set(r["file"] for r in rows)):
        writable(repo, rel)
        markings[rel] = Marking(os.path.join(repo.root, rel), found.files[rel])

    def finish(row, target, **fields):
        """Mark the row's TODO handled, unless this is a dry run."""
        if not args.dry_run:
            marking = markings[row["file"]]
            marking.mark(row["first"], row["last"], target)
            marking.write()
        handled = None if target is None else decode(HANDLED % target.encode("utf-8"))
        data["filed"].append(dict(row, handled=handled, **fields))

    errors = []
    for i, row in enumerate(rows):
        if row["route"] == ROUTE_SKILL:
            finish(row, row["skill"])
            continue
        if args.dry_run:
            comment = row["route"] == ROUTE_COMMENT
            target = COMMENT_TARGET % row["issue"]["number"] if comment else None
            finish(row, target, number=None, url=None)
            continue
        try:
            if row["route"] == ROUTE_COMMENT:
                number = row["issue"]["number"]
                url = github.comment(number, row["body"])
            else:
                number, url = github.create(row["title"], row["body"], row["labels"])
        except GhFailed as exc:
            errors.append(
                "draft %d (%s): %s. Filing stopped there, and the TODOs of the drafts not"
                " filed or posted are still in their files" % (row["draft"], where(row), exc)
            )
            data["left"] = rows[i:]
            break
        target = (COMMENT_TARGET if row["route"] == ROUTE_COMMENT else ISSUE_TARGET) % number
        finish(row, target, number=number, url=url)
    data["handoffs"] = handoffs(data["filed"], found, checkout)

    def human():
        for r in data["filed"]:
            comment = r["route"] == ROUTE_COMMENT
            if r["route"] == ROUTE_SKILL:
                print("%s %s" % ("would hand to" if args.dry_run else "handing to", r["skill"]))
            elif args.dry_run and comment:
                print(
                    "would comment on %s#%d: %s"
                    % (github.name, r["issue"]["number"], r["issue"]["title"])
                )
            elif args.dry_run:
                print(
                    "would file in %s: %s  [%s]"
                    % (github.name, r["title"], ", ".join(r["labels"]) or "no labels")
                )
            else:
                verb = "commented on" if comment else "filed"
                print("%s #%d %s" % (verb, r["number"], r["url"]))
            verb = "mark" if args.dry_run else "marked"
            if r["handled"] is None:
                print("  and %s %s with the new issue's number" % (verb, where(r)))
            else:
                print("  and %s %s as %s" % (verb, where(r), r["handled"]))
        for r in data["left"]:
            print("not filed: draft %d, %s, left in place" % (r["draft"], where(r)))
        for handoff in data["handoffs"]:
            print_handoff(handoff)

    return emit(args, "file", data, errors=errors, human=human)


def handoffs(finished, found, checkout):
    """One hand-off per skill, holding every finished TODO routed to it, in
    file and line order, with its passage, and the checkout the passages were
    read in, or None for this tree."""
    out = {}
    for row in sorted(finished, key=lambda r: (r["file"], r["first"])):
        if row["route"] != ROUTE_SKILL:
            continue
        passage = None
        if row["above"] is not None:
            passage = dict(found.files[row["file"]].found.passage(row["above"]), file=row["file"])
        todo = {"draft": row["draft"], "title": row["title"], "detail": row["detail"]}
        todo["passage"] = passage
        out.setdefault(row["skill"], []).append(todo)
    return [
        {"skill": skill, "checkout": checkout, "todos": items}
        for skill, items in sorted(out.items())
    ]


def print_handoff(handoff):
    print("\nhand-off to %s" % handoff["skill"])
    checkout = handoff["checkout"]
    if checkout is not None:
        branch = checkout["branch"]
        print("  read in %s%s" % (checkout["root"], ", on %s" % branch if branch else ""))
    for todo in handoff["todos"]:
        print("\ndraft %d" % todo["draft"])
        print("  title   %s" % todo["title"])
        if todo["detail"]:
            print_block("detail", todo["detail"])
        passage = todo["passage"]
        if passage is None:
            print("  passage (none: the TODO was at the end of its file)")
            continue
        span = where(passage)
        changed = ", ".join(str(n) for n in passage["changed"]) or "none"
        print("  passage %s, changed since the last commit: %s" % (span, changed))
        print_block("text", passage["text"])


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
    source = argparse.ArgumentParser(add_help=False)
    source.add_argument(
        "--from",
        dest="source",
        metavar="TREE",
        help=(
            "read the TODOs of another worktree of this repository instead, named by its"
            " folder or by the branch it has checked out"
        ),
    )

    p = sub.add_parser(
        "setup",
        parents=[common, dry_run],
        help="copy this script into %s/, which git ignores" % COPY_DIR,
    )
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser(
        "scan",
        parents=[common, source],
        help=(
            "list the TODOs in the changes since the last commit, the open issues like each,"
            " and the repository's labels"
        ),
    )
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser(
        "report",
        parents=[common, drafts, source],
        help="check the drafts against the files now, and print them with an approval token",
        epilog=DRAFTS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.set_defaults(func=cmd_report)

    p = sub.add_parser(
        "file",
        parents=[common, drafts, dry_run, source],
        help=(
            "file or post each draft report showed, mark its TODO handled, and print the"
            " hand-offs to skills"
        ),
        epilog=DRAFTS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--token", required=True, help="the approval token report printed")
    p.set_defaults(func=cmd_file)

    p = sub.add_parser(
        "questions",
        parents=[common, source],
        help="write the questions to %s, for the author to answer on a page" % QUESTIONS_FILE,
    )
    p.add_argument(
        "--batch",
        required=True,
        metavar="PATH",
        help=(
            "the questions as a JSON array, or %s for stdin; each has question, options"
            " (label, description) and todos (file, line, as scan gave file and first)" % STDIN_PATH
        ),
    )
    p.set_defaults(func=cmd_questions)

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

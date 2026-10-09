#!/usr/bin/env python3
"""Deterministic half of the prose-tuning skills.

The three skills in this plugin use the model only for what genuinely needs
judgment: inferring a rule from an edit, writing prose, deciding whether a
passage conforms. Everything else - parsing markup, selecting files, diffing,
resolving tags, reading the config - happens here, because the
first run of this workflow by hand produced five malformed tags that survived
until a parser existed, and a parser that was rewritten three times.

Usage:
    python3 prose.py <command> [options]
    python3 prose.py --help

Commands:
    preflight   refuse-to-run check for one skill
    scope       which files the prose rules govern
    segments    the prose-eligible spans of each file, one per line
    patterns    where each rule's pattern matches those spans
    pass        the rules, segments and patterns together, which apply-prose
                reads to start a pass
    evidence    explicit tags + inferred edits
    reproduce   whether the rules' patterns reproduce the edits since HEAD
    config      list | lint | check-id | classify | adopt | resolve | write |
                init | move
    tags        resolve
    report      the findings for approval, and which of them overlap, also
                written to .prose-tuning/report.md for the author to read
    apply       apply approved rewrites
    questions   write update-prose-config's interview to .prose-tuning/
                questions.md, for the author to answer on a page
    setup       which surface this is running on, local or cowork, and
                locally, copy this script into the project
    stage       copy this script and the shipped rules into Cowork's outputs

evidence and reproduce take --from with another worktree of the repository,
named by its folder or by the branch it has checked out, and read that
worktree's edits against this tree's prose-style.md. The rules are still
written here: Claude Code will not let a worktree session edit another
checkout's .claude/. --from naming this tree reads as no --from, so the skill
can pass on whichever checkout the author named. When this tree does not hold
any pending edit and another worktree does, evidence names each such worktree
and exits 1, so a session opened in a fresh worktree still finds the edits left
in the checkout where the author writes.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Where this runs. From a copy in the project at .prose-tuning/, on every
surface, beside the shipped rules and a .gitignore of `*` that keeps the whole
folder out of the project's commits. preflight refuses to run from a copy git
would commit. Each shell call a skill makes starts without the variables of
the last, in Claude Code as on Cowork's device, so every command names the
script again. From the project root, `PROSE=.prose-tuning/prose.py` is short
enough to repeat, and the plugin's own install path is not. In Claude Code,
`setup` makes the copy. In Cowork, `stage` does, and the copy runs on the
device side, because only the device can see the project; COWORK.md at the
root of the claude-plugins repo says what Cowork allows and why.

Where the rules live. A project keeps them in .claude/rules/prose-style.md,
with no paths: key. Claude Code and Cowork both load that folder into their
sessions, so every agent writing in the project has the rules, whether or not
a skill runs. COWORK.md, "How instruction files load", has what each product
loads and when. A copy at the project root is where they used to
live and nothing loads it: preflight refuses one, and `config move` copies it
across.

The shipped rules. `config init` starts a project's prose-style.md from
templates/prose-style.md in this plugin. The copy in the project has no plugin
around it, so a copy in a .prose-tuning/ folder reads the rules `setup` or
`stage` put beside it, and never looks for a templates/ folder in the project. The name
init writes into it is the main working tree's folder, not the checkout's: run
from a git worktree, the checkout's folder is a throwaway name
(Repo.project_name has how).

Some things in here look like bugs and are not:

1. Files are rewritten in place with open(path, "w") rather than written to a
   temp file and moved into position. The usual temp-file-then-os.replace dance
   unlinks the target, and this script has to run against a folder on the Cowork
   device bridge, which cannot unlink. Do not "fix" this.

2. Git is only ever read (rev-parse, ls-files, status, check-ignore, show,
   worktree list). Nothing here writes through git, so no .git/*.lock is
   ever created. The bridge strands those locks because it cannot delete
   them, which is the whole reason the projects this runs against carry a
   commit.sh. Another worktree that --from names is only read, with plain
   file reads and git show.

3. report prints an approval token, and apply refuses to run without the same
   one. The token is a hash of the findings, every document a finding names
   and prose-style.md, so a batch or a file that changed after the author
   approved the report is refused rather than written. Nothing records the
   token on disk: apply recomputes it, because a state file on the Cowork
   bridge could never be deleted. approval_token has what it covers.
   config write --dry-run prints a token in the same way, and config write
   refuses a batch or a prose-style.md that changed since; rules_token has
   what it covers.

4. apply and tags resolve can delete a blank line that nothing names. They do
   so when a whole block that sat between two blank lines is cut, by findings
   or by a block-form <del>, so that one blank line is left between its
   neighbors rather than two. plan_findings has the rule. Neutralizing a file
   for evidence takes only the blank line an author added beside a tag on a
   line of its own, by the narrower rule in apart_blanks.

5. questions writes .prose-tuning/questions.md, and report writes
   .prose-tuning/report.md, and neither takes --dry-run, because nothing
   reads a preview of either: the skill always wants the page, and the file
   is git-ignored scratch that the next run replaces. report writes its page
   because Claude Code shows a command's output to the model and not reliably
   to the author, who has to read what they approve. A report that fails
   writes its errors and no token, so a stale token never reaches the author.
   config write --dry-run writes .prose-tuning/rules.md for the same reason,
   and a dry run that would write no rule writes no token either. So a dry
   run writes a file, and only to .prose-tuning/.

Python 3.9 is the floor. No match statements, no X | Y unions.
"""

import argparse
import difflib
import hashlib
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys

ENVELOPE_VERSION = 3

# Opens each part of pass's output: the rules, the segments, the matches.
PASS_HEADING = "== %s =="

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

# How many hex digits of the token report prints for apply, and config
# write --dry-run for config write.
TOKEN_LENGTH = 16
TOKEN_LABEL = "approval token: "
TOKEN_STALE = (
    "the findings, a document they name or %s changed since report ran, "
    "apply was not given the files report was, "
    "or the token is not the one it printed; run report again and show it to the author"
)
RULES_TOKEN_STALE = (
    "the batch or %s changed since config write --dry-run ran, or the token is not "
    "the one it printed; run config write --dry-run again and show its page to the author"
)
RULES_TOKEN_MISSING = (
    "config write needs --token: run config write --dry-run, show the author the page it "
    "writes, and pass the token it prints"
)
# What a report token hashes before the files report was given.
TOKEN_CHECKED = b"checked files"
# What the rules token hashes first, so it can never equal a report token.
RULES_TOKEN_DOMAIN = b"config write"

CONFIG_NAME = "prose-style.md"
# Where a project keeps it. See "Where the rules live" above.
CONFIG_DIR = ".claude/rules"
CONFIG_PATH = CONFIG_DIR + "/" + CONFIG_NAME
# Where it lived before, which preflight refuses and config move leaves behind.
LEGACY_CONFIG_PATH = CONFIG_NAME
# The front matter key that scopes a rule file to matching paths, so that it
# no longer loads in every session. lint rejects it.
PATHS_KEY = "paths"

# The copy in the project. See "Where this runs" above.
SCRIPT_PATH = os.path.abspath(__file__)
OUTPUTS_ROOT = "/mnt/user-data/outputs"
DEFAULT_STAGE = OUTPUTS_ROOT + "/prose-tuning"
COPY_DIR = ".prose-tuning"
COPY_SCRIPT = COPY_DIR + "/prose.py"
# What a command starts with to reach the copy, from the project root.
COPY_PREFIX = "PROSE=" + COPY_SCRIPT
COPY_TEMPLATE = COPY_DIR + "/prose-style.template.md"
# The rules a new prose-style.md starts from, relative to the plugin root, and
# the placeholder in them that init fills with the project's name.
SHIPPED_TEMPLATE = "templates/" + CONFIG_NAME
PROJECT_NAME_SLOT = "{{PROJECT_NAME}}"
# What a repository's git directory is called, which init strips to name it.
GIT_DIR_NAME = ".git"
# Ignores the folder it sits in, itself included, so the project's .gitignore
# never has to know this plugin exists.
COPY_IGNORE = COPY_DIR + "/.gitignore"
COPY_IGNORE_TEXT = b"*\n"
# Where questions writes the interview, for the author to answer on a page,
# where report writes the findings and config write --dry-run the rules, for
# the author to read whole, and the info string of the fence that holds a
# piece of evidence or a finding's text, and of the one that holds a rule.
QUESTIONS_FILE = COPY_DIR + "/questions.md"
REPORT_FILE = COPY_DIR + "/report.md"
RULES_FILE = COPY_DIR + "/rules.md"
PAGE_FENCE_INFO = "text"
RULES_FENCE_INFO = "markdown"
DEVICE_MOUNT_ROOT = "$HOME/mnt"

# What evidence, reproduce and restore compare the working tree against.
BASE_REF = "HEAD"

# The lines of `git worktree list --porcelain` that Repo.worktrees reads.
WORKTREE_LINE = "worktree "
BRANCH_LINE = "branch "
BRANCH_REF_PREFIX = "refs/heads/"
BARE_LINE = "bare"
# The command evidence names when another worktree holds the pending edits.
FROM_COMMAND = "evidence --from %s"

DEFAULT_INCLUDE = ["**/*.md"]
DEFAULT_EXCLUDE = [
    ".claude/**",
    "CLAUDE.md",
    "**/README.md",
    "skills/**",
]


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def envelope(command, repo, data, errors=None, warnings=None):
    errors = errors or []
    return {
        "version": ENVELOPE_VERSION,
        "command": command,
        "repo": repo,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings or [],
        "data": data,
    }


def emit(args, command, repo, data, errors=None, warnings=None, human=None):
    """Print JSON or human output, and return the exit code."""
    errors = errors or []
    warnings = warnings or []
    if getattr(args, "json", False):
        print(json.dumps(envelope(command, repo, data, errors, warnings), indent=2, sort_keys=True))
    else:
        if human:
            human()
        for w in warnings:
            sys.stderr.write("warning: %s\n" % w)
        for e in errors:
            sys.stderr.write("%s\n" % e)
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# glob matching
#
# fnmatch does not understand "**", and PurePath.match anchors from the right.
# Both would silently mis-scope, so the translation is spelled out here.
# --------------------------------------------------------------------------


def glob_to_regex(pattern):
    out, i, n = ["(?s:"], 0, len(pattern)
    while i < n:
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append(")\\Z")
    return re.compile("".join(out))


class Matcher:
    def __init__(self, patterns):
        self.patterns = list(patterns)
        self.regexes = [glob_to_regex(p) for p in self.patterns]

    def match(self, relpath):
        """Return the pattern that matched, or None."""
        for pat, rx in zip(self.patterns, self.regexes):
            if rx.match(relpath):
                return pat
        return None


# --------------------------------------------------------------------------
# text and edits
# --------------------------------------------------------------------------


class Text:
    """A file's text, addressable by 1-indexed line and 0-indexed column.

    Lines keep their endings, so join(lines) == original text, including a
    missing final newline.

    A line ends at "\n" and nowhere else. str.splitlines() would be the obvious
    way to cut them and is wrong here: it also breaks on \v, \f, \x1c, \x1d,
    \x1e, U+0085, U+2028 and U+2029, none of which git, an editor or markdown
    treats as a line break. A document carrying one of those - they arrive in
    text pasted from other tools - would be numbered differently by this script
    than by everything the author can see, and a report saying landscape.md:42
    would send them to the wrong passage.
    """

    def __init__(self, s):
        self.s = s
        parts = s.split("\n")
        self.lines = [p + "\n" for p in parts[:-1]]
        if parts[-1]:
            self.lines.append(parts[-1])
        self.starts = []
        off = 0
        for ln in self.lines:
            self.starts.append(off)
            off += len(ln)
        self.end = off

    @classmethod
    def read(cls, path):
        with open(path, encoding="utf-8", newline="") as fh:
            return cls(fh.read())

    def write(self, path):
        # In place, on purpose. See the module docstring.
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(self.s)

    def line_count(self):
        return len(self.lines)

    def line(self, n):
        """1-indexed, with its ending."""
        return self.lines[n - 1]

    def bare(self, n):
        """1-indexed, without its ending."""
        raw = self.lines[n - 1]
        if raw.endswith("\r\n"):
            return raw[:-2]
        return raw[:-1] if raw.endswith("\n") else raw

    def offset(self, line, col=0):
        if line < 1 or line > len(self.lines):
            raise Fatal("line %d out of range (file has %d lines)" % (line, len(self.lines)))
        return self.starts[line - 1] + col

    def line_of(self, offset):
        """1-indexed line containing an absolute offset."""
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1


class EditEngine:
    """Absolute-offset replacements, applied bottom-up from one snapshot.

    Bottom-up from a single snapshot is the only correct order: every edit
    shifts the offsets of everything after it, so a top-down pass would leave
    every later edit pointing at the wrong place. This is why apply takes a
    batch of findings rather than being called once per finding.
    """

    def __init__(self, text):
        self.text = text
        self.edits = []

    def replace(self, start, end, replacement, label=None):
        if start > end:
            raise Fatal("edit start %d after end %d" % (start, end))
        self.edits.append((start, end, replacement, label))

    def conflicts(self):
        """Every pair of edits whose result would depend on the order they were
        added in, as (edit, edit) with the earlier-starting one first.

        Sorted by (start, end), a zero-width point comes immediately before any
        span starting at the same offset, and the scan from each edit stops at
        the first one starting past its end, since every later one starts
        further on still. That finds every pair, not only neighbors, so a
        report can name each finding a long cut swallows.

        The second clause - two edits beginning at the same offset - is where
        everything that shares a boundary lands. Such a pair overlaps by no
        definition, so the first clause passes it, and then the answer depends
        on the order the edits happened to arrive in. A finding that inserts
        at the offset another finding's rewrite starts from is one: the splice
        discards whichever went first.

        There is no order this class can be resolved in that is right, so it
        is refused, and report names the pair for the author to choose between
        rather than writing a mangled file half the time.
        """
        out = []
        ordered = sorted(self.edits, key=lambda e: (e[0], e[1]))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                if b[0] >= a[1] and b[0] > a[0]:
                    break
                out.append((a, b))
        return out

    @staticmethod
    def describe(edit):
        """An edit's label, or its offsets when it was given none."""
        start, end, _, label = edit
        if label is None:
            return "the edit at offsets %d-%d" % (start, end)
        return str(label)

    def result(self):
        bad = self.conflicts()
        if bad:
            raise Fatal(
                "; ".join("%s overlaps %s" % (self.describe(a), self.describe(b)) for a, b in bad)
            )
        s = self.text.s
        for start, end, replacement, _ in sorted(self.edits, key=lambda e: e[0], reverse=True):
            s = s[:start] + replacement + s[end:]
        return s


# --------------------------------------------------------------------------
# git, read-only
# --------------------------------------------------------------------------


class Repo:
    def __init__(self, start=None):
        start = os.path.abspath(start or os.getcwd())
        if not os.path.isdir(start):
            start = os.path.dirname(start)
        try:
            out = subprocess.run(
                ["git", "-C", start, "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise Fatal("git is not installed, or not on PATH") from exc
        if out.returncode != 0:
            raise Fatal("%s is not inside a git repository" % start)
        self.root = out.stdout.strip()

    def git(self, *args):
        out = subprocess.run(
            ["git", "-C", self.root, *args], capture_output=True, text=True, check=False
        )
        return out.returncode, out.stdout, out.stderr

    def project_name(self):
        """The folder name of the main working tree, the same from any worktree.

        In a linked worktree, --show-toplevel is the worktree's own folder, a
        throwaway name. --git-common-dir is shared by every worktree: the main
        tree's .git, or a bare repository whose name drops its .git suffix.
        Falls back to the toplevel's name when git does not answer.
        """
        code, stdout, _ = self.git("rev-parse", "--git-common-dir")
        if code != 0 or not stdout.strip():
            return os.path.basename(self.root)
        common = os.path.normpath(os.path.join(self.root, stdout.strip()))
        name = os.path.basename(common)
        if name == GIT_DIR_NAME:
            return os.path.basename(os.path.dirname(common))
        if name.endswith(GIT_DIR_NAME):
            return name[: -len(GIT_DIR_NAME)]
        return name

    def _lines(self, *args):
        code, stdout, stderr = self.git(*args)
        if code != 0:
            raise Fatal("git %s failed: %s" % (" ".join(args), stderr.strip()))
        return [x for x in stdout.split("\n") if x]

    def tracked_md(self):
        return self._lines("ls-files", "--", "*.md")

    def untracked_md(self):
        return self._lines("ls-files", "--others", "--exclude-standard", "--", "*.md")

    def all_md(self):
        seen, out = set(), []
        for p in sorted(self.tracked_md() + self.untracked_md()):
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def show(self, ref, relpath):
        """File content at a ref, or None when it is not there."""
        code, stdout, _ = self.git("show", "%s:%s" % (ref, relpath))
        return stdout if code == 0 else None

    def dirty(self):
        """[(status, relpath)] for everything git reports as changed."""
        code, stdout, stderr = self.git("status", "--porcelain")
        if code != 0:
            raise Fatal("git status failed: %s" % stderr.strip())
        out = []
        for line in stdout.split("\n"):
            if not line.strip():
                continue
            status, path = line[:2].strip() or "?", line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            out.append((status, path.strip('"')))
        return out

    def dirty_md(self):
        return [(s, p) for s, p in self.dirty() if p.endswith(".md")]

    def pending(self):
        """Every path with an uncommitted change, each untracked file named.

        status names an untracked folder rather than the files in it, so the
        untracked markdown comes from ls-files instead.
        """
        return set(p for _, p in self.dirty()) | set(self.untracked_md())

    def trees(self):
        """[(root, branch)] for every worktree of this repository, this one too.

        branch is None for a detached HEAD. A bare repository has no tree,
        and a worktree whose folder is gone has nothing to read, so neither
        is listed.
        """
        trees = []
        for line in self._lines("worktree", "list", "--porcelain"):
            if line.startswith(WORKTREE_LINE):
                trees.append({"root": line[len(WORKTREE_LINE) :], "branch": None, "bare": False})
            elif trees and line.startswith(BRANCH_LINE):
                branch = line[len(BRANCH_LINE) :]
                if branch.startswith(BRANCH_REF_PREFIX):
                    branch = branch[len(BRANCH_REF_PREFIX) :]
                trees[-1]["branch"] = branch
            elif trees and line == BARE_LINE:
                trees[-1]["bare"] = True
        return [
            (t["root"], t["branch"]) for t in trees if not t["bare"] and os.path.isdir(t["root"])
        ]

    def worktrees(self):
        """[(root, branch)] for every other worktree of this repository."""
        here = os.path.realpath(self.root)
        return [(root, branch) for root, branch in self.trees() if os.path.realpath(root) != here]

    def abspath(self, relpath):
        return os.path.join(self.root, relpath)


# --------------------------------------------------------------------------
# prose-style.md
# --------------------------------------------------------------------------

RULE_HEADING = re.compile(r"^###\s+([a-z][a-z0-9]*)-(\S+?)\s*:\s*(.+?)\s*$")
SECTION = re.compile(r"^[a-z][a-z0-9]*$")
RULE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*$")
POSITIONAL = re.compile(r"^\d+$")
MAX_NAME_WORDS = 4
# The score at or above which two rules are worth the author's look.
SIMILAR_THRESHOLD = 0.6
# adopt-prose's buckets, in the order it acts on them.
BUCKET_NEW = "new"
BUCKET_IDENTICAL = "identical"
BUCKET_COLLIDING = "colliding"
BUCKET_SIMILAR = "similar"
BUCKETS = (BUCKET_NEW, BUCKET_IDENTICAL, BUCKET_COLLIDING, BUCKET_SIMILAR)
ANY_H3 = re.compile(r"^###\s+(.*)$")
ANY_H2 = re.compile(r"^##\s+(.+?)\s*$")
META_COMMENT = re.compile(r"^<!--\s*prose-rule\s*:\s*(.*?)\s*-->\s*$")
BEFORE_LINE = re.compile(r"^>\s*\*\*Before\.\*\*\s*(.*?)\s*$")
AFTER_LINE = re.compile(r"^>\s*\*\*After\.\*\*\s*(.*?)\s*$")
# A pattern a rule's breaches can be found by, as one code span after the lead
# word. The backtick run is matched by length, so a pattern holding a backtick
# is fenced in two.
PATTERN_LINE = re.compile(r"^\*\*Pattern\.\*\*(.*)$")
PATTERN_SPAN = re.compile(r"^\s+(`+)(.+?)\1\s*$")
# A flag group such as (?i) anywhere but the start of a pattern. Python 3.11
# refuses one; 3.9 accepts it with a warning, so lint refuses it on both.
LATE_FLAGS = re.compile(r"(?<!\\)\(\?[aiLmsux]+\)")
FM_KEY = re.compile(r"^([a-z][a-z0-9_-]*)\s*:\s*(.*?)\s*$")
FM_SUBKEY = re.compile(r"^ {2}(include|exclude)\s*:\s*$")
FM_ITEM = re.compile(r"^ {4}-\s+(.+?)\s*$")

# Nothing writes a prose-rule comment any more: where a rule came from goes in
# the commit that brings it in. Files written by earlier versions carry these
# keys, so lint accepts them with any value.
META_KEYS = {"source", "origin"}
# The line config adopt gives the author for the commit description.
ADOPTED_NOTE = "Adopted from %s: %s"


def validate_rule_name(name):
    """The part of an id after the section. Returns a message, or None.

    One message per shape of mistake. A checker that says two things about
    one typo teaches the author to skim its output.
    """
    if POSITIONAL.match(name):
        return (
            "rule id is positional; expected "
            "'### <section>-<name>: <Title>', where the name is one to "
            "%d words saying what the rule means" % MAX_NAME_WORDS
        )
    words = name.split("-")
    if any(w[:1].isdigit() for w in words):
        return (
            "rule name %r carries a number; a name says what a rule "
            "means, not where it was written" % name
        )
    if not RULE_NAME.match(name):
        return "rule name %r is not lower-case words joined by '-'" % name
    if len(words) > MAX_NAME_WORDS:
        return (
            "rule name %r has %d words; at most %d. A name that needs "
            "more is a rule that has not been decided yet" % (name, len(words), MAX_NAME_WORDS)
        )
    return None


def rule_similarity(a, b):
    """(body, name, score) for two rules, each 0..1.

    Deliberately crude, and returned in parts so a test can see which half
    fired. A rule can be restated in different words under the same
    name, or say the same thing under a different one, and either is worth
    a look - so the score is the higher of the two rather than a blend that
    hides both. The corpus is a few dozen rules, so the quadratic is free.
    """
    body = difflib.SequenceMatcher(None, a.body_key(), b.body_key()).ratio()
    at, bt = set(a.name.split("-")), set(b.name.split("-"))
    name = len(at & bt) / float(len(at | bt)) if (at | bt) else 0.0
    return body, name, max(body, name)


def similar_pairs(config, other):
    """The pairs of rules across two files scoring at or above
    SIMILAR_THRESHOLD.

    A shared id is adopt-prose's identical or colliding bucket, so a pair
    under one id is left out. These are the pairs that agree in substance
    under two different names, which nothing else can see. Highest first.
    """
    pairs = []
    for a in config.rules:
        for b in other.rules:
            if a.id == b.id:
                continue
            score = rule_similarity(a, b)[2]
            if score >= SIMILAR_THRESHOLD:
                pairs.append((round(score, 2), a.id, b.id))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
    return [{"source": src, "target": tgt} for _, src, tgt in pairs]


def classify_rules(config, other):
    """One entry per rule in config, in its order: the bucket it falls in
    when adopted into other, and the rule of other it matched, each with its
    body, so adopt-prose's step 3 can show the author both in full.

    An id match settles a rule before any score is read. A rule the target
    already names is a question about that rule, and the similar bucket is
    for rules the target would otherwise take as new. Of two target rules
    sharing an id, the first counts; `config lint` fails the second.
    """
    by_id = {}
    for r in other.rules:
        by_id.setdefault(r.id, r)
    pairs = similar_pairs(config, other)
    out = []
    for a in config.rules:
        match = by_id.get(a.id)
        candidates = []
        if match is not None:
            same = a.body_key() == match.body_key()
            bucket = BUCKET_IDENTICAL if same else BUCKET_COLLIDING
            target = match.id
        else:
            candidates = [
                {"target": p["target"], "target_body": by_id[p["target"]].body_text()}
                for p in pairs
                if p["source"] == a.id
            ]
            bucket = BUCKET_SIMILAR if candidates else BUCKET_NEW
            target = candidates[0]["target"] if candidates else None
        out.append(
            {
                "id": a.id,
                "bucket": bucket,
                "body": a.body_text(),
                "target": target,
                "target_body": by_id[target].body_text() if target else None,
                "candidates": candidates,
            }
        )
    return out


def parse_pattern(rest):
    """(the regex a **Pattern.** line holds, None), or (None, a message).

    rest is the line after the lead word. CommonMark strips one space from
    each end of a code span that has one at both, so a pattern that starts or
    ends with a backtick can be written `` `x` ``; this does the same. Like
    CommonMark, it leaves a span of nothing but spaces whole, and a tab counts
    as something other than a space.
    """
    m = PATTERN_SPAN.match(rest)
    if not m:
        return None, "a **Pattern.** line holds one code span and nothing else"
    source = m.group(2)
    if len(source) > 2 and source[0] == " " and source[-1] == " " and source.strip(" "):
        source = source[1:-1]
    late = LATE_FLAGS.search(source, 1)
    if late:
        return None, "pattern %r sets the flag %s part way along; put it first" % (
            source,
            late.group(0),
        )
    try:
        rx = re.compile(source)
    except re.error as exc:
        return None, "pattern %r does not compile: %s" % (source, exc)
    if rx.match(""):
        return None, "pattern %r matches an empty string, so it would match everywhere" % source
    return source, None


def unquote(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


class Rule:
    def __init__(self, rid, section, name, title, line):
        self.id = rid
        self.section = section
        self.name = name
        self.title = title
        self.line = line
        self.group = ""
        self.meta = {}
        self.body = []
        self.before = None
        self.after = None
        # (line, regex source) for each **Pattern.** line that parses, and
        # whether any did not.
        self.patterns = []
        self.bad_pattern = False

    def body_text(self):
        return "\n".join(self.body).strip()

    def body_key(self):
        """The body normalized for comparison, for adopt-prose.

        HTML comments go: a FILL marker tells one project what to supply and is
        not part of the rule, so two rules differing only by one are the same
        rule. Whitespace collapses, because a rewrap is not an edit.
        """
        stripped = re.sub(r"<!--.*?-->", " ", self.body_text(), flags=re.S)
        return " ".join(stripped.split())

    def as_dict(self):
        return {
            "id": self.id,
            "section": self.section,
            "name": self.name,
            "title": self.title,
            "line": self.line,
            "group": self.group,
            "meta": self.meta,
            "body": self.body_text(),
            "body_key": self.body_key(),
            "example": (
                None
                if self.before is None and self.after is None
                else {"before": self.before, "after": self.after}
            ),
            "patterns": [source for _line, source in self.patterns],
        }


class Config:
    """prose-style.md: restricted front matter plus one H3 per rule.

    The front-matter grammar is deliberately small rather than accidentally
    small. Stdlib only means no PyYAML, so anything richer would be parsed by
    guesswork. lint rejects out-of-grammar keys loudly, because a silently
    dropped key is a scope override that looks like it works.
    """

    def __init__(self, path, shown=None, text=None):
        """text, when given, is parsed in place of the file at path, so that
        config write can lint what it would write before writing it.
        """
        self.path = path
        # How messages name the file: its repo-relative path when there is one.
        self.shown = shown or os.path.basename(path)
        self.front = {}
        self.scope_include = []
        self.scope_exclude = []
        self.rules = []
        self.errors = []
        self.warnings = []
        self.exists = text is not None or os.path.exists(path)
        if self.exists:
            self._parse(Text(text) if text is not None else Text.read(path))

    def rel(self):
        return self.shown

    def _err(self, line, msg):
        self.errors.append("%s:%d  %s" % (self.rel(), line, msg))

    def _warn(self, line, msg):
        self.warnings.append("%s:%d  %s" % (self.rel(), line, msg))

    def _parse(self, text):
        lines = [ln.rstrip("\n").rstrip("\r") for ln in text.lines]
        body_start = self._parse_front(lines)
        self._parse_rules(lines, body_start)
        self._check()

    def _parse_front(self, lines):
        if not lines or lines[0].strip() != "---":
            self.errors.append(
                "%s:1  no front matter; the file must open with a --- fence" % self.rel()
            )
            return 0
        close = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                close = i
                break
        if close is None:
            self.errors.append("%s:1  front matter is never closed" % self.rel())
            return 0

        target = None  # None at top level, else the list being filled
        in_scope = False
        for i in range(1, close):
            raw, num = lines[i], i + 1
            if not raw.strip():
                continue
            sub = FM_SUBKEY.match(raw)
            if sub:
                if not in_scope:
                    self._err(num, "%s: is only valid inside scope:" % sub.group(1))
                    continue
                target = self.scope_include if sub.group(1) == "include" else self.scope_exclude
                continue
            item = FM_ITEM.match(raw)
            if item:
                if target is None:
                    self._err(num, "list item outside include: or exclude:")
                    continue
                target.append(unquote(item.group(1)))
                continue
            if raw[0] in " \t":
                self._err(num, "indented line is not a scope key or list item: %r" % raw)
                continue
            key = FM_KEY.match(raw)
            if not key:
                self._err(num, "not a key: value pair: %r" % raw)
                continue
            name, value = key.group(1), key.group(2)
            if name == "scope":
                if value:
                    self._err(num, "scope: takes no value; put include: and exclude: beneath it")
                in_scope, target = True, None
                continue
            in_scope, target = False, None
            if name == PATHS_KEY:
                self._err(
                    num,
                    "%s: would stop these rules loading in every session; remove it" % PATHS_KEY,
                )
                continue
            self.front[name] = unquote(value)
        return close + 1

    def _parse_rules(self, lines, start):
        group, current = "", None
        for i in range(start, len(lines)):
            raw, num = lines[i], i + 1
            h2 = ANY_H2.match(raw)
            if h2:
                current, group = None, h2.group(1)
                continue
            h3 = ANY_H3.match(raw)
            if h3:
                m = RULE_HEADING.match(raw)
                if not m:
                    current = None
                    self._err(
                        num, "rule heading carries no id; expected '### <section>-<name>: <Title>'"
                    )
                    continue
                current = Rule(
                    ("%s-%s" % (m.group(1), m.group(2))), m.group(1), m.group(2), m.group(3), num
                )
                current.group = group
                self.rules.append(current)
                continue
            if current is None:
                continue
            meta = META_COMMENT.match(raw.strip())
            if meta:
                for pair in meta.group(1).split():
                    if "=" not in pair:
                        self._err(num, "metadata %r is not key=value" % pair)
                        continue
                    k, v = pair.split("=", 1)
                    current.meta[k] = v
                continue
            pattern = PATTERN_LINE.match(raw)
            if pattern:
                source, problem = parse_pattern(pattern.group(1))
                if problem:
                    self._err(num, problem)
                    current.bad_pattern = True
                else:
                    current.patterns.append((num, source))
            before, after = BEFORE_LINE.match(raw), AFTER_LINE.match(raw)
            if before:
                current.before = before.group(1)
            elif after:
                current.after = after.group(1)
            current.body.append(raw)

    def _check(self):
        seen = {}
        for rule in self.rules:
            if rule.id in seen:
                self._err(
                    rule.line,
                    "duplicate rule id %s; first defined at line %d" % (rule.id, seen[rule.id]),
                )
            else:
                seen[rule.id] = rule.line
            bad = validate_rule_name(rule.name)
            if bad:
                self._err(rule.line, bad)
            elif rule.name.split("-")[0] == rule.section:
                self._warn(
                    rule.line,
                    "rule name %s opens with its own "
                    "section; the id already says %s" % (rule.name, rule.section),
                )
            for k in rule.meta:
                if k not in META_KEYS:
                    self._err(
                        rule.line,
                        "unknown metadata key %r; allowed: %s" % (k, ", ".join(sorted(META_KEYS))),
                    )
            self._check_patterns(rule)
            if not rule.body_text():
                self._err(rule.line, "rule %s has no body" % rule.id)
            if rule.before is None and rule.after is None:
                self._warn(
                    rule.line,
                    "rule %s has no worked example; a rule "
                    "with no example does not survive contact" % rule.id,
                )
            elif rule.before is None or rule.after is None:
                self._err(
                    rule.line,
                    "rule %s has half an example; Before and After come as a pair" % rule.id,
                )
        if self.exists and "name" not in self.front:
            self._warn(1, "front matter has no name:")

    def _check_patterns(self, rule):
        """A rule's patterns against its own worked example.

        The example is the rule's evidence, so a pattern that misses the
        Before text finds nothing the rule was written for, and one that
        matches the After text flags the prose the rule holds up as right.
        Skipped when the rule has no whole example, or when one of its
        pattern lines did not parse, since the set is then incomplete and
        that line already has its error.
        """
        if not rule.patterns or rule.bad_pattern or rule.before is None or rule.after is None:
            return
        compiled = [(line, source, re.compile(source)) for line, source in rule.patterns]
        if not any(m.group(0) for _l, _s, rx in compiled for m in rx.finditer(rule.before)):
            self._err(
                rule.patterns[0][0],
                "no pattern of %s finds anything in its Before example" % rule.id,
            )
        for line, source, rx in compiled:
            if any(m.group(0) for m in rx.finditer(rule.after)):
                self._err(line, "pattern %r matches the After example of %s" % (source, rule.id))

    def check_id(self, section, name):
        """(id, message or None). Grammar first, then whether it is taken.

        There is no allocator to replace this, because there is nothing to
        allocate: the author names the rule and the script rules on the
        name. Catching a collision before the file is edited is the whole
        job - lint catches one afterwards either way.
        """
        rid = "%s-%s" % (section, name)
        if not SECTION.match(section):
            return rid, ("section %r is not a lower-case word" % section)
        bad = validate_rule_name(name)
        if bad:
            return rid, bad
        taken = self.by_id().get(rid)
        if taken:
            return rid, (
                "%s is already the id of the rule at %s:%d - %s"
                % (rid, self.rel(), taken.line, taken.title)
            )
        return rid, None

    def by_id(self):
        return dict((r.id, r) for r in self.rules)

    def patterned(self):
        """The rules that carry a pattern, in file order."""
        return [r for r in self.rules if r.patterns]


def config_path(repo, override=None):
    if override:
        return os.path.abspath(override)
    return os.path.join(repo.root, *CONFIG_PATH.split("/"))


def legacy_config_path(repo):
    return os.path.join(repo.root, LEGACY_CONFIG_PATH)


# --------------------------------------------------------------------------
# which files the rules govern
# --------------------------------------------------------------------------


class Scope:
    """File selection, with the config's scope: block overriding the defaults.

    include/exclude replace the defaults wholesale when present. Partial
    override was considered and rejected: "which of the four defaults am I
    still getting" is not a question anyone should answer by reading a script.

    prose-style.md is excluded unconditionally, override or not, and so is a
    copy left at the root until the author deletes it. apply-prose rewriting
    its own rulebook is not a thing anyone wants to debug.
    """

    def __init__(self, repo, config, config_rel=None):
        self.repo = repo
        self.config = config
        self.include = config.scope_include or list(DEFAULT_INCLUDE)
        self.exclude = config.scope_exclude or list(DEFAULT_EXCLUDE)
        self.overridden = bool(config.scope_include or config.scope_exclude)
        self._inc = Matcher(self.include)
        self._exc = Matcher(self.exclude)
        self._config_rel = config_rel or (
            os.path.relpath(config.path, repo.root) if config.path.startswith(repo.root) else None
        )

    def verdicts(self):
        out = []
        for rel in self.repo.all_md():
            if self._config_rel and rel == self._config_rel:
                out.append({"path": rel, "included": False, "reason": "the config itself"})
                continue
            if rel == LEGACY_CONFIG_PATH:
                out.append({"path": rel, "included": False, "reason": "the config's old place"})
                continue
            hit = self._inc.match(rel)
            if not hit:
                out.append({"path": rel, "included": False, "reason": "no include pattern matched"})
                continue
            bad = self._exc.match(rel)
            if bad:
                out.append({"path": rel, "included": False, "reason": "excluded by %s" % bad})
                continue
            out.append({"path": rel, "included": True, "reason": "included by %s" % hit})
        return out

    def files(self):
        return [v["path"] for v in self.verdicts() if v["included"]]


# --------------------------------------------------------------------------
# markdown block structure
# --------------------------------------------------------------------------

FENCE_OPEN = re.compile(r"^(\s{0,3})(`{3,}|~{3,})\s*(\S*)")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
LIST_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+")
BLOCKQUOTE = re.compile(r"^\s{0,3}>")
TABLE_DELIM = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(?:\|\s*:?-{1,}:?\s*)*\|?\s*$")
COMMENT_OPEN = "<!--"
COMMENT_CLOSE = "-->"
COMMENT_BLOCK = re.compile(r"^\s{0,3}" + re.escape(COMMENT_OPEN))

# An indented code block is indented this many columns past its container.
CODE_INDENT = 4
# The kinds after which an indented line is code rather than more of a
# paragraph.
CODE_FOLLOWS = ("blank", "heading", "fence", "frontmatter", "comment", "html-block", "code-block")

# CommonMark's HTML blocks other than comments, which COMMENT_BLOCK handles.
# Each start pattern pairs with the pattern that ends the block on the line
# holding it, or None for a block that ends at a blank line.
HTML_RAW_TAGS = ("pre", "script", "style", "textarea")
HTML_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|"
    "details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|"
    "h1|h2|h3|h4|h5|h6|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|"
    "noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|"
    "thead|title|tr|track|ul"
)
HTML_STARTS = (
    (
        re.compile(r"^\s{0,3}<(?:%s)(?:\s|>|$)" % "|".join(HTML_RAW_TAGS), re.I),
        re.compile(r"</(?:%s)>" % "|".join(HTML_RAW_TAGS), re.I),
    ),
    (re.compile(r"^\s{0,3}<\?"), re.compile(re.escape("?>"))),
    (re.compile(r"^\s{0,3}<![A-Za-z]"), re.compile(">")),
    (re.compile(r"^\s{0,3}<!\[CDATA\["), re.compile(re.escape("]]>"))),
    (re.compile(r"^\s{0,3}</?(?:%s)(?:\s|/?>|$)" % HTML_BLOCK_TAGS, re.I), None),
)
# A whole line of one open or closing tag, which opens an HTML block only
# where it does not interrupt a paragraph.
HTML_LONE_TAG = re.compile(
    r"""^\s{0,3}(?:<([A-Za-z][A-Za-z0-9-]*)"""
    r"""(?:\s+[A-Za-z_:][\w.:-]*(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?)*\s*/?>"""
    r"""|</([A-Za-z][A-Za-z0-9-]*)\s*>)\s*$"""
)

# Kinds that prose rules must never be applied inside. An HTML comment is a
# note for people - a FILL marker in the shipped rules is one - and not
# the document's prose. Code and HTML blocks are what a preview shows as
# code and as raw HTML.
PROTECTED_KINDS = {"frontmatter", "fence", "blockquote", "comment", "code-block", "html-block"}
# The protected kinds whose text the tag scanner skips as well.
SHIELDED_KINDS = ("frontmatter", "fence", "code-block", "html-block")

# Kinds whose text can carry an inline comment, `prose <!-- note --> prose`.
INLINE_COMMENT_KINDS = ("heading", "paragraph", "list-item", "table")


class Blocks:
    """Per-line classification of one markdown file.

    segments uses this so apply-prose is handed only the spans it may rewrite.
    Telling a model "do not touch code fences" is a rule that gets broken;
    never showing it the fence makes the mistake unavailable.

    HTML comments follow CommonMark. A line that opens with `<!--` starts a
    block that runs through the line holding the next `-->`, or to the end of
    the file, and every line of it is a "comment", text after the `-->`
    included. A `<!--` further along a line of prose is inline: it closes at
    the next `-->` in the same paragraph, or it is literal text. The lines
    wholly inside it are "comment"; a line only partly inside keeps its kind,
    and segments hands out the prose either side. self.comments holds every
    comment's absolute (start, end), so apply can refuse a column range that
    touches one.

    A paragraph line can belong to a list item without being its first line.
    self.items holds, for each line, the (line, content column) of the list
    item it belongs to, or None. _items says how a line is placed.

    An indented code block and an HTML block follow CommonMark too, and
    _items and _html_block say how each is found. A line holding only one of
    the markup's own tags, such as `<del>`, is the author's markup and opens
    no HTML block.
    """

    def __init__(self, text):
        self.text = text
        n = text.line_count()
        self.kinds = ["paragraph"] * n
        self.info = [""] * n
        self.headings = []
        self.comments = []
        self._classify()
        # Finding an indented code block needs each line's list item, and
        # the inline comments need the code blocks found first.
        self._items(find_code=True)
        self._inline_comments()
        self.items = self._items()

    def _classify(self):
        lines = [self.text.bare(i + 1) for i in range(self.text.line_count())]
        n = len(lines)
        i = 0

        if n and lines[0].strip() == "---":
            for j in range(1, n):
                if lines[j].strip() == "---":
                    for k in range(0, j + 1):
                        self.kinds[k] = "frontmatter"
                    i = j + 1
                    break

        while i < n:
            line = lines[i]
            if not line.strip():
                self.kinds[i] = "blank"
                i += 1
                continue

            fence = FENCE_OPEN.match(line)
            if fence:
                marker, info = fence.group(2), fence.group(3)
                char, width = marker[0], len(marker)
                self.kinds[i] = "fence"
                self.info[i] = info
                j = i + 1
                while j < n:
                    self.kinds[j] = "fence"
                    self.info[j] = info
                    close = re.match(r"^\s{0,3}(%s{%d,})\s*$" % (re.escape(char), width), lines[j])
                    if close:
                        break
                    j += 1
                i = j + 1
                continue

            # Before headings and tables, so a `#` or `|` inside a comment is
            # never taken for one.
            if COMMENT_BLOCK.match(line):
                opened = line.index(COMMENT_OPEN) + len(COMMENT_OPEN)
                j = i
                while j < n and COMMENT_CLOSE not in lines[j][opened if j == i else 0 :]:
                    j += 1
                j = min(j, n - 1)
                for k in range(i, j + 1):
                    self.kinds[k] = "comment"
                end = self.text.offset(j + 2) if j + 1 < n else self.text.end
                self.comments.append((self.text.offset(i + 1), end))
                i = j + 1
                continue

            end = self._html_block(lines, i)
            if end is not None:
                for k in range(i, end + 1):
                    self.kinds[k] = "html-block"
                i = end + 1
                continue

            head = HEADING_RE.match(line)
            if head:
                self.kinds[i] = "heading"
                self.headings.append((i + 1, len(head.group(1)), head.group(2)))
                i += 1
                continue

            if BLOCKQUOTE.match(line):
                self.kinds[i] = "blockquote"
                i += 1
                continue

            if (
                "|" in line
                and i + 1 < n
                and TABLE_DELIM.match(lines[i + 1])
                and "|" in lines[i + 1]
            ):
                j = i
                while j < n and "|" in lines[j] and lines[j].strip():
                    self.kinds[j] = "table"
                    j += 1
                i = j
                continue

            if LIST_ITEM.match(line):
                self.kinds[i] = "list-item"
                i += 1
                continue

            self.kinds[i] = "paragraph"
            i += 1

    def _items(self, find_code=False):
        """The list item each line belongs to, as (line, content column) or None.

        A list item's line belongs to that item. A paragraph line straight
        after a line of an item's text belongs to the same item, whatever its
        indent, as CommonMark's lazy continuation has it. Any other line
        belongs to the innermost open item whose content column its indent
        reaches, and closes the items it does not reach. Inside a fence,
        comment or front matter only the first line counts, because what it
        holds is not markdown and its indent says nothing about the list.

        With find_code, a line that does not carry on a paragraph and is
        indented CODE_INDENT columns past its item's content column, or past
        the margin outside a list, becomes a "code-block" line. That has to
        happen during the walk: a line taken for a list item opens an item
        that later lines would wrongly belong to.
        """
        out = [None] * len(self.kinds)
        stack = []
        prev = "blank"
        for i, kind in enumerate(self.kinds):
            if kind == "blank" or (kind in PROTECTED_KINDS and kind == prev):
                prev = kind
                continue
            raw = self.text.bare(i + 1)
            lead = len(raw) - len(raw.lstrip())
            if kind == "paragraph" and prev in ("paragraph", "list-item") and out[i - 1]:
                out[i] = out[i - 1]
            else:
                while stack and stack[-1][1] > lead:
                    stack.pop()
                margin = stack[-1][1] if stack else 0
                width = len(raw.expandtabs(CODE_INDENT)) - len(raw.expandtabs(CODE_INDENT).lstrip())
                if (
                    find_code
                    and kind in ("paragraph", "list-item", "table")
                    and prev in CODE_FOLLOWS
                    and width - margin >= CODE_INDENT
                ):
                    kind = self.kinds[i] = "code-block"
                if kind == "list-item":
                    stack.append((i + 1, len(LIST_ITEM.match(raw).group(0))))
                out[i] = stack[-1] if stack else None
            prev = kind
        return out

    def _html_block(self, lines, i):
        """The index of the last line of the HTML block line i opens, or None.

        A block with an end marker ends on the line holding it, or at the end
        of the file. One without ends on the line before the next blank line.
        A lone tag cannot interrupt a paragraph.
        """
        found = [end for start, end in HTML_STARTS if start.match(lines[i])]
        if found:
            end = found[0]
        else:
            lone = HTML_LONE_TAG.match(lines[i])
            if not lone:
                return None
            name = (lone.group(1) or lone.group(2)).lower()
            if (
                name in HTML_RAW_TAGS
                or name in TAG_KINDS
                or (i and self.kinds[i - 1] in ("paragraph", "list-item"))
            ):
                return None
            end = None
        j = i
        if end is None:
            while j + 1 < len(lines) and lines[j + 1].strip():
                j += 1
            return j
        while j + 1 < len(lines) and not end.search(lines[j]):
            j += 1
        return j

    def item(self, line):
        """The (line, content column) of the list item `line` belongs to, or None."""
        return self.items[line - 1]

    def _inline_comments(self):
        """Find the comments that open part way along a line of prose.

        One closes at the next `-->` before its paragraph ends - a blank line,
        a protected line or a heading - and a heading's closes on its own line.
        One that does not close is literal text, as CommonMark has it, and is
        left as prose rather than hiding everything after it.
        """
        s = self.text.s
        spans = self.code_span_offsets(self.protected_offsets())
        pos = 0
        while True:
            a = s.find(COMMENT_OPEN, pos)
            if a < 0:
                break
            pos = a + len(COMMENT_OPEN)
            line = self.text.line_of(a)
            if self.kinds[line - 1] not in INLINE_COMMENT_KINDS:
                continue
            if any(x <= a < y for x, y in spans):
                continue
            last = line
            if self.kinds[line - 1] != "heading":
                while last < len(self.kinds):
                    nxt = self.kinds[last]
                    if nxt == "blank" or nxt == "heading" or nxt in PROTECTED_KINDS:
                        break
                    last += 1
            limit = self.text.offset(last) + len(self.text.bare(last))
            b = s.find(COMMENT_CLOSE, pos, limit)
            if b < 0:
                continue
            pos = b + len(COMMENT_CLOSE)
            self.comments.append((a, pos))
            for ln in range(line, self.text.line_of(pos - 1) + 1):
                start = self.text.offset(ln)
                outside = self.uncovered(start, start + len(self.text.bare(ln)))
                if not any(s[x:y].strip() for x, y in outside):
                    self.kinds[ln - 1] = "comment"

    def comment_overlaps(self, a, b):
        """Whether the range [a, b) touches an HTML comment. An empty range,
        an insertion, touches one only from strictly inside it."""
        return any(x < b and a < y for x, y in self.comments)

    def uncovered(self, a, b):
        """The parts of [a, b) outside every HTML comment, in order."""
        out = [(a, b)]
        for x, y in self.comments:
            out = [
                piece
                for p, q in out
                for piece in ((p, min(q, x)), (max(p, y), q))
                if piece[0] < piece[1]
            ]
        return out

    def kind(self, line):
        return self.kinds[line - 1]

    def is_protected(self, line):
        return self.kinds[line - 1] in PROTECTED_KINDS

    def code_span_offsets(self, fences):
        """Backtick code spans: `<del>` in prose is a quotation, not markup.

        Without this, any document that documents this vocabulary fails its own
        markup check, and so does any project document quoting HTML.
        """
        out = []
        runs = [
            m
            for m in re.finditer(r"`+", self.text.s)
            if not any(a <= m.start() < b for a, b in fences)
        ]
        i = 0
        while i < len(runs):
            width = len(runs[i].group(0))
            j = i + 1
            while j < len(runs) and len(runs[j].group(0)) != width:
                j += 1
            if j < len(runs):
                out.append((runs[i].start(), runs[j].end()))
                i = j + 1
            else:
                i += 1
        return out

    def shielded_offsets(self):
        """Everything the tag scanner must ignore: fences, front matter, code
        spans and HTML comments. A comment is where an author writes about the
        markup, so a `<del>` there is a mention, not an edit."""
        fences = self.protected_offsets()
        return fences + self.code_span_offsets(fences) + self.comments

    def protected_offsets(self):
        """[(start, end)] absolute ranges of front matter, fences, and code
        and HTML blocks."""
        out, start = [], None
        for i, kind in enumerate(self.kinds):
            if kind in SHIELDED_KINDS:
                if start is None:
                    start = i
            elif start is not None:
                out.append((self.text.offset(start + 1), self.text.offset(i + 1)))
                start = None
        if start is not None:
            out.append((self.text.offset(start + 1), self.text.end))
        return out

    def heading_path(self, line):
        path, level = [], 99
        for hline, hlevel, title in reversed(self.headings):
            if hline < line and hlevel < level:
                path.append(title)
                level = hlevel
        return list(reversed(path))

    def continuation_indent(self, line):
        """Indent a whole-line tag needs so an enclosing list item survives it.

        Strictly the lines before `line`: a span that starts on a list item is
        wrapping that item, not sitting inside it, and must not be pushed in.
        """
        for i in range(line - 2, -1, -1):
            raw = self.text.bare(i + 1)
            if not raw.strip():
                continue
            item = LIST_ITEM.match(raw)
            if item:
                return len(item.group(0))
            if self.kinds[i] in ("heading", "fence", "frontmatter"):
                return 0
            return len(raw) - len(raw.lstrip())
        return 0


# --------------------------------------------------------------------------
# the markup
# --------------------------------------------------------------------------

TAG_KINDS = ("ins", "del", "repl", "why", "alt")
TAG_RE = re.compile(r"</?(%s)(\s[^<>]*?)?\s*/?>" % "|".join(TAG_KINDS))
ATTR_RE = re.compile(r"""([A-Za-z_][-A-Za-z0-9_]*)\s*=\s*("([^"]*)"|'([^']*)')""")

EDIT_KINDS = {"ins", "del", "repl"}
COMMENT_KINDS = {"why", "alt"}
ALLOWED_ATTRS = {
    "ins": {"why"},
    "del": {"why"},
    "repl": {"why"},
    "why": set(),
    "alt": set(),
}
ALLOWED_CHILDREN = {
    "ins": COMMENT_KINDS,
    "del": COMMENT_KINDS,
    "repl": COMMENT_KINDS | {"del", "ins"},
    "why": set(),
    "alt": set(),
}


class Tag:
    def __init__(self, kind, attrs, open_start, open_end, line):
        self.kind = kind
        self.attrs = attrs
        self.open_start = open_start
        self.open_end = open_end
        self.close_start = None
        self.close_end = None
        self.line = line
        self.children = []
        self.parent = None

    def inner(self, text):
        return text.s[self.open_end : self.close_start]

    def span(self):
        return (self.open_start, self.close_end)

    def child(self, kind):
        for c in self.children:
            if c.kind == kind:
                return c
        return None

    def whys(self, text):
        out = []
        if "why" in self.attrs:
            out.append(self.attrs["why"])
        for c in self.children:
            if c.kind == "why":
                out.append(strip_tags(c.inner(text)).strip())
        return out

    def alts(self, text):
        return [strip_tags(c.inner(text)).strip() for c in self.children if c.kind == "alt"]


def strip_tags(s):
    return TAG_RE.sub("", s)


class TagScanner:
    """Hand-rolled, because html.parser cannot express this grammar.

    Errors accumulate rather than raising, so one run reports every malformed
    tag in the tree. The first run of this workflow by hand produced five
    malformed tags that all survived because nothing checked.
    """

    def __init__(self, text, blocks=None, path="<text>"):
        self.text = text
        self.path = path
        self.blocks = blocks or Blocks(text)
        self.roots = []
        self.all = []
        self.errors = []
        self.warnings = []
        self._scan()

    def _err(self, offset, msg):
        self.errors.append("%s:%d  %s" % (self.path, self.text.line_of(offset), msg))

    def _scan(self):
        protected = self.blocks.shielded_offsets()

        def shielded(pos):
            return any(a <= pos < b for a, b in protected)

        stack = []
        for m in TAG_RE.finditer(self.text.s):
            start, end = m.start(), m.end()
            if shielded(start):
                continue
            kind = m.group(1)
            raw_attrs = m.group(2) or ""
            closing = self.text.s[start : start + 2] == "</"

            if closing:
                if not stack:
                    self._err(start, "stray </%s> closing nothing" % kind)
                    continue
                node = stack.pop()
                if node.kind != kind:
                    # Close it anyway. One typo should produce one message,
                    # not a mismatch now and an "unclosed" later.
                    self._err(
                        start, "</%s> closes <%s> opened at line %d" % (kind, node.kind, node.line)
                    )
                node.close_start, node.close_end = start, end
                continue

            attrs = {}
            for am in ATTR_RE.finditer(raw_attrs):
                attrs[am.group(1)] = am.group(3) if am.group(3) is not None else am.group(4)
            leftover = ATTR_RE.sub("", raw_attrs).strip()

            allowed = ALLOWED_ATTRS[kind]
            for name in attrs:
                if name not in allowed:
                    self._err(
                        start,
                        "<%s> has no %r attribute; allowed: %s"
                        % (kind, name, ", ".join(sorted(allowed)) or "none"),
                    )
            if leftover:
                self._err(
                    start,
                    "<%s> has unparseable attribute text %r; "
                    "attribute values need quotes" % (kind, leftover),
                )

            node = Tag(kind, attrs, start, end, self.text.line_of(start))
            if stack:
                parent = stack[-1]
                if kind not in ALLOWED_CHILDREN[parent.kind]:
                    self._err(start, "<%s> is not allowed inside <%s>" % (kind, parent.kind))
                node.parent = parent
                parent.children.append(node)
            else:
                self.roots.append(node)
            self.all.append(node)
            stack.append(node)

        for node in stack:
            self._err(node.open_start, "<%s> is never closed" % node.kind)
        self.all = [n for n in self.all if n.close_end is not None]
        self.roots = [n for n in self.roots if n.close_end is not None]
        self._check()

    def _check(self):
        for node in self.all:
            if node.kind == "repl":
                dels = [c for c in node.children if c.kind == "del"]
                inss = [c for c in node.children if c.kind == "ins"]
                if len(dels) != 1 or len(inss) != 1:
                    self._err(
                        node.open_start,
                        "<repl> holds %d <del> and %d <ins>; it takes "
                        "exactly one of each, <del> first" % (len(dels), len(inss)),
                    )
                elif dels[0].open_start > inss[0].open_start:
                    self._err(
                        node.open_start, "<repl> has <ins> before <del>; the old prose comes first"
                    )

    def counts(self):
        out = {}
        for node in self.all:
            out[node.kind] = out.get(node.kind, 0) + 1
        return out

    def pairs(self):
        """Top-level <del> immediately followed by <ins>: a bare replacement."""
        out, used = [], set()
        for a, b in zip(self.roots, self.roots[1:]):
            if (
                a.kind == "del"
                and b.kind == "ins"
                and not self.text.s[a.close_end : b.open_start].strip()
            ):
                out.append((a, b))
                used.add(id(a))
                used.add(id(b))
        return out, used


# --------------------------------------------------------------------------
# resolving markup
#
# One implementation, two modes. "accept" is tags resolve: the edits the markup
# proposes are taken, and the file becomes committable prose. "reject" drops
# the markup and its edits, and the underlying text comes back unchanged.
#
# "reject" is what evidence uses to neutralize a file before diffing it, so an
# edit the author tagged is reported once, as an explicit record, and not
# again as an inferred hunk. A plain git diff cannot tell the two apart.
# --------------------------------------------------------------------------

ACCEPT, REJECT = "accept", "reject"


def _line_bounds(text, offset):
    line = text.line_of(offset)
    start = text.offset(line)
    return start, start + len(text.line(line))


def is_block_form(node, text):
    start, _ = _line_bounds(text, node.open_start)
    if text.s[start : node.open_start].strip():
        return False
    _, end = _line_bounds(text, max(node.close_end - 1, 0))
    return not text.s[node.close_end : end].strip()


def tidy_block(s):
    """Drop exactly what a block tag's own two lines contribute, and no more.

    That is one leading newline (the one ending the opening tag's line) and any
    indent sitting before the closing tag. Stripping every blank line at the
    edges instead would silently eat an author's own blank line, which shows up
    later as a phantom deletion in the next evidence run.

    Deliberately does not dedent either. Insertion never re-indents the text it
    wraps, so removing indentation here would shift every wrapped line left.
    """
    if s.startswith("\r\n"):
        s = s[2:]
    elif s.startswith("\n"):
        s = s[1:]
    if not s.strip():
        return ""
    return re.sub(r"\n[ \t]*\Z", "\n", s)


def node_span(node, text):
    """The offsets a resolved tag replaces.

    A block-form tag owns its whole lines, including the indent before the
    opening tag and the newline after the closing one. Replacing only the tags
    themselves would leave that indent stranded on the line below.
    """
    if not is_block_form(node, text):
        return node.open_start, node.close_end
    start, _ = _line_bounds(text, node.open_start)
    _, end = _line_bounds(text, max(node.close_end - 1, 0))
    return start, end


def top_replacement(node, text, mode):
    """A block tag owns whole lines, so what replaces it has to end one.

    Unless the span it replaces did not: a block tag on the last line of a file
    that has no trailing newline must not add one, or every resolve pass
    returns the file a byte longer than it was.
    """
    out = resolved(node, text, mode)
    if out and is_block_form(node, text) and not out.endswith("\n"):
        _, end = node_span(node, text)
        if text.s[end - 1 : end] == "\n":
            out += "\n"
    return out


def resolved_inner(node, text, mode):
    parts, cursor = [], node.open_end
    for child in node.children:
        start, end = node_span(child, text)
        parts.append(text.s[cursor : max(start, cursor)])
        parts.append(top_replacement(child, text, mode))
        cursor = max(end, cursor)
    parts.append(text.s[cursor : node.close_start])
    out = "".join(parts)
    return tidy_block(out) if is_block_form(node, text) else out


def resolved(node, text, mode):
    if node.kind in COMMENT_KINDS:
        return ""
    if node.kind == "ins":
        return "" if mode == REJECT else resolved_inner(node, text, mode)
    if node.kind == "del":
        return "" if mode == ACCEPT else resolved_inner(node, text, mode)
    if node.kind == "repl":
        want = "ins" if mode == ACCEPT else "del"
        child = node.child(want)
        if child is None:
            return tidy_block(strip_tags(node.inner(text)))
        return resolved_inner(child, text, mode)
    return resolved_inner(node, text, mode)


def resolve_text(text, mode, blocks=None, path="<text>"):
    """Return (new_text, scanner). Errors live on the scanner."""
    scanner = TagScanner(text, blocks, path)
    return resolve_scanned(text, scanner, mode), scanner


def resolve_scanned(text, scanner, mode):
    """The text with every tag the scanner found resolved.

    On accept, a block-form tag that resolves to nothing takes its whole lines
    with it, and cut_runs drops a blank line beside them by the rule
    plan_findings gives for apply. Without that, cutting a paragraph that
    stood between two blank lines left the two touching. A blank line inside a
    tag that is kept is never taken.

    Reject has to return the file byte for byte as it was before the author
    tagged it, because evidence diffs against it. It takes a blank line only
    where apart_blanks says the author added it with the tag.
    """
    engine = EditEngine(text)
    cut, touched = set(), set()
    for node in scanner.roots:
        start, end = node_span(node, text)
        new = top_replacement(node, text, mode)
        lines = set(range(text.line_of(start), text.line_of(max(end - 1, start)) + 1))
        if not new and is_block_form(node, text):
            cut |= lines
            if mode == ACCEPT:
                continue
        else:
            touched |= lines
        engine.replace(start, end, new)
    if mode == ACCEPT:
        for start, end in cut_runs(text, scanner.blocks, cut, touched):
            engine.replace(start, end, "")
        return engine.result()
    last = text.line_count()
    for n in apart_blanks(text, scanner.blocks, cut, touched):
        engine.replace(text.offset(n), text.offset(n + 1) if n < last else text.end, "")
    return engine.result()


def apart_blanks(text, blocks, cut, touched):
    """The blank lines an author added to set a cut tag apart from its neighbors.

    A tag on a line of its own between two paragraphs needs a blank line on
    each side, and only one of them was there before. So a blank line goes
    when a cut lies between it and the blank line before it, or the start of
    the file. A blank line after a trailing cut goes the same way. An author's
    own two blank lines in a row have no cut between them, and both stay.
    """
    last = text.line_count()

    def blank(n):
        return not text.bare(n).strip() and not blocks.is_protected(n) and n not in touched

    out, kept, after_cut = [], [], False
    for n in range(1, last + 1):
        if n in cut:
            after_cut = True
            continue
        if after_cut and blank(n) and (not kept or blank(kept[-1])):
            out.append(n)
        else:
            kept.append(n)
        after_cut = False
    if after_cut and kept and blank(kept[-1]):
        out.append(kept[-1])
    return out


def neutralize(text, blocks=None, path="<text>"):
    """The file as it would read with every tag abandoned."""
    out, _ = resolve_text(text, REJECT, blocks, path)
    return out


def resolve_warnings(scanner, text):
    """Block-form tags inside a list are the one case worth eyeballing.

    A tag placed between two list items ends the list and starts a new one,
    and the damage outlives the resolve. The inline path cannot cause this
    because it never splits a line, so only block form is reported.
    """
    out = []
    for node in scanner.roots:
        if not is_block_form(node, text):
            continue
        if scanner.blocks.continuation_indent(node.line) > 0:
            out.append(
                "%s:%d  block-form <%s> resolved inside a list; check "
                "the list still reads as one list" % (scanner.path, node.line, node.kind)
            )
    return out


# --------------------------------------------------------------------------
# prose-eligible spans
# --------------------------------------------------------------------------

HEADING_PREFIX = re.compile(r"^(\s{0,3}#{1,6}\s+)")


def segments_for(text, blocks):
    """Every prose-eligible span, with inline HTML comments cut out of it.

    A line with no comment on it gives exactly what line_segments does. One
    with a comment part way along gives the prose either side as separate
    segments of the same kind, each trimmed, and nothing for the comment.
    """
    out = []
    for seg in line_segments(text, blocks):
        start = text.offset(seg["line"])
        whole = (start + seg["col_start"], start + seg["col_end"])
        pieces = blocks.uncovered(*whole)
        if pieces == [whole]:
            out.append(seg)
            continue
        raw = text.bare(seg["line"])
        for x, y in pieces:
            piece = raw[x - start : y - start]
            if not piece.strip():
                continue
            col_start = x - start + len(piece) - len(piece.lstrip())
            col_end = y - start - (len(piece) - len(piece.rstrip()))
            out.append(dict(seg, col_start=col_start, col_end=col_end, text=raw[col_start:col_end]))
    return out


def line_segments(text, blocks):
    """The prose-eligible span of each line, before comments are cut out."""
    out = []
    for line in range(1, text.line_count() + 1):
        kind = blocks.kind(line)
        raw = text.bare(line)
        if kind in PROTECTED_KINDS or kind == "blank" or not raw.strip():
            continue
        if kind == "heading":
            m = HEADING_PREFIX.match(raw)
            start = len(m.group(1)) if m else 0
            out.append(
                {
                    "line": line,
                    "col_start": start,
                    "col_end": len(raw),
                    "kind": "heading",
                    "text": raw[start:],
                }
            )
        elif kind == "table":
            if TABLE_DELIM.match(raw):
                continue
            col = 0
            for cell in raw.split("|"):
                if cell.strip():
                    lead = len(cell) - len(cell.lstrip())
                    out.append(
                        {
                            "line": line,
                            "col_start": col + lead,
                            "col_end": col + len(cell.rstrip()),
                            "kind": "table-cell",
                            "text": cell.strip(),
                        }
                    )
                col += len(cell) + 1
        elif kind == "list-item":
            m = LIST_ITEM.match(raw)
            start = len(m.group(0)) if m else 0
            out.append(
                {
                    "line": line,
                    "col_start": start,
                    "col_end": len(raw),
                    "kind": "list-item",
                    "text": raw[start:],
                }
            )
        else:
            lead = len(raw) - len(raw.lstrip())
            seg = {
                "line": line,
                "col_start": lead,
                "col_end": len(raw),
                "kind": "paragraph",
                "text": raw.strip(),
            }
            item = blocks.item(line)
            if item:
                seg["kind"] = "list-continuation"
                seg["item"] = item[0]
            out.append(seg)
    return out


# --------------------------------------------------------------------------
# pattern matches
# --------------------------------------------------------------------------

# The segment kinds a pattern may read on into the next line from, and the
# ones that continue the line before. A line that opens a new list item starts
# afresh.
RUN_KINDS = ("paragraph", "list-item", "list-continuation")
CONTINUING_KINDS = ("paragraph", "list-continuation")


class ProseRun:
    """Segments that read as one passage, joined so a pattern can cross lines.

    A sentence wrapped across two lines has a newline and the next line's
    indent in the middle of it. The run holds each line break as one space,
    which is how markdown renders it, so a pattern written for one line finds
    a breach that wraps. `starts` and `ends` hold the file offset each
    character of the run starts and ends at; a line break's space covers the
    whole of the newline and indent it stands for.
    """

    def __init__(self):
        self.chars = []
        self.starts = []
        self.ends = []
        self.breaks = set()

    def add(self, text, start, end):
        if self.chars:
            self.breaks.add(len(self.chars))
            self.chars.append(" ")
            self.starts.append(self.ends[-1])
            self.ends.append(start)
        self.chars.extend(text.s[start:end])
        self.starts.extend(range(start, end))
        self.ends.extend(range(start + 1, end + 1))

    def string(self):
        return "".join(self.chars)

    def span(self, a, b):
        """The file (start, end) of run characters [a, b), less any line break
        at either edge. None when nothing but line breaks is left.
        """
        while a < b and a in self.breaks:
            a += 1
        while b > a and b - 1 in self.breaks:
            b -= 1
        if a == b:
            return None
        return self.starts[a], self.ends[b - 1]


def prose_runs(text, blocks):
    """The eligible prose of a file as runs, each one passage.

    A segment joins the run before it when it is the next line of the same
    paragraph or list item: the line before is one of RUN_KINDS, this line is
    one of CONTINUING_KINDS, and neither is cut short by an HTML comment at the
    line break. Anything else starts a new run.
    """
    runs, prev = [], None
    for seg in segments_for(text, blocks):
        line = seg["line"]
        raw = text.bare(line)
        piece = raw[seg["col_start"] : seg["col_end"]].rstrip()
        start = text.offset(line) + seg["col_start"]
        joins = (
            prev is not None
            and prev["line"] == line - 1
            and prev["kind"] in RUN_KINDS
            and prev["col_end"] >= len(text.bare(prev["line"]).rstrip())
            and seg["kind"] in CONTINUING_KINDS
            and seg["col_start"] == len(raw) - len(raw.lstrip())
        )
        if not joins:
            runs.append(ProseRun())
        runs[-1].add(text, start, start + len(piece))
        prev = seg
    return runs


def pattern_matches(text, blocks, rules):
    """Every place a rule's pattern matches the file's eligible prose.

    Returns dicts of rule, line, col_start, end_line, col_end and text, where
    text is exactly what the file holds there, newline and indent included when
    the match wraps, so it can be copied into a finding as it stands. A match
    that touches a code span is left out: a code span quotes code, which a
    prose rule has nothing to say about. So is an empty match, and a second
    pattern of the same rule matching the same text.
    """
    spans = blocks.code_span_offsets(blocks.protected_offsets())
    compiled = [(r.id, re.compile(source)) for r in rules for _line, source in r.patterns]
    out, seen = [], set()
    for run in prose_runs(text, blocks):
        s = run.string()
        for rid, rx in compiled:
            for m in rx.finditer(s):
                where = run.span(m.start(), m.end())
                if where is None:
                    continue
                a, b = where
                if (rid, a, b) in seen or any(x < b and a < y for x, y in spans):
                    continue
                seen.add((rid, a, b))
                line, end_line = text.line_of(a), text.line_of(b)
                out.append(
                    {
                        "rule": rid,
                        "line": line,
                        "col_start": a - text.offset(line),
                        "end_line": end_line,
                        "col_end": b - text.offset(end_line),
                        "text": text.s[a:b],
                    }
                )
    out.sort(key=lambda x: (x["line"], x["col_start"], x["rule"]))
    return out


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------

NUM_RE = re.compile(r"\d+")
LINK_RE = re.compile(r"\((?:https?://|\.{0,2}/)[^)\s]*\)")


def classify_signal(old, new):
    """Why a hunk might not be a statement about prose.

    Every uncommitted edit is treated as style by default. The escape hatch
    matters for the run where a fact genuinely was corrected in passing, and a
    number that changed is the shape that takes.
    """
    if " ".join(old.split()) == " ".join(new.split()):
        return "whitespace-only"
    if NUM_RE.sub("#", old) == NUM_RE.sub("#", new):
        return "numeric-only"
    if LINK_RE.sub("(#)", old) == LINK_RE.sub("(#)", new):
        return "link-only"
    return None


def line_map(src_lines, dst_lines):
    """src line index -> dst line index, for lines that survived unchanged."""
    out = {}
    sm = difflib.SequenceMatcher(None, src_lines, dst_lines, autojunk=False)
    for tag, i1, i2, j1, _j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out[i1 + k] = j1 + k
    return out


def nearest(mapping, index, fallback):
    if index in mapping:
        return mapping[index]
    for step in range(1, 200):
        if index - step in mapping:
            return mapping[index - step] + step
        if index + step in mapping:
            return max(mapping[index + step] - step, 0)
    return fallback


def explicit_records(scanner, text, blocks, rel):
    """Tag records, with a bare <del>+<ins> pair reported as one replacement,
    and an <alt> tied to no passage reported on its own."""
    out = []
    pairs, paired = scanner.pairs()
    for a, b in pairs:
        out.append(
            {
                "file": rel,
                "kind": "repl",
                "start": a.line,
                "end": b.line,
                "old_text": tidy_block(strip_tags(a.inner(text))).strip(),
                "new_text": tidy_block(strip_tags(b.inner(text))).strip(),
                "why": a.whys(text) + b.whys(text),
                "alt": a.alts(text) + b.alts(text),
                "heading_path": blocks.heading_path(a.line),
                "block_kind": blocks.kind(a.line),
                "form": "pair",
            }
        )
    for node in scanner.roots:
        if id(node) in paired or node.kind not in EDIT_KINDS | {"alt"}:
            continue
        rec = {
            "file": rel,
            "kind": node.kind,
            "start": node.line,
            "end": text.line_of(max(node.close_end - 1, 0)),
            "why": node.whys(text),
            "alt": node.alts(text),
            "heading_path": blocks.heading_path(node.line),
            "block_kind": blocks.kind(node.line),
            "form": "block" if is_block_form(node, text) else "inline",
        }
        if node.kind == "alt":
            # An <alt> tied to no passage is a rule the author proposed, and
            # the record carries it as its own proposal.
            rec["alt"] = [strip_tags(node.inner(text)).strip()]
            rec["old_text"] = rec["new_text"] = ""
        elif node.kind == "repl":
            d, i = node.child("del"), node.child("ins")
            rec["old_text"] = tidy_block(strip_tags(d.inner(text))).strip() if d else ""
            rec["new_text"] = tidy_block(strip_tags(i.inner(text))).strip() if i else ""
        elif node.kind == "del":
            rec["old_text"] = resolved_inner(node, text, REJECT).strip()
            rec["new_text"] = ""
        else:
            rec["old_text"] = ""
            rec["new_text"] = resolved_inner(node, text, ACCEPT).strip()
        out.append(rec)
    return out


def bare_lines(text):
    return [text.bare(i + 1) for i in range(text.line_count())]


def inferred_hunks(repo, rel, text, neutral, ref):
    """(hunks, the file at ref as a Text), or (None, None) for a file new
    since ref. Each hunk is (its record, the index of its first line at ref).

    Lines are cut as Text cuts them, so a hunk's index at ref addresses the
    same line in the Text returned.

    A hunk that changed only HTML comments is left out. A comment is a note
    for people, such as a FILL marker or a skill's spec marker, and not the
    document's prose, so it is not an edit to learn a rule from.
    """
    base = repo.show(ref, rel)
    if base is None:
        return None, None
    base_text = Text(base)
    neutral_text = Text(neutral)
    base_blocks, neutral_blocks = Blocks(base_text), Blocks(neutral_text)
    base_lines = bare_lines(base_text)
    neutral_lines = bare_lines(neutral_text)
    to_work = line_map(neutral_lines, bare_lines(text))
    out = []
    sm = difflib.SequenceMatcher(None, base_lines, neutral_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old = base_lines[i1:i2]
        new = neutral_lines[j1:j2]
        line = nearest(to_work, j1, j1) + 1
        before = prose_outside_comments(base_text, base_blocks, i1, i2)
        after = prose_outside_comments(neutral_text, neutral_blocks, j1, j2)
        if before[0] == after[0] and (before[1] or after[1]):
            continue
        rec = {
            "file": rel,
            "start": line,
            "end": nearest(to_work, max(j2 - 1, j1), j2) + 1,
            "change": tag,
            "old_lines": old,
            "new_lines": new,
            "signal": classify_signal("\n".join(old), "\n".join(new)),
        }
        out.append((rec, i1))
    return out, base_text


def prose_outside_comments(text, blocks, first, stop):
    """(the words of lines [first, stop) outside every HTML comment, whether
    those lines touch a comment). Lines are 0-indexed, as a diff opcode has
    them. The words are joined by single spaces, so the space either side of
    a comment taken out of a line does not count as a change.
    """

    def at(i):
        return text.starts[i] if i < text.line_count() else text.end

    a, b = at(first), at(stop)
    words = "".join(text.s[x:y] for x, y in blocks.uncovered(a, b)).split()
    return " ".join(words), blocks.comment_overlaps(a, b)


def inferred_records(repo, rel, text, neutral, ref):
    hunks, _base_text = inferred_hunks(repo, rel, text, neutral, ref)
    return [rec for rec, _first in hunks or []]


def changed_spans(base_text, first, old_lines, new_lines):
    """The file offsets at ref of what one hunk changed, as (start, end).

    The diff is by character within the hunk, so a hunk that changed one word
    of a line does not claim the rest of it. A pure insertion is an empty span
    at the point it went in.
    """
    old, new = "\n".join(old_lines), "\n".join(new_lines)
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    out = []
    for tag, a1, a2, _b1, _b2 in sm.get_opcodes():
        if tag == "equal":
            continue
        out.append((hunk_offset(base_text, first, old, a1), hunk_offset(base_text, first, old, a2)))
    return out


def hunk_offset(base_text, first, old, pos):
    """The file offset of character pos of a hunk's old lines joined by \\n.

    A hunk with no old lines, a pure insertion, has none of its own; it sits
    at the start of the line it went in before, or at the end of the file.
    """
    if first >= base_text.line_count():
        return base_text.end
    k = old.count("\n", 0, pos)
    return base_text.offset(first + 1 + k) + pos - (old.rfind("\n", 0, pos) + 1)


def reproduced_by(base_text, matches, spans):
    """The matches, of those made at ref, that overlap what a hunk changed.

    A match overlaps a span when they share a character, and an empty span
    when it falls within the match or at either edge of it: a comma inserted
    right after a matched word is still an edit to what the pattern found.
    """
    out = []
    for m in matches:
        a = base_text.offset(m["line"]) + m["col_start"]
        b = base_text.offset(m["end_line"]) + m["col_end"]
        for x, y in spans:
            if (a <= x <= b) if x == y else (x < b and a < y):
                out.append(m)
                break
    return out


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def read_json(source, what):
    """JSON from a file, or from stdin when source is -.

    stdin spares Cowork a scratch file in the project, which the bridge could
    write but never delete.
    """
    return read_json_bytes(source, what)[1]


def read_json_bytes(source, what):
    """(raw bytes, parsed JSON) from a file, or from stdin when source is -.

    The bytes are what an approval token hashes, so they are read once and
    parsed from the same read. stdin cannot be read twice.
    """
    if source != "-":
        return read_json_file_bytes(source, what)
    return parse_json_bytes(sys.stdin.read().encode("utf-8"), what)


def read_json_file_bytes(path, what):
    """(raw bytes, parsed JSON) from a file, where - is a file of that name."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise Fatal("cannot read %s: %s" % (what, exc)) from exc
    return parse_json_bytes(raw, what)


def parse_json_bytes(raw, what):
    """(raw, parsed JSON), or Fatal naming what is not valid JSON."""
    try:
        return raw, json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise Fatal("%s is not valid JSON: %s" % (what, exc)) from exc


def load(args):
    """repo, config, scope for one invocation.

    The config override is `config_file`, not `file`: restore takes a --file of
    its own, and one shared attribute name would have it silently reinterpreted
    as a path to prose-style.md.
    """
    repo = Repo(args.repo)
    path = config_path(repo, getattr(args, "config_file", None))
    inside = path.startswith(repo.root + os.sep)
    config = Config(path, os.path.relpath(path, repo.root) if inside else None)
    return repo, config, Scope(repo, config)


def cmd_scope(args):
    repo, config, scope = load(args)
    verdicts = scope.verdicts()
    shown = verdicts if args.all else [v for v in verdicts if v["included"]]
    data = {
        "include": scope.include,
        "exclude": scope.exclude,
        "overridden": scope.overridden,
        "files": shown,
        "count": sum(1 for v in verdicts if v["included"]),
    }

    def human():
        for v in shown:
            if args.all:
                print("%s %-62s %s" % ("+" if v["included"] else "-", v["path"], v["reason"]))
            else:
                print(v["path"])
        print("\n%d file(s) in scope of %d markdown file(s)" % (data["count"], len(verdicts)))

    return emit(args, "scope", repo.root, data, human=human)


def unignored_copy(repo):
    """This script's path in the repo when it is a copy git would commit.

    None when the script runs from anywhere but the repo's .prose-tuning/, or
    when git ignores the copy.
    """
    rel = os.path.relpath(os.path.realpath(SCRIPT_PATH), os.path.realpath(repo.root))
    rel = rel.replace(os.sep, "/")
    if not rel.startswith(COPY_DIR + "/"):
        return None
    code, _, _ = repo.git("check-ignore", "-q", "--", rel)
    return None if code == 0 else rel


def legacy_blockers(repo, config):
    """A prose-style.md still at the project root, where nothing loads it."""
    if not os.path.exists(legacy_config_path(repo)):
        return []
    if not config.exists:
        return [
            "%s  the rules are at the project root, where no session loads them; "
            "run: prose.py config move" % LEGACY_CONFIG_PATH
        ]
    return [
        "%s  a second copy of the rules, beside %s; delete the one at the root"
        % (LEGACY_CONFIG_PATH, CONFIG_PATH)
    ]


def cmd_preflight(args):
    repo, config, scope = load(args)
    want = args.for_target
    blockers = []
    if sys.version_info < (3, 9):  # noqa: UP036 - the message a user on an older Python sees
        blockers.append("python3 is %d.%d; this script needs 3.9 or newer" % sys.version_info[:2])
    blockers += legacy_blockers(repo, config)
    if not config.exists:
        if want in ("apply", "adopt") and not os.path.exists(legacy_config_path(repo)):
            blockers.append("%s  no config; run: prose.py config init" % config.rel())
    else:
        blockers += config.errors
    unignored = unignored_copy(repo)
    if unignored:
        blockers.append(
            "%s  not ignored, so the project's next commit would take it in; "
            "run setup again, or on Cowork stage and copy again, which puts %s beside it"
            % (unignored, COPY_IGNORE)
        )

    files = scope.files()
    tagged, markup, markup_errors = [], {}, []
    for rel in files:
        path = repo.abspath(rel)
        if not os.path.exists(path):
            continue
        scanner = TagScanner(Text.read(path), None, rel)
        markup_errors += scanner.errors
        if scanner.all:
            tagged.append((rel, scanner.all[0].line))
            markup[rel] = scanner.counts()
    blockers += markup_errors

    hints = []
    if want == "apply":
        # Only documents the rules govern. An uncommitted prose-style.md is
        # the expected output of an update-prose-config run, not a reason to
        # refuse the conformance pass that validates it.
        in_scope = set(files)
        for rel, line in tagged:
            blockers.append(
                "%s:%d  markup is present; once update-prose-config has learned from it, "
                "run: prose.py tags resolve, and commit the result" % (rel, line)
            )
        for status, rel in repo.dirty_md():
            if rel in in_scope:
                blockers.append(
                    "%s  uncommitted (%s); commit or stash before conforming prose" % (rel, status)
                )
        if blockers and not args.force:
            hints.append("pass --force only if the author asked for it by name")

    data = {
        "for": want,
        "blockers": blockers,
        "hints": hints,
        "markup": markup,
        "config_exists": config.exists,
        "scope_count": len(files),
    }

    def human():
        if not blockers:
            print("ok: nothing blocks %s" % want)
        else:
            print("%d blocker(s) for %s" % (len(blockers), want))
        if want == "config" and not blockers:
            # The progress update-prose-config starts from: whether there are
            # rules to add to, and the author's markup it is about to read.
            missing = "missing; run: prose.py config init"
            print("config  %s" % (config.rel() if config.exists else missing))
            for rel in sorted(markup):
                counts = ", ".join("%d %s" % (n, k) for k, n in sorted(markup[rel].items()))
                print("markup  %s  %s" % (rel, counts))
            if not markup:
                print("markup  none")

    if args.force and want == "apply":
        blockers = []
    return emit(args, "preflight", repo.root, data, errors=blockers, warnings=hints, human=human)


def segment_line(rel, seg):
    """One segment as a line of text: its address, its kind, then its text.

    The address is file:line:col_start-col_end, which holds every field a
    finding may need, so a model copies it rather than working it out.
    """
    return "%s:%d:%d-%d  %s  %s" % (
        rel,
        seg["line"],
        seg["col_start"],
        seg["col_end"],
        seg["kind"],
        seg["text"],
    )


def read_targets(repo, targets):
    """([(rel, Text)] for each target that exists, an error for each that does not)."""
    texts, errors = [], []
    for rel in targets:
        path = repo.abspath(rel)
        if not os.path.exists(path):
            errors.append("%s  no such file" % rel)
            continue
        texts.append((rel, Text.read(path)))
    return texts, errors


def cmd_segments(args):
    repo, config, scope = load(args)
    texts, errors = read_targets(repo, args.paths or scope.files())
    data = {}
    for rel, text in texts:
        data[rel] = {"segments": segments_for(text, Blocks(text))}

    def human():
        for rel in sorted(data):
            for seg in data[rel]["segments"]:
                print(segment_line(rel, seg))

    return emit(args, "segments", repo.root, data, errors=errors, human=human)


def match_line(rel, m):
    """One match as a line of text: its address, its rule, then its text.

    The address is file:line:col_start-col_end, or file:line:col_start-
    end_line:col_end for a match that wraps. The text is a JSON string, so a
    wrapped match's newline shows as \\n and the text can be pasted into a
    finding as it stands.
    """
    end = "%d" % m["col_end"]
    if m["end_line"] != m["line"]:
        end = "%d:%d" % (m["end_line"], m["col_end"])
    return "%s:%d:%d-%s  %s  %s" % (
        rel,
        m["line"],
        m["col_start"],
        end,
        m["rule"],
        json.dumps(m["text"], ensure_ascii=False),
    )


def all_matches(texts, rules):
    """Every match of rules' patterns in texts, [(rel, Text)], in address order."""
    matches = []
    for rel, text in texts:
        for m in pattern_matches(text, Blocks(text), rules):
            matches.append(dict(m, file=rel))
    matches.sort(key=lambda m: (m["file"], m["line"], m["col_start"], m["rule"]))
    return matches


def unlinted(args, command, repo, config):
    """The refusal a command that runs the patterns gives on a rule file lint refuses."""
    return emit(
        args,
        command,
        repo.root,
        {},
        errors=[*config.errors, "%s  fix it first; see: prose.py config lint" % config.rel()],
    )


def cmd_patterns(args):
    """Every match of every rule's pattern, over the same spans segments gives.

    A match is a place for the model to judge, not a finding: a spaced hyphen
    can be a minus sign. So matches exit 0, like segments; a rule file lint
    refuses exits 1 before anything is read, because a pattern it drops would
    look like a rule with nothing to report.
    """
    repo, config, scope = load(args)
    if config.errors:
        return unlinted(args, "patterns", repo, config)
    rules = config.patterned()
    targets = args.paths or scope.files()
    texts, errors = read_targets(repo, targets)
    matches = all_matches(texts, rules)
    data = {"rules": [r.id for r in rules], "files": len(targets), "matches": matches}

    def human():
        print_matches(matches, len(targets), data["rules"])

    return emit(args, "patterns", repo.root, data, errors=errors, human=human)


def print_matches(matches, files, ids):
    """patterns' output: a line per match, then the count and the rules checked."""
    for m in matches:
        print(match_line(m["file"], m))
    print(
        "\n%d match(es) in %d file(s). Checked by pattern: %s"
        % (len(matches), files, ", ".join(ids) or "no rule carries one")
    )


def rule_text(rule):
    """A rule as prose-style.md words it: its heading, then its body."""
    return "\n\n".join(x for x in ("### %s: %s" % (rule.id, rule.title), rule.body_text()) if x)


def cmd_pass(args):
    """What an apply-prose pass reads, in one output: config list, segments, patterns.

    The three commands ran one after another with nothing decided between
    them, so the model only carried their output across (#196). Each stays a
    command of its own; this one composes them over one read of each file.
    """
    repo, config, scope = load(args)
    if config.errors:
        return unlinted(args, "pass", repo, config)
    patterned = config.patterned()
    targets = args.paths or scope.files()
    texts, errors = read_targets(repo, targets)
    segments = {rel: segments_for(text, Blocks(text)) for rel, text in texts}
    matches = all_matches(texts, patterned)
    data = {
        "rules": [r.as_dict() for r in config.rules],
        "files": len(targets),
        "segments": segments,
        "matches": matches,
        "patterned": [r.id for r in patterned],
    }

    def human():
        print(PASS_HEADING % "rules")
        for rule in config.rules:
            print(rule_text(rule) + "\n")
        print(PASS_HEADING % "segments")
        for rel in sorted(segments):
            for seg in segments[rel]:
                print(segment_line(rel, seg))
        print("\n" + PASS_HEADING % "matches")
        print_matches(matches, len(targets), data["patterned"])

    return emit(args, "pass", repo.root, data, errors=errors, human=human)


def pending_files(repo):
    """The files a run would learn from in repo, by repo's own prose-style.md.

    Every file in its scope with an uncommitted change, and prose-style.md
    itself when it has one, since an author can edit the rules by hand too.
    A file deleted since the last commit has nothing to read.
    """
    config = Config(config_path(repo), CONFIG_PATH)
    pending = repo.pending()
    out = [
        rel
        for rel in Scope(repo, config).files()
        if rel in pending and os.path.exists(repo.abspath(rel))
    ]
    if CONFIG_PATH in pending and os.path.exists(config.path):
        out.append(CONFIG_PATH)
    return out


def open_tree(args, repo):
    """(the tree a command reads, its checkout): this tree, or the one --from names.

    --from names a worktree by its folder, or by the branch it has checked
    out, tried in that order. The checkout is None when the tree read is this
    one, so --from naming this tree reads as no --from, and is otherwise
    {root, branch}.
    """
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


def load_from(args):
    """repo, config, and the tree to read with its checkout and scope.

    The tree read is the one --from names, or this one. Its scope comes from
    this tree's prose-style.md, which also leaves out the tree's own copy.
    """
    repo, config, scope = load(args)
    source, checkout = open_tree(args, repo)
    if checkout is not None:
        scope = Scope(source, config, config_rel=CONFIG_PATH)
    return repo, config, source, checkout, scope


def checkout_label(checkout):
    """A checkout as a person reads it: its folder, and its branch if it has one."""
    if checkout["branch"]:
        return "%s, on %s" % (checkout["root"], checkout["branch"])
    return checkout["root"]


def other_pending(repo):
    """[{root, branch, files}] for each other worktree holding pending files."""
    out = []
    for root, branch in repo.worktrees():
        files = pending_files(Repo(root))
        if files:
            out.append({"root": root, "branch": branch, "files": files})
    return out


def cmd_evidence(args):
    repo, config, source, checkout, scope = load_from(args)
    explicit, inferred, errors, warnings = [], [], [], []
    for rel in scope.files():
        path = source.abspath(rel)
        if not os.path.exists(path):
            continue
        text = Text.read(path)
        blocks = Blocks(text)
        scanner = TagScanner(text, blocks, rel)
        errors += scanner.errors
        if scanner.errors:
            continue
        explicit += explicit_records(scanner, text, blocks, rel)
        neutral = neutralize(text, blocks, rel)
        inferred += inferred_records(source, rel, text, neutral, BASE_REF)

    # A tree with nothing to learn from may be a fresh worktree, opened while
    # the author's edits sit in another checkout of the same repository.
    elsewhere = []
    if not (explicit or inferred or errors) and checkout is None:
        elsewhere = other_pending(repo)
    for tree in elsewhere:
        errors.append(
            "this tree does not hold any pending edits, and %s%s holds them in %s. Run `%s`, "
            "and pass the same --from to reproduce."
            % (
                tree["root"],
                ", on %s," % tree["branch"] if tree["branch"] else "",
                ", ".join(tree["files"]),
                FROM_COMMAND % shlex.quote(tree["root"]),
            )
        )
    # The run reads this tree's rules, so rules the author edited by hand in
    # the other checkout are not among them.
    if checkout is not None and CONFIG_PATH in source.pending():
        warnings.append(
            "%s has uncommitted changes in %s, and this run does not read them: it reads %s here"
            % (CONFIG_PATH, source.root, CONFIG_PATH)
        )

    data = {
        "explicit": explicit,
        "inferred": inferred,
        # Every candidate is checked against these, so a rule that says the
        # same thing is rewritten rather than added under a second id.
        "rules": [
            {
                "id": r.id,
                "body": r.body_text(),
                "patterns": [source for _line, source in r.patterns],
            }
            for r in config.rules
        ],
        "checkout": checkout,
        "other_worktrees": elsewhere,
    }

    def human():
        if checkout is not None:
            print("reading %s" % checkout_label(checkout))
        print("base %s" % BASE_REF)
        for rec in explicit:
            print(
                "  explicit %s:%d [%s] %s"
                % (rec["file"], rec["start"], rec["kind"], (rec["why"] or rec["alt"] or [""])[0])
            )
        for rec in inferred:
            flag = " (%s)" % rec["signal"] if rec["signal"] else ""
            print("  inferred %s:%d [%s]%s" % (rec["file"], rec["start"], rec["change"], flag))
        print("\nexplicit: %d  inferred: %d" % (len(explicit), len(inferred)))

    return emit(args, "evidence", repo.root, data, errors=errors, warnings=warnings, human=human)


def cmd_reproduce(args):
    """Whether the rules reproduce the edits made since HEAD.

    Each edit is a hunk as `evidence` reports it under `inferred`, read with
    the author's markup resolved, so a tagged edit is a plain hunk too: its
    <ins> text kept and its <del> text gone, as apply-prose will commit it.
    Every rule's pattern runs over the file as it was at HEAD, and an edit is
    reproduced when some match overlaps what it changed; changed_spans and
    reproduced_by have what counts. The matches carry line numbers at HEAD,
    since that is the text they were found in.

    An edit a pattern does not reproduce is for the model to check against the
    rules with no pattern, which are listed by id. A pure insertion is never
    reproduced, because there was nothing before it for a pattern to find. So
    an unreproduced edit exits 0, like a match in `patterns`; a rule file lint
    refuses exits 1 before anything is read.
    """
    repo, config, source, checkout, scope = load_from(args)
    if config.errors:
        return unlinted(args, "reproduce", repo, config)
    rules = config.patterned()
    edits = []
    for rel in scope.files():
        path = source.abspath(rel)
        if not os.path.exists(path):
            continue
        text = Text.read(path)
        resolved_text, _ = resolve_text(text, ACCEPT, None, rel)
        hunks, base_text = inferred_hunks(source, rel, text, resolved_text, BASE_REF)
        if not hunks:
            continue
        matches = pattern_matches(base_text, Blocks(base_text), rules)
        for rec, first in hunks:
            spans = changed_spans(base_text, first, rec["old_lines"], rec["new_lines"])
            found = reproduced_by(base_text, matches, spans)
            edits.append(dict(rec, reproduced=bool(found), matches=found))
    data = {
        "checkout": checkout,
        "edits": edits,
        "unpatterned": [r.id for r in config.rules if not r.patterns],
    }

    def human():
        if checkout is not None:
            print("reading %s" % checkout_label(checkout))
        for e in edits:
            if e["reproduced"]:
                rules = ", ".join(sorted({m["rule"] for m in e["matches"]}))
                print("%s:%d  reproduced  %s" % (e["file"], e["start"], rules))
            else:
                print("%s:%d  NOT reproduced" % (e["file"], e["start"]))
        done = sum(1 for e in edits if e["reproduced"])
        print("\n%d of %d edit(s) reproduced by a pattern." % (done, len(edits)))
        print("Checked by reading, no pattern: %s" % (", ".join(data["unpatterned"]) or "none"))

    return emit(args, "reproduce", repo.root, data, human=human)


CONFIG_SKELETON = """---
name: {name} prose style
scope:
  include:
{include}
  exclude:
{exclude}
---

# {name}: prose style

The house style for everything written in this repo: its documents, and also
commit messages, pull request titles and descriptions, issues and code
comments. It covers how the sentences read. Mechanics - front matter, TODO
markers, commit format - are out of its scope.

This file sits in `.claude/rules/`, so every session in the project loads it.
The `scope:` block above decides only which files `apply-prose` checks.

A rule here has a stable id of the form `<section>-<name>`, where the name is
one to four words saying what the rule means. Reports name the id, and a rule
that gets reworded keeps its name. Git holds what the rule used to say, so
nothing here is ever marked retired.

## Standing instructions

<!-- One "### standing-<name>: Title" per rule, as in
     "### standing-us-spelling: Use US spelling". Run update-prose-config to
     fill this in from edits rather than writing rules from scratch. -->
"""


def shipped_template():
    """The shipped rules: beside the script on the device, else in the plugin."""
    here = os.path.dirname(SCRIPT_PATH)
    if os.path.basename(here) == COPY_DIR:
        path = os.path.join(here, os.path.basename(COPY_TEMPLATE))
    else:
        path = os.path.join(os.path.dirname(here), *SHIPPED_TEMPLATE.split("/"))
    if not os.path.isfile(path):
        raise Fatal("shipped rules not found at %s" % path)
    return path


def config_move(args, repo, config):
    """Copy a root prose-style.md to where sessions load it.

    Copies and never deletes: this script only reads git, and Cowork's bridge
    cannot delete a file. The author removes the root copy.
    """
    legacy = legacy_config_path(repo)
    if not os.path.exists(legacy):
        raise Fatal("%s does not exist; nothing to move" % LEGACY_CONFIG_PATH)
    if config.exists:
        raise Fatal(
            "%s already exists; compare it with %s and delete the one at the root"
            % (CONFIG_PATH, LEGACY_CONFIG_PATH)
        )
    if not args.dry_run:
        os.makedirs(os.path.dirname(config.path), exist_ok=True)
        with open(legacy, "rb") as src:
            body = src.read()
        with open(config.path, "wb") as dst:
            dst.write(body)
    data = {
        "from": LEGACY_CONFIG_PATH,
        "to": os.path.relpath(config.path, repo.root),
        "dry_run": args.dry_run,
        "next": "delete %s" % LEGACY_CONFIG_PATH,
    }
    return emit(
        args,
        "config move",
        repo.root,
        data,
        human=lambda: print(
            "%s %s to %s; now delete %s"
            % (
                "would copy" if args.dry_run else "copied",
                LEGACY_CONFIG_PATH,
                data["to"],
                LEGACY_CONFIG_PATH,
            )
        ),
    )


def heading_end(lines, start):
    """The index of the first line after lines[start] that opens a ## or ###
    heading, or len(lines). A rule's block, as Config._parse_rules reads it.
    """
    end = start + 1
    while end < len(lines):
        raw = lines[end].rstrip("\n").rstrip("\r")
        if ANY_H2.match(raw) or ANY_H3.match(raw):
            break
        end += 1
    return end


def adopted_block(lines, rule):
    """A rule's lines as the source has them, without a metadata comment.

    The block is sliced from the file rather than rendered from Rule, so that
    wrapping, the worked example and anything the parser does not model come
    across byte for byte. Only a prose-rule comment an earlier version wrote
    is dropped, since the target's commit records where the rule came from.
    Trailing blank lines go, since the target decides its own spacing.
    """
    start = rule.line - 1
    body = [
        ln
        for ln in lines[start + 1 : heading_end(lines, start)]
        if not META_COMMENT.match(ln.strip())
    ]
    while body and not body[-1].strip():
        body.pop()
    block = [lines[start], *body]
    return [ln if ln.endswith("\n") else ln + "\n" for ln in block]


def adopted_from(config):
    """What the commit note calls the source: the folder name of the
    repository holding it, else its path.
    """
    try:
        return Repo(os.path.dirname(config.path)).project_name()
    except Fatal:
        return config.path


def plan_adoption(config, source_lines, target, target_lines, ids):
    """(the target's new lines, the ids adopted, the ids refused with why).

    Every insertion point is found on the target as read, then applied from the
    bottom up, so an earlier insertion cannot move a later one. A rule goes
    after the last target rule of its section; failing that, under a ## heading
    matching the one it sat under in the source; failing that, at the end under
    a new copy of that heading. Rules going to one place keep the source's order.
    """
    source_ids = config.by_id()
    target_ids = target.by_id()
    refused, chosen, seen = [], [], set()
    for rid in ids:
        if rid in seen:
            refused.append({"id": rid, "reason": "%s is named twice" % rid})
        elif rid not in source_ids:
            refused.append({"id": rid, "reason": "%s has no rule %s" % (config.rel(), rid)})
        elif rid in target_ids:
            refused.append(
                {
                    "id": rid,
                    "reason": "%s already has %s; that is a collision, not a new rule."
                    " Run config adopt again without it, and put the pair to the"
                    " author for config resolve" % (target.rel(), rid),
                }
            )
        else:
            chosen.append(source_ids[rid])
        seen.add(rid)
    chosen.sort(key=lambda r: r.line)
    spots = adoption_spots(source_lines, target, target_lines, chosen)
    return place_blocks(target_lines, spots), [r.id for r in chosen], refused


def adoption_spots(source_lines, target, target_lines, rules):
    """The spots place_blocks takes for copying rules into the target, each
    rule found where plan_adoption says. rules are in the source's order.
    """
    h2s = {}
    for i, ln in enumerate(target_lines):
        m = ANY_H2.match(ln.rstrip("\n").rstrip("\r"))
        if m:
            h2s.setdefault(m.group(1), i)

    # (position, heading to open or None) -> blocks, in first-seen order.
    spots = {}
    for rule in rules:
        mine = [r for r in target.rules if r.section == rule.section]
        if mine:
            key = (heading_end(target_lines, mine[-1].line - 1), None)
        elif rule.group in h2s:
            key = (heading_end(target_lines, h2s[rule.group]), None)
        else:
            key = (len(target_lines), rule.group or None)
        spots.setdefault(key, []).append(adopted_block(source_lines, rule))
    return spots


def place_blocks(lines, spots, replaced=None):
    """lines with each rule block put in its spot, and each replaced range
    swapped for its new lines.

    spots maps (position, heading to open or None) to blocks, in first-seen
    order. replaced maps (start, end) to lines. Every position is one read
    from lines as given, and the edits go in from the bottom up, so an
    earlier one cannot move a later one. Where an insertion and a
    replacement start on one line, the replacement goes first and the
    insertion lands above it.
    """
    by_pos = {}
    for (pos, heading), blocks in spots.items():
        piece = ["## %s\n" % heading, "\n"] if heading else []
        for i, block in enumerate(blocks):
            piece += (["\n"] if i else []) + block
        by_pos.setdefault(pos, []).append(piece)

    edits = [((pos, pos), None) for pos in by_pos]
    edits += [(span, new) for span, new in (replaced or {}).items()]
    out = list(lines)
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    for (start, end), new in sorted(edits, key=lambda e: e[0], reverse=True):
        if new is not None:
            out[start:end] = new
            continue
        chunk = []
        for i, piece in enumerate(by_pos[start]):
            chunk += (["\n"] if i else []) + piece
        if start > 0 and out[start - 1].strip():
            chunk.insert(0, "\n")
        if start < len(out):
            chunk.append("\n")
        out[start:start] = chunk
    return out


def linted_target(args, config):
    """The Config at --to, once it and config both lint clean.

    classify, adopt and resolve share it: a rule read from a malformed file is
    classified or copied wrong, and the error then looks like the command's.
    """
    target = Config(os.path.abspath(args.to))
    if not target.exists:
        raise Fatal("%s does not exist" % args.to)
    for cfg in (config, target):
        if cfg.errors:
            raise Fatal(
                "%s does not lint clean; run: prose.py config lint --file %s" % (cfg.path, cfg.path)
            )
    return target


def config_adopt(args, repo, config):
    """Copy named rules from this file into --to, and say where they came from.

    adopt-prose's step 2. Refuses an id the target already has, because a
    shared id is step 3's question, and writes nothing while any id is refused
    unless --partial is passed.
    """
    target = linted_target(args, config)
    source_lines = Text.read(config.path).lines
    target_lines = Text.read(target.path).lines
    out, adopted, refused = plan_adoption(config, source_lines, target, target_lines, args.rule)
    errors = [r["reason"] for r in refused]
    write = adopted and not (refused and not args.partial)
    if refused and not args.partial:
        errors.append("nothing was written; pass --partial to adopt the rest")
        adopted = []
    if write and not args.dry_run:
        Text("".join(out)).write(target.path)

    lines = {}
    for i, ln in enumerate(out):
        m = RULE_HEADING.match(ln.rstrip("\n").rstrip("\r"))
        if m:
            lines.setdefault("%s-%s" % (m.group(1), m.group(2)), i + 1)
    data = {
        "commit_note": (
            ADOPTED_NOTE % (adopted_from(config), ", ".join(adopted)) if adopted else None
        ),
        "adopted": [{"id": rid} for rid in adopted],
        "refused": refused,
    }

    def human():
        verb = "would adopt" if args.dry_run else "adopted"
        for rid in adopted:
            print("%s  %s  at line %d" % (verb, rid, lines[rid]))
        for r in refused:
            print("refused  %s" % r["id"])
        if data["commit_note"]:
            print("\nfor the commit description: %s" % data["commit_note"])

    return emit(args, "config adopt", repo.root, data, errors=errors, human=human)


# config write: the parts of a rule a record can give, the fields of each
# kind of record, and what a written rule is reported as.
WRITE_PARTS = ("title", "body", "example", "patterns")
NEW_RULE_FIELDS = frozenset(("section", "name", "heading", *WRITE_PARTS))
REWRITE_FIELDS = frozenset(("id", "expect", *WRITE_PARTS))
WRITTEN_NEW = "new"
WRITTEN_REWRITE = "rewritten"
# What config write prefixes to a block to lint it on its own.
LINT_FRONT = "---\nname: one rule\n---\n\n"


def pattern_line(source):
    """The **Pattern.** line that holds source, as parse_pattern reads it.

    The code span is fenced by one more backtick than the longest run inside
    it, and padded with a space at each end when source starts or ends with a
    backtick or a space, which parse_pattern strips again. A source of nothing
    but spaces goes unpadded, because parse_pattern leaves such a span whole.
    """
    runs = [len(r) for r in re.findall(r"`+", source)]
    fence = "`" * (max([*runs, 0]) + 1)
    edge = source[:1] in "` " or source[-1:] in "` "
    pad = " " if edge and source.strip(" ") else ""
    return "**Pattern.** %s%s%s%s%s\n" % (fence, pad, source, pad, fence)


def rule_block(rid, title, prose, patterns, example):
    """A rule's lines, in the order prose-style-format.md shows: heading,
    prose, patterns, worked example. prose is a list of lines.
    """
    block = ["### %s: %s\n" % (rid, title), "\n"]
    block += [ln if ln.endswith("\n") else ln + "\n" for ln in prose]
    if patterns:
        block += ["\n"] + [pattern_line(p) for p in patterns]
    if example:
        block += [
            "\n",
            "> **Before.** %s\n" % example["before"],
            "> **After.** %s\n" % example["after"],
        ]
    return block


def rule_parts(lines, rule):
    """(start, end, prose lines) of a rule's block as the file has it.

    start is the heading's index and end the index after its last line that is
    not blank. The prose is every line under the heading but its patterns, its
    worked example and a metadata comment, less blank lines at either end.
    """
    start = rule.line - 1
    end = heading_end(lines, start)
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    prose = [
        ln
        for ln in lines[start + 1 : end]
        if not (
            PATTERN_LINE.match(ln)
            or BEFORE_LINE.match(ln.rstrip("\r\n"))
            or AFTER_LINE.match(ln.rstrip("\r\n"))
            or META_COMMENT.match(ln.strip())
        )
    ]
    while prose and not prose[0].strip():
        prose.pop(0)
    while prose and not prose[-1].strip():
        prose.pop()
    return start, end, prose


def one_line(value, what):
    """A message when value is not one non-empty line of text, else None."""
    if not isinstance(value, str) or not value.strip():
        return "%s is not a non-empty string" % what
    if "\n" in value or "\r" in value:
        return "%s runs over more than one line" % what
    return None


def part_problem(record, part):
    """A message when the record's value for part cannot go into a rule."""
    value = record[part]
    if part == "title":
        return one_line(value, "title")
    if part == "body":
        if not isinstance(value, str) or not value.strip():
            return "body is not a non-empty string"
        for ln in value.split("\n"):
            ln = ln.rstrip("\r")
            if ANY_H2.match(ln) or ANY_H3.match(ln):
                return "body holds a heading: %r" % ln
            if PATTERN_LINE.match(ln):
                return "body holds a **Pattern.** line; give it in patterns"
            if BEFORE_LINE.match(ln) or AFTER_LINE.match(ln):
                return "body holds a worked example; give it in example"
            if META_COMMENT.match(ln.strip()):
                return "body holds a prose-rule comment; where a rule came from goes in the commit"
        return None
    if part == "example":
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"before", "after"}:
            return "example is not null or an object with before and after"
        return one_line(value["before"], "example before") or one_line(
            value["after"], "example after"
        )
    if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
        return "patterns is not a list of strings"
    for source in value:
        parsed, problem = parse_pattern(pattern_line(source)[len("**Pattern.**") : -1])
        if problem:
            return problem
    return None


class WriteRefusal(Exception):
    """One record config write, or one answer config resolve, cannot write,
    and why."""


def record_id(rec):
    """The id a record names, or None when it is not a record."""
    if not isinstance(rec, dict):
        return None
    if "id" in rec:
        return rec["id"]
    return "%s-%s" % (rec.get("section"), rec.get("name"))


def checked_fields(rec):
    """Whether rec is a rewrite. Raises WriteRefusal on a field that is
    unknown, missing or cannot go into a rule.
    """
    if not isinstance(rec, dict):
        raise WriteRefusal("record is not an object")
    rewrite = "id" in rec
    fields = REWRITE_FIELDS if rewrite else NEW_RULE_FIELDS
    unknown = sorted(set(rec) - fields)
    if unknown:
        raise WriteRefusal(
            "unknown field %s; a %s takes %s"
            % (", ".join(unknown), "rewrite" if rewrite else "new rule", ", ".join(sorted(fields)))
        )
    if rewrite and not isinstance(rec["id"], str):
        raise WriteRefusal("id is not a string")
    missing = [] if rewrite else [f for f in ("section", "name", "title", "body") if f not in rec]
    if missing:
        raise WriteRefusal("a new rule needs %s" % ", ".join(missing))
    if not rewrite and not (isinstance(rec["section"], str) and isinstance(rec["name"], str)):
        raise WriteRefusal("section and name are not strings")
    for part in WRITE_PARTS:
        problem = part in rec and part_problem(rec, part)
        if problem:
            raise WriteRefusal(problem)
    if "heading" in rec:
        problem = one_line(rec["heading"], "heading")
        if problem:
            raise WriteRefusal(problem)
    return rewrite


def rewritten_block(config, lines, rec):
    """((start, end), block) for a rewrite: the range of the rule it replaces,
    and the rule with the parts the record names put in place of the old ones.
    """
    rid = rec["id"]
    rule = config.by_id().get(rid)
    if rule is None:
        raise WriteRefusal("%s has no rule %s to rewrite" % (config.rel(), rid))
    if rec.get("expect") != rule.body_text():
        raise WriteRefusal(
            "the body of %s is not what expect holds; it changed since it was "
            "read, so run config list --json and rebuild this record" % rid
        )
    if not any(part in rec for part in WRITE_PARTS):
        raise WriteRefusal("the record names no part of %s to rewrite" % rid)
    start, end, prose = rule_parts(lines, rule)
    example = {"before": rule.before, "after": rule.after} if rule.before is not None else None
    block = rule_block(
        rid,
        rec.get("title", rule.title),
        rec["body"].strip("\n").split("\n") if "body" in rec else prose,
        rec.get("patterns", [source for _l, source in rule.patterns]),
        rec.get("example", example),
    )
    return (start, end), block


def new_block(config, lines, rec, opened):
    """((position, heading to open or None), block) for a new rule.

    opened maps each section a record earlier in the batch opened to its spot,
    so a later rule in that section goes under the same heading.
    """
    _, problem = config.check_id(rec["section"], rec["name"])
    if problem:
        raise WriteRefusal(problem)
    section, heading = rec["section"], rec.get("heading")
    mine = [r for r in config.rules if r.section == section]
    known = bool(mine) or section in opened
    if heading is not None and known:
        raise WriteRefusal(
            "heading opens a new section, and %s already has rules in %s" % (config.rel(), section)
        )
    if heading is None and not known:
        raise WriteRefusal(
            "%s has no rule in section %s; give heading, the ## heading "
            "to open the section under" % (config.rel(), section)
        )
    if mine:
        spot = (heading_end(lines, mine[-1].line - 1), None)
    else:
        spot = opened.get(section, (len(lines), heading))
    block = rule_block(
        "%s-%s" % (section, rec["name"]),
        rec["title"],
        rec["body"].strip("\n").split("\n"),
        rec.get("patterns"),
        rec.get("example"),
    )
    return spot, block


def plan_writes(config, lines, records):
    """(the file's new lines, what was written, what was refused).

    Each written entry carries its rule's text as the file will hold it, and
    for a rewrite the text it replaces, for the page config write --dry-run
    writes.

    Each record is checked against the file as read and against the records
    accepted before it, so a second rule in a section new to the file goes
    under the heading the first opened. A record is refused whole: on a
    malformed field, a name check_id refuses, an id written twice, a rewrite
    of an id the file does not have or whose body changed since expect was
    read, and a block that would not lint on its own.
    """
    opened, seen = {}, {}
    spots, replaced, written, refused = {}, {}, [], []
    for n, rec in enumerate(records, 1):
        rid = record_id(rec)
        try:
            rewrite = checked_fields(rec)
            if rid in seen:
                raise WriteRefusal("%s is written by record %d too" % (rid, seen[rid]))
            if rewrite:
                where, block = rewritten_block(config, lines, rec)
            else:
                where, block = new_block(config, lines, rec, opened)
            alone = Config(config.path, config.rel(), LINT_FRONT + "".join(block))
            if alone.errors:
                raise WriteRefusal("; ".join(e.split("  ", 1)[-1] for e in alone.errors))
        except WriteRefusal as exc:
            refused.append({"index": n, "id": rid, "reason": str(exc)})
            continue
        seen[rid] = n
        if rewrite:
            replaced[where] = block
            old = "".join(lines[where[0] : where[1]])
        else:
            opened.setdefault(rec["section"], where)
            spots.setdefault(where, []).append(block)
            old = None
        written.append(
            {
                "id": rid,
                "change": WRITTEN_REWRITE if rewrite else WRITTEN_NEW,
                "old": old,
                "new": "".join(block),
            }
        )
    return place_blocks(lines, spots, replaced), written, refused


def rules_token(config, raw):
    """The token config write --dry-run prints and config write requires.

    A sha256 over the batch's bytes and prose-style.md's bytes, so a batch
    edited after the author read the page, or a file changed under it, is
    refused. --partial is left out: a batch the dry run refused part of shows
    no token unless --partial was given, and config write without it refuses
    that batch whole.
    """
    digest = TokenHash()
    digest.part(RULES_TOKEN_DOMAIN)
    digest.part(raw)
    digest.document(config.path)
    return digest.token()


def rules_markdown(rel, written, errors, token):
    """The rules config write --dry-run would write, as markdown: what the
    author reads whole, and approves.

    Each rule sits in a fence as the file will hold it, and a rewrite shows
    the rule as the file holds it now above it.
    """
    out = ["# Rules to write", "", "Into `%s`." % rel]
    if errors:
        out += ["", "## Refused", "", "Settle these and run config write --dry-run again:", ""]
        out += ["- %s" % e for e in errors]
    for w in written:
        if w["change"] == WRITTEN_REWRITE:
            out += ["", "## Rewrite `%s`, at line %d" % (w["id"], w["line"])]
            out += ["", "Now:", "", fenced(w["old"], RULES_FENCE_INFO)]
            out += ["", "Becomes:", "", fenced(w["new"], RULES_FENCE_INFO)]
        else:
            out += ["", "## New `%s`, at line %d" % (w["id"], w["line"])]
            out += ["", fenced(w["new"], RULES_FENCE_INFO)]
    out += ["", "%d rule(s) to write." % len(written)]
    if token:
        out += ["", "%s`%s`" % (TOKEN_LABEL.capitalize(), token)]
    return "\n".join(out) + "\n"


def config_write(args, repo, config):
    """Write approved rules into prose-style.md from a JSON batch.

    update-prose-config's step 6. A record is either a new rule (section,
    name, title, body, and optionally example, patterns and heading) or a
    rewrite (id, expect, and any of title, body, example and patterns). Writes
    nothing while any record is refused unless --partial is passed, and
    nothing at all when the result would not lint clean.

    --dry-run also writes the rules as the file would hold them to
    .prose-tuning/rules.md, and prints a token when it would write any.
    Without --dry-run, config write takes that token, and writes nothing when
    the batch or the file changed since.
    """
    if config.errors:
        raise Fatal(
            "%s does not lint clean; run: prose.py config lint" % config.rel()
            + ("" if not args.config_file else " --file %s" % config.path)
        )
    raw, records = read_json_bytes(args.batch, "the batch")
    if not isinstance(records, list):
        raise Fatal("the batch is not a JSON list of records")
    if not args.dry_run and args.token is None:
        raise Fatal(RULES_TOKEN_MISSING)
    token = rules_token(config, raw)
    data = {
        "path": config.rel(),
        "dry_run": args.dry_run,
        "written": [],
        "refused": [],
        "token": None,
        "rules": None,
    }
    if not args.dry_run and args.token != token:
        stale = RULES_TOKEN_STALE % config.rel()
        return emit(args, "config write", repo.root, data, errors=[stale])

    lines = Text.read(config.path).lines
    out, written, refused = plan_writes(config, lines, records)
    errors = ["record %d (%s): %s" % (r["index"], r["id"], r["reason"]) for r in refused]
    if refused and not args.partial:
        errors.append("nothing was written; fix the records named, or pass --partial")
        written = []
    result = Config(config.path, config.rel(), "".join(out))
    if written and result.errors:
        errors += result.errors
        errors.append("nothing was written; the result would not lint clean")
        written = []
    if written and not args.dry_run:
        Text("".join(out)).write(config.path)

    at = {r.id: r.line for r in result.rules}
    for w in written:
        w["line"] = at[w["id"]]
    data["written"] = written
    data["refused"] = refused
    if args.dry_run:
        # No token for a batch that would write nothing: there is nothing to
        # approve.
        data["token"] = token if written else None
        page = rules_markdown(config.rel(), written, errors, data["token"])
        data["rules"] = write_page(repo, RULES_FILE, page)
    for w in written:
        # The page holds the rules' text; stdout names them.
        del w["old"], w["new"]

    def human():
        verb = "would write" if args.dry_run else "wrote"
        for w in written:
            print("%s  %s  %s at line %d" % (verb, w["id"], w["change"], w["line"]))
        for r in refused:
            print("refused  record %d  %s" % (r["index"], r["id"]))
        if data["token"]:
            print(TOKEN_LABEL + data["token"])

    return emit(args, "config write", repo.root, data, errors=errors, human=human)


# config resolve: the author's answers to adopt-prose's step 3. A pair under
# one id is a collision; a pair under two ids is a similar pair.
RESOLVE_TAKE = "take-source"
RESOLVE_KEEP = "keep-target"
RESOLVE_COMBINE = "combine"
RESOLVE_BOTH = "keep-both"
RESOLVE_DROP = "drop-source"
SAME_ID_RESOLUTIONS = (RESOLVE_TAKE, RESOLVE_KEEP, RESOLVE_COMBINE)
TWO_ID_RESOLUTIONS = (RESOLVE_BOTH, RESOLVE_COMBINE, RESOLVE_DROP)
ANSWER_FIELDS = frozenset(("source", "target", "resolution", "expect", *WRITE_PARTS))
EXPECT_SIDES = ("source", "target")


def checked_answer(config, target, ans):
    """(source rule, target rule) for one answer. Raises WriteRefusal on a
    field that is unknown, missing or malformed, a rule either file lacks, a
    body that changed since expect was read, and a resolution the pair's kind
    does not offer.
    """
    if not isinstance(ans, dict):
        raise WriteRefusal("answer is not an object")
    unknown = sorted(set(ans) - ANSWER_FIELDS)
    if unknown:
        raise WriteRefusal(
            "unknown field %s; an answer takes %s"
            % (", ".join(unknown), ", ".join(sorted(ANSWER_FIELDS)))
        )
    missing = [f for f in ("source", "target", "resolution", "expect") if f not in ans]
    if missing:
        raise WriteRefusal("an answer needs %s" % ", ".join(missing))
    if not all(isinstance(ans[f], str) for f in ("source", "target", "resolution")):
        raise WriteRefusal("source, target and resolution are not strings")
    expect = ans["expect"]
    if not (
        isinstance(expect, dict)
        and set(expect) == set(EXPECT_SIDES)
        and all(isinstance(v, str) for v in expect.values())
    ):
        raise WriteRefusal("expect is not an object with source and target bodies")
    rules = []
    for side, cfg in zip(EXPECT_SIDES, (config, target)):
        rule = cfg.by_id().get(ans[side])
        if rule is None:
            raise WriteRefusal("%s has no rule %s" % (cfg.rel(), ans[side]))
        if expect[side] != rule.body_text():
            raise WriteRefusal(
                "the body of %s in %s is not what expect holds; it changed since it was "
                "read, so run config classify again and put the pair to the author again"
                % (rule.id, cfg.rel())
            )
        rules.append(rule)
    offered = SAME_ID_RESOLUTIONS if ans["source"] == ans["target"] else TWO_ID_RESOLUTIONS
    if ans["resolution"] not in offered:
        raise WriteRefusal(
            "%s does not settle a %s; it takes %s"
            % (
                ans["resolution"],
                "collision" if ans["source"] == ans["target"] else "pair under two ids",
                ", ".join(offered),
            )
        )
    parts = [p for p in WRITE_PARTS if p in ans]
    if parts and ans["resolution"] != RESOLVE_COMBINE:
        raise WriteRefusal("only %s takes %s" % (RESOLVE_COMBINE, ", ".join(parts)))
    for part in parts:
        problem = part_problem(ans, part)
        if problem:
            raise WriteRefusal(problem)
    return rules[0], rules[1]


def plan_resolutions(config, source_lines, target, target_lines, answers):
    """(the target's new lines, the answers taken, the answers refused).

    take-source puts the source's rule in place of the target's, byte for
    byte as config adopt copies one. combine rewrites the target's rule with
    the parts the answer gives, under the target's id, as config write
    rewrites one. keep-both copies the source's rule in as config adopt does.
    keep-target and drop-source write nothing. A source rule is answered once,
    and a target rule is written once. Every range is read from the target as
    given, so an earlier answer cannot move a later one.
    """
    taken, refused, kept = [], [], []
    replaced, answered, written = {}, {}, {}
    for n, ans in enumerate(answers, 1):
        try:
            src, tgt = checked_answer(config, target, ans)
            how = ans["resolution"]
            if src.id in answered:
                raise WriteRefusal("%s is answered by answer %d too" % (src.id, answered[src.id]))
            if how in (RESOLVE_TAKE, RESOLVE_COMBINE) and tgt.id in written:
                raise WriteRefusal("%s is written by answer %d too" % (tgt.id, written[tgt.id]))
            if how == RESOLVE_BOTH and src.id in target.by_id():
                raise WriteRefusal("%s already has %s" % (target.rel(), src.id))
            block = None
            if how == RESOLVE_TAKE:
                block = adopted_block(source_lines, src)
            elif how == RESOLVE_COMBINE:
                rec = {"id": tgt.id, "expect": tgt.body_text()}
                rec.update((p, ans[p]) for p in WRITE_PARTS if p in ans)
                _, block = rewritten_block(target, target_lines, rec)
                alone = Config(target.path, target.rel(), LINT_FRONT + "".join(block))
                if alone.errors:
                    raise WriteRefusal("; ".join(e.split("  ", 1)[-1] for e in alone.errors))
        except WriteRefusal as exc:
            named = ans if isinstance(ans, dict) else {}
            refused.append(
                {
                    "index": n,
                    "source": named.get("source"),
                    "target": named.get("target"),
                    "reason": str(exc),
                }
            )
            continue
        answered[src.id] = n
        if block is not None:
            written[tgt.id] = n
            start, end, _ = rule_parts(target_lines, tgt)
            replaced[(start, end)] = block
        if how == RESOLVE_BOTH:
            kept.append(src)
        taken.append({"index": n, "source": src.id, "target": tgt.id, "resolution": how})
    kept.sort(key=lambda r: r.line)
    spots = adoption_spots(source_lines, target, target_lines, kept)
    return place_blocks(target_lines, spots, replaced), taken, refused


def config_resolve(args, repo, config):
    """Write the author's answer to each colliding and similar pair into --to.

    adopt-prose's step 3. Each answer names a source rule, the target rule it
    was paired with, the resolution, and both bodies as config classify read
    them.
    Writes nothing while any answer is refused unless --partial is passed, and
    nothing at all when the result would not lint clean.
    """
    target = linted_target(args, config)
    answers = read_json(args.answers, "the answers")
    if not isinstance(answers, list):
        raise Fatal("the answers are not a JSON list")
    source_lines = Text.read(config.path).lines
    target_lines = Text.read(target.path).lines
    out, taken, refused = plan_resolutions(config, source_lines, target, target_lines, answers)
    errors = [
        "answer %d (%s -> %s): %s" % (r["index"], r["source"], r["target"], r["reason"])
        for r in refused
    ]
    if refused and not args.partial:
        errors.append("nothing was written; fix the answers named, or pass --partial")
        taken = []
    result = Config(target.path, target.rel(), "".join(out))
    if taken and result.errors:
        errors += result.errors
        errors.append("nothing was written; the result would not lint clean")
        taken = []
    if taken:
        Text("".join(out)).write(target.path)

    at = {r.id: r.line for r in result.rules}
    written = {RESOLVE_TAKE: "target", RESOLVE_COMBINE: "target", RESOLVE_BOTH: "source"}
    copied = [t["source"] for t in taken if t["resolution"] in (RESOLVE_TAKE, RESOLVE_BOTH)]
    data = {
        "commit_note": ADOPTED_NOTE % (adopted_from(config), ", ".join(copied)) if copied else None,
        "resolved": taken,
        "refused": refused,
    }

    def human():
        for t in taken:
            side = written.get(t["resolution"])
            where = "  at line %d" % at[t[side]] if side else ""
            print("%s  %s -> %s%s" % (t["resolution"], t["source"], t["target"], where))
        for r in refused:
            print("refused  answer %d  %s" % (r["index"], r["source"]))
        if data["commit_note"]:
            print("\nfor the commit description: %s" % data["commit_note"])

    return emit(args, "config resolve", repo.root, data, errors=errors, human=human)


def cmd_config(args):
    repo, config, scope = load(args)
    which = args.config_cmd

    if which == "move":
        return config_move(args, repo, config)

    if which == "init":
        if config.exists:
            raise Fatal("%s already exists" % config.path)
        os.makedirs(os.path.dirname(config.path), exist_ok=True)
        if args.source:
            if not os.path.exists(args.source):
                raise Fatal("%s does not exist" % args.source)
            Text(Text.read(args.source).s).write(config.path)
        elif not args.empty:
            shipped = Text.read(shipped_template()).s
            name = repo.project_name()
            Text(shipped.replace(PROJECT_NAME_SLOT, name)).write(config.path)
        else:

            def fmt(xs):
                return "\n".join('    - "%s"' % x for x in xs)

            Text(
                CONFIG_SKELETON.format(
                    name=repo.project_name(),
                    include=fmt(DEFAULT_INCLUDE),
                    exclude=fmt(DEFAULT_EXCLUDE),
                )
            ).write(config.path)
        return emit(
            args,
            "config init",
            repo.root,
            {"path": config.path},
            human=lambda: print("wrote %s" % config.path),
        )

    if not config.exists:
        if not args.config_file and os.path.exists(legacy_config_path(repo)):
            raise Fatal("%s does not exist; run: prose.py config move" % config.path)
        raise Fatal("%s does not exist; run: prose.py config init" % config.path)

    if which == "adopt":
        return config_adopt(args, repo, config)

    if which == "write":
        return config_write(args, repo, config)

    if which == "resolve":
        return config_resolve(args, repo, config)

    if which == "check-id":
        rid, problem = config.check_id(args.section, args.name)
        return emit(
            args,
            "config check-id",
            repo.root,
            {"id": rid, "section": args.section, "name": args.name, "free": problem is None},
            errors=([problem] if problem else []),
            # The id goes to stdout only when it is usable, so that
            # ID=$(... check-id ...) cannot capture a refused one.
            human=lambda: problem or print(rid),
        )

    if which == "classify":
        other = linted_target(args, config)
        rules = classify_rules(config, other)
        counts = {b: sum(1 for r in rules if r["bucket"] == b) for b in BUCKETS}

        def human():
            w = max([len(r["id"]) for r in rules] + [8])
            for r in rules:
                arrow = "  -> %s" % r["target"] if r["target"] else ""
                print("%-9s  %-*s%s" % (r["bucket"], w, r["id"], arrow))
            print("\n" + ", ".join("%d %s" % (counts[b], b) for b in BUCKETS))

        return emit(
            args,
            "config classify",
            repo.root,
            {"rules": rules},
            human=human,
        )

    if which == "lint":

        def human():
            print(
                "%s: %d rule(s), %d error(s), %d warning(s)"
                % (config.rel(), len(config.rules), len(config.errors), len(config.warnings))
            )

        return emit(
            args,
            "config lint",
            repo.root,
            {"rules": len(config.rules)},
            errors=config.errors,
            warnings=config.warnings,
            human=human,
        )

    rules = config.rules
    if args.rule:
        rules = [r for r in rules if r.id == args.rule]
        if not rules:
            raise Fatal("no rule with id %s in %s" % (args.rule, config.rel()))
    data = {"path": config.rel(), "front": config.front, "rules": [r.as_dict() for r in rules]}

    def human():
        if args.ids:
            for r in rules:
                print(r.id)
            return
        w = max([len(r.id) for r in rules] + [16])
        for r in rules:
            mark = " " if (r.before or r.after) else "!"
            print("%s %-*s %s" % (mark, w, r.id, r.title))
        print(
            "\n%d rule(s)%s"
            % (
                len(rules),
                "; ! marks one with no worked example"
                if any(not (r.before or r.after) for r in rules)
                else "",
            )
        )

    # list reads the rules; lint checks the file. Repeating lint's warnings
    # here would bury the listing under them on every call.
    return emit(args, "config list", repo.root, data, human=human)


def cmd_tags(args):
    repo, config, scope = load(args)
    which = args.tags_cmd
    targets = scope.files()

    errors, warnings, resolved = [], [], {}
    pending = []
    for rel in targets:
        path = repo.abspath(rel)
        if not os.path.exists(path):
            continue
        text = Text.read(path)
        blocks = Blocks(text)
        scanner = TagScanner(text, blocks, rel)
        if scanner.errors:
            errors += scanner.errors
            continue
        if not scanner.all:
            continue
        pending.append((path, rel, resolve_scanned(text, scanner, ACCEPT), len(scanner.all)))
        warnings += resolve_warnings(scanner, text)
    if errors:
        errors.append("nothing was written; fix the markup and re-run")
        return emit(args, "tags " + which, repo.root, {}, errors=errors, warnings=warnings)
    for path, rel, new, count in pending:
        resolved[rel] = count
        if not args.dry_run:
            Text(new).write(path)

    def human():
        for rel in sorted(resolved):
            print(
                "%s  %d tag(s) %s"
                % (rel, resolved[rel], "would be resolved" if args.dry_run else "resolved")
            )
        if not resolved:
            print("no markup found")

    return emit(args, "tags " + which, repo.root, {}, warnings=warnings, human=human)


# The kinds a finding may cross lines within. Anything else between two lines
# of prose, such as a blank line, a heading or a table row, is structure that
# a rewrite across it would erase.
SPANNING_KINDS = ("paragraph", "list-item")
# The field a finding carries in place of `replacement` for a match that stays.
DISMISS_KEY = "dismiss"
# What to run again when a finding's text is no longer where it was addressed.
REPORT_RERUN = "Re-run the report."
# The refusal of an empty span, which would insert rather than rewrite.
EMPTY_SPAN = "%s: the text is empty, so this would insert; rewrite the text beside the gap instead"


def locate(text, line, f, label):
    """The absolute (start, end) that a finding covers, or (None, why not).

    The text in f["text"] is looked for among the places that start on its
    line, and it has to start at exactly one of them. col_start says which,
    and the span runs as far as the text does, onto a later line if the text
    holds a newline. An empty text is refused: a finding rewrites text, and
    the text beside a gap is what to rewrite. label names the finding in a
    refusal.
    """
    width = len(text.bare(line))
    base = text.offset(line)
    want = f.get("text")
    if want is None:
        return None, "%s has no text; copy it from the segment it rewrites" % label
    if "col_end" in f:
        return None, (
            "%s has col_end; leave it out, and give col_start only when the text "
            "starts at more than one place on the line" % label
        )
    if want == "":
        return None, EMPTY_SPAN % label
    col_start = f.get("col_start")
    if col_start is not None:
        col_start = int(col_start)
        # Text.offset validates the line and then adds the column blind, so
        # a column past the end of its line resolves somewhere further down
        # the file and this would rewrite a passage nobody approved.
        if not 0 <= col_start <= width:
            return None, "column %d is outside the line (%d characters)" % (col_start, width)
        a = base + col_start
        b = a + len(want)
    else:
        # Up to and including the line's end, so a text that starts with the
        # newline, to join this line to the next, still has a place to start.
        starts = [c for c in range(width + 1) if text.s.startswith(want, base + c)]
        if not starts:
            return None, "%s: %r does not start on this line. %s" % (label, want[:60], REPORT_RERUN)
        if len(starts) > 1:
            return None, (
                "%s: %r starts at columns %s on this line; add col_start to say which"
                % (label, want[:60], ", ".join(str(c) for c in starts))
            )
        a = base + starts[0]
        b = a + len(want)
    current = text.s[a:b]
    if current != want:
        return None, "the text moved; expected %r, found %r. %s" % (
            want[:60],
            current[:60],
            REPORT_RERUN,
        )
    return (a, b), None


class FindingLabel:
    """Which findings an edit carries out, for a message that names them.

    An edit is one finding's, except the removal of a run of cut lines, which
    carries out every finding in the run.
    """

    def __init__(self, refs):
        self.refs = refs

    def __str__(self):
        return " and ".join(
            "finding %d (%s:%d, %s)" % (r["finding"], r["file"], r["line"], r["rule"])
            for r in self.refs
        )


def plan_findings(text, blocks, rel, findings, numbers=None):
    """Plan one file's approved findings against one snapshot of it.

    Returns (new text or None, applied, rejected). The new text is None only
    when the batch as a whole cannot be applied, as when two findings overlap,
    and the rejection then names both. Nothing is written here; cmd_apply
    decides that. stage_findings does the planning.
    """
    staged = stage_findings(text, blocks, rel, findings, numbers)
    try:
        return staged.engine.result(), staged.applied, staged.rejected
    except Fatal as exc:
        staged.rejected.append("%s  %s" % (rel, exc))
        return None, staged.applied, staged.rejected


class Staged:
    """One file's findings, checked and turned into edits, not yet applied.

    `accepted` holds (finding number, finding, start, end) for each finding
    that passed its checks, `applied` and `rejected` what plan_findings
    returns, and `engine` the edits, labeled with the findings they carry out.
    `dismissed` holds the same four for each dismissal that passed, which
    makes no edit.
    """

    def __init__(self, engine, accepted, applied, rejected, dismissed):
        self.engine = engine
        self.accepted = accepted
        self.applied = applied
        self.rejected = rejected
        self.dismissed = dismissed


def stage_findings(text, blocks, rel, findings, numbers=None):
    """Check one file's findings and turn the ones that pass into edits.

    `numbers` are the findings' places in the whole batch, so a rejection can
    name one; they default to counting from 1.

    locate works out where each finding is. A finding whose span holds a
    newline crosses lines, and every line it reaches has to be a paragraph or
    a list item. Only such a finding, or one in a paragraph, may put a newline
    in its replacement. When the finding starts in a list item, including on
    a paragraph line that continues one, indent_new_lines keeps every new
    line inside the item.

    A line is cut when it has characters, every finding on it replaces with
    nothing, and together they cover the whole of it. Consecutive cut lines
    form a run, and the run is removed with its newlines as one edit in place
    of its findings' own edits. Without that, cutting a passage left a blank
    line for every line it had. cut_lines says when a finding keeps its own
    edit instead.

    Removing a paragraph that stood between two blank lines would leave those
    two blank lines touching, so a blank line beside a cut goes too when the
    line kept before it is blank, or when nothing is kept before or after it.
    The file keeps one blank line between the blocks either side of the cut,
    and no blank line at either end. A blank line that is protected or carries
    a finding of its own is left alone.

    A finding may cover a code span whole, so a sentence can be rewritten
    around one, but it may not start or end inside one, and its replacement
    has to hold every code span it covers, unchanged and in order. A code span
    quotes code, which a prose rule has nothing to say about.

    A dismissal passes the same checks on where it is, and then makes no edit.
    """
    engine = EditEngine(text)
    code_spans = blocks.code_span_offsets(blocks.protected_offsets())
    applied, rejected, accepted, placed, dismissed = [], [], [], [], []
    for n, f in zip(numbers or range(1, len(findings) + 1), findings):
        line = int(f.get("line", 0))
        if line < 1 or line > text.line_count():
            rejected.append("%s:%s  line is outside the file" % (rel, line))
            continue
        dismiss = f.get(DISMISS_KEY)
        if dismiss is not None:
            if "replacement" in f:
                rejected.append(
                    "%s:%d  finding %d has both dismiss and replacement; a dismissed "
                    "match stays as it is" % (rel, line, n)
                )
                continue
            if not isinstance(dismiss, str) or not dismiss.strip():
                rejected.append(
                    "%s:%d  finding %d: dismiss needs a reason the match stays" % (rel, line, n)
                )
                continue
        if blocks.is_protected(line):
            rejected.append(
                "%s:%d  is a %s; prose rules do not apply there" % (rel, line, blocks.kind(line))
            )
            continue
        span, problem = locate(text, line, f, "finding %d" % n)
        if problem:
            rejected.append("%s:%d  %s" % (rel, line, problem))
            continue
        a, b = span
        crossing = "\n" in text.s[a:b]
        reach = range(line, (text.line_of(b) if crossing else line) + 1)
        guarded = [ln for ln in reach if blocks.is_protected(ln)]
        if guarded:
            rejected.append(
                "%s:%d  is a %s; prose rules do not apply there"
                % (rel, guarded[0], blocks.kind(guarded[0]))
            )
            continue
        if crossing:
            wrong = [ln for ln in reach if blocks.kind(ln) not in SPANNING_KINDS]
            if wrong:
                kind = blocks.kind(wrong[0])
                rejected.append(
                    "%s:%d  finding %d crosses line %d, which is %s; a finding can cross "
                    "lines only within a paragraph or a list item"
                    % (rel, line, n, wrong[0], "blank" if kind == "blank" else "a " + kind)
                )
                continue
        if blocks.comment_overlaps(a, b):
            where = (
                "finding %d touches" % n
                if crossing
                else "columns %d-%d touch" % (a - text.offset(line), b - text.offset(line))
            )
            rejected.append(
                "%s:%d  %s an HTML comment; prose rules do not apply there" % (rel, line, where)
            )
            continue
        if any(x < b and a < y and not (a <= x and y <= b) for x, y in code_spans):
            where = (
                "finding %d cuts" % n
                if crossing
                else "columns %d-%d cut" % (a - text.offset(line), b - text.offset(line))
            )
            rejected.append(
                "%s:%d  %s into a code span; prose rules do not apply there" % (rel, line, where)
            )
            continue
        if dismiss is not None:
            dismissed.append((n, f, a, b))
            continue
        new = f.get("replacement", "")
        if blocks.kind(line) == "table" and ("|" in text.s[a:b] + new or "\n" in new):
            rejected.append(
                "%s:%d  a table rewrite cannot add or remove a | or add a newline" % (rel, line)
            )
            continue
        if "\n" in new and blocks.kind(line) != "paragraph" and not crossing:
            rejected.append(
                "%s:%d  a %s replacement cannot span lines" % (rel, line, blocks.kind(line))
            )
            continue
        item = blocks.item(line)
        if item:
            new = indent_new_lines(new, item[1])
        lost = dropped_code_span(text.s, new, [(x, y) for x, y in code_spans if a <= x < y <= b])
        if lost:
            rejected.append(
                "%s:%d  finding %d's replacement does not keep the code span %s as it was"
                % (rel, line, n, lost)
            )
            continue
        touched = set(range(line, (text.line_of(b - 1) if b > a else line) + 1))
        ref = {"finding": n, "file": rel, "line": line, "rule": f["rule"]}
        accepted.append((a, b, new, touched, ref))
        placed.append((n, f, a, b))
        applied.append({"file": rel, "line": line, "rule": f["rule"]})

    cut = cut_lines(text, accepted)
    for a, b, new, touched, ref in accepted:
        if not touched <= cut:
            engine.replace(a, b, new, FindingLabel([ref]))
    marked = set().union(*(x[3] for x in accepted))
    for start, end in cut_runs(text, blocks, cut, marked):
        inside = [x[4] for x in accepted if x[3] <= cut and start <= x[0] and x[1] <= end]
        engine.replace(start, end, "", FindingLabel(inside) if inside else None)
    return Staged(engine, placed, applied, rejected, dismissed)


def dropped_code_span(s, new, covered):
    """The first of the code spans `covered` that `new` does not hold, or None.

    Each span has to turn up in `new` after the one before it, so a
    replacement that reorders two spans, or holds one span twice in place of
    two, loses one.
    """
    pos = 0
    for x, y in covered:
        at = new.find(s[x:y], pos)
        if at < 0:
            return s[x:y]
        pos = at + (y - x)
    return None


def indent_new_lines(new, column):
    """`new` with every line after its first indented to at least `column`.

    A replacement in a list item that starts a line at column 0 ends the item
    there, and a line starting with `-`, `#` or `1.` turns into a block of its
    own. A line already indented that far is left as the model wrote it, and
    so is an empty one, since a blank line inside an item needs no indent.
    """
    first, *rest = new.split("\n")
    out = [first]
    for piece in rest:
        lead = len(piece) - len(piece.lstrip(" "))
        out.append(" " * (column - lead) + piece if piece and lead < column else piece)
    return "\n".join(out)


def cut_lines(text, accepted):
    """The lines whose every character an accepted finding replaces with nothing.

    A line with any non-empty replacement on it is kept, even if deletions
    around it cover the rest, because the replacement has to land somewhere.

    So is a line covered by a finding that also reaches into a line that is
    kept. That finding's own edit removes the newline between the two, and a
    run removing the covered line as well would overlap it. Keeping one line
    can leave another finding in the same position, so this repeats until
    nothing changes.
    """
    spans, kept = {}, set()
    for a, b, new, touched, _ref in accepted:
        if new:
            kept |= touched
        for line in touched:
            start = text.offset(line)
            end = start + len(text.bare(line))
            spans.setdefault(line, []).append((max(a, start) - start, min(b, end) - start))
    out = set()
    for line, parts in spans.items():
        width = len(text.bare(line))
        if not width or line in kept:
            continue
        reach = 0
        for col_start, col_end in sorted(parts):
            if col_start > reach:
                break
            reach = max(reach, col_end)
        if reach == width:
            out.add(line)
    changed = True
    while changed:
        changed = False
        for _a, _b, _new, touched, _ref in accepted:
            if touched & out and not touched <= out:
                out -= touched
                changed = True
    return out


def cut_runs(text, blocks, cut, touched):
    """(start, end) offsets that remove each run of cut lines, newlines included.

    plan_findings says why a blank line beside a cut can go too. The blank
    lines are chosen against the lines that survive, not run by run, because
    two cuts either side of one blank line would otherwise both claim it.
    """

    def loose(n):
        return (
            not text.bare(n).strip()
            and not blocks.is_protected(n)
            and n not in touched
            and (n - 1 in cut or n + 1 in cut)
        )

    last = text.line_count()
    removed = set(cut)
    kept = []
    for n in range(1, last + 1):
        if n in cut:
            continue
        if loose(n) and (not kept or not text.bare(kept[-1]).strip()):
            removed.add(n)
            continue
        kept.append(n)
    while kept and loose(kept[-1]):
        removed.add(kept.pop())

    out = []
    for n in sorted(removed):
        if out and out[-1][1] == n - 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    spans = []
    for first, final in out:
        start = text.offset(first)
        end = text.offset(final + 1) if final < last else text.end
        # The file ended without a newline. Taking the one before the run
        # keeps it that way rather than leaving a newline the file never had.
        if final == last and not text.line(last).endswith("\n") and first > 1:
            start -= len(text.line(first - 1)) - len(text.bare(first - 1))
        spans.append((start, end))
    return spans


FINDINGS_HELP = """\
findings:
  Each finding is one JSON object with these fields.

  file         the document, relative to the repository root
  line         the 1-indexed line the finding starts on
  rule         the one rule id it applies, from prose-style.md
  text         the text as it stands, copied exactly; every finding needs
               one. apply finds it among the places that start on the
               line and refuses a finding with no text, or whose text
               starts at none of them, or at more than one. A
               text holding a newline ends on a later line, so a wrapped
               sentence is one finding. A finding with an empty text
               would insert, so apply refuses it. Rewrite the text beside
               the gap instead
  replacement  the rewrite; "" cuts the text, and a line cut whole goes
               with its newline. Defaults to ""
  dismiss      in place of replacement: why a pattern's match stays as it
               is, such as a hyphen that is a minus sign. apply leaves the
               text alone, report lists the reason, and a finding with both
               dismiss and replacement is refused
  col_start    optional: the 0-indexed column the text starts at, when it
               starts at more than one place on the line. It is the only
               column a finding takes; apply refuses a col_end

  A replacement may hold a newline when the finding starts in a paragraph,
  or when its span already crosses a line. A span can cross lines only
  within paragraphs and list items. In a list item, apply indents each new
  line to the item's text, so it stays in the item. A table cell's
  replacement can hold neither a newline nor a |.

  report runs every rule's pattern over every file in scope, and fails on a
  match that no finding or dismissal of the same rule contains.

example:
  [{"file": "notes.md", "line": 12, "rule": "sentences-own-subject",
    "text": "Able to state\\n  what is inside the file.",
    "replacement": "A reader can state what is inside the file."}]
"""


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
        # A leading byte tells a missing file from an empty one, so creating
        # or deleting a document changes the token too.
        if not os.path.isfile(path):
            self.digest.update(b"-")
            return
        self.digest.update(b"+")
        with open(path, "rb") as fh:
            self.part(fh.read())

    def token(self):
        return self.digest.hexdigest()[:TOKEN_LENGTH]


def approval_token(repo, config, raw, findings, paths):
    """The token report prints and apply requires, for this batch as it is now.

    A sha256 over the findings' bytes, the path and bytes of every document any
    finding names, and prose-style.md's bytes. report takes no filter, so the
    token covers every finding it printed. apply's --only and --file are left
    out: they select within the approved set, so they must not change what
    was approved. The files report was given are what it checked for
    uncovered matches, so the token covers their paths and bytes too, and
    apply has to be given the same ones.
    """
    digest = TokenHash()
    digest.part(raw)
    names = set()
    if isinstance(findings, list):
        for f in findings:
            if isinstance(f, dict) and isinstance(f.get("file"), str):
                names.add(os.path.normpath(f["file"]))
    for rel in sorted(names):
        digest.part(rel.encode("utf-8"))
        digest.document(repo.abspath(rel))
    digest.document(config.path)
    checked = sorted(set(os.path.normpath(p) for p in paths))
    if checked:
        # A marker part, so the named files cannot hash the same as more
        # documents the findings name.
        digest.part(TOKEN_CHECKED)
    for rel in checked:
        digest.part(rel.encode("utf-8"))
        digest.document(repo.abspath(rel))
    return digest.token()


def select_findings(config, findings, only=None, file=None):
    """The findings apply's --only and --file keep, by file, and the ones refused.

    `only` and `file` are the flags as argparse gives them; report passes
    neither and gets every finding. Returns (by_file, rejected). by_file maps
    each file to its findings as (place in the whole batch, counting from 1,
    finding).
    """
    only = set(x.strip() for x in only.split(",")) if only else None
    files = set(os.path.normpath(p) for p in file) if file else None
    known = config.by_id()

    # The filters are how an approval by rule or by file reaches apply, so
    # the model never trims the findings by hand. They combine: a finding is
    # kept only if it passes both.
    by_file, rejected = {}, []
    for n, f in enumerate(findings):
        if only and f.get("rule") not in only:
            continue
        if files and os.path.normpath(f.get("file") or "") not in files:
            continue
        if f.get("rule") not in known:
            rejected.append(
                "finding %d names rule %r, which is not in %s"
                % (n + 1, f.get("rule"), config.rel())
            )
            continue
        by_file.setdefault(f.get("file"), []).append((n + 1, f))

    # A filter that selects nothing is almost always a typo. Left alone it
    # would write nothing and exit clean, which reads as success.
    rules_seen = set(f.get("rule") for f in findings)
    files_seen = set(os.path.normpath(f.get("file") or "") for f in findings)
    unmatched = [
        "--only %s matches no finding" % r for r in sorted(only or ()) if r not in rules_seen
    ]
    unmatched += [
        "--file %s matches no finding" % p for p in sorted(files or ()) if p not in files_seen
    ]
    if not unmatched and (only or files) and not by_file and not rejected:
        unmatched.append("--only and --file together match no finding")
    rejected.extend(unmatched)
    return by_file, rejected


def selected_files(repo, by_file, rejected):
    """(path, rel, text, numbers, findings) for each selected file that exists.

    A file that does not exist is added to `rejected` instead.
    """
    out = []
    for rel in sorted(by_file):
        path = repo.abspath(rel) if rel else None
        if not rel or not os.path.exists(path):
            rejected.append("%s  no such file" % rel)
            continue
        numbers = [n for n, _f in by_file[rel]]
        mine = [f for _n, f in by_file[rel]]
        out.append((path, rel, Text.read(path), numbers, mine))
    return out


# What the report shows for an empty proposed text, which would otherwise
# print as nothing at all and read as a finding with its rewrite missing.
REPORT_CUT = "(cut)"
REPORT_LABEL_WIDTH = len("proposed") + 2
# Each line of a current or proposed text is printed between these, so a
# space at either end of it shows. A finding's text often starts with one: the
# dash in "holds - until" is addressed as " - until".
REPORT_FENCE = "|"


def report_text(value):
    """A current or proposed text as the report prints it: each line fenced,
    or the unfenced REPORT_CUT when the text is empty. Only a proposed text
    can be, since locate refuses an empty span.

    The placeholder stays unfenced so it cannot be read as a text, even one
    that says "(cut)".
    """
    if not value:
        return REPORT_CUT
    return "\n".join(REPORT_FENCE + ln + REPORT_FENCE for ln in value.split("\n"))


def report_field(label, value):
    """One labeled field of a report row, with a wrapped text's later lines
    indented under its first, so a newline in the text shows where it is.
    """
    pad = " " * (2 + REPORT_LABEL_WIDTH)
    lines = value.split("\n")
    out = ["  %-*s%s" % (REPORT_LABEL_WIDTH, label, lines[0])]
    out.extend(pad + ln for ln in lines[1:])
    return "\n".join(out)


def edit_refs(edit):
    """The findings an edit carries out, as FindingLabel holds them."""
    label = edit[3]
    return label.refs if isinstance(label, FindingLabel) else []


def uncovered_matches(repo, config, targets, findings):
    """Every pattern match in these files that no finding of the same rule contains.

    The files are the ones `patterns` reads when given the same paths, and
    must exist. Every finding in the batch counts, dismissals included. A
    finding that does not locate covers nothing.
    """
    by_file = {}
    for n, f in enumerate(findings, 1):
        if isinstance(f, dict) and isinstance(f.get("file"), str):
            by_file.setdefault(os.path.normpath(f["file"]), []).append((n, f))
    rules = config.patterned()
    out = []
    for rel in targets:
        text = Text.read(repo.abspath(rel))
        matches = pattern_matches(text, Blocks(text), rules)
        if not matches:
            continue
        spans = []
        for n, f in by_file.get(os.path.normpath(rel), []):
            try:
                line = int(f.get("line", 0))
            except (TypeError, ValueError):
                continue
            if not 1 <= line <= text.line_count():
                continue
            span, problem = locate(text, line, f, "finding %d" % n)
            if not problem:
                spans.append((f.get("rule"), span[0], span[1]))
        for m in matches:
            a = text.offset(m["line"]) + m["col_start"]
            b = text.offset(m["end_line"]) + m["col_end"]
            if not any(r == m["rule"] and x <= a and b <= y for r, x, y in spans):
                out.append(dict(m, file=rel))
    return out


def report_markdown(data, rejected):
    """The report as markdown: what the author reads whole, and approves.

    Each text sits in a fence between the same | marks stdout uses, so a
    space at either end shows on the page too.
    """
    out = ["# Prose report"]
    if rejected:
        out += ["", "## Refused", "", "Settle these and run report again:", ""]
        out += ["- %s" % e for e in rejected]
    for r in data["findings"] + data["dismissed"]:
        out += [
            "",
            "## Finding %d: `%s:%d`, `%s`" % (r["finding"], r["file"], r["line"], r["rule"]),
        ]
        out += ["", "Current:", "", fenced(report_text(r["current"]))]
        if "reason" in r:
            out += ["", "Dismissed: %s" % r["reason"]]
            continue
        out += ["", "Proposed:", "", fenced(report_text(r["proposed"]))]
    rows = data["findings"]
    out += ["", "%d finding(s) in %d file(s)." % (len(rows), len(set(r["file"] for r in rows)))]
    if data["dismissed"]:
        out.append("%d match(es) dismissed." % len(data["dismissed"]))
    out += [
        "",
        "Checked by pattern: %s. Every other rule was checked by reading."
        % (", ".join("`%s`" % r for r in data["checked_by_pattern"]) or "none"),
    ]
    if data["token"]:
        out += ["", "%s`%s`" % (TOKEN_LABEL.capitalize(), data["token"])]
    return "\n".join(out) + "\n"


def cmd_report(args):
    """The findings as the author approves them, read against the files now.

    The current text is what is at each finding's place in the file, not what
    the finding says is there, so the report cannot show one text and apply
    change another. A finding apply would refuse is an error here too, and so
    is each pair of findings apply could not do both of.

    It runs every rule's pattern itself, as `patterns` does over the same
    paths, and each match no finding or dismissal covers is an error, so a
    match the model left out fails the report rather than going unmentioned.
    It ends by naming those rules, so the author can tell them from the rules
    checked by reading.
    """
    repo, config, scope = load(args)
    raw, findings = read_json_file_bytes(args.findings, "findings")
    by_file, rejected = select_findings(config, findings)
    rows, overlaps, dismissed = [], [], []
    for _path, rel, text, numbers, mine in selected_files(repo, by_file, rejected):
        staged = stage_findings(text, Blocks(text), rel, mine, numbers)
        rejected.extend(staged.rejected)
        for n, f, a, b in staged.dismissed:
            dismissed.append(
                {
                    "finding": n,
                    "file": rel,
                    "line": int(f["line"]),
                    "rule": f["rule"],
                    "current": text.s[a:b],
                    "reason": f[DISMISS_KEY],
                }
            )
        for n, f, a, b in staged.accepted:
            rows.append(
                {
                    "finding": n,
                    "file": rel,
                    "line": int(f["line"]),
                    "rule": f["rule"],
                    "current": text.s[a:b],
                    "proposed": f.get("replacement", ""),
                }
            )
        for x, y in staged.engine.conflicts():
            overlaps.append({"first": edit_refs(x), "second": edit_refs(y)})
            rejected.append(
                "%s  %s overlaps %s, and they cannot both apply; "
                "put the pair to the author and keep the side they choose"
                % (rel, EditEngine.describe(x), EditEngine.describe(y))
            )
    rows.sort(key=lambda r: (r["file"], r["line"], r["finding"]))
    dismissed.sort(key=lambda r: (r["file"], r["line"], r["finding"]))
    uncovered = []
    if config.errors:
        # A pattern that cannot run would check nothing, and every match it
        # missed would pass as covered.
        rejected.extend(config.errors)
        rejected.append("%s  fix it first; see: prose.py config lint" % config.rel())
    else:
        targets = []
        for rel in args.paths or scope.files():
            if os.path.exists(repo.abspath(rel)):
                targets.append(rel)
            else:
                rejected.append("%s  no such file" % rel)
        uncovered = uncovered_matches(repo, config, targets, findings)
    rejected.extend(
        "%s  no finding or dismissal covers this match; add a finding that rewrites it, "
        "or a dismissal if it stays" % match_line(m["file"], m)
        for m in uncovered
    )
    patterned = [r.id for r in config.patterned()]
    # No token for a report that failed: the author cannot approve a batch
    # apply would refuse.
    token = None if rejected else approval_token(repo, config, raw, findings, args.paths)
    data = {
        "findings": rows,
        "dismissed": dismissed,
        "overlaps": overlaps,
        "uncovered": uncovered,
        "checked_by_pattern": patterned,
        "token": token,
    }
    data["report"] = write_page(repo, REPORT_FILE, report_markdown(data, rejected))

    def human():
        for r in rows:
            print("%s:%d  %s  (finding %d)" % (r["file"], r["line"], r["rule"], r["finding"]))
            print(report_field("current", report_text(r["current"])))
            print(report_field("proposed", report_text(r["proposed"])))
            print()
        for r in dismissed:
            print("%s:%d  %s  (finding %d)" % (r["file"], r["line"], r["rule"], r["finding"]))
            print(report_field("current", report_text(r["current"])))
            print(report_field("dismissed", r["reason"]))
            print()
        print("%d finding(s) in %d file(s)" % (len(rows), len(set(r["file"] for r in rows))))
        if dismissed:
            print("%d match(es) dismissed" % len(dismissed))
        print(
            "checked by pattern: %s. Every other rule was checked by reading."
            % (", ".join(patterned) or "none")
        )
        if token:
            print(TOKEN_LABEL + token)

    return emit(args, "report", repo.root, data, errors=rejected, human=human)


def cmd_apply(args):
    repo, config, _ = load(args)
    raw, findings = read_json_file_bytes(args.findings, "findings")
    if args.token != approval_token(repo, config, raw, findings, args.paths):
        stale = TOKEN_STALE % config.rel()
        return emit(args, "apply", repo.root, {"applied": []}, errors=[stale])
    by_file, rejected = select_findings(config, findings, args.only, args.file)
    staged, applied = [], []
    for path, rel, text, numbers, mine in selected_files(repo, by_file, rejected):
        new, done, refused = plan_findings(text, Blocks(text), rel, mine, numbers)
        applied.extend(done)
        rejected.extend(refused)
        if new is not None:
            staged.append((path, rel, new))

    if rejected and not args.partial:
        rejected.append("nothing was written; pass --partial to apply the rest")
        return emit(args, "apply", repo.root, {"applied": []}, errors=rejected)

    for path, _rel, new in staged:
        if not args.dry_run:
            Text(new).write(path)

    per_rule = {}
    for a in applied:
        per_rule[a["rule"]] = per_rule.get(a["rule"], 0) + 1
    data = {
        "applied": applied,
        "per_rule": per_rule,
        "files": sorted(set(a["file"] for a in applied)),
    }

    def human():
        for rel in data["files"]:
            n = sum(1 for a in applied if a["file"] == rel)
            print("%s  %d edit(s)" % (rel, n))
        for rid in sorted(per_rule):
            print("  %-16s %d" % (rid, per_rule[rid]))
        print(
            "\n%d edit(s) %s"
            % (len(applied), "not written (dry run)" if args.dry_run else "written")
        )

    return emit(args, "apply", repo.root, data, errors=rejected, human=human)


def fenced(text, info=PAGE_FENCE_INFO):
    """text in a code fence longer than any run of backticks inside it, so a
    diff or a markdown passage shows as it stands."""
    longest = max([len(run) for run in re.findall(r"`+", text)] + [2])
    fence = "`" * (longest + 1)
    return "%s%s\n%s\n%s" % (fence, info, text.rstrip("\n"), fence)


def question_refusals(n, q):
    """Why question n cannot go on the page, as a list of reasons."""
    if not isinstance(q, dict):
        return ["question %d is not a JSON object" % n]
    reasons = []
    if not isinstance(q.get("question"), str) or not q["question"].strip():
        reasons.append("question %d has no question text" % n)
    options = q.get("options")
    if not isinstance(options, list) or not options:
        reasons.append("question %d has no options" % n)
    else:
        for i, o in enumerate(options, 1):
            if not isinstance(o, dict) or not isinstance(o.get("label"), str) or not o["label"]:
                reasons.append("question %d, option %d has no label" % (n, i))
            elif not isinstance(o.get("description", ""), str):
                reasons.append("question %d, option %d has a description that is not text" % (n, i))
    evidence = q.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        reasons.append("question %d has no evidence" % n)
    elif not all(isinstance(e, str) and e.strip() for e in evidence):
        reasons.append("question %d has evidence that is not text" % n)
    return reasons


def questions_markdown(questions, refused):
    """The interview as the author reads it whole, or the refusals instead."""
    out = ["# Questions from update-prose-config", ""]
    if refused:
        out += ["Fix these questions and run questions again:", ""]
        out += ["- %s" % r for r in refused]
        return "\n".join(out) + "\n"
    out.append(
        "Answer each question by commenting on it and sending the comment to Claude. "
        "Pick an option, or say what you mean in your own words."
    )
    for n, q in enumerate(questions, 1):
        out += ["", "## Question %d" % n, "", q["question"].strip(), "", "Options:", ""]
        for o in q["options"]:
            line = "- **%s**" % o["label"]
            if o.get("description"):
                line += ": %s" % o["description"]
            out.append(line)
        out += ["", "Evidence:"]
        for e in q["evidence"]:
            out += ["", fenced(e)]
    return "\n".join(out) + "\n"


def write_page(repo, rel, text):
    """Write text to rel in .prose-tuning/, beside the .gitignore that keeps
    it out of the project's commits, and return its path."""
    ignore = repo.abspath(COPY_IGNORE)
    os.makedirs(os.path.dirname(ignore), exist_ok=True)
    if not os.path.isfile(ignore):
        # In place, on purpose. See the module docstring.
        with open(ignore, "wb") as fh:
            fh.write(COPY_IGNORE_TEXT)
    path = repo.abspath(rel)
    Text(text).write(path)
    return path


def cmd_questions(args):
    """Write the interview to .prose-tuning/questions.md, for the author to
    answer on a page when one dialog cannot hold it.

    The file is scratch that the next run replaces, and the folder's
    .gitignore keeps it out of the project's commits. A batch with a refused
    question writes the refusals and no question, so a page from an earlier
    run is never published as this one.
    """
    repo = Repo(args.repo)
    questions = read_json(args.batch, "the questions")
    if not isinstance(questions, list) or not questions:
        raise Fatal("the questions are not a JSON list of at least one question")
    refused = []
    for n, q in enumerate(questions, 1):
        refused += question_refusals(n, q)
    path = write_page(repo, QUESTIONS_FILE, questions_markdown(questions, refused))
    data = {"page": path, "questions": 0 if refused else len(questions)}
    return emit(
        args, "questions", repo.root, data, errors=refused, human=lambda: print("wrote %s" % path)
    )


def copy_sources():
    """(path in the project, bytes) for each file the copy in .prose-tuning/ holds."""
    with open(SCRIPT_PATH, "rb") as fh:
        script = fh.read()
    with open(shipped_template(), "rb") as fh:
        template = fh.read()
    return [
        (COPY_SCRIPT, script),
        (COPY_IGNORE, COPY_IGNORE_TEXT),
        (COPY_TEMPLATE, template),
    ]


def cmd_setup(args):
    """local or cowork, so a skill need not judge it from the tools it holds.

    Cowork's container has its outputs directory and no project checkout, so
    there setup only reports; `stage` does the copying. Locally it copies this
    script into the project, because each shell call starts without the
    variables of the last, and the plugin's own path is too long to repeat.
    """
    if os.path.isdir(OUTPUTS_ROOT):
        data = {"surface": "cowork", "files": [], "prefix": None, "dry_run": args.dry_run}
        return emit(args, "setup", None, data, human=lambda: print("cowork"))

    repo = Repo(args.repo)
    files = []
    for rel, content in copy_sources():
        path = repo.abspath(rel)
        if not args.dry_run:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # In place, on purpose. See the module docstring.
            with open(path, "wb") as fh:
                fh.write(content)
        files.append({"file": rel, "sha256": hashlib.sha256(content).hexdigest()})
    data = {"surface": "local", "files": files, "prefix": COPY_PREFIX, "dry_run": args.dry_run}

    def human():
        print("local")
        print("\nfrom %s, start every command with:\n%s && " % (repo.root, COPY_PREFIX))

    return emit(args, "setup", repo.root, data, human=human)


def normalize_folder(value, name):
    """A device folder as get_device_info lists it, without a trailing slash."""
    folder = (value or "").rstrip("/")
    if not folder.startswith("/"):
        raise Fatal(
            "--%s must be an absolute path on the device, as get_device_info lists it" % name
        )
    return posixpath.normpath(folder)


def cmd_stage(args):
    folder = normalize_folder(args.folder, "folder")
    connected = normalize_folder(args.connected or args.folder, "connected")
    if folder == connected:
        sub = ""
    elif folder.startswith(connected + "/"):
        sub = folder[len(connected) + 1 :]
    else:
        raise Fatal("--folder %s is not inside --connected %s" % (folder, connected))
    mount = (
        posixpath.join(posixpath.basename(connected), sub) if sub else posixpath.basename(connected)
    )
    if not mount:
        raise Fatal("--connected %s has no folder name to mount" % connected)

    sources = copy_sources()

    stage = os.path.abspath(args.stage)
    warnings = []
    if not (stage + "/").startswith(OUTPUTS_ROOT + "/"):
        warnings.append(
            "stage %s is outside %s; device_commit_files will reject it" % (stage, OUTPUTS_ROOT)
        )
    if os.path.exists(stage) and not os.path.isdir(stage):
        raise Fatal("stage %s exists and is not a directory" % stage)

    files = []
    for rel, content in sources:
        staged = os.path.join(stage, *rel.split("/"))
        if not args.dry_run:
            os.makedirs(os.path.dirname(staged), exist_ok=True)
            # In place, on purpose. See the module docstring.
            with open(staged, "wb") as fh:
                fh.write(content)
        files.append(
            {
                "file": rel,
                "staged_path": staged,
                "device_path": posixpath.join(folder, rel),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    cd = 'cd "%s"/%s' % (DEVICE_MOUNT_ROOT, shlex.quote(mount))
    check = [cd + " && sha256sum --check --strict - <<'SUMS'"]
    check += ["%s  %s" % (f["sha256"], f["file"]) for f in files]
    check.append("SUMS")
    data = {
        "dry_run": args.dry_run,
        "stage": stage,
        "files": files,
        "commit_files": [
            {"stagedPath": f["staged_path"], "devicePath": f["device_path"]} for f in files
        ],
        "check_command": "\n".join(check),
        "device_setup": "%s && %s" % (cd, COPY_PREFIX),
    }

    def human():
        for f in files:
            print("%s  %s" % (f["sha256"][:12], f["device_path"]))
        print("\ncheck after copying, through device_bash:\n%s" % data["check_command"])
        print("\nstart every device command with:\n%s && " % data["device_setup"])

    return emit(args, "stage", None, data, warnings=warnings, human=human)


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------


def build_parser():
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common = argparse.ArgumentParser(add_help=False, parents=[output])
    common.add_argument(
        "-C",
        "--repo",
        metavar="PATH",
        default=None,
        help="a path inside the repository (default: cwd)",
    )

    source = argparse.ArgumentParser(add_help=False)
    source.add_argument(
        "--from",
        dest="source",
        metavar="TREE",
        help=(
            "read the edits of another worktree of this repository instead, named by its"
            " folder or by the branch it has checked out"
        ),
    )

    ap = argparse.ArgumentParser(
        prog="prose.py", description="Deterministic half of the prose-tuning skills."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", parents=[common], help="refuse-to-run check for one skill")
    p.add_argument("--for", dest="for_target", required=True, choices=["config", "apply", "adopt"])
    p.add_argument("--force", action="store_true", help="apply only: proceed despite blockers")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("scope", parents=[common], help="which files the prose rules govern")
    p.add_argument(
        "--all", action="store_true", help="every candidate, with the reason for each verdict"
    )
    p.set_defaults(func=cmd_scope)

    p = sub.add_parser(
        "segments",
        parents=[common],
        help="the prose-eligible spans of each file, one per line",
        description="Every prose-eligible span, one per line, as "
        "FILE:LINE:COL_START-COL_END  KIND  TEXT. With no path, every file in scope.",
    )
    p.add_argument("paths", nargs="*", help="files to read (default: every file in scope)")
    p.set_defaults(func=cmd_segments)

    p = sub.add_parser(
        "patterns",
        parents=[common],
        help="where each rule's pattern matches the eligible prose",
        description="Run the pattern of every rule that carries one over the spans segments "
        "gives, and print each match as FILE:LINE:COL_START-COL_END  RULE  TEXT, with "
        "END_LINE:COL_END for a match that wraps. The text is a JSON string. With no path, "
        "every file in scope.",
    )
    p.add_argument("paths", nargs="*", help="files to read (default: every file in scope)")
    p.set_defaults(func=cmd_patterns)

    p = sub.add_parser(
        "pass",
        parents=[common],
        help="the rules, the segments and the pattern matches, for an apply-prose pass",
        description="Print every rule as prose-style.md words it, then what segments prints, "
        "then what patterns prints, each part under its own == heading ==. With no path, "
        "every file in scope.",
    )
    p.add_argument("paths", nargs="*", help="files to read (default: every file in scope)")
    p.set_defaults(func=cmd_pass)

    p = sub.add_parser(
        "evidence", parents=[common, source], help="explicit tags and inferred edits"
    )
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser(
        "reproduce",
        parents=[common, source],
        help="whether the rules' patterns reproduce the edits since HEAD",
        description="Diff every file in scope against HEAD, run the pattern of every rule "
        "that carries one over each file as it was at HEAD, and say for each edit whether a "
        "match overlaps what it changed. Rules with no pattern are listed by id.",
    )
    p.set_defaults(func=cmd_reproduce)

    p = sub.add_parser("config", parents=[common], help="the rule file")
    csub = p.add_subparsers(dest="config_cmd", required=True)
    for name, helptext in [
        ("list", "the rules"),
        ("lint", "check the file"),
        ("check-id", "is this id well-formed and free"),
        ("classify", "which bucket each rule falls in when adopted"),
        ("adopt", "copy new rules into another file, marked as adopted"),
        ("resolve", "write the answer to each colliding and similar pair into another file"),
        ("write", "write approved rules into the file from JSON"),
        ("init", "start one from the shipped rules"),
        ("move", "move a root prose-style.md to %s" % CONFIG_DIR),
    ]:
        c = csub.add_parser(name, parents=[common], help=helptext)
        c.add_argument(
            "--file",
            dest="config_file",
            metavar="PATH",
            help="a prose-style.md other than this repo's",
        )
        if name == "list":
            c.add_argument("--rule", metavar="ID")
            c.add_argument("--ids", action="store_true")
        if name == "check-id":
            c.add_argument("--section", required=True)
            c.add_argument("--name", required=True, help="one to four lower-case words joined by -")
        if name == "classify":
            c.add_argument(
                "--to", required=True, metavar="PATH", help="the prose-style.md to compare against"
            )
        if name == "adopt":
            c.add_argument(
                "--to", required=True, metavar="PATH", help="the prose-style.md to copy into"
            )
            c.add_argument(
                "--rule", required=True, action="append", metavar="ID", help="repeatable"
            )
            c.add_argument("--dry-run", action="store_true", help="say what would be copied")
            c.add_argument(
                "--partial", action="store_true", help="adopt what is valid instead of nothing"
            )
        if name == "resolve":
            c.add_argument(
                "--to", required=True, metavar="PATH", help="the prose-style.md to write into"
            )
            c.add_argument(
                "--answers",
                required=True,
                metavar="PATH",
                help="the answers as a JSON list, or - for stdin",
            )
            c.add_argument(
                "--partial", action="store_true", help="write what is valid instead of nothing"
            )
        if name == "write":
            c.add_argument(
                "--batch",
                required=True,
                metavar="PATH",
                help="the records as a JSON list, or - for stdin",
            )
            c.add_argument(
                "--dry-run",
                action="store_true",
                help="say what would be written, write the rules to %s for the author to "
                "read, and print the token config write takes" % RULES_FILE,
            )
            c.add_argument(
                "--partial", action="store_true", help="write what is valid instead of nothing"
            )
            c.add_argument(
                "--token",
                help="the approval token config write --dry-run printed for this batch; "
                "config write refuses a batch or rules that changed since",
            )
        if name == "move":
            c.add_argument("--dry-run", action="store_true", help="say what would be copied")
        if name == "init":
            how = c.add_mutually_exclusive_group()
            how.add_argument(
                "--from", dest="source", metavar="PATH", help="copy an existing config instead"
            )
            how.add_argument(
                "--empty", action="store_true", help="write a skeleton with no rules instead"
            )
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("tags", parents=[common], help="the markup")
    tsub = p.add_subparsers(dest="tags_cmd", required=True)
    t = tsub.add_parser("resolve", parents=[common], help="accept the edits and remove markup")
    t.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_tags)

    # report and apply read one findings file. Only apply takes --only and
    # --file: a filtered report would print a token over findings it did not
    # show (#116).
    findings = argparse.ArgumentParser(add_help=False)
    findings.add_argument(
        "--findings",
        required=True,
        metavar="FILE",
        help="a file holding the JSON array of findings described below",
    )

    p = sub.add_parser(
        "report",
        parents=[common, findings],
        help="the findings, for approval",
        description="Print the findings for approval, read against the files as they are now, "
        "and name every pair of them that overlaps. Also write them to %s, for the author "
        "to read whole. Fail on every pattern match in the files given that no finding "
        "covers. With no path, every file in scope." % REPORT_FILE,
        epilog=FINDINGS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "paths", nargs="*", help="files to check for matches (default: every file in scope)"
    )
    p.set_defaults(func=cmd_report)

    p = sub.add_parser(
        "apply",
        parents=[common, findings],
        help="apply approved rewrites",
        description="Apply approved rewrites.",
        epilog=FINDINGS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("paths", nargs="*", help="the files report was given, which its token covers")
    p.add_argument("--only", metavar="ID,ID", help="only these rule ids")
    p.add_argument(
        "--file",
        action="append",
        metavar="PATH",
        help="only findings in this file; repeat for more",
    )
    p.add_argument(
        "--partial",
        action="store_true",
        help="apply what is valid and report the rest, instead of writing nothing",
    )
    p.add_argument(
        "--token",
        required=True,
        help="the approval token report printed for these findings; apply refuses "
        "a batch, a document or rules that changed since",
    )
    p.add_argument("--dry-run", action="store_true", help="report without writing")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser(
        "questions",
        parents=[common],
        help="write the interview to %s, for the author to answer on a page" % QUESTIONS_FILE,
    )
    p.add_argument(
        "--batch",
        required=True,
        metavar="PATH",
        help="the questions as a JSON list, or - for stdin; each has question, "
        "options (label, description) and evidence (a list of text)",
    )
    p.set_defaults(func=cmd_questions)

    # -C is used only locally: in Cowork's container, setup has no repo to find.
    p = sub.add_parser(
        "setup",
        parents=[common],
        help="local or cowork, and locally copy this script into the project",
    )
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_setup)

    # No -C: stage runs in Cowork's container, which has no repo.

    p = sub.add_parser(
        "stage",
        parents=[output],
        help="copy this script and the shipped rules into Cowork's outputs for the device",
    )
    p.add_argument(
        "--folder",
        required=True,
        metavar="PATH",
        help="the project folder on the device, as get_device_info lists it",
    )
    p.add_argument(
        "--connected",
        metavar="PATH",
        help="the connected folder holding --folder, when that is not the project itself",
    )
    p.add_argument("--stage", default=DEFAULT_STAGE, metavar="DIR", help="default: %(default)s")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_stage)

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not hasattr(args, "paths"):
        args.paths = []
    try:
        return args.func(args)
    except Fatal as exc:
        sys.stderr.write("prose.py: %s\n" % exc)
        return CANNOT_RUN
    except BrokenPipeError:
        return OK


if __name__ == "__main__":
    sys.exit(main())

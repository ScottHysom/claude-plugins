#!/usr/bin/env python3
"""Deterministic half of the prose-tuning skills.

The three skills in this plugin use the model only for what genuinely needs
judgment: inferring a rule from an edit, writing prose, deciding whether a
passage conforms. Everything else - parsing markup, selecting files, diffing,
inserting and resolving tags, reading the config - happens here, because the
first run of this workflow by hand produced five malformed tags that survived
until a parser existed, and a parser that was rewritten three times.

Usage:
    python3 prose.py <command> [options]
    python3 prose.py --help

Commands:
    preflight   refuse-to-run check for one skill
    status      what is in the working tree right now
    scope       which files the prose rules govern
    segments    the prose-eligible spans of each file, one per line
    evidence    explicit tags + inferred edits + open questions
    config      list | lint | check-id | similar | init | move
    tags        check | list | insert | resolve | strip
    report      the findings for approval, and which of them overlap
    apply       apply approved rewrites
    restore     put a file back to its committed state
    setup       which surface this is running on, local or cowork, and
                locally, copy this script into the project
    stage       copy this script and the shipped rules into Cowork's outputs

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

2. Git is only ever read (rev-parse, ls-files, status, check-ignore, show).
   Nothing here writes through git, so no .git/*.lock is ever created. The
   bridge strands those locks because it cannot delete them, which is the whole
   reason the projects this runs against carry a commit.sh.

3. apply can delete a blank line that no finding names. It does so when the
   findings cut a whole block that sat between two blank lines, so that one
   blank line is left between its neighbors rather than two. plan_findings
   has the rule.

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

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

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
DEVICE_MOUNT_ROOT = "$HOME/mnt"

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
    every later edit pointing at the wrong place. This is why tags insert takes
    a batch rather than being called once per tag.
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
        on the order the records happened to arrive in. Two ordinary requests
        hit this. A <q> on the first line of a block <del> puts a zero-width
        insert at the offset the block replacement starts from, and the splice
        discards whichever went first. Two neighboring inline <del> spans put
        the first one's closing tag and the second one's opening tag on one
        offset, and one of the two orders emits
        `<del>Curated<del></del>, not</del>`, which does not even parse.

        There is no order this class can be resolved in that is right for both,
        so it is refused. The author writes one span instead of two, and gets
        told so rather than getting a mangled file half the time.
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

    def has_ref(self, ref):
        code, _, _ = self.git("rev-parse", "--verify", "--quiet", ref)
        return code == 0

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
ANY_H3 = re.compile(r"^###\s+(.*)$")
ANY_H2 = re.compile(r"^##\s+(.+?)\s*$")
META_COMMENT = re.compile(r"^<!--\s*prose-rule\s*:\s*(.*?)\s*-->\s*$")
BEFORE_LINE = re.compile(r"^>\s*\*\*Before\.\*\*\s*(.*?)\s*$")
AFTER_LINE = re.compile(r"^>\s*\*\*After\.\*\*\s*(.*?)\s*$")
FM_KEY = re.compile(r"^([a-z][a-z0-9_-]*)\s*:\s*(.*?)\s*$")
FM_SUBKEY = re.compile(r"^ {2}(include|exclude)\s*:\s*$")
FM_ITEM = re.compile(r"^ {4}-\s+(.+?)\s*$")

META_KEYS = {"source", "origin"}
META_SOURCES = {"shipped", "inferred", "interview", "adopted"}


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

    Deliberately crude, and reported in parts so the author can see which
    half fired. A rule can be restated in different words under the same
    name, or say the same thing under a different one, and either is worth
    a look - so the score is the higher of the two rather than a blend that
    hides both. The corpus is a few dozen rules, so the quadratic is free.
    """
    body = difflib.SequenceMatcher(None, a.body_key(), b.body_key()).ratio()
    at, bt = set(a.name.split("-")), set(b.name.split("-"))
    name = len(at & bt) / float(len(at | bt)) if (at | bt) else 0.0
    return body, name, max(body, name)


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
        }


class Config:
    """prose-style.md: restricted front matter plus one H3 per rule.

    The front-matter grammar is deliberately small rather than accidentally
    small. Stdlib only means no PyYAML, so anything richer would be parsed by
    guesswork. lint rejects out-of-grammar keys loudly, because a silently
    dropped key is a scope override that looks like it works.
    """

    def __init__(self, path, shown=None):
        self.path = path
        # How messages name the file: its repo-relative path when there is one.
        self.shown = shown or os.path.basename(path)
        self.front = {}
        self.scope_include = []
        self.scope_exclude = []
        self.rules = []
        self.errors = []
        self.warnings = []
        self.exists = os.path.exists(path)
        if self.exists:
            self._parse(Text.read(path))

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
            for k, v in rule.meta.items():
                if k not in META_KEYS:
                    self._err(
                        rule.line,
                        "unknown metadata key %r; allowed: %s" % (k, ", ".join(sorted(META_KEYS))),
                    )
                elif k == "source" and v not in META_SOURCES:
                    self._err(
                        rule.line,
                        "source=%s is not one of %s" % (v, ", ".join(sorted(META_SOURCES))),
                    )
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

    def __init__(self, repo, config):
        self.repo = repo
        self.config = config
        self.include = config.scope_include or list(DEFAULT_INCLUDE)
        self.exclude = config.scope_exclude or list(DEFAULT_EXCLUDE)
        self.overridden = bool(config.scope_include or config.scope_exclude)
        self._inc = Matcher(self.include)
        self._exc = Matcher(self.exclude)
        self._config_rel = (
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

# Kinds that prose rules must never be applied inside. An HTML comment is a
# note for people - a FILL marker in the shipped rules is one - and not
# the document's prose.
PROTECTED_KINDS = {"frontmatter", "fence", "blockquote", "comment"}

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
    """

    def __init__(self, text):
        self.text = text
        n = text.line_count()
        self.kinds = ["paragraph"] * n
        self.info = [""] * n
        self.headings = []
        self.comments = []
        self._classify()
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

    def _items(self):
        """The list item each line belongs to, as (line, content column) or None.

        A list item's line belongs to that item. A paragraph line straight
        after a line of an item's text belongs to the same item, whatever its
        indent, as CommonMark's lazy continuation has it. Any other line
        belongs to the innermost open item whose content column its indent
        reaches, and closes the items it does not reach. Inside a fence,
        comment or front matter only the first line counts, because what it
        holds is not markdown and its indent says nothing about the list.
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
                if kind == "list-item":
                    stack.append((i + 1, len(LIST_ITEM.match(raw).group(0))))
                out[i] = stack[-1] if stack else None
            prev = kind
        return out

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
        tags check, and so does any project document quoting HTML.
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
        """Everything the tag scanner must ignore: fences, front matter, spans."""
        fences = self.protected_offsets()
        return fences + self.code_span_offsets(fences)

    def protected_offsets(self):
        """[(start, end)] absolute ranges of front matter and fenced blocks."""
        out, start = [], None
        for i, kind in enumerate(self.kinds):
            if kind in ("frontmatter", "fence"):
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

TAG_KINDS = ("ins", "del", "repl", "why", "alt", "q", "a")
TAG_RE = re.compile(r"</?(%s)(\s[^<>]*?)?\s*/?>" % "|".join(TAG_KINDS))
ATTR_RE = re.compile(r"""([A-Za-z_][-A-Za-z0-9_]*)\s*=\s*("([^"]*)"|'([^']*)')""")

EDIT_KINDS = {"ins", "del", "repl"}
COMMENT_KINDS = {"why", "alt"}
ALLOWED_ATTRS = {
    "ins": {"why"},
    "del": {"why"},
    "repl": {"why"},
    "q": {"id"},
    "a": set(),
    "why": set(),
    "alt": set(),
}
ALLOWED_CHILDREN = {
    "ins": COMMENT_KINDS,
    "del": COMMENT_KINDS,
    "repl": COMMENT_KINDS | {"del", "ins"},
    "why": set(),
    "alt": set(),
    "q": set(),
    "a": set(),
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

    def _warn(self, offset, msg):
        self.warnings.append("%s:%d  %s" % (self.path, self.text.line_of(offset), msg))

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

            # <a href="..."> is an HTML anchor, not an answer. Skipping it is
            # deliberate; erroring would make ordinary markdown unparseable.
            if kind == "a" and attrs:
                continue

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
        qids = {}
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
            if node.kind == "q":
                qid = node.attrs.get("id")
                if qid is None:
                    self._warn(node.open_start, "<q> has no id; run tags insert to number it")
                elif qid in qids:
                    self._err(
                        node.open_start,
                        "duplicate question id %s; first at line %d" % (qid, qids[qid]),
                    )
                else:
                    qids[qid] = node.line

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
# One implementation, two names. "accept" is tags resolve: the edits the markup
# proposes are taken, and the file becomes committable prose. "reject" is tags
# strip: the markup is abandoned and the underlying text comes back unchanged.
#
# "reject" is also what evidence uses to neutralize a file before diffing it,
# which is the only way to tell the author's own edits apart from the markup
# this tool inserted. A plain git diff cannot: it reports our own tags back to
# us as author evidence.
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
    if node.kind in ("why", "alt", "q", "a"):
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
    engine = EditEngine(text)
    for node in scanner.roots:
        start, end = node_span(node, text)
        engine.replace(start, end, top_replacement(node, text, mode))
    return engine.result(), scanner


def neutralize(text, blocks=None, path="<text>"):
    """The file as it would read with every tag abandoned."""
    out, _ = resolve_text(text, REJECT, blocks, path)
    return out


def resolve_warnings(scanner, text):
    """Block-form tags inside a list are the one case worth eyeballing.

    A tag placed between two list items ends the list and starts a new one,
    and the damage outlives the strip. The inline path cannot cause this
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


def resolve_file(path, relpath, mode, dry_run=False):
    text = Text.read(path)
    blocks = Blocks(text)
    scanner = TagScanner(text, blocks, relpath)
    if scanner.errors:
        return None, scanner, []
    engine = EditEngine(text)
    for node in scanner.roots:
        start, end = node_span(node, text)
        engine.replace(start, end, top_replacement(node, text, mode))
    new = engine.result()
    warnings = resolve_warnings(scanner, text)
    if not dry_run and new != text.s:
        Text(new).write(path)
    return new, scanner, warnings


# --------------------------------------------------------------------------
# inserting markup
#
# Addressed by line and column, applied as one batch, bottom-up from a single
# snapshot. A loop of twenty single invocations cannot work: each insertion
# shifts every line number below it, so anchors two onward are already stale.
# The first run of this workflow used twenty exact-match anchor strings and
# three of them failed. Batch is correctness here, not convenience.
# --------------------------------------------------------------------------

INSERTABLE = ("ins", "del", "repl", "q", "alt")
UNSAFE_SPAN_KINDS = ("frontmatter", "fence", "heading", "table")

# <q> and <alt> go in as a whole new line above the one they ask about, so they
# are governed by a different rule than a span is. Above a heading is fine:
# the heading itself is untouched. Inside anything with structure is not: the
# new line lands in the middle of it, and inside a fence it is worse than broken,
# because the scanner then shields it as code and no later strip ever removes
# it. That is a tag the author cannot get rid of, so refuse instead.
UNSAFE_INSERT_KINDS = ("frontmatter", "fence", "blockquote", "table")


def attr_text(why):
    if not why:
        return ""
    return ' why="%s"' % why if '"' not in why else ""


class InsertRefusal(Exception):
    pass


def plan_one_insert(text, blocks, rec, path, qid):
    """Return a list of (start, end, replacement). Raises InsertRefusal."""
    kind = rec.get("kind")
    if kind not in INSERTABLE:
        raise InsertRefusal("kind %r is not one of %s" % (kind, ", ".join(INSERTABLE)))
    start_line = int(rec.get("start", 0))
    if start_line < 1 or start_line > text.line_count():
        raise InsertRefusal(
            "line %d is outside the file (%d lines)" % (start_line, text.line_count())
        )
    end_line = int(rec.get("end", start_line))
    if end_line < start_line or end_line > text.line_count():
        raise InsertRefusal("end line %d is outside the span" % end_line)
    why = rec.get("why", "")
    body = rec.get("text", "")
    indent = " " * blocks.continuation_indent(start_line)

    if kind in ("q", "alt"):
        if not body:
            raise InsertRefusal("<%s> needs text" % kind)
        if blocks.kind(start_line) in UNSAFE_INSERT_KINDS:
            raise InsertRefusal(
                "line %d is a %s; a new line there would land "
                "inside it" % (start_line, blocks.kind(start_line))
            )
        ident = ' id="%s"' % qid if kind == "q" else ""
        at = text.offset(start_line, 0)
        return [(at, at, "%s<%s%s>%s</%s>\n" % (indent, kind, ident, body, kind))]

    for line in range(start_line, end_line + 1):
        if blocks.kind(line) in UNSAFE_SPAN_KINDS:
            raise InsertRefusal(
                "line %d is a %s; markup there would break it" % (line, blocks.kind(line))
            )

    col_start = int(rec.get("col_start", 0))
    last = text.bare(end_line)
    col_end = int(rec.get("col_end", len(last)))

    # Columns are bounds-checked here because Text.offset does not check them:
    # it validates the line and then adds the column blind. A col_end past the
    # end of its line resolves to an offset further down the file, so the
    # closing tag of a one-line edit lands wherever that offset happens to be -
    # for a large enough column, the end of the document.
    first_bare = text.bare(start_line)
    if not 0 <= col_start <= len(first_bare):
        raise InsertRefusal(
            "col_start %d is outside line %d (%d characters)"
            % (col_start, start_line, len(first_bare))
        )
    if not 0 <= col_end <= len(last):
        raise InsertRefusal(
            "col_end %d is outside line %d (%d characters)" % (col_end, end_line, len(last))
        )

    whole_lines = col_start == 0 and col_end == len(last)
    inline = start_line == end_line

    if inline and col_end < col_start:
        raise InsertRefusal("col_end %d is before col_start %d" % (col_end, col_start))

    if not inline and not whole_lines:
        raise InsertRefusal(
            "a span that starts mid-line and ends on another "
            "line straddles blocks; give whole lines, or keep "
            "it inside one line"
        )

    a = text.offset(start_line, col_start)
    b = text.offset(end_line, col_end)

    if kind == "ins":
        if not body:
            raise InsertRefusal("<ins> needs text")
        if inline:
            # An inline tag that ends up alone on its line is indistinguishable
            # from a block tag, and a block tag owns its whole line - so
            # stripping it would take the author's blank line with it.
            if not first_bare.strip():
                raise InsertRefusal(
                    "line %d is blank; an <ins> alone on a "
                    "line reads as a block tag and would take "
                    "the line with it" % start_line
                )
            return [(a, a, "<ins>%s</ins>" % body)]
        raise InsertRefusal("<ins> inserts at a point; give one line")

    if inline:
        # A zero-width span has no text in it to mark up, and the two tags it
        # would emit share an offset - which EditEngine now refuses outright.
        # Note this also catches an inline record aimed at a blank line, where
        # both columns default to 0.
        if col_start == col_end:
            raise InsertRefusal("the span is empty; give a span with text in it, or whole lines")
        if why and '"' in why:
            raise InsertRefusal(
                "a why containing a double quote needs block form; give whole lines"
            )
        if kind == "del":
            return [(a, a, "<del%s>" % attr_text(why)), (b, b, "</del>")]
        new = rec.get("with")
        if new is None:
            raise InsertRefusal("<repl> needs a with value")
        if why:
            return [
                (a, a, "<repl%s><del>" % attr_text(why)),
                (b, b, "</del><ins>%s</ins></repl>" % new),
            ]
        return [(a, a, "<del>"), (b, b, "</del><ins>%s</ins>" % new)]

    # Block form. The span is replaced wholesale so the opening and closing
    # tags land on their own lines at the enclosing list item's indent, which
    # is what keeps a tag from ending the list it sits in.
    first = text.bare(start_line)
    indent = " " * (len(first) - len(first.lstrip()))
    block_start = text.offset(start_line, 0)
    block_end = text.offset(end_line) + len(text.line(end_line))
    original = text.s[block_start:block_end]
    if not original.strip():
        raise InsertRefusal("the span is blank; there is nothing to tag")
    # A file whose last line has no newline is an ordinary shape. The closing
    # tag goes straight after the text in that case rather than on a line of
    # its own, because a newline invented here is one strip would have to
    # invent a reason to remove, and the file would come back a byte longer.
    tail = "\n" if original.endswith("\n") else ""
    why_line = ""
    if why and '"' in why:
        why_line = "%s  <why>%s</why>\n" % (indent, why)
        why = ""
    attrs = attr_text(why)

    if kind == "del":
        out = "%s<del%s>\n%s%s%s</del>%s" % (indent, attrs, why_line, original, indent, tail)
        return [(block_start, block_end, out)]

    new = rec.get("with")
    if new is None:
        raise InsertRefusal("<repl> needs a with value")
    new_block = "".join("%s%s\n" % (indent, x) for x in new.split("\n"))

    out = "%s<repl%s>\n%s%s<del>\n%s%s</del>\n%s<ins>\n%s%s</ins>\n%s</repl>%s" % (
        indent,
        attrs,
        why_line,
        indent,
        original,
        indent,
        indent,
        new_block,
        indent,
        indent,
        tail,
    )
    return [(block_start, block_end, out)]


def next_question_id(repo, files):
    highest = 0
    for rel in files:
        path = repo.abspath(rel)
        if not os.path.exists(path):
            continue
        text = Text.read(path)
        for node in TagScanner(text, None, rel).all:
            if node.kind == "q" and node.attrs.get("id", "").isdigit():
                highest = max(highest, int(node.attrs["id"]))
    return highest + 1


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
    """Tag records, with a bare <del>+<ins> pair reported as one replacement."""
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
        if id(node) in paired or node.kind not in EDIT_KINDS:
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
        if node.kind == "repl":
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


def question_records(scanner, text, rel):
    out = []
    roots = scanner.roots
    for n, node in enumerate(roots):
        if node.kind != "q":
            continue
        answer = None
        for later in roots[n + 1 :]:
            if later.kind == "a":
                answer = strip_tags(later.inner(text)).strip()
                break
            if later.kind == "q":
                break
        out.append(
            {
                "file": rel,
                "line": node.line,
                "id": node.attrs.get("id"),
                "question": strip_tags(node.inner(text)).strip(),
                "answer": answer,
            }
        )
    return out


def inferred_records(repo, rel, text, neutral, ref, ignore):
    base = repo.show(ref, rel)
    if base is None:
        return [], True
    base_lines = base.splitlines()
    neutral_lines = neutral.splitlines()
    work_lines = [text.bare(i + 1) for i in range(text.line_count())]
    to_work = line_map(neutral_lines, work_lines)
    out = []
    sm = difflib.SequenceMatcher(None, base_lines, neutral_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old = base_lines[i1:i2]
        new = neutral_lines[j1:j2]
        line = nearest(to_work, j1, j1) + 1
        if "%s:%d" % (rel, line) in ignore:
            continue
        out.append(
            {
                "file": rel,
                "start": line,
                "end": nearest(to_work, max(j2 - 1, j1), j2) + 1,
                "change": tag,
                "old_lines": old,
                "new_lines": new,
                "signal": classify_signal("\n".join(old), "\n".join(new)),
            }
        )
    return out, False


def apply_inserts(text, blocks, records, path, qid_start):
    """Returns (engine, refusals, next_qid). The caller decides all-or-nothing."""
    engine = EditEngine(text)
    refusals, qid, claimed = [], qid_start, []
    for n, rec in enumerate(records):
        try:
            edits = plan_one_insert(text, blocks, rec, path, qid)
        except InsertRefusal as exc:
            refusals.append(
                "%s:%s  record %d refused: %s" % (path, rec.get("start", "?"), n + 1, exc)
            )
            continue
        except (TypeError, ValueError) as exc:
            refusals.append("%s  record %d is malformed: %s" % (path, n + 1, exc))
            continue

        # Each record marks up one region, and the regions have to be disjoint.
        # Overlap is two judgments about one passage, which the markup has no
        # way to express; nesting is worse, because an <ins> landing inside
        # another record's <del> is a grammar the scanner rejects, and the file
        # written would be one this tool's own `tags check` turns down.
        # plan_one_insert cannot see this - it is handed one record at a time.
        span = (min(a for a, _, _ in edits), max(b for _, b, _ in edits))
        clash = next((c for c in claimed if span[0] < c[1][1] and c[1][0] < span[1]), None)
        if clash:
            refusals.append(
                "%s:%s  record %d overlaps record %d; each record "
                "marks up its own passage" % (path, rec.get("start", "?"), n + 1, clash[0])
            )
            continue
        claimed.append((n + 1, span))

        if rec.get("kind") == "q":
            qid += 1
        for a, b, replacement in edits:
            engine.replace(a, b, replacement)
    return engine, refusals, qid


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def read_json(source, what):
    """JSON from a file, or from stdin when source is -.

    stdin spares Cowork a scratch file in the project, which the bridge could
    write but never delete.
    """
    if source == "-":
        raw = sys.stdin.read()
    else:
        try:
            with open(source, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            raise Fatal("cannot read %s: %s" % (what, exc)) from exc
    try:
        return json.loads(raw)
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


def cmd_status(args):
    repo, config, scope = load(args)
    files = scope.files()
    tags, unanswered, errors = {}, 0, []
    for rel in files:
        path = repo.abspath(rel)
        if not os.path.exists(path):
            continue
        text = Text.read(path)
        scanner = TagScanner(text, None, rel)
        errors += scanner.errors
        if scanner.all:
            tags[rel] = scanner.counts()
        for q in question_records(scanner, text, rel):
            if q["answer"] is None:
                unanswered += 1
    dirty = repo.dirty_md()
    data = {
        "config": {
            "path": config.rel(),
            "exists": config.exists,
            "rules": len(config.rules),
            "errors": config.errors,
            "warnings": config.warnings,
        },
        "scope": {"count": len(files), "overridden": scope.overridden},
        "dirty": [{"status": s, "path": p} for s, p in dirty],
        "tags": tags,
        "unanswered_questions": unanswered,
        "markup_errors": errors,
    }

    def human():
        print("repo    %s" % repo.root)
        print(
            "config  %s  %s"
            % (
                config.rel(),
                "%d rule(s)" % len(config.rules) if config.exists else "MISSING - run config init",
            )
        )
        print("scope   %d file(s)%s" % (len(files), " (overridden)" if scope.overridden else ""))
        print("dirty   %d markdown file(s)" % len(dirty))
        for s, p in dirty:
            print("          %-2s %s" % (s, p))
        if tags:
            print("markup")
            for rel in sorted(tags):
                counts = ", ".join("%d %s" % (v, k) for k, v in sorted(tags[rel].items()))
                print("          %s  %s" % (rel, counts))
            print("        %d unanswered question(s)" % unanswered)
        else:
            print("markup  none")
        for e in errors:
            print("!! %s" % e)

    # status reports; it does not judge. Tags present is a normal mid-run
    # state for update-prose-config, so this never exits 1.
    return emit(args, "status", repo.root, data, human=human)


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
    tagged, markup_errors = [], []
    for rel in files:
        path = repo.abspath(rel)
        if not os.path.exists(path):
            continue
        scanner = TagScanner(Text.read(path), None, rel)
        markup_errors += scanner.errors
        if scanner.all:
            tagged.append((rel, scanner.all[0].line))
    blockers += markup_errors

    hints = []
    if want == "apply":
        # Only documents the rules govern. An uncommitted prose-style.md is
        # the expected output of an update-prose-config run, not a reason to
        # refuse the conformance pass that validates it.
        in_scope = set(files)
        for rel, line in tagged:
            blockers.append(
                "%s:%d  markup is present; an update-prose-config run is in progress" % (rel, line)
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
        "tagged_files": [r for r, _ in tagged],
        "config_exists": config.exists,
        "scope_count": len(files),
    }

    def human():
        if not blockers:
            print("ok: nothing blocks %s" % want)
        else:
            print("%d blocker(s) for %s" % (len(blockers), want))

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


def cmd_segments(args):
    repo, config, scope = load(args)
    targets = args.paths or scope.files()
    data, errors = {}, []
    for rel in targets:
        path = repo.abspath(rel)
        if not os.path.exists(path):
            errors.append("%s  no such file" % rel)
            continue
        text = Text.read(path)
        blocks = Blocks(text)
        segs = segments_for(text, blocks)
        protected = sum(1 for k in blocks.kinds if k in PROTECTED_KINDS)
        data[rel] = {
            "segment_count": len(segs),
            "chars": sum(len(s["text"]) for s in segs),
            "protected_lines": protected,
            "lines": text.line_count(),
        }
        if not args.summary:
            data[rel]["segments"] = segs

    def human():
        if not args.summary:
            for rel in sorted(data):
                for seg in data[rel]["segments"]:
                    print(segment_line(rel, seg))
            return
        for rel in sorted(data):
            d = data[rel]
            print(
                "%s  %d segment(s), %d character(s), %d protected line(s) of %d"
                % (rel, d["segment_count"], d["chars"], d["protected_lines"], d["lines"])
            )
        print(
            "\n%d file(s), %d segment(s), %d character(s)"
            % (
                len(data),
                sum(d["segment_count"] for d in data.values()),
                sum(d["chars"] for d in data.values()),
            )
        )

    return emit(args, "segments", repo.root, data, errors=errors, human=human)


def cmd_evidence(args):
    repo, config, scope = load(args)
    ref = args.since
    if not repo.has_ref(ref):
        raise Fatal("%s is not a ref in this repository" % ref)
    ignore = set(args.ignore or [])
    explicit, inferred, questions, errors, new_files = [], [], [], [], []
    for rel in scope.files():
        path = repo.abspath(rel)
        if not os.path.exists(path):
            continue
        text = Text.read(path)
        blocks = Blocks(text)
        scanner = TagScanner(text, blocks, rel)
        errors += scanner.errors
        if scanner.errors:
            continue
        explicit += explicit_records(scanner, text, blocks, rel)
        questions += question_records(scanner, text, rel)
        neutral = neutralize(text, blocks, rel)
        hunks, is_new = inferred_records(repo, rel, text, neutral, ref, ignore)
        if is_new:
            new_files.append(rel)
        inferred += hunks

    unanswered = sum(1 for q in questions if q["answer"] is None)
    data = {
        "base_ref": ref,
        "explicit": explicit,
        "inferred": inferred,
        "questions": questions,
        "new_files": new_files,
        "counts": {
            "explicit": len(explicit),
            "inferred": len(inferred),
            "questions": len(questions),
            "unanswered": unanswered,
            "files": len(scope.files()),
        },
    }

    def human():
        print("base %s" % ref)
        for rec in explicit:
            print(
                "  explicit %s:%d [%s] %s"
                % (rec["file"], rec["start"], rec["kind"], (rec["why"] or [""])[0])
            )
        for rec in inferred:
            flag = " (%s)" % rec["signal"] if rec["signal"] else ""
            print("  inferred %s:%d [%s]%s" % (rec["file"], rec["start"], rec["change"], flag))
        for q in questions:
            print(
                "  question %s:%d #%s %s"
                % (q["file"], q["line"], q["id"], "answered" if q["answer"] else "OPEN")
            )
        print(
            "\nexplicit: %d  inferred: %d  unanswered: %d"
            % (len(explicit), len(inferred), unanswered)
        )
        if new_files:
            print("untracked at %s: %s" % (ref, ", ".join(new_files)))

    return emit(args, "evidence", repo.root, data, errors=errors, human=human)


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

    if which == "similar":
        other = Config(os.path.abspath(args.to))
        if not other.exists:
            raise Fatal("%s does not exist" % args.to)
        pairs = []
        for a in config.rules:
            for b in other.rules:
                # A shared id is already adopt-prose's identical or colliding
                # bucket. This command is for the pairs that agree in substance
                # under two different names, which nothing else can see.
                if a.id == b.id:
                    continue
                body, name, score = rule_similarity(a, b)
                if score >= args.threshold:
                    pairs.append(
                        {
                            "source": a.id,
                            "target": b.id,
                            "score": round(score, 2),
                            "body": round(body, 2),
                            "name": round(name, 2),
                        }
                    )
        pairs.sort(key=lambda p: (-p["score"], p["source"], p["target"]))

        def human():
            w = max([len(p["source"]) for p in pairs] + [8])
            for p in pairs:
                print(
                    "%.2f  %-*s  %s   (body %.2f, name %.2f)"
                    % (p["score"], w, p["source"], p["target"], p["body"], p["name"])
                )
            print(
                "\n%d candidate pair(s) at or above %.2f; each is a question"
                " for the author, not a decision." % (len(pairs), args.threshold)
            )

        return emit(
            args,
            "config similar",
            repo.root,
            {
                "source": config.path,
                "target": os.path.abspath(args.to),
                "threshold": args.threshold,
                "pairs": pairs,
            },
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
            print("%s %-*s %-10s %s" % (mark, w, r.id, r.meta.get("source", "-"), r.title))
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
    targets = args.paths or scope.files()

    if which in ("check", "list"):
        errors, warnings, data = [], [], {}
        for rel in targets:
            path = repo.abspath(rel)
            if not os.path.exists(path):
                errors.append("%s  no such file" % rel)
                continue
            text = Text.read(path)
            scanner = TagScanner(text, None, rel)
            errors += scanner.errors
            warnings += scanner.warnings
            if scanner.all:
                data[rel] = {
                    "counts": scanner.counts(),
                    "tags": [
                        {
                            "kind": n.kind,
                            "line": n.line,
                            "form": "block" if is_block_form(n, text) else "inline",
                            "why": n.whys(text),
                            "alt": n.alts(text),
                            "text": strip_tags(n.inner(text)).strip()[:200],
                        }
                        for n in scanner.roots
                    ],
                }

        def human():
            total = 0
            for rel in sorted(data):
                print(rel)
                for tag in data[rel]["tags"]:
                    total += 1
                    if which == "list":
                        why = ("  %s" % tag["why"][0]) if tag["why"] else ""
                        print(
                            "  %4d  %-5s %-6s %s%s"
                            % (tag["line"], tag["kind"], tag["form"], tag["text"][:60], why)
                        )
            print("\n%d tag(s) in %d file(s)" % (total, len(data)))

        return emit(
            args, "tags " + which, repo.root, data, errors=errors, warnings=warnings, human=human
        )

    if which in ("resolve", "strip"):
        mode = ACCEPT if which == "resolve" else REJECT
        errors, warnings, data = [], [], {}
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
            engine = EditEngine(text)
            for node in scanner.roots:
                start, end = node_span(node, text)
                engine.replace(start, end, top_replacement(node, text, mode))
            pending.append((path, rel, engine.result(), len(scanner.all)))
            warnings += resolve_warnings(scanner, text)
        if errors:
            errors.append("nothing was written; fix the markup and re-run")
            return emit(args, "tags " + which, repo.root, {}, errors=errors, warnings=warnings)
        for path, rel, new, count in pending:
            data[rel] = {"tags": count}
            if not args.dry_run:
                Text(new).write(path)

        def human():
            for rel in sorted(data):
                print(
                    "%s  %d tag(s) %s"
                    % (rel, data[rel]["tags"], "would be " + which if args.dry_run else which + "d")
                )
            if not data:
                print("no markup found")

        return emit(args, "tags " + which, repo.root, data, warnings=warnings, human=human)

    # insert
    records = read_json(args.batch, "batch")
    if not isinstance(records, list):
        raise Fatal("batch must be a JSON array of records")

    by_file = {}
    for rec in records:
        by_file.setdefault(rec.get("file"), []).append(rec)
    qid = next_question_id(repo, scope.files())

    staged, refusals = [], []
    for rel in sorted(by_file):
        path = repo.abspath(rel) if rel else None
        if not rel or not os.path.exists(path):
            refusals.append("%s  no such file" % rel)
            continue
        text = Text.read(path)
        blocks = Blocks(text)
        engine, bad, qid = apply_inserts(text, blocks, by_file[rel], rel, qid)
        refusals += bad
        if bad and not args.partial:
            continue
        try:
            staged.append((path, rel, engine.result()))
        except Fatal as exc:
            refusals.append("%s  %s" % (rel, exc))

    if refusals and not args.partial:
        refusals.append(
            "nothing was written; a half-applied batch leaves "
            "every later line number wrong. Fix the batch and "
            "re-run, or pass --partial."
        )
        return emit(args, "tags insert", repo.root, {"refused": len(refusals)}, errors=refusals)

    data = {}
    for path, rel, new in staged:
        if not args.dry_run:
            Text(new).write(path)
        scanner = TagScanner(Text(new), None, rel)
        data[rel] = {"tags": [{"kind": n.kind, "line": n.line} for n in scanner.roots]}

    def human():
        for rel in sorted(data):
            for tag in data[rel]["tags"]:
                print("%s:%d  %s" % (rel, tag["line"], tag["kind"]))
        print("\n%d file(s) %s" % (len(data), "unchanged (dry run)" if args.dry_run else "written"))

    return emit(args, "tags insert", repo.root, data, errors=refusals, human=human)


# The kinds a finding may cross lines within. Anything else between two lines
# of prose, such as a blank line, a heading or a table row, is structure that
# a rewrite across it would erase.
SPANNING_KINDS = ("paragraph", "list-item")


def locate(text, line, f, n):
    """The absolute (start, end) that finding n covers, or (None, why not).

    With no columns, the finding's text is looked for among the places that
    start on its line, and it has to start at exactly one of them. col_start
    alone says which, and the span runs as far as the text does, onto a later
    line if the text holds a newline. col_end pins the end on the same line,
    which is the one form that needs no text; without text, the columns
    default to the whole line.
    """
    width = len(text.bare(line))
    base = text.offset(line)
    want = f.get("text")
    col_start, col_end = f.get("col_start"), f.get("col_end")
    if want is None or col_end is not None:
        col_start = int(col_start if col_start is not None else 0)
        col_end = int(col_end if col_end is not None else width)
        # Text.offset validates the line and then adds the column blind, so
        # a column past the end of its line resolves somewhere further down
        # the file and this would rewrite a passage nobody approved.
        if not 0 <= col_start <= col_end <= width:
            return None, "columns %d-%d are outside the line (%d characters)" % (
                col_start,
                col_end,
                width,
            )
        a, b = base + col_start, base + col_end
    elif col_start is not None:
        col_start = int(col_start)
        if not 0 <= col_start <= width:
            return None, "column %d is outside the line (%d characters)" % (col_start, width)
        a = base + col_start
        b = a + len(want)
    elif not want:
        return None, "finding %d: an empty text needs col_start to say where it goes" % n
    else:
        # Up to and including the line's end, so a text that starts with the
        # newline, to join this line to the next, still has a place to start.
        starts = [c for c in range(width + 1) if text.s.startswith(want, base + c)]
        if not starts:
            return None, "finding %d: %r does not start on this line. Re-run the report." % (
                n,
                want[:60],
            )
        if len(starts) > 1:
            return None, (
                "finding %d: %r starts at columns %s on this line; add col_start to say which"
                % (n, want[:60], ", ".join(str(c) for c in starts))
            )
        a = base + starts[0]
        b = a + len(want)
    current = text.s[a:b]
    if want is not None and current != want:
        return None, "the text moved; expected %r, found %r. Re-run the report." % (
            want[:60],
            current[:60],
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
    """

    def __init__(self, engine, accepted, applied, rejected):
        self.engine = engine
        self.accepted = accepted
        self.applied = applied
        self.rejected = rejected


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
    """
    engine = EditEngine(text)
    applied, rejected, accepted, placed = [], [], [], []
    for n, f in zip(numbers or range(1, len(findings) + 1), findings):
        line = int(f.get("line", 0))
        if line < 1 or line > text.line_count():
            rejected.append("%s:%s  line is outside the file" % (rel, line))
            continue
        if blocks.is_protected(line):
            rejected.append(
                "%s:%d  is a %s; prose rules do not apply there" % (rel, line, blocks.kind(line))
            )
            continue
        span, problem = locate(text, line, f, n)
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
        new = f.get("replacement", "")
        if blocks.kind(line) == "table" and ("|" in new or "\n" in new):
            rejected.append("%s:%d  a table cell cannot contain | or a newline" % (rel, line))
            continue
        if "\n" in new and blocks.kind(line) != "paragraph" and not crossing:
            rejected.append(
                "%s:%d  a %s replacement cannot span lines" % (rel, line, blocks.kind(line))
            )
            continue
        item = blocks.item(line)
        if item:
            new = indent_new_lines(new, item[1])
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
    return Staged(engine, placed, applied, rejected)


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
  text         the text as it stands, copied exactly. apply finds it among
               the places that start on the line and refuses a finding
               whose text starts at none of them, or at more than one. A
               text holding a newline ends on a later line, so a wrapped
               sentence is one finding
  replacement  the rewrite; "" cuts the text, and a line cut whole goes
               with its newline. Defaults to ""
  col_start    optional: the 0-indexed column the text starts at, when it
               starts at more than one place on the line
  col_end      optional: the column the span ends at, on the same line.
               With both columns, text may be left out, and without text
               the columns default to the whole line
  why          optional: one clause saying why, which report shows and
               apply ignores

  A replacement may hold a newline when the finding starts in a paragraph,
  or when its span already crosses a line. A span can cross lines only
  within paragraphs and list items. In a list item, apply indents each new
  line to the item's text, so it stays in the item. A table cell's
  replacement can hold neither a newline nor a |.

example:
  [{"file": "notes.md", "line": 12, "rule": "sentences-own-subject",
    "text": "Able to state\\n  what is inside the file.",
    "replacement": "A reader can state what is inside the file."}]
"""


def select_findings(args, config):
    """The findings --only and --file keep, by file, and the ones refused.

    Returns (by_file, rejected). by_file maps each file to its
    findings as (place in the whole batch, counting from 1, finding).
    """
    findings = read_json(args.findings, "findings")
    only = set(x.strip() for x in args.only.split(",")) if args.only else None
    files = set(os.path.normpath(p) for p in args.file) if args.file else None
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


# What the report shows for an empty text, which would otherwise print as
# nothing at all and read as a finding with its text missing.
REPORT_NOTHING = "(nothing: this inserts)"
REPORT_CUT = "(cut)"
REPORT_LABEL_WIDTH = len("proposed") + 2
# Each line of a current or proposed text is printed between these, so a
# space at either end of it shows. A finding's text often starts with one: the
# dash in "holds - until" is addressed as " - until".
REPORT_FENCE = "|"


def report_text(value, placeholder):
    """A current or proposed text as the report prints it: each line fenced,
    or the unfenced placeholder when the text is empty.

    The placeholder stays unfenced so it cannot be read as a text, even one
    that says "(cut)".
    """
    if not value:
        return placeholder
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


def cmd_report(args):
    """The findings as the author approves them, read against the files now.

    The current text is what is at each finding's place in the file, not what
    the finding says is there, so the report cannot show one text and apply
    change another. A finding apply would refuse is an error here too, and so
    is each pair of findings apply could not do both of.
    """
    repo, config, _ = load(args)
    by_file, rejected = select_findings(args, config)
    rows, overlaps = [], []
    for _path, rel, text, numbers, mine in selected_files(repo, by_file, rejected):
        staged = stage_findings(text, Blocks(text), rel, mine, numbers)
        rejected.extend(staged.rejected)
        for n, f, a, b in staged.accepted:
            rows.append(
                {
                    "finding": n,
                    "file": rel,
                    "line": int(f["line"]),
                    "rule": f["rule"],
                    "current": text.s[a:b],
                    "proposed": f.get("replacement", ""),
                    "why": f.get("why", ""),
                }
            )
        for x, y in staged.engine.conflicts():
            overlaps.append({"first": edit_refs(x), "second": edit_refs(y)})
            rejected.append(
                "%s  %s overlaps %s; they cannot both apply"
                % (rel, EditEngine.describe(x), EditEngine.describe(y))
            )
    rows.sort(key=lambda r: (r["file"], r["line"], r["finding"]))
    data = {"findings": rows, "overlaps": overlaps}

    def human():
        for r in rows:
            print("%s:%d  %s  (finding %d)" % (r["file"], r["line"], r["rule"], r["finding"]))
            print(report_field("current", report_text(r["current"], REPORT_NOTHING)))
            print(report_field("proposed", report_text(r["proposed"], REPORT_CUT)))
            if r["why"]:
                print(report_field("why", r["why"]))
            print()
        print("%d finding(s) in %d file(s)" % (len(rows), len(set(r["file"] for r in rows))))

    return emit(args, "report", repo.root, data, errors=rejected, human=human)


def cmd_apply(args):
    repo, config, _ = load(args)
    by_file, rejected = select_findings(args, config)
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


def cmd_restore(args):
    repo, _, _ = load(args)
    rel = os.path.relpath(os.path.abspath(args.target), repo.root)
    content = repo.show(args.ref, rel)
    if content is None:
        raise Fatal("%s is not in %s" % (rel, args.ref))
    # git show into the file, rather than git checkout, because the bridge
    # cannot unlink and checkout fails there.
    Text(content).write(repo.abspath(rel))
    return emit(
        args,
        "restore",
        repo.root,
        {"path": rel, "ref": args.ref},
        human=lambda: print("restored %s from %s" % (rel, args.ref)),
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

    ap = argparse.ArgumentParser(
        prog="prose.py", description="Deterministic half of the prose-tuning skills."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", parents=[common], help="refuse-to-run check for one skill")
    p.add_argument("--for", dest="for_target", required=True, choices=["config", "apply", "adopt"])
    p.add_argument("--force", action="store_true", help="apply only: proceed despite blockers")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("status", parents=[common], help="what is in the working tree right now")
    p.set_defaults(func=cmd_status)

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
    p.add_argument(
        "--summary",
        action="store_true",
        help="one line per file: segments, characters and protected lines, then the totals",
    )
    p.set_defaults(func=cmd_segments)

    p = sub.add_parser(
        "evidence", parents=[common], help="explicit tags, inferred edits and open questions"
    )
    p.add_argument("--since", default="HEAD", metavar="REF")
    p.add_argument(
        "--ignore",
        action="append",
        metavar="FILE:LINE",
        help="suppress one inferred hunk (repeatable)",
    )
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("config", parents=[common], help="the rule file")
    csub = p.add_subparsers(dest="config_cmd", required=True)
    for name, helptext in [
        ("list", "the rules"),
        ("lint", "check the file"),
        ("check-id", "is this id well-formed and free"),
        ("similar", "rules two files state twice"),
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
        if name == "similar":
            c.add_argument(
                "--to", required=True, metavar="PATH", help="the prose-style.md to compare against"
            )
            c.add_argument("--threshold", type=float, default=0.6, metavar="N")
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
    for name, helptext in [
        ("check", "validate"),
        ("list", "report"),
        ("insert", "add markup"),
        ("resolve", "accept the edits and remove markup"),
        ("strip", "abandon the edits and remove markup"),
    ]:
        t = tsub.add_parser(name, parents=[common], help=helptext)
        if name == "insert":
            t.add_argument(
                "--batch",
                required=True,
                metavar="FILE",
                help="JSON array of records, or - for stdin",
            )
            t.add_argument(
                "--partial", action="store_true", help="apply what is valid instead of nothing"
            )
            t.add_argument("--dry-run", action="store_true")
        else:
            t.add_argument("paths", nargs="*")
        if name in ("resolve", "strip"):
            t.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_tags)

    # report and apply read one findings file through the same filters, so
    # the report the author approves is the batch apply is handed.
    findings = argparse.ArgumentParser(add_help=False)
    findings.add_argument(
        "--findings",
        required=True,
        metavar="FILE",
        help="JSON array of findings, described below, or - for stdin",
    )
    findings.add_argument("--only", metavar="ID,ID", help="only these rule ids")
    findings.add_argument(
        "--file",
        action="append",
        metavar="PATH",
        help="only findings in this file; repeat for more",
    )

    p = sub.add_parser(
        "report",
        parents=[common, findings],
        help="the findings, for approval",
        description="Print the findings for approval, read against the files as they are now, "
        "and name every pair of them that overlaps.",
        epilog=FINDINGS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    p.add_argument(
        "--partial",
        action="store_true",
        help="apply what is valid and report the rest, instead of writing nothing",
    )
    p.add_argument("--dry-run", action="store_true", help="report without writing")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("restore", parents=[common], help="put a file back to its committed state")
    p.add_argument("--file", dest="target", required=True, metavar="PATH")
    p.add_argument("--ref", default="HEAD")
    p.set_defaults(func=cmd_restore)

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

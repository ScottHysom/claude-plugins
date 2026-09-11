#!/usr/bin/env python3
"""Deterministic half of the prose-tuning skills.

The three skills in this plugin use the model only for what genuinely needs
judgement: inferring a rule from an edit, writing prose, deciding whether a
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
    segments    the prose-eligible spans of a file
    evidence    explicit tags + inferred edits + open questions
    config      list | lint | check-id | similar | init
    tags        check | list | insert | resolve | strip
    apply       apply approved rewrites
    restore     put a file back to its committed state

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Two things in here look like bugs and are not:

1. Files are rewritten in place with open(path, "w") rather than written to a
   temp file and moved into position. The usual temp-file-then-os.replace dance
   unlinks the target, and this script has to run against a folder on the Cowork
   device bridge, which cannot unlink. Do not "fix" this.

2. Git is only ever read (rev-parse, ls-files, status, check-ignore, show).
   Nothing here writes through git, so no .git/*.lock is ever created. The
   bridge strands those locks because it cannot delete them, which is the whole
   reason the projects this runs against carry a commit.sh.

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

CONFIG_NAME = "prose-style.md"

DEFAULT_INCLUDE = ["**/*.md"]
DEFAULT_EXCLUDE = [
    CONFIG_NAME,
    "project-instructions.md",
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
        print(json.dumps(envelope(command, repo, data, errors, warnings),
                         indent=2, sort_keys=True))
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
    missing final newline. scripts/tests asserts that.
    """

    def __init__(self, s):
        self.s = s
        self.lines = s.splitlines(keepends=True)
        self.starts = []
        off = 0
        for ln in self.lines:
            self.starts.append(off)
            off += len(ln)
        self.end = off

    @classmethod
    def read(cls, path):
        with open(path, "r", encoding="utf-8", newline="") as fh:
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
        return self.lines[n - 1].splitlines()[0] if self.lines[n - 1] else ""

    def offset(self, line, col=0):
        if line < 1 or line > len(self.lines):
            raise Fatal("line %d out of range (file has %d lines)"
                        % (line, len(self.lines)))
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
        out = []
        ordered = sorted(self.edits, key=lambda e: (e[0], e[1]))
        for a, b in zip(ordered, ordered[1:]):
            if b[0] < a[1]:
                out.append("overlapping edits at offsets %d-%d and %d-%d"
                           % (a[0], a[1], b[0], b[1]))
        return out

    def result(self):
        bad = self.conflicts()
        if bad:
            raise Fatal("; ".join(bad))
        s = self.text.s
        for start, end, replacement, _ in sorted(
                self.edits, key=lambda e: e[0], reverse=True):
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
                capture_output=True, text=True, check=False)
        except FileNotFoundError:
            raise Fatal("git is not installed, or not on PATH")
        if out.returncode != 0:
            raise Fatal("%s is not inside a git repository" % start)
        self.root = out.stdout.strip()

    def git(self, *args):
        out = subprocess.run(["git", "-C", self.root] + list(args),
                             capture_output=True, text=True, check=False)
        return out.returncode, out.stdout, out.stderr

    def _lines(self, *args):
        code, stdout, stderr = self.git(*args)
        if code != 0:
            raise Fatal("git %s failed: %s" % (" ".join(args), stderr.strip()))
        return [x for x in stdout.split("\n") if x]

    def tracked_md(self):
        return self._lines("ls-files", "--", "*.md")

    def untracked_md(self):
        return self._lines("ls-files", "--others", "--exclude-standard",
                           "--", "*.md")

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
        return ("rule id is positional; expected "
                "'### <section>-<name>: <Title>', where the name is one to "
                "%d words saying what the rule means" % MAX_NAME_WORDS)
    words = name.split("-")
    if any(w[:1].isdigit() for w in words):
        return ("rule name %r carries a number; a name says what a rule "
                "means, not where it was written" % name)
    if not RULE_NAME.match(name):
        return "rule name %r is not lower-case words joined by '-'" % name
    if len(words) > MAX_NAME_WORDS:
        return ("rule name %r has %d words; at most %d. A name that needs "
                "more is a rule that has not been decided yet"
                % (name, len(words), MAX_NAME_WORDS))
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
        """The body normalised for comparison, for adopt-prose.

        HTML comments go: a FILL marker tells one project what to supply and is
        not part of the rule, so two rules differing only by one are the same
        rule. Whitespace collapses, because a rewrap is not an edit.
        """
        stripped = re.sub(r"<!--.*?-->", " ", self.body_text(), flags=re.S)
        return " ".join(stripped.split())

    def as_dict(self):
        return {
            "id": self.id, "section": self.section, "name": self.name,
            "title": self.title, "line": self.line, "group": self.group,
            "meta": self.meta, "body": self.body_text(),
            "body_key": self.body_key(),
            "example": (None if self.before is None and self.after is None
                        else {"before": self.before, "after": self.after}),
        }


class Config:
    """prose-style.md: restricted front matter plus one H3 per rule.

    The front-matter grammar is deliberately small rather than accidentally
    small. Stdlib only means no PyYAML, so anything richer would be parsed by
    guesswork. lint rejects out-of-grammar keys loudly, because a silently
    dropped key is a scope override that looks like it works.
    """

    def __init__(self, path):
        self.path = path
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
        return os.path.basename(self.path)

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
            self.errors.append("%s:1  no front matter; the file must open "
                               "with a --- fence" % self.rel())
            return 0
        close = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                close = i
                break
        if close is None:
            self.errors.append("%s:1  front matter is never closed" % self.rel())
            return 0

        target = None       # None at top level, else the list being filled
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
                target = (self.scope_include if sub.group(1) == "include"
                          else self.scope_exclude)
                continue
            item = FM_ITEM.match(raw)
            if item:
                if target is None:
                    self._err(num, "list item outside include: or exclude:")
                    continue
                target.append(unquote(item.group(1)))
                continue
            if raw[0] in " \t":
                self._err(num, "indented line is not a scope key or list item: %r"
                          % raw)
                continue
            key = FM_KEY.match(raw)
            if not key:
                self._err(num, "not a key: value pair: %r" % raw)
                continue
            name, value = key.group(1), key.group(2)
            if name == "scope":
                if value:
                    self._err(num, "scope: takes no value; put include: and "
                                   "exclude: beneath it")
                in_scope, target = True, None
                continue
            in_scope, target = False, None
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
                    self._err(num, "rule heading carries no id; expected "
                                   "'### <section>-<name>: <Title>'")
                    continue
                current = Rule(("%s-%s" % (m.group(1), m.group(2))),
                               m.group(1), m.group(2), m.group(3), num)
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
                self._err(rule.line, "duplicate rule id %s; first defined at "
                                     "line %d" % (rule.id, seen[rule.id]))
            else:
                seen[rule.id] = rule.line
            bad = validate_rule_name(rule.name)
            if bad:
                self._err(rule.line, bad)
            elif rule.name.split("-")[0] == rule.section:
                self._warn(rule.line, "rule name %s opens with its own "
                                      "section; the id already says %s"
                           % (rule.name, rule.section))
            for k, v in rule.meta.items():
                if k not in META_KEYS:
                    self._err(rule.line, "unknown metadata key %r; allowed: %s"
                              % (k, ", ".join(sorted(META_KEYS))))
                elif k == "source" and v not in META_SOURCES:
                    self._err(rule.line, "source=%s is not one of %s"
                              % (v, ", ".join(sorted(META_SOURCES))))
            if not rule.body_text():
                self._err(rule.line, "rule %s has no body" % rule.id)
            if rule.before is None and rule.after is None:
                self._warn(rule.line, "rule %s has no worked example; a rule "
                                      "with no example does not survive contact"
                           % rule.id)
            elif rule.before is None or rule.after is None:
                self._err(rule.line, "rule %s has half an example; Before and "
                                     "After come as a pair" % rule.id)
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
            return rid, ("%s is already the id of the rule at %s:%d - %s"
                         % (rid, self.rel(), taken.line, taken.title))
        return rid, None

    def by_id(self):
        return dict((r.id, r) for r in self.rules)


def config_path(repo, override=None):
    return os.path.abspath(override) if override \
        else os.path.join(repo.root, CONFIG_NAME)


# --------------------------------------------------------------------------
# which files the rules govern
# --------------------------------------------------------------------------

class Scope:
    """File selection, with the config's scope: block overriding the defaults.

    include/exclude replace the defaults wholesale when present. Partial
    override was considered and rejected: "which of the four defaults am I
    still getting" is not a question anyone should answer by reading a script.

    prose-style.md is excluded unconditionally, override or not. apply-prose
    rewriting its own rulebook is not a thing anyone wants to debug.
    """

    def __init__(self, repo, config):
        self.repo = repo
        self.config = config
        self.include = config.scope_include or list(DEFAULT_INCLUDE)
        self.exclude = config.scope_exclude or list(DEFAULT_EXCLUDE)
        self.overridden = bool(config.scope_include or config.scope_exclude)
        self._inc = Matcher(self.include)
        self._exc = Matcher(self.exclude)
        self._config_rel = os.path.relpath(config.path, repo.root) \
            if config.path.startswith(repo.root) else None

    def verdicts(self):
        out = []
        for rel in self.repo.all_md():
            if self._config_rel and rel == self._config_rel:
                out.append({"path": rel, "included": False,
                            "reason": "the config itself"})
                continue
            hit = self._inc.match(rel)
            if not hit:
                out.append({"path": rel, "included": False,
                            "reason": "no include pattern matched"})
                continue
            bad = self._exc.match(rel)
            if bad:
                out.append({"path": rel, "included": False,
                            "reason": "excluded by %s" % bad})
                continue
            out.append({"path": rel, "included": True,
                        "reason": "included by %s" % hit})
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

# Kinds that prose rules must never be applied inside.
PROTECTED_KINDS = {"frontmatter", "fence", "blockquote"}


class Blocks:
    """Per-line classification of one markdown file.

    segments uses this so apply-prose is handed only the spans it may rewrite.
    Telling a model "do not touch code fences" is a rule that gets broken;
    never showing it the fence makes the mistake unavailable.
    """

    def __init__(self, text):
        self.text = text
        n = text.line_count()
        self.kinds = ["paragraph"] * n
        self.info = [""] * n
        self.headings = []
        self._classify()

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
                    close = re.match(r"^\s{0,3}(%s{%d,})\s*$"
                                     % (re.escape(char), width), lines[j])
                    if close:
                        break
                    j += 1
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

            if "|" in line and i + 1 < n and TABLE_DELIM.match(lines[i + 1]) \
                    and "|" in lines[i + 1]:
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
        runs = [m for m in re.finditer(r"`+", self.text.s)
                if not any(a <= m.start() < b for a, b in fences)]
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
                out.append((self.text.offset(start + 1),
                            self.text.offset(i + 1)))
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
ALLOWED_ATTRS = {"ins": {"why"}, "del": {"why"}, "repl": {"why"},
                 "q": {"id"}, "a": set(), "why": set(), "alt": set()}
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
        return text.s[self.open_end:self.close_start]

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
        return [strip_tags(c.inner(text)).strip()
                for c in self.children if c.kind == "alt"]


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
        self.errors.append("%s:%d  %s"
                           % (self.path, self.text.line_of(offset), msg))

    def _warn(self, offset, msg):
        self.warnings.append("%s:%d  %s"
                             % (self.path, self.text.line_of(offset), msg))

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
            closing = self.text.s[start:start + 2] == "</"

            if closing:
                if not stack:
                    self._err(start, "stray </%s> closing nothing" % kind)
                    continue
                node = stack.pop()
                if node.kind != kind:
                    # Close it anyway. One typo should produce one message,
                    # not a mismatch now and an "unclosed" later.
                    self._err(start, "</%s> closes <%s> opened at line %d"
                              % (kind, node.kind, node.line))
                node.close_start, node.close_end = start, end
                continue

            attrs = {}
            for am in ATTR_RE.finditer(raw_attrs):
                attrs[am.group(1)] = am.group(3) if am.group(3) is not None \
                    else am.group(4)
            leftover = ATTR_RE.sub("", raw_attrs).strip()

            # <a href="..."> is an HTML anchor, not an answer. Skipping it is
            # deliberate; erroring would make ordinary markdown unparseable.
            if kind == "a" and attrs:
                continue

            allowed = ALLOWED_ATTRS[kind]
            for name in attrs:
                if name not in allowed:
                    self._err(start, "<%s> has no %r attribute; allowed: %s"
                              % (kind, name,
                                 ", ".join(sorted(allowed)) or "none"))
            if leftover:
                self._err(start, "<%s> has unparseable attribute text %r; "
                                 "attribute values need quotes"
                          % (kind, leftover))

            node = Tag(kind, attrs, start, end, self.text.line_of(start))
            if stack:
                parent = stack[-1]
                if kind not in ALLOWED_CHILDREN[parent.kind]:
                    self._err(start, "<%s> is not allowed inside <%s>"
                              % (kind, parent.kind))
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
                    self._err(node.open_start,
                              "<repl> holds %d <del> and %d <ins>; it takes "
                              "exactly one of each, <del> first"
                              % (len(dels), len(inss)))
                elif dels[0].open_start > inss[0].open_start:
                    self._err(node.open_start,
                              "<repl> has <ins> before <del>; the old prose "
                              "comes first")
            if node.kind == "q":
                qid = node.attrs.get("id")
                if qid is None:
                    self._warn(node.open_start,
                               "<q> has no id; run tags insert to number it")
                elif qid in qids:
                    self._err(node.open_start,
                              "duplicate question id %s; first at line %d"
                              % (qid, qids[qid]))
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
            if a.kind == "del" and b.kind == "ins" \
                    and not self.text.s[a.close_end:b.open_start].strip():
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
    if text.s[start:node.open_start].strip():
        return False
    _, end = _line_bounds(text, max(node.close_end - 1, 0))
    return not text.s[node.close_end:end].strip()


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
    out = resolved(node, text, mode)
    if out and is_block_form(node, text) and not out.endswith("\n"):
        out += "\n"
    return out


def resolved_inner(node, text, mode):
    parts, cursor = [], node.open_end
    for child in node.children:
        start, end = node_span(child, text)
        parts.append(text.s[cursor:max(start, cursor)])
        parts.append(top_replacement(child, text, mode))
        cursor = max(end, cursor)
    parts.append(text.s[cursor:node.close_start])
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
            out.append("%s:%d  block-form <%s> resolved inside a list; check "
                       "the list still reads as one list"
                       % (scanner.path, node.line, node.kind))
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
        raise InsertRefusal("kind %r is not one of %s"
                            % (kind, ", ".join(INSERTABLE)))
    start_line = int(rec.get("start", 0))
    if start_line < 1 or start_line > text.line_count():
        raise InsertRefusal("line %d is outside the file (%d lines)"
                            % (start_line, text.line_count()))
    end_line = int(rec.get("end", start_line))
    if end_line < start_line or end_line > text.line_count():
        raise InsertRefusal("end line %d is outside the span" % end_line)
    why = rec.get("why", "")
    body = rec.get("text", "")
    indent = " " * blocks.continuation_indent(start_line)

    if kind in ("q", "alt"):
        if not body:
            raise InsertRefusal("<%s> needs text" % kind)
        ident = ' id="%s"' % qid if kind == "q" else ""
        at = text.offset(start_line, 0)
        return [(at, at, "%s<%s%s>%s</%s>\n" % (indent, kind, ident, body, kind))]

    for line in range(start_line, end_line + 1):
        if blocks.kind(line) in UNSAFE_SPAN_KINDS:
            raise InsertRefusal("line %d is a %s; markup there would break it"
                                % (line, blocks.kind(line)))

    col_start = int(rec.get("col_start", 0))
    last = text.bare(end_line)
    col_end = int(rec.get("col_end", len(last)))
    whole_lines = col_start == 0 and col_end == len(last)
    inline = start_line == end_line

    if not inline and not whole_lines:
        raise InsertRefusal("a span that starts mid-line and ends on another "
                            "line straddles blocks; give whole lines, or keep "
                            "it inside one line")

    a = text.offset(start_line, col_start)
    b = text.offset(end_line, col_end)

    if kind == "ins":
        if not body:
            raise InsertRefusal("<ins> needs text")
        if inline:
            return [(a, a, "<ins>%s</ins>" % body)]
        raise InsertRefusal("<ins> inserts at a point; give one line")

    if inline:
        if why and '"' in why:
            raise InsertRefusal("a why containing a double quote needs block "
                                "form; give whole lines")
        if kind == "del":
            return [(a, a, "<del%s>" % attr_text(why)), (b, b, "</del>")]
        new = rec.get("with")
        if new is None:
            raise InsertRefusal("<repl> needs a with value")
        if why:
            return [(a, a, '<repl%s><del>' % attr_text(why)),
                    (b, b, "</del><ins>%s</ins></repl>" % new)]
        return [(a, a, "<del>"), (b, b, "</del><ins>%s</ins>" % new)]

    # Block form. The span is replaced wholesale so the opening and closing
    # tags land on their own lines at the enclosing list item's indent, which
    # is what keeps a tag from ending the list it sits in.
    first = text.bare(start_line)
    indent = " " * (len(first) - len(first.lstrip()))
    block_start = text.offset(start_line, 0)
    block_end = text.offset(end_line) + len(text.line(end_line))
    original = text.s[block_start:block_end]
    if not original.endswith("\n"):
        original += "\n"
    why_line = ""
    if why and '"' in why:
        why_line = "%s  <why>%s</why>\n" % (indent, why)
        why = ""
    attrs = attr_text(why)

    if kind == "del":
        out = "%s<del%s>\n%s%s%s</del>\n" % (indent, attrs, why_line,
                                             original, indent)
        return [(block_start, block_end, out)]

    new = rec.get("with")
    if new is None:
        raise InsertRefusal("<repl> needs a with value")
    new_block = "".join("%s%s\n" % (indent, x) for x in new.split("\n"))

    out = ("%s<repl%s>\n%s%s<del>\n%s%s</del>\n%s<ins>\n%s%s</ins>\n%s</repl>\n"
           % (indent, attrs, why_line, indent, original, indent,
              indent, new_block, indent, indent))
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
    out = []
    for line in range(1, text.line_count() + 1):
        kind = blocks.kind(line)
        raw = text.bare(line)
        if kind in PROTECTED_KINDS or kind == "blank" or not raw.strip():
            continue
        if kind == "heading":
            m = HEADING_PREFIX.match(raw)
            start = len(m.group(1)) if m else 0
            out.append({"line": line, "col_start": start, "col_end": len(raw),
                        "kind": "heading", "text": raw[start:]})
        elif kind == "table":
            if TABLE_DELIM.match(raw):
                continue
            col = 0
            for cell in raw.split("|"):
                if cell.strip():
                    lead = len(cell) - len(cell.lstrip())
                    out.append({"line": line, "col_start": col + lead,
                                "col_end": col + len(cell.rstrip()),
                                "kind": "table-cell", "text": cell.strip()})
                col += len(cell) + 1
        elif kind == "list-item":
            m = LIST_ITEM.match(raw)
            start = len(m.group(0)) if m else 0
            out.append({"line": line, "col_start": start, "col_end": len(raw),
                        "kind": "list-item", "text": raw[start:]})
        else:
            lead = len(raw) - len(raw.lstrip())
            out.append({"line": line, "col_start": lead, "col_end": len(raw),
                        "kind": "paragraph", "text": raw.strip()})
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
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
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
        out.append({
            "file": rel, "kind": "repl", "start": a.line, "end": b.line,
            "old_text": tidy_block(strip_tags(a.inner(text))).strip(),
            "new_text": tidy_block(strip_tags(b.inner(text))).strip(),
            "why": a.whys(text) + b.whys(text),
            "alt": a.alts(text) + b.alts(text),
            "heading_path": blocks.heading_path(a.line),
            "block_kind": blocks.kind(a.line),
            "form": "pair",
        })
    for node in scanner.roots:
        if id(node) in paired or node.kind not in EDIT_KINDS:
            continue
        rec = {
            "file": rel, "kind": node.kind, "start": node.line,
            "end": text.line_of(max(node.close_end - 1, 0)),
            "why": node.whys(text), "alt": node.alts(text),
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
        for later in roots[n + 1:]:
            if later.kind == "a":
                answer = strip_tags(later.inner(text)).strip()
                break
            if later.kind == "q":
                break
        out.append({"file": rel, "line": node.line,
                    "id": node.attrs.get("id"),
                    "question": strip_tags(node.inner(text)).strip(),
                    "answer": answer})
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
    sm = difflib.SequenceMatcher(None, base_lines, neutral_lines,
                                 autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old = base_lines[i1:i2]
        new = neutral_lines[j1:j2]
        line = nearest(to_work, j1, j1) + 1
        if "%s:%d" % (rel, line) in ignore:
            continue
        out.append({
            "file": rel, "start": line,
            "end": nearest(to_work, max(j2 - 1, j1), j2) + 1,
            "change": tag,
            "old_lines": old, "new_lines": new,
            "signal": classify_signal("\n".join(old), "\n".join(new)),
        })
    return out, False


def apply_inserts(text, blocks, records, path, qid_start):
    """Returns (engine, refusals, next_qid). The caller decides all-or-nothing."""
    engine = EditEngine(text)
    refusals, qid = [], qid_start
    for n, rec in enumerate(records):
        try:
            edits = plan_one_insert(text, blocks, rec, path, qid)
        except InsertRefusal as exc:
            refusals.append("%s:%s  record %d refused: %s"
                            % (path, rec.get("start", "?"), n + 1, exc))
            continue
        except (TypeError, ValueError) as exc:
            refusals.append("%s  record %d is malformed: %s" % (path, n + 1, exc))
            continue
        if rec.get("kind") == "q":
            qid += 1
        for a, b, replacement in edits:
            engine.replace(a, b, replacement)
    return engine, refusals, qid


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def load(args):
    """repo, config, scope for one invocation.

    The config override is `config_file`, not `file`: restore takes a --file of
    its own, and one shared attribute name would have it silently reinterpreted
    as a path to prose-style.md.
    """
    repo = Repo(args.repo)
    config = Config(config_path(repo, getattr(args, "config_file", None)))
    return repo, config, Scope(repo, config)


def cmd_scope(args):
    repo, config, scope = load(args)
    verdicts = scope.verdicts()
    shown = verdicts if args.all else [v for v in verdicts if v["included"]]
    data = {"include": scope.include, "exclude": scope.exclude,
            "overridden": scope.overridden, "files": shown,
            "count": sum(1 for v in verdicts if v["included"])}

    def human():
        for v in shown:
            if args.all:
                print("%s %-62s %s" % ("+" if v["included"] else "-",
                                       v["path"], v["reason"]))
            else:
                print(v["path"])
        print("\n%d file(s) in scope of %d markdown file(s)"
              % (data["count"], len(verdicts)))
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
        "config": {"path": config.rel(), "exists": config.exists,
                   "rules": len(config.rules),
                   "errors": config.errors, "warnings": config.warnings},
        "scope": {"count": len(files), "overridden": scope.overridden},
        "dirty": [{"status": s, "path": p} for s, p in dirty],
        "tags": tags, "unanswered_questions": unanswered,
        "markup_errors": errors,
    }

    def human():
        print("repo    %s" % repo.root)
        print("config  %s  %s"
              % (config.rel(), "%d rule(s)" % len(config.rules)
                 if config.exists else "MISSING - run config init"))
        print("scope   %d file(s)%s"
              % (len(files), " (overridden)" if scope.overridden else ""))
        print("dirty   %d markdown file(s)" % len(dirty))
        for s, p in dirty:
            print("          %-2s %s" % (s, p))
        if tags:
            print("markup")
            for rel in sorted(tags):
                counts = ", ".join("%d %s" % (v, k)
                                   for k, v in sorted(tags[rel].items()))
                print("          %s  %s" % (rel, counts))
            print("        %d unanswered question(s)" % unanswered)
        else:
            print("markup  none")
        for e in errors:
            print("!! %s" % e)
    # status reports; it does not judge. Tags present is a normal mid-run
    # state for update-prose-config, so this never exits 1.
    return emit(args, "status", repo.root, data, human=human)


def cmd_preflight(args):
    repo, config, scope = load(args)
    want = args.for_target
    blockers = []
    if sys.version_info < (3, 9):
        blockers.append("python3 is %d.%d; this script needs 3.9 or newer"
                        % sys.version_info[:2])
    if not config.exists:
        if want in ("apply", "adopt"):
            blockers.append("%s  no config; run: prose.py config init"
                            % config.rel())
    else:
        blockers += config.errors

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
            blockers.append("%s:%d  markup is present; an update-prose-config "
                            "run is in progress" % (rel, line))
        for status, rel in repo.dirty_md():
            if rel in in_scope:
                blockers.append("%s  uncommitted (%s); commit or stash before "
                                "conforming prose" % (rel, status))
        if blockers and not args.force:
            hints.append("pass --force only if the author asked for it by name")

    data = {"for": want, "blockers": blockers, "hints": hints,
            "tagged_files": [r for r, _ in tagged],
            "config_exists": config.exists, "scope_count": len(files)}

    def human():
        if not blockers:
            print("ok: nothing blocks %s" % want)
        else:
            print("%d blocker(s) for %s" % (len(blockers), want))

    if args.force and want == "apply":
        blockers = []
    return emit(args, "preflight", repo.root, data, errors=blockers,
                warnings=hints, human=human)


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
        data[rel] = {"segments": segs, "protected_lines": protected,
                     "lines": text.line_count()}

    def human():
        for rel in sorted(data):
            d = data[rel]
            print("%s  %d segment(s), %d protected line(s) of %d"
                  % (rel, len(d["segments"]), d["protected_lines"], d["lines"]))
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
        "base_ref": ref, "explicit": explicit, "inferred": inferred,
        "questions": questions, "new_files": new_files,
        "counts": {"explicit": len(explicit), "inferred": len(inferred),
                   "questions": len(questions), "unanswered": unanswered,
                   "files": len(scope.files())},
    }

    def human():
        print("base %s" % ref)
        for rec in explicit:
            print("  explicit %s:%d [%s] %s"
                  % (rec["file"], rec["start"], rec["kind"],
                     (rec["why"] or [""])[0]))
        for rec in inferred:
            flag = " (%s)" % rec["signal"] if rec["signal"] else ""
            print("  inferred %s:%d [%s]%s"
                  % (rec["file"], rec["start"], rec["change"], flag))
        for q in questions:
            print("  question %s:%d #%s %s"
                  % (q["file"], q["line"], q["id"],
                     "answered" if q["answer"] else "OPEN"))
        print("\nexplicit: %d  inferred: %d  unanswered: %d"
              % (len(explicit), len(inferred), unanswered))
        if new_files:
            print("untracked at %s: %s" % (ref, ", ".join(new_files)))
    return emit(args, "evidence", repo.root, data, errors=errors, human=human)


CONFIG_SKELETON = '''---
name: {name} prose style
scope:
  include:
{include}
  exclude:
{exclude}
---

# {name}: prose style

The house style for every document in this repo. Document mechanics - front
matter, TODO markers, commit format - live in the project's maintenance skill.
This file is authoritative on how the sentences read. The two never overlap.

A rule here has a stable id of the form `<section>-<name>`, where the name is
one to four words saying what the rule means. Reports name the id, and a rule
that gets reworded keeps its name. Git holds what the rule used to say, so
nothing here is ever marked retired.

## Standing instructions

<!-- One "### standing-<name>: Title" per rule, as in
     "### standing-us-spelling: Use US spelling". Run update-prose-config to
     fill this in from edits rather than writing rules from scratch. -->
'''


def cmd_config(args):
    repo, config, scope = load(args)
    which = args.config_cmd

    if which == "init":
        if config.exists:
            raise Fatal("%s already exists" % config.path)
        if args.source:
            if not os.path.exists(args.source):
                raise Fatal("%s does not exist" % args.source)
            Text(Text.read(args.source).s).write(config.path)
        else:
            fmt = lambda xs: "\n".join('    - "%s"' % x for x in xs)
            Text(CONFIG_SKELETON.format(
                name=os.path.basename(repo.root),
                include=fmt(DEFAULT_INCLUDE),
                exclude=fmt(DEFAULT_EXCLUDE))).write(config.path)
        return emit(args, "config init", repo.root, {"path": config.path},
                    human=lambda: print("wrote %s" % config.path))

    if not config.exists:
        raise Fatal("%s does not exist; run: prose.py config init"
                    % config.path)

    if which == "check-id":
        rid, problem = config.check_id(args.section, args.name)
        return emit(args, "config check-id", repo.root,
                    {"id": rid, "section": args.section, "name": args.name,
                     "free": problem is None},
                    errors=([problem] if problem else []),
                    # The id goes to stdout only when it is usable, so that
                    # ID=$(... check-id ...) cannot capture a refused one.
                    human=lambda: problem or print(rid))

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
                    pairs.append({"source": a.id, "target": b.id,
                                  "score": round(score, 2),
                                  "body": round(body, 2),
                                  "name": round(name, 2)})
        pairs.sort(key=lambda p: (-p["score"], p["source"], p["target"]))

        def human():
            w = max([len(p["source"]) for p in pairs] + [8])
            for p in pairs:
                print("%.2f  %-*s  %s   (body %.2f, name %.2f)"
                      % (p["score"], w, p["source"], p["target"],
                         p["body"], p["name"]))
            print("\n%d candidate pair(s) at or above %.2f; each is a question"
                  " for the author, not a decision."
                  % (len(pairs), args.threshold))
        return emit(args, "config similar", repo.root,
                    {"source": config.path,
                     "target": os.path.abspath(args.to),
                     "threshold": args.threshold, "pairs": pairs},
                    human=human)

    if which == "lint":
        def human():
            print("%s: %d rule(s), %d error(s), %d warning(s)"
                  % (config.rel(), len(config.rules), len(config.errors),
                     len(config.warnings)))
        return emit(args, "config lint", repo.root,
                    {"rules": len(config.rules)},
                    errors=config.errors, warnings=config.warnings,
                    human=human)

    rules = config.rules
    if args.rule:
        rules = [r for r in rules if r.id == args.rule]
        if not rules:
            raise Fatal("no rule with id %s in %s" % (args.rule, config.rel()))
    data = {"path": config.rel(), "front": config.front,
            "rules": [r.as_dict() for r in rules]}

    def human():
        if args.ids:
            for r in rules:
                print(r.id)
            return
        w = max([len(r.id) for r in rules] + [16])
        for r in rules:
            mark = " " if (r.before or r.after) else "!"
            print("%s %-*s %-10s %s" % (mark, w, r.id,
                                        r.meta.get("source", "-"), r.title))
        print("\n%d rule(s)%s" % (len(rules),
                                  "; ! marks one with no worked example"
                                  if any(not (r.before or r.after)
                                         for r in rules) else ""))
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
                data[rel] = {"counts": scanner.counts(), "tags": [
                    {"kind": n.kind, "line": n.line,
                     "form": "block" if is_block_form(n, text) else "inline",
                     "why": n.whys(text), "alt": n.alts(text),
                     "text": strip_tags(n.inner(text)).strip()[:200]}
                    for n in scanner.roots]}

        def human():
            total = 0
            for rel in sorted(data):
                print(rel)
                for tag in data[rel]["tags"]:
                    total += 1
                    if which == "list":
                        why = ("  %s" % tag["why"][0]) if tag["why"] else ""
                        print("  %4d  %-5s %-6s %s%s"
                              % (tag["line"], tag["kind"], tag["form"],
                                 tag["text"][:60], why))
            print("\n%d tag(s) in %d file(s)" % (total, len(data)))
        return emit(args, "tags " + which, repo.root, data,
                    errors=errors, warnings=warnings, human=human)

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
            return emit(args, "tags " + which, repo.root, {}, errors=errors,
                        warnings=warnings)
        for path, rel, new, count in pending:
            data[rel] = {"tags": count}
            if not args.dry_run:
                Text(new).write(path)

        def human():
            for rel in sorted(data):
                print("%s  %d tag(s) %s" % (rel, data[rel]["tags"],
                                            "would be " + which if args.dry_run
                                            else which + "d"))
            if not data:
                print("no markup found")
        return emit(args, "tags " + which, repo.root, data,
                    warnings=warnings, human=human)

    # insert
    raw = sys.stdin.read() if args.batch == "-" else open(
        args.batch, encoding="utf-8").read()
    try:
        records = json.loads(raw)
    except ValueError as exc:
        raise Fatal("batch is not valid JSON: %s" % exc)
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
        refusals.append("nothing was written; a half-applied batch leaves "
                        "every later line number wrong. Fix the batch and "
                        "re-run, or pass --partial.")
        return emit(args, "tags insert", repo.root, {"refused": len(refusals)},
                    errors=refusals)

    data = {}
    for path, rel, new in staged:
        if not args.dry_run:
            Text(new).write(path)
        scanner = TagScanner(Text(new), None, rel)
        data[rel] = {"tags": [{"kind": n.kind, "line": n.line}
                              for n in scanner.roots]}

    def human():
        for rel in sorted(data):
            for tag in data[rel]["tags"]:
                print("%s:%d  %s" % (rel, tag["line"], tag["kind"]))
        print("\n%d file(s) %s" % (len(data),
                                   "unchanged (dry run)" if args.dry_run
                                   else "written"))
    return emit(args, "tags insert", repo.root, data, errors=refusals,
                human=human)


def cmd_apply(args):
    repo, config, scope = load(args)
    try:
        findings = json.loads(open(args.findings, encoding="utf-8").read())
    except (IOError, ValueError) as exc:
        raise Fatal("cannot read findings: %s" % exc)
    only = set(x.strip() for x in args.only.split(",")) if args.only else None
    known = config.by_id()

    by_file, rejected = {}, []
    for n, f in enumerate(findings):
        if only and f.get("rule") not in only:
            continue
        if f.get("rule") not in known:
            rejected.append("finding %d names rule %r, which is not in %s"
                            % (n + 1, f.get("rule"), config.rel()))
            continue
        by_file.setdefault(f.get("file"), []).append(f)

    staged, applied = [], []
    for rel in sorted(by_file):
        path = repo.abspath(rel) if rel else None
        if not rel or not os.path.exists(path):
            rejected.append("%s  no such file" % rel)
            continue
        text = Text.read(path)
        blocks = Blocks(text)
        engine = EditEngine(text)
        for f in by_file[rel]:
            line = int(f.get("line", 0))
            if line < 1 or line > text.line_count():
                rejected.append("%s:%s  line is outside the file" % (rel, line))
                continue
            if blocks.is_protected(line):
                rejected.append("%s:%d  is a %s; prose rules do not apply there"
                                % (rel, line, blocks.kind(line)))
                continue
            a = text.offset(line, int(f.get("col_start", 0)))
            b = text.offset(line, int(f.get("col_end", len(text.bare(line)))))
            current = text.s[a:b]
            if f.get("text") is not None and current != f["text"]:
                rejected.append("%s:%d  the text moved; expected %r, found %r. "
                                "Re-run the report."
                                % (rel, line, f["text"][:60], current[:60]))
                continue
            new = f.get("replacement", "")
            if blocks.kind(line) == "table" and ("|" in new or "\n" in new):
                rejected.append("%s:%d  a table cell cannot contain | or a "
                                "newline" % (rel, line))
                continue
            if "\n" in new and blocks.kind(line) != "paragraph":
                rejected.append("%s:%d  a %s replacement cannot span lines"
                                % (rel, line, blocks.kind(line)))
                continue
            engine.replace(a, b, new)
            applied.append({"file": rel, "line": line, "rule": f["rule"]})
        try:
            staged.append((path, rel, engine.result()))
        except Fatal as exc:
            rejected.append("%s  %s" % (rel, exc))

    if rejected and not args.partial:
        rejected.append("nothing was written; pass --partial to apply the rest")
        return emit(args, "apply", repo.root, {"applied": []}, errors=rejected)

    for path, rel, new in staged:
        if not args.dry_run:
            Text(new).write(path)

    per_rule = {}
    for a in applied:
        per_rule[a["rule"]] = per_rule.get(a["rule"], 0) + 1
    data = {"applied": applied, "per_rule": per_rule,
            "files": sorted(set(a["file"] for a in applied))}

    def human():
        for rel in data["files"]:
            n = sum(1 for a in applied if a["file"] == rel)
            print("%s  %d edit(s)" % (rel, n))
        for rid in sorted(per_rule):
            print("  %-16s %d" % (rid, per_rule[rid]))
        print("\n%d edit(s) %s" % (len(applied),
                                   "not written (dry run)" if args.dry_run
                                   else "written"))
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
    return emit(args, "restore", repo.root, {"path": rel, "ref": args.ref},
                human=lambda: print("restored %s from %s" % (rel, args.ref)))


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------

def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true",
                        help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="PATH", default=None,
                        help="a path inside the repository (default: cwd)")

    ap = argparse.ArgumentParser(
        prog="prose.py",
        description="Deterministic half of the prose-tuning skills.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", parents=[common],
                       help="refuse-to-run check for one skill")
    p.add_argument("--for", dest="for_target", required=True,
                   choices=["config", "apply", "adopt"])
    p.add_argument("--force", action="store_true",
                   help="apply only: proceed despite blockers")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("status", parents=[common],
                       help="what is in the working tree right now")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("scope", parents=[common],
                       help="which files the prose rules govern")
    p.add_argument("--all", action="store_true",
                   help="every candidate, with the reason for each verdict")
    p.set_defaults(func=cmd_scope)

    p = sub.add_parser("segments", parents=[common],
                       help="the prose-eligible spans of a file")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_segments)

    p = sub.add_parser("evidence", parents=[common],
                       help="explicit tags, inferred edits and open questions")
    p.add_argument("--since", default="HEAD", metavar="REF")
    p.add_argument("--ignore", action="append", metavar="FILE:LINE",
                   help="suppress one inferred hunk (repeatable)")
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("config", parents=[common], help="the rule file")
    csub = p.add_subparsers(dest="config_cmd", required=True)
    for name, helptext in [("list", "the rules"), ("lint", "check the file"),
                           ("check-id", "is this id well-formed and free"),
                           ("similar", "rules two files state twice"),
                           ("init", "write a skeleton")]:
        c = csub.add_parser(name, parents=[common], help=helptext)
        c.add_argument("--file", dest="config_file", metavar="PATH",
                       help="a prose-style.md other than this repo's")
        if name == "list":
            c.add_argument("--rule", metavar="ID")
            c.add_argument("--ids", action="store_true")
        if name == "check-id":
            c.add_argument("--section", required=True)
            c.add_argument("--name", required=True,
                           help="one to four lower-case words joined by -")
        if name == "similar":
            c.add_argument("--to", required=True, metavar="PATH",
                           help="the prose-style.md to compare against")
            c.add_argument("--threshold", type=float, default=0.6, metavar="N")
        if name == "init":
            c.add_argument("--from", dest="source", metavar="PATH",
                           help="copy an existing config instead")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("tags", parents=[common], help="the markup")
    tsub = p.add_subparsers(dest="tags_cmd", required=True)
    for name, helptext in [("check", "validate"), ("list", "report"),
                           ("insert", "add markup"),
                           ("resolve", "accept the edits and remove markup"),
                           ("strip", "abandon the edits and remove markup")]:
        t = tsub.add_parser(name, parents=[common], help=helptext)
        if name == "insert":
            t.add_argument("--batch", required=True, metavar="FILE",
                           help="JSON array of records, or - for stdin")
            t.add_argument("--partial", action="store_true",
                           help="apply what is valid instead of nothing")
            t.add_argument("--dry-run", action="store_true")
        else:
            t.add_argument("paths", nargs="*")
        if name in ("resolve", "strip"):
            t.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_tags)

    p = sub.add_parser("apply", parents=[common],
                       help="apply approved rewrites")
    p.add_argument("--findings", required=True, metavar="FILE")
    p.add_argument("--only", metavar="ID,ID", help="only these rule ids")
    p.add_argument("--partial", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("restore", parents=[common],
                       help="put a file back to its committed state")
    p.add_argument("--file", dest="target", required=True, metavar="PATH")
    p.add_argument("--ref", default="HEAD")
    p.set_defaults(func=cmd_restore)

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

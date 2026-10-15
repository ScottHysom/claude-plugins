#!/usr/bin/env python3
"""File a plan's issues under a tracking issue once the owner approves the plan,
and close the tracking issue once every one of them has closed.

README.md, under "Issues", describes the process. The queue and the claim
lock that keep two agents off the same approved issue live in the flywheel
plugin's flywheel.py, and these plan commands move there too, under #647.

Run from anywhere in a clone, with git and an authenticated gh on PATH:

    python3 .github/scripts/issues.py plan draft
    python3 .github/scripts/issues.py plan report --drafts plan.json
    python3 .github/scripts/issues.py plan file --drafts plan.json --token 3f9a1c0e7b2d4a68
    python3 .github/scripts/issues.py plan close 347

Commands:
    plan draft  make an empty file in the temporary directory for a plan's
                drafts, named so that no other run gets it, and print its path.
    plan report check a plan's drafts, print the plan as it will be filed,
                ending with an approval token, and write the same report to
                .issues-plan/report.md.
    plan file   file the plan that report showed: its issues, their "blocked
                by" links, the tracking issue and its sub-issues, then read
                them back.
    plan close N
                close approved tracking issue N, with a comment naming its
                sub-issues, once every one of them is closed.

Every command takes --json and -C/--repo; plan file takes --dry-run.

Exit codes: 0 clean, 1 ran and found problems (a plan is refused or not filed
as it says, a tracking issue is not an open approved plan or has open
sub-issues), 2 could not run.

Plans. The file-plan skill, at .claude/skills/file-plan/SKILL.md, drives the
plan commands. `plan report --help` shows the shape of the plan file. The
model writes a plan's issues as JSON, each under a key of its own, and names
another issue of the plan in a body as {KEY}. `plan report` checks each draft
against CLAUDE.md's rules for issues, and checks the plan's keys and links.
It refuses a draft's body or the tracking issue's plan that continues a
paragraph or a list item onto a second line, outside a fence or an HTML
comment, and names the line. GitHub renders that newline in an issue body as
a line break, so the paragraph reads as a ragged column.
It then orders the issues so each comes after the issues that block it, with
ties in the order the plan lists them. The tracking issue's body is the plan
text, after `**Claude:**`, then an Order section written from that order.
A refused plan's report holds the faults and no token. An issue that is open
already joins a plan by its number in place of a draft. The report shows it
as GitHub holds it, and `plan file` links it and adds it as a sub-issue
without filing or editing it.

`plan draft` gives each run of the skill a plan file of its own. Every Claude
Code session on a machine shares one temporary directory, so a fixed name
there lets one session's plan replace another's between the skill's steps.
It prints a literal path, because a session that Claude Code isolates in a
worktree refuses a command that expands ${TMPDIR:-/tmp} as too complex to
verify.

The token hashes the plan file's bytes, the repository gh resolves for the
clone, and its labels. `plan file` refuses a token that does not match them
as they are now, then checks the plan again, since an outside blocker may
have closed since the report. It files the issues in order, putting each
number in place of its {KEY} in the bodies that follow. So a body may name
only an issue filed before it, and `plan report` refuses one that names a
later issue. It then adds the links, files the tracking issue, adds the
sub-issues in order, and reads every link and the sub-issues back.

A filed issue cannot be counted on to come back, since deleting one takes
admin rights. So `plan file` records each issue it files in
.issues-plan/filed.json the moment GitHub returns its number. A later run
files only the issues that file does not hold, and reads GitHub for the
links and sub-issues already there, so it adds only the missing ones. The
record is kept by key, so a run after the plan was revised still files each
key once, and the report marks the keys already filed. Once a plan is filed
and read back whole, the record is marked finished. The same plan is then
refused, and any other plan starts a new record. The root .gitignore ignores
.issues-plan/.

Things that look like bugs and are not:
- `plan` reads a {KEY} outside code only, so a body can show the syntax in a
  code span or a fence. As a simplification, a fence is a line opening with
  three or more backticks or tildes, and a code span lies within one line.
- `plan report` does not count a line that opens a list item, a heading, a
  table row, a blockquote line, an HTML block, a thematic break or an
  indented code block as a continuation, even straight under a paragraph.
  A line after a trailing hard break (two spaces or a backslash) still is
  one: the body puts each paragraph on one line.
- `plan file` checks that the plan's open blockers are open, and does not
  check the issues it filed in an earlier run. The record says it filed them.
- `plan file` adds a missing sub-issue at the end of the tracking issue's
  list. A run cut short adds them in order up to where it stopped, so the
  rest follow in order. A list put out of order some other way is reported by
  the read-back rather than reordered.
- `plan report` reads an issue named by number for its state, title, labels
  and body, and does not check them against the rules for a draft, or read a
  {KEY} in its body. GitHub holds that body, and filing does not change it.
- When gh creates an issue and prints something that is not its address,
  `plan file` cannot record the number and stops. A re-run would file that
  issue again, so check the repository before running it again.

`plan` writes files under .issues-plan/ and files issues through gh. It is
not for Cowork's device bridge.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

import closed_pipe

ENVELOPE_VERSION = 2

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "issues.py"
APPROVED = "approved"
LIST_LIMIT = 1000
TRACKING = "tracking"
BLOCKED_BY_PATH = "repos/{owner}/{repo}/issues/%d/dependencies/blocked_by"
# GitHub caps a parent at 100 sub-issues, so one page holds them all.
SUB_ISSUES_PATH = "repos/{owner}/{repo}/issues/%d/sub_issues?per_page=100"
SUB_ISSUES_ADD_PATH = "repos/{owner}/{repo}/issues/%d/sub_issues"
ISSUE_PATH = "repos/{owner}/{repo}/issues/%d"
# The command that takes a plan's next issue, in the flywheel plugin.
QUEUE_TRACKING = "flywheel.py queue --tracking %d"

# `plan`: what an issue's body opens with and the headings it holds, as
# CLAUDE.md, under "Issues", asks. A tracking issue's body opens the same way.
OPENING = "**Claude:**"
HEADINGS = ("What's wrong", "Evidence", "Done when", "Requirements")
HEADING_RE = re.compile(r"^##[ \t]+(.*?)[ \t]*$", re.M)
KIND_LABELS = ("bug", "enhancement", "docs")
AREA_LABEL_RE = re.compile(r"^(?:repo|plugin:.+)$")
# Labels a plan's issue never carries: only the owner approves, and the
# tracking issue is the plan's own.
WITHHELD_LABELS = (APPROVED, TRACKING)
PLAN_KEYS = ("issues", "tracking")
ISSUE_KEYS = ("key", "title", "labels", "body", "blocked_by")
# An issue of the plan that is open on GitHub already, named by its number.
FILED_KEYS = ("key", "number", "blocked_by")
FILED_FIELDS = "number,title,state,labels,body,url"
TRACKING_KEYS = ("title", "plan")
# `plan draft`: the name of the file a run of the file-plan skill writes its plan to.
DRAFT_PREFIX, DRAFT_SUFFIX = "plan-", ".json"
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
REFERENCE_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_-]*)\}")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
CODE_SPAN_RE = re.compile(r"(`+).*?\1")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# What `plan report` reads as a line that GitHub does not join to the one
# above it: an ATX heading, a list item, an indented code line, a table row,
# a blockquote, an HTML block, or a thematic break or setext underline.
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)")
NOT_TEXT_RE = re.compile(r"^\s*(?:\||>|<|(?:[-*_=][ \t]*){3,}$|=+[ \t]*$)")
ISSUE_URL_RE = re.compile(r"/issues/(\d+)$")
ORDER_HEADING = "## Order"
# Where `plan report` writes the report for the owner to read, and where
# `plan file` records what it has filed. Root .gitignore ignores the folder.
PLAN_DIR = ".issues-plan"
PLAN_REPORT = PLAN_DIR + "/report.md"
PLAN_LEDGER = PLAN_DIR + "/filed.json"
TOKEN_LENGTH = 16
TOKEN_LABEL = "approval token: "
TOKEN_STALE = (
    "the token does not match the plan, the repository or its labels as they are now, "
    "so nothing was filed. Run plan report again, show it to the owner, and file with "
    "its token"
)
PLAN_HELP = """\
--drafts names a file holding one JSON object. "issues" lists the plan's
issues, each with a "key" of its own, its "title", its "labels", its "body"
and, if it waits on anything, "blocked_by": keys of issues in the plan, or
numbers of open issues outside it. "tracking" holds the tracking issue's
"title" and "plan", the text of its body after **Claude:**, which the
Order section follows. A body or the plan names an issue of the plan as
{KEY}, and filing puts the issue's number there, so #{KEY} becomes #342. A
{KEY} in a code span or a fence stays as it is.

An issue that is open already takes a "key" and its "number" in place of a
title, labels and body, and may take "blocked_by". Filing leaves it as it
is, links it and adds it to the tracking issue in the plan's order.

example:
  {"issues": [
     {"key": "A", "title": "report() hides the token", "labels": ["bug", "repo"],
      "body": "**Claude:**\\n\\n## What's wrong\\n..."},
     {"key": "B", "title": "file() files twice", "labels": ["bug", "repo"],
      "blocked_by": ["A", 340], "body": "**Claude:**\\n\\n## What's wrong\\nAfter #{A}..."},
     {"key": "C", "number": 338, "blocked_by": ["B"]}],
   "tracking": {"title": "Make filing safe", "plan": "Fix the report first."}}
"""


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


class UnreadableAddress(Fatal):
    """gh created an issue and printed something that is not its address."""


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
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# git and gh
# --------------------------------------------------------------------------


def run(repo, cmd, check=True, stdin=None):
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, input=stdin)
    except OSError as exc:
        raise Fatal("cannot run %s: %s" % (cmd[0], exc)) from exc
    if check and proc.returncode != 0:
        raise Fatal("`%s` failed: %s" % (" ".join(cmd), proc.stderr.strip()))
    return proc


def git(repo, *args, check=True):
    return run(repo, ["git", *args], check)


def gh(repo, *args, stdin=None):
    """Run gh and return its stdout. Tests replace this."""
    return run(repo, ["gh", *args], stdin=stdin).stdout


def gh_json(repo, *args):
    out = gh(repo, *args)
    try:
        return json.loads(out)
    except ValueError as exc:
        raise Fatal("gh %s did not return JSON: %s" % (args[0], exc)) from exc


def toplevel(path):
    return git(path, "rev-parse", "--show-toplevel").stdout.strip()


def issue(repo, number):
    return gh_json(
        repo, "issue", "view", str(number), "--json", "number,title,state,labels,comments"
    )


def labels(item):
    return {lbl.get("name", "").lower() for lbl in item.get("labels", [])}


def sub_issues(repo, number):
    """Issue `number`'s sub-issues, in the order the issue lists them."""
    return gh_json(repo, "api", SUB_ISSUES_PATH % number)


def is_open(item):
    # gh issue list says "OPEN"; the REST API says "open".
    return item.get("state", "").lower() == "open"


# --------------------------------------------------------------------------
# plan: checking a plan
# --------------------------------------------------------------------------


def read_plan(path):
    """The plan file's bytes, and the JSON they hold."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise Fatal("cannot read %s: %s" % (path, exc.strerror)) from exc
    try:
        return raw, json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise Fatal("%s is not JSON: %s. Fix it, then run again" % (path, exc)) from exc


def references(text):
    """The (start, end, key) of each {KEY} in text, outside code spans and fences."""
    out, pos, fence = [], 0, None
    for line in text.splitlines(True):
        m = FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
        elif m:
            fence = m.group(1)
        else:
            masked = CODE_SPAN_RE.sub(lambda span: " " * len(span.group(0)), line)
            for r in REFERENCE_RE.finditer(masked):
                out.append((pos + r.start(), pos + r.end(), r.group(1)))
        pos += len(line)
    return out


def split_lines(text):
    """The number of each line of text that continues a paragraph or a list
    item, outside a fence or an HTML comment.

    GitHub renders that newline in an issue body as a line break. A comment is
    emptied but keeps its line breaks, so each number is the line as written.
    """
    text = COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out, previous, code, fence = [], None, False, None
    for i, line in enumerate(text.splitlines()):
        m = FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            previous = None
            continue
        if m:
            fence, previous = m.group(1), None
            continue
        # An indented code block opens after a line that is not text, and
        # runs while its lines stay indented or blank.
        indented = INDENTED_CODE_RE.match(line) is not None
        code = (indented or not line.strip()) if code else (indented and previous != i - 1)
        is_text = (
            bool(line.strip())
            and not code
            and not ATX_HEADING_RE.match(line)
            and not NOT_TEXT_RE.match(line)
        )
        if is_text and previous == i - 1 and not LIST_ITEM_RE.match(line):
            out.append(i + 1)
        previous = i if is_text else None
    return out


def render(text, numbers):
    """text with each {KEY} whose number is known replaced by that number."""
    out, last = [], 0
    for start, end, key in references(text):
        if key in numbers:
            out += [text[last:start], str(numbers[key])]
            last = end
    out.append(text[last:])
    return "".join(out)


def repository(repo):
    """{name, url} of the repository gh files issues in for this clone."""
    found = gh_json(repo, "repo", "view", "--json", "nameWithOwner,url")
    return {"name": found["nameWithOwner"], "url": found["url"]}


def repo_labels(repo):
    """The repository's label names, sorted."""
    listed = gh_json(repo, "label", "list", "--limit", str(LIST_LIMIT), "--json", "name")
    return sorted(lbl["name"] for lbl in listed)


def is_text(value):
    return isinstance(value, str) and bool(value.strip())


def check_blockers(name, blocked_by, faults):
    """blocked_by without repeats, or [] with a fault when it is not a list of
    keys and issue numbers."""
    if not (
        isinstance(blocked_by, list)
        and all(
            isinstance(b, str) or (isinstance(b, int) and not isinstance(b, bool))
            for b in blocked_by
        )
    ):
        faults.append("%s's blocked_by is not a list of keys and issue numbers" % name)
        return []
    deduped = []
    for b in blocked_by:
        if b not in deduped:
            deduped.append(b)
    return deduped


def check_filed(name, key, item, faults):
    """A row for an issue the plan names by number. Its title, labels and body
    come from GitHub, in check_plan."""
    number = item["number"]
    for extra in sorted(set(item) - set(FILED_KEYS)):
        faults.append(
            "%s names an issue filed already, so it takes only %s, and has %r"
            % (name, ", ".join(FILED_KEYS), extra)
        )
    if not (isinstance(number, int) and not isinstance(number, bool) and number > 0):
        faults.append("%s's number is not an issue number" % name)
        number = None
    row = {
        "key": key if not name.startswith("issue") else None,
        "name": name,
        "title": "",
        "labels": [],
        "body": "",
        "blocked_by": check_blockers(name, item.get("blocked_by", []), faults),
        "number": number,
        "url": None,
    }
    return row, faults


def check_issue(index, item, known):
    """One issue of the plan as a row, or None, and the faults in it.

    `known` maps each of the repository's labels, in lower case, to its name.
    A row for an issue filed already carries its number; a draft's is None.
    """
    if not isinstance(item, dict):
        return None, ["issue %d is not a JSON object" % index]
    key = item.get("key")
    name = "`%s`" % key if isinstance(key, str) and KEY_RE.match(key) else "issue %d" % index
    faults = []
    if name.startswith("issue"):
        faults.append(
            "%s has no key, or one that is not a letter followed by letters, digits, _ or -" % name
        )
    if "number" in item:
        return check_filed(name, key, item, faults)
    for extra in sorted(set(item) - set(ISSUE_KEYS)):
        faults.append("%s has %r, which is not one of %s" % (name, extra, ", ".join(ISSUE_KEYS)))
    title, body, labels = item.get("title"), item.get("body"), item.get("labels")
    blocked_by = item.get("blocked_by", [])
    if not is_text(title):
        faults.append("%s has no title" % name)
    if not isinstance(body, str):
        faults.append("%s has no body" % name)
        body = ""
    elif not body.startswith(OPENING):
        faults.append("%s's body does not open with %s" % (name, OPENING))
    missing = [h for h in HEADINGS if h not in HEADING_RE.findall(body)]
    if missing:
        faults.append(
            "%s's body lacks the heading%s %s"
            % (name, "s" if len(missing) > 1 else "", ", ".join("`## %s`" % h for h in missing))
        )
    if not (isinstance(labels, list) and all(isinstance(lbl, str) for lbl in labels)):
        faults.append("%s's labels are not a list of names" % name)
        labels = []
    kinds = [lbl for lbl in labels if lbl.lower() in KIND_LABELS]
    areas = [lbl for lbl in labels if AREA_LABEL_RE.match(lbl.lower())]
    for what, found, choices in (
        ("kind", kinds, ", ".join(KIND_LABELS)),
        ("area", areas, "`plugin:<name>` or `repo`"),
    ):
        if len(found) != 1:
            faults.append(
                "%s carries %d %s labels%s; it takes exactly one, from %s"
                % (name, len(found), what, " (%s)" % ", ".join(found) if found else "", choices)
            )
    for lbl in labels:
        if lbl.lower() == APPROVED:
            faults.append("%s carries `%s`, which only the owner adds" % (name, lbl))
        elif lbl.lower() == TRACKING:
            faults.append("%s carries `%s`, which only the tracking issue carries" % (name, lbl))
        elif lbl.lower() not in known:
            faults.append("%s carries `%s`, a label the repository does not have" % (name, lbl))
    row = {
        "key": key if not name.startswith("issue") else None,
        "name": name,
        "title": title if is_text(title) else "",
        "labels": [known.get(lbl.lower(), lbl) for lbl in labels],
        "body": body,
        "blocked_by": check_blockers(name, blocked_by, faults),
        "number": None,
        "url": None,
    }
    return row, faults


def fill_filed(repo, rows):
    """Fill each row the plan names by number with the issue as GitHub holds
    it, and return the faults: a number named twice, or one that is closed or
    cannot be read."""
    faults, named = [], {}
    for r in rows:
        if r["number"] is None:
            continue
        if r["number"] in named:
            faults.append("%s and %s both name #%d" % (named[r["number"]], r["name"], r["number"]))
            continue
        named[r["number"]] = r["name"]
        try:
            item = gh_json(repo, "issue", "view", str(r["number"]), "--json", FILED_FIELDS)
        except Fatal as exc:
            faults.append("%s names #%d, which cannot be read: %s" % (r["name"], r["number"], exc))
            continue
        if not is_open(item):
            faults.append("%s names #%d, which is closed" % (r["name"], r["number"]))
            continue
        r["title"], r["body"], r["url"] = item["title"], item.get("body") or "", item["url"]
        r["labels"] = [lbl["name"] for lbl in item.get("labels", [])]
    return faults


def plan_numbers(ledger, rows):
    """{key: number} for every issue of the plan known to be filed: by an
    earlier run of plan file, or before the plan."""
    numbers = {k: e["number"] for k, e in ledger["issues"].items()}
    numbers.update({r["key"]: r["number"] for r in rows if r["number"] is not None})
    return numbers


def plan_order(rows):
    """The keys in filing order: each after its blockers in the plan, ties in
    the plan's listed order. Returns (order, the keys left on or behind a cycle)."""
    keys = [r["key"] for r in rows]
    deps = {r["key"]: [b for b in r["blocked_by"] if b in keys] for r in rows}
    order, left = [], list(keys)
    while left:
        ready = next((k for k in left if all(d in order for d in deps[k])), None)
        if ready is None:
            break
        order.append(ready)
        left.remove(ready)
    return order, left, deps


def a_cycle(left, deps):
    """One cycle among the keys `left`, as a list of keys, each blocked by the next."""
    path, at = [], left[0]
    while at not in path:
        path.append(at)
        at = next(d for d in deps[at] if d in left)
    return [*path[path.index(at) :], at]


def check_plan(repo, plan, labels):
    """The plan's issue rows in filing order, its tracking issue, and every fault.

    Rows come in the plan's listed order when a fault leaves no order to give.
    """
    faults = []
    if not isinstance(plan, dict):
        return [], None, ["the plan is not a JSON object; plan report --help shows its shape"]
    for extra in sorted(set(plan) - set(PLAN_KEYS)):
        faults.append("the plan has %r, which is not one of %s" % (extra, ", ".join(PLAN_KEYS)))
    issues = plan.get("issues")
    if not isinstance(issues, list) or not issues:
        faults.append('the plan\'s "issues" is not a list holding at least one issue')
        issues = []
    tracking = plan.get("tracking")
    if not (isinstance(tracking, dict) and all(is_text(tracking.get(k)) for k in TRACKING_KEYS)):
        faults.append('the plan\'s "tracking" is not an object with a "title" and a "plan"')
        tracking = None
    else:
        for extra in sorted(set(tracking) - set(TRACKING_KEYS)):
            faults.append(
                "the tracking issue has %r, which is not one of %s"
                % (extra, ", ".join(TRACKING_KEYS))
            )
        tracking = {"title": tracking["title"], "plan": tracking["plan"]}

    known = {lbl.lower(): lbl for lbl in labels}
    rows, seen = [], set()
    for index, item in enumerate(issues, 1):
        row, found = check_issue(index, item, known)
        faults += found
        if row is None or row["key"] is None:
            continue
        if row["key"] in seen:
            faults.append("the key `%s` names more than one issue" % row["key"])
            continue
        seen.add(row["key"])
        rows.append(row)

    faults += fill_filed(repo, rows)
    drafts = [r for r in rows if r["number"] is None]
    texts = [(r["name"] + "'s body", r["body"]) for r in drafts]
    if tracking:
        texts.append(("the tracking issue's plan", tracking["plan"]))
    for where, text in texts:
        for n in split_lines(text):
            faults.append(
                "%s: line %d continues the paragraph or list item above it. GitHub renders "
                "the newline as a line break, so join the line to the one above" % (where, n)
            )
        for _, _, key in references(text):
            if key not in seen:
                faults.append("%s names {%s}, and no issue in the plan has that key" % (where, key))

    outside = {}
    for r in rows:
        for b in r["blocked_by"]:
            if isinstance(b, str) and b not in seen:
                faults.append(
                    "%s is blocked by `%s`, and no issue in the plan has that key" % (r["name"], b)
                )
            elif isinstance(b, int):
                outside.setdefault(b, []).append(r["name"])
    for number in sorted(outside):
        who = " and ".join(outside[number])
        try:
            item = gh_json(repo, "issue", "view", str(number), "--json", "number,state")
        except Fatal as exc:
            faults.append("%s is blocked by #%d, which cannot be read: %s" % (who, number, exc))
            continue
        if not is_open(item):
            faults.append("%s is blocked by #%d, which is closed" % (who, number))

    order, left, deps = plan_order(rows)
    if left:
        cycle = a_cycle(left, deps)
        faults.append(
            "the links form a cycle: %s"
            % ", ".join("`%s` is blocked by `%s`" % (a, b) for a, b in zip(cycle, cycle[1:]))
        )
        return rows, tracking, faults

    place = {k: i for i, k in enumerate(order)}
    by_key = {r["key"]: r for r in rows}
    for key in order:
        if by_key[key]["number"] is not None:
            continue
        for _, _, ref in references(by_key[key]["body"]):
            if by_key.get(ref, {}).get("number") is not None:
                continue
            if ref in place and place[ref] >= place[key]:
                faults.append(
                    "`%s`'s body names {%s}, which is filed %s, so its number is not known "
                    "yet. Name `%s` in `%s`'s body instead, or make `%s` wait on `%s`"
                    % (
                        key,
                        ref,
                        "as the same issue" if ref == key else "after it",
                        key,
                        ref,
                        key,
                        ref,
                    )
                )
    return [by_key[k] for k in order], tracking, faults


def tracking_body(tracking, rows, numbers):
    """The tracking issue's body: the plan, then its Order section, with each
    known number in place of its {KEY}."""
    lines = []
    for i, r in enumerate(rows, 1):
        after = ", ".join("#{%s}" % b if isinstance(b, str) else "#%d" % b for b in r["blocked_by"])
        lines.append(
            "%d. #{%s} %s%s" % (i, r["key"], r["title"], ", blocked by " + after if after else "")
        )
    text = "%s\n\n%s\n\n%s\n\n%s\n" % (
        OPENING,
        tracking["plan"].strip(),
        ORDER_HEADING,
        "\n".join(lines),
    )
    return render(text, numbers)


def approval_token(raw, name, labels):
    """A sha256 over the plan's bytes, the repository's name and its labels.

    Each part carries its length, so bytes cannot move from one part to the
    next and hash the same.
    """
    digest = hashlib.sha256()
    for part in (raw, name.encode("utf-8"), "\n".join(labels).encode("utf-8")):
        digest.update(b"%d:" % len(part))
        digest.update(part)
    return digest.hexdigest()[:TOKEN_LENGTH]


def empty_ledger(name):
    return {"repository": name, "plan": None, "issues": {}, "tracking": None, "complete": False}


def read_ledger(repo, name, raw):
    """What earlier runs of `plan file` filed for this repository and are not
    done with, and the faults that stop this plan being filed.

    A finished ledger is for a plan already filed: the same plan again is a
    fault, and any other starts afresh.
    """
    path = os.path.join(repo, PLAN_LEDGER)
    try:
        with open(path, encoding="utf-8") as fh:
            ledger = json.load(fh)
    except FileNotFoundError:
        return empty_ledger(name), []
    except (OSError, ValueError) as exc:
        raise Fatal(
            "cannot read %s: %s. It records what plan file filed; restore it, or ask the "
            "owner before removing it" % (PLAN_LEDGER, exc)
        ) from exc
    if ledger.get("repository") != name:
        return empty_ledger(name), []
    if ledger.get("complete"):
        if ledger.get("plan") == hashlib.sha256(raw).hexdigest():
            return ledger, [
                "this plan was filed already, under tracking issue #%d; nothing is left to file"
                % ledger["tracking"]["number"]
            ]
        return empty_ledger(name), []
    return ledger, []


def write_ledger(repo, ledger):
    os.makedirs(os.path.join(repo, PLAN_DIR), exist_ok=True)
    with open(os.path.join(repo, PLAN_LEDGER), "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)
        fh.write("\n")


def ledger_warnings(ledger, rows):
    """An issue an earlier run filed that the plan no longer holds."""
    keys = set(r["key"] for r in rows)
    return [
        "`%s` was filed as #%d by an earlier run of plan file and is not in this plan; "
        "it stays as it is, outside the tracking issue" % (key, entry["number"])
        for key, entry in sorted(ledger["issues"].items())
        if key not in keys
    ]


def quoted(text):
    """text as a markdown quote, so a body's own headings stay inside it."""
    return "\n".join(("> " + line).rstrip() for line in text.rstrip("\n").split("\n"))


def blockers_text(blocked_by, numbers):
    named = [
        ("#%d" % numbers[b] if b in numbers else "`%s`" % b) if isinstance(b, str) else "#%d" % b
        for b in blocked_by
    ]
    return ", ".join(named) or "nothing"


def report_markdown(data, faults, warnings):
    """The report as markdown: what the owner reads whole, and approves."""
    numbers = data["numbers"]
    out = ["# Plan report", "", "Filing in [%s](%s)." % (data["repository"], data["url"])]
    if faults:
        out += ["", "## Refused", "", "Fix these and run plan report again:", ""]
        out += ["- %s" % f for f in faults]
    if warnings:
        out += ["", "## Warnings", ""]
        out += ["- %s" % w for w in warnings]
    for i, row in enumerate(data["issues"], 1):
        out += ["", "## %d. `%s`: %s" % (i, row["key"], row["title"]), ""]
        out.append("- **Labels:** %s" % (", ".join(row["labels"]) or "none"))
        out.append("- **Blocked by:** %s" % blockers_text(row["blocked_by"], numbers))
        if row["number"] is not None:
            out.append(
                "- **Filed already** as #%d, before this plan. plan file leaves it as it is, "
                "and adds it to the plan." % row["number"]
            )
            out += ["", quoted(row["body"])]
            continue
        if row["key"] in numbers:
            out.append(
                "- **Filed already** as #%d, by an earlier run. plan file leaves it as it is."
                % numbers[row["key"]]
            )
        out += ["", quoted(render(row["body"], numbers))]
    if data["tracking"]:
        out += ["", "## Tracking issue: %s" % data["tracking"]["title"], ""]
        out.append("- **Labels:** %s" % TRACKING)
        if data["tracking"].get("number"):
            out.append(
                "- **Filed already** as #%d, by an earlier run. plan file leaves it as it is."
                % data["tracking"]["number"]
            )
        if data["tracking"].get("body"):
            out += ["", quoted(data["tracking"]["body"])]
    out += ["", "%d issue(s), and a tracking issue." % len(data["issues"])]
    if data["token"]:
        out += ["", "%s`%s`" % (TOKEN_LABEL.capitalize(), data["token"])]
    return "\n".join(out) + "\n"


def checked(args, repo):
    """Read and check the plan: (raw, repository, labels, rows, tracking,
    ledger, faults, warnings)."""
    raw, plan = read_plan(args.drafts)
    where = repository(repo)
    labels = repo_labels(repo)
    rows, tracking, faults = check_plan(repo, plan, labels)
    ledger, stopped = read_ledger(repo, where["name"], raw)
    return (
        raw,
        where,
        labels,
        rows,
        tracking,
        ledger,
        faults + stopped,
        ledger_warnings(ledger, rows),
    )


# --------------------------------------------------------------------------
# plan: commands
# --------------------------------------------------------------------------


def cmd_plan_draft(args, repo):
    try:
        fd, path = tempfile.mkstemp(prefix=DRAFT_PREFIX, suffix=DRAFT_SUFFIX)
    except OSError as exc:
        raise Fatal(
            "cannot make a file for the plan in %s: %s. Set TMPDIR to a directory you can "
            "write and run this again." % (tempfile.gettempdir(), exc)
        ) from exc
    os.close(fd)

    def human():
        print(path)

    return emit(args, "plan draft", {"path": path}, human=human)


def cmd_plan_report(args, repo):
    raw, where, labels, rows, tracking, ledger, faults, warnings = checked(args, repo)
    numbers = plan_numbers(ledger, rows)
    shown = None
    if tracking:
        shown = {"title": tracking["title"], "body": None, "number": None}
        if ledger["tracking"]:
            shown["number"] = ledger["tracking"]["number"]
        if not faults:
            shown["body"] = tracking_body(tracking, rows, numbers)
    # No token for a refused plan: the owner cannot approve what file would refuse.
    token = None if faults else approval_token(raw, where["name"], labels)
    data = {
        "repository": where["name"],
        "url": where["url"],
        "issues": [
            {k: r[k] for k in ("key", "number", "title", "labels", "body", "blocked_by")}
            for r in rows
        ],
        "order": [] if faults else [r["key"] for r in rows],
        "tracking": shown,
        "numbers": numbers,
        "token": token,
    }
    text = report_markdown(data, faults, warnings)
    os.makedirs(os.path.join(repo, PLAN_DIR), exist_ok=True)
    data["report"] = os.path.join(repo, PLAN_REPORT)
    with open(data["report"], "w", encoding="utf-8") as fh:
        fh.write(text)

    def human():
        sys.stdout.write(text)

    return emit(args, "plan report", data, faults, warnings, human=human)


def issue_number(url):
    m = ISSUE_URL_RE.search(url.strip())
    if not m:
        raise UnreadableAddress("gh issue create printed %r, not an issue's address" % url.strip())
    return int(m.group(1))


def create_issue(repo, title, body, labels):
    """File one issue, and return (number, url)."""
    flags = []
    for lbl in labels:
        flags += ["--label", lbl]
    url = gh(repo, "issue", "create", "--title", title, "--body-file", "-", *flags, stdin=body)
    url = url.strip().splitlines()[-1] if url.strip() else ""
    return issue_number(url), url


def database_id(repo, number, cache):
    """The id GitHub's REST API links issues by, which is not the number."""
    if number not in cache:
        cache[number] = gh_json(repo, "api", ISSUE_PATH % number)["id"]
    return cache[number]


def linked(repo, number):
    """The numbers of every issue GitHub lists as blocking `number`, open or closed."""
    return sorted(b["number"] for b in gh_json(repo, "api", BLOCKED_BY_PATH % number))


def numbered(numbers):
    return ", ".join("#%d" % n for n in numbers) or "nothing"


def cmd_plan_file(args, repo):
    raw, where, labels, rows, tracking, ledger, faults, warnings = checked(args, repo)
    data = {
        "repository": where["name"],
        "issues": [],
        "tracking": None,
        "links": [],
        "sub_issues": [],
        "dry_run": args.dry_run,
    }
    if args.token != approval_token(raw, where["name"], labels):
        return emit(args, "plan file", data, [TOKEN_STALE], warnings)
    if faults:
        return emit(args, "plan file", data, [*faults, "nothing was filed"], warnings)

    numbers = plan_numbers(ledger, rows)
    expected = {}

    def before(r):
        """The entry for an issue the plan names by number, or None."""
        if r["number"] is None:
            return None
        return {"number": r["number"], "title": r["title"], "url": r["url"]}

    def said(what, item):
        if not item["filed"]:
            return "already filed %s#%d %s" % (what, item["number"], item["title"])
        if args.dry_run:
            return "would file %s%s" % (what, item["title"])
        return "filed %s#%d %s  %s" % (what, item["number"], item["title"], item["url"])

    def human():
        for item in data["issues"]:
            print(said("", item))
        for link in data["links"]:
            print("linked #%d, blocked by #%d" % (link["issue"], link["blocked_by"]))
        if data["tracking"]:
            print(said("tracking issue ", data["tracking"]))
        for sub in data["sub_issues"]:
            print("added #%d to #%d" % (sub["issue"], sub["tracking"]))

    if args.dry_run:
        for r in rows:
            entry = before(r) or ledger["issues"].get(r["key"])
            data["issues"].append(
                {
                    "key": r["key"],
                    "title": r["title"],
                    "number": entry["number"] if entry else None,
                    "url": entry["url"] if entry else None,
                    "filed": entry is None,
                }
            )
        t = ledger["tracking"]
        data["tracking"] = {
            "title": tracking["title"],
            "number": t["number"] if t else None,
            "url": t["url"] if t else None,
            "filed": t is None,
        }
        return emit(args, "plan file", data, warnings=warnings, human=human)

    ledger["plan"] = hashlib.sha256(raw).hexdigest()
    ids = {}
    try:
        for r in rows:
            entry = before(r) or ledger["issues"].get(r["key"])
            filed = entry is None
            if filed:
                number, url = create_issue(
                    repo, r["title"], render(r["body"], numbers), r["labels"]
                )
                entry = {"number": number, "title": r["title"], "url": url}
                ledger["issues"][r["key"]] = entry
                write_ledger(repo, ledger)
            numbers[r["key"]] = entry["number"]
            data["issues"].append(dict(entry, key=r["key"], filed=filed))

        for r in rows:
            n = numbers[r["key"]]
            expected[n] = sorted(numbers[b] if isinstance(b, str) else b for b in r["blocked_by"])
            have = linked(repo, n) if expected[n] else []
            for b in expected[n]:
                if b in have:
                    continue
                gh(
                    repo,
                    "api",
                    "-X",
                    "POST",
                    BLOCKED_BY_PATH % n,
                    "-F",
                    "issue_id=%d" % database_id(repo, b, ids),
                )
                data["links"].append({"issue": n, "blocked_by": b})

        t = ledger["tracking"]
        filed = t is None
        if filed:
            body = tracking_body(tracking, rows, numbers)
            number, url = create_issue(repo, tracking["title"], body, [TRACKING])
            t = {"number": number, "title": tracking["title"], "url": url}
            ledger["tracking"] = t
            write_ledger(repo, ledger)
        data["tracking"] = dict(t, filed=filed)

        have = [s["number"] for s in sub_issues(repo, t["number"])]
        for r in rows:
            n = numbers[r["key"]]
            if n in have:
                continue
            gh(
                repo,
                "api",
                "-X",
                "POST",
                SUB_ISSUES_ADD_PATH % t["number"],
                "-F",
                "sub_issue_id=%d" % database_id(repo, n, ids),
            )
            data["sub_issues"].append({"issue": n, "tracking": t["number"]})
    except Fatal as exc:
        if isinstance(exc, UnreadableAddress):
            remedy = (
                "that issue may exist on GitHub and is not recorded, so check the "
                "repository for it before running plan file again, which would file it again"
            )
        else:
            remedy = "run plan file again with the same plan and token to file the rest"
        return emit(
            args,
            "plan file",
            data,
            [
                "%s. plan file stopped there. What it filed is listed above and recorded in "
                "%s; %s" % (exc, PLAN_LEDGER, remedy)
            ],
            warnings,
            human=human,
        )

    errors = []
    for n, want in sorted(expected.items()):
        on = linked(repo, n)
        if on != want:
            errors.append(
                "#%d is blocked by %s on GitHub, and the plan says %s"
                % (n, numbered(on), numbered(want))
            )
    on = [s["number"] for s in sub_issues(repo, t["number"])]
    want = [numbers[r["key"]] for r in rows]
    if on != want:
        errors.append(
            "#%d lists its sub-issues as %s, and the plan's order is %s"
            % (t["number"], numbered(on), numbered(want))
        )
    if not errors:
        ledger["complete"] = True
        write_ledger(repo, ledger)
    return emit(args, "plan file", data, errors, warnings, human=human)


def cmd_plan_close(args, repo):
    n = args.number
    item = issue(repo, n)
    data = {"number": n, "sub_issues": [], "closed": False}
    problems = []
    if not is_open(item):
        problems.append("#%d is closed already" % n)
    if TRACKING not in labels(item):
        problems.append("#%d is not labeled %s; plan close closes only a plan" % (n, TRACKING))
    if APPROVED not in labels(item):
        problems.append(
            "#%d is not labeled %s; ask the owner to approve the plan or close it" % (n, APPROVED)
        )
    if problems:
        return emit(args, "plan close", data, problems)

    subs = sub_issues(repo, n)
    data["sub_issues"] = [s["number"] for s in subs]
    still_open = [s for s in subs if is_open(s)]
    if not subs:
        return emit(
            args, "plan close", data, ["#%d has no sub-issues; ask the owner what it tracks" % n]
        )
    if still_open:
        return emit(
            args,
            "plan close",
            data,
            [
                "#%d still has open sub-issues: %s. Run %s for the next one"
                % (n, numbered([s["number"] for s in still_open]), QUEUE_TRACKING % n)
            ],
        )

    comment = "Every sub-issue is closed: %s." % numbered(data["sub_issues"])
    gh(repo, "issue", "close", str(n), "--reason", "completed", "--comment", comment)
    data["closed"] = True

    def human():
        print("Closed #%d. %s" % (n, comment))

    return emit(args, "plan close", data, human=human)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(prog=PROG, description="File a plan's issues, and close it.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "plan", help="file a plan's issues under a tracking issue, and close it when finished"
    )
    plans = p.add_subparsers(dest="plan_command", required=True)
    drafts = argparse.ArgumentParser(add_help=False)
    drafts.add_argument("--drafts", required=True, metavar="FILE", help="the plan, as JSON")

    p = plans.add_parser(
        "draft",
        parents=[common],
        help="make an empty file for the plan that no other run is given, and print its path",
    )
    p.set_defaults(func=cmd_plan_draft)

    p = plans.add_parser(
        "report",
        parents=[common, drafts],
        help="check the plan, and print it as it will be filed, with an approval token",
        epilog=PLAN_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.set_defaults(func=cmd_plan_report)

    p = plans.add_parser(
        "file",
        parents=[common, drafts],
        help="file the plan report showed: issues, links, tracking issue and sub-issues",
        epilog=PLAN_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--token", required=True, help="the approval token plan report printed")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_plan_file)

    p = plans.add_parser(
        "close",
        parents=[common],
        help="close an approved tracking issue once every sub-issue is closed",
    )
    p.add_argument("number", type=int)
    p.set_defaults(func=cmd_plan_close)

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

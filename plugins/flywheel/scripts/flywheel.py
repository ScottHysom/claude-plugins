#!/usr/bin/env python3
"""Deterministic half of the flywheel plugin.

The issue loop takes an approved issue from claim to a merged pull request,
through sessions in the Claude desktop app that each play one role: the
dispatcher starts the others, an implementer works one issue, and a reviewer
reviews its pull request. This script does the loop's work that needs no
judgment. Its skills, which arrive in later versions, run it.

Usage:
    python3 flywheel.py <command> [options]
    python3 flywheel.py --help

    python3 flywheel.py queue
    python3 flywheel.py queue --count 3
    python3 flywheel.py queue --tracking 347
    python3 flywheel.py claim 12
    python3 flywheel.py claim --next
    python3 flywheel.py claim --next --tracking 347
    python3 flywheel.py brief 12
    python3 flywheel.py release 12
    python3 flywheel.py stale
    python3 flywheel.py clear 12
    python3 flywheel.py sweep --dry-run
    python3 flywheel.py plan draft
    python3 flywheel.py plan report --drafts plan.json
    python3 flywheel.py plan file --drafts plan.json --token 3f9a1c0e7b2d4a68
    python3 flywheel.py plan close 347

Run from anywhere in a clone, with git and, for every command but setup,
config init and ids, an authenticated gh on PATH.

Commands:
    setup        copy this script, the templates it reads and the plugin's
                 manifest into the project's .flywheel/, which git ignores
    config init  write .flywheel/roles.json from the plugin's template, and
                 name each field the owner fills in
    queue        up to --count of the oldest open approved issues nobody
                 holds and no open issue blocks, or an approved tracking
                 issue that comes first. With --tracking N, up to --count of
                 tracking issue N's sub-issues in its order instead, or that
                 N's plan is finished when every sub-issue is closed. Changes
                 nothing.
    claim N      take issue N: push issue/N, switch to it, label and comment.
    claim --next take the issue `queue` would offer, or with --tracking N
                 the one `queue --tracking N` would. When another agent
                 wins it, take the next free one, until a claim is won or
                 none is free.
    brief N      print the first message of a session that works issue N: the
                 issue as the owner approved it, the owner's comments since,
                 the role, and the gate commands.
    release N    give issue N up: delete issue/N if it holds no work, remove
                 the label, comment.
    stale        labels, branches and issue states that disagree, including a
                 closed issue that still has the label and a held issue that
                 lacks it.
    clear N      once issue N is closed, delete the local issue/N if a merged
                 pull request or main has everything on it, first moving any
                 worktree on it to a detached origin/main.
    sweep        delete every local branch but main whose work is on main,
                 and name each branch kept with the reason.
    ids          name each principle or stage-rule id cited in the plugin's
                 templates, skills or the repo's specs/flywheel.md that no
                 document under the plugin's docs/ defines
    plan draft   make an empty file in the temporary directory for a plan's
                 drafts, named so that no other run gets it, and print its path.
    plan report  check a plan's drafts, print the plan as it will be filed,
                 ending with an approval token, and write the same report to
                 .flywheel/plan/report.md.
    plan file    file the plan that report showed: its issues, their "blocked
                 by" links, the tracking issue and its sub-issues, then read
                 them back.
    plan close N close approved tracking issue N, with a comment naming its
                 sub-issues, once every one of them is closed.

Every command takes --json and -C/--repo; claim, release, clear, sweep and
plan file take --dry-run.

Exit codes: 0 clean, 1 ran and found problems (the issue is held or not
approved, or still open, the branch holds work, a label and a branch
disagree, the issue changed after approval, the roles file exists already,
`claim --next` found nothing free to claim, a plan is refused or not filed
as it says, a tracking issue is not an open approved plan or has open
sub-issues), 2 could not run.

The copy. Each shell call in Claude Code starts without the last one's
variables, and the plugin's own path is too long to repeat in every command,
so `setup` copies the script into the project and prints the prefix that
reaches it. It copies the roles template and plugin.json beside it, so the
copy can run `config init` and read the plugin's version without reaching
back into the plugin. A file is read beside the script when the script sits
in .flywheel/, and from the plugin otherwise.

What git ignores. .flywheel/ also holds what the owner sets and commits, such
as roles.json, so the .gitignore that `setup` writes names only the files it
copies, and itself, rather than `*`.

The roles file. One entry per role, each with its tier from the method's
roles.md, the model and the default effort, and the plugin version it was set
under. `config init` fills in the version. A field the template leaves null is
one only the owner can fill, such as the model behind a tier, and `config
init` names each one by its path in the file.

The gates file. .flywheel/gates.json maps each gate the project has, such as
`check` or `verify`, to the command that runs it, under "gates". The owner
writes it. `brief` names those commands to the session it starts, and warns
when the file is missing.

The lock. The claim on an approved issue is a branch named `issue/<N>` on
origin. `claim` creates it with a push that the server refuses when the
branch already exists, so of two agents claiming at once exactly one wins. The
`in-progress` label and a comment then say so where people look. The branch
is the lock and the label is the signal: when they disagree the branch is
right, and `stale` reports the disagreement. `release` takes the label off a
claim given up; a workflow in the project may take it off an issue that
closes. `clear` then deletes the local claim branch that the merge left
behind. `sweep` deletes every local branch whose work is on main, whatever its
name.

The brief. `brief` reads the issue through GitHub's GraphQL API, since only
that reports when the body was last edited and when each label was added. The
issue as approved is its body as it stands, and `brief` refuses one edited
after `approved` was last added, since the edit has not been approved.
Removing the label and adding it again is how the owner re-approves. Agents
post under the owner's account, so the owner's comments are those by the
repository's owner that open with neither `**Claude:**` nor the text this
script writes when it claims or releases.

The method's ids. The documents under docs/ define each principle and
stage-rule id as a row of a table whose header has an ID column. A file
cites one by naming it in backticks after the words "the method's", in the
same sentence: "Source: the method's `one-home-per-artifact`." `ids` reads
the citations in the plugin's templates and skills and in specs/flywheel.md,
when the repo has one, and needs the plugin's own docs/, so it runs from the
plugin rather than from the copy in .flywheel/.

Plans. The file-issue skill drives the plan commands. `plan report --help`
shows the shape of the plan file. The model writes a plan's issues as JSON,
each under a key of its own, and names another issue of the plan in a body as
{KEY}. A plan of several issues takes a tracking issue. A plan of one issue
may leave it out, and is then filed as that issue alone. `plan report` checks
each draft's opening, headings and labels against OPENING, HEADINGS,
KIND_LABELS and AREA_LABEL_RE, the issue rules of the repository this plugin
comes from, and checks the plan's keys and links. It refuses a draft's
body or the tracking issue's plan that continues a paragraph or a list item
onto a second line, outside a fence or an HTML comment, and names the line.
GitHub renders that newline in an issue body as a line break, so the
paragraph reads as a ragged column. It then orders the issues so each comes
after the issues that block it, with ties in the order the plan lists them.
The tracking issue's body is the plan text, after `**Claude:**`, then an
Order section written from that order. A refused plan's report holds the
faults and no token. An issue that is open already joins a plan by its
number in place of a draft. The report shows it as GitHub holds it, and
`plan file` links it and adds it as a sub-issue without filing or editing it.

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
.flywheel/plan/filed.json the moment GitHub returns its number. A later run
files only the issues that file does not hold, and reads GitHub for the
links and sub-issues already there, so it adds only the missing ones. The
record is kept by key, so a run after the plan was revised still files each
key once, and the report marks the keys already filed. Once a plan is filed
and read back whole, the record is marked finished. The same plan is then
refused, and any other plan starts a new record. .flywheel/plan/ holds a
.gitignore of its own that ignores the folder, so the report and the record
stay out of every commit whether or not `setup` has run.

Things that look like bugs and are not:
- `queue` exits 0 when nothing is free, or when every free issue is blocked.
  An empty queue is not a problem. `claim` ignores blockers, so the owner can
  still name a blocked issue.
- `queue` never offers a sub-issue of an approved tracking issue, even the
  lowest-numbered free one. The plan's issues are taken in the plan's order,
  through `queue --tracking N`, so `queue` names the plan in their place, and
  offers no issue after it.
- `queue --tracking N` exits 0 when every sub-issue is closed, and says the
  plan is finished. A finished plan is not a problem; `plan close N` closes
  it. A tracking issue without sub-issues is not finished, since an empty
  plan is a mistake for the owner to fix.
- `queue --tracking N` stops at an unapproved sub-issue instead of skipping
  to a later approved one, since skipping would work the plan out of its
  order. It exits 1 when that sub-issue is the first it would offer, and
  otherwise offers the ones before it and warns.
- `claim --next` exits 1 when it claims nothing, though `queue` exits 0 on
  the same queue. The agent asked for an issue and has none to work. `claim N`
  stops on a held issue rather than moving on, since the owner named it.
- `claim` exits 0 when the push succeeded but labeling or commenting failed.
  The branch is the claim; those failures are warnings to fix by hand.
- `release` refuses to delete a branch with commits not on main, and `clear`
  one with changes main lacks. Neither has a flag to force it. Throwing away
  work is for a person to decide.
- `clear` never asks whether issue/N's commits are on main. A squash or rebase
  merge gives the work new hashes, so they never are, and `git branch -d` calls
  such a branch unmerged. It asks instead whether a merged pull request from
  issue/N had the local tip in its head. Failing that, it asks whether merging
  issue/N into main would change main. That second test alone would refuse a
  branch merged long ago whose lines main has edited since.
- `clear` refuses when a worktree on issue/N has uncommitted changes, even ones
  the switch to origin/main would carry along. Uncommitted changes are for a
  person to keep or discard, not to move silently.
- `sweep` counts a branch as merged by the same tests as `clear`. A branch the
  desktop app made for a session and never committed to passes the second,
  since its tip is already on main. It exits 0 when it keeps branches:
  unmerged work on a branch is normal.
- `sweep` keeps a branch any worktree has checked out, even a clean one whose
  work has merged. It cannot tell a finished session's worktree from a live
  one, and moving a live session off its branch would strand its next commit.
  The branch goes in a later sweep, once the desktop app removes the worktree.
- `sweep` keeps a branch that still exists on origin. A claim just made has no
  commits of its own, so it looks merged, and someone may be working on it.
- `clear` deletes only the local branch and removes no worktree. GitHub
  deletes the remote branch when the pull request merges, and the desktop app
  manages worktrees.
- `brief` reads the last 100 label events and the last 100 comments. As a
  simplification, it treats an issue whose approval is older than those label
  events as never edited after approval, and leaves out older comments.
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

`setup`, `config init`, `plan report` and `plan file` write only under
.flywheel/, and `plan file` also files issues through gh. `claim`, `release`,
`clear` and `sweep` write to git (a push, a branch switch, a branch deletion),
so they are not for Cowork's device bridge, where a git write strands
`.git/*.lock` files. COWORK.md, at the repo root, has the rest of what the
bridge allows.

Python 3.9 is the floor. No match statements, no X | Y unions.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

ENVELOPE_VERSION = 1

OK = 0
PROBLEMS = 1
CANNOT_RUN = 2

PROG = "flywheel.py"

SCRIPT_PATH = os.path.abspath(__file__)
SCRIPT_NAME = os.path.basename(SCRIPT_PATH)
MANIFEST = "plugin.json"
SHIPPED_MANIFEST = ".claude-plugin/" + MANIFEST
ROLES_TEMPLATE = "roles.json"
SHIPPED_ROLES = "templates/" + ROLES_TEMPLATE

COPY_DIR = ".flywheel"
COPY_SCRIPT = COPY_DIR + "/" + SCRIPT_NAME
COPY_MANIFEST = COPY_DIR + "/" + MANIFEST
COPY_ROLES = COPY_DIR + "/roles.template.json"
COPY_IGNORE = COPY_DIR + "/.gitignore"
COPY_PREFIX = "FLYWHEEL=" + COPY_SCRIPT

DOCS_DIR = "docs"
TEMPLATES_DIR = "templates"
SKILLS_DIR = "skills"
SPEC_FILE = "specs/flywheel.md"
ID_HEADER = "ID"
METHOD_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")
# "the method's" opens a citation, which runs to the end of its sentence or
# its paragraph.
CITATION = re.compile(r"\bthe\s+method's\b(.*?)(?:\.(?=\s|$)|\n[ \t]*\n|$)", re.S)
BACKTICKED = re.compile(r"`([^`\n]+)`")

ROLES_FILE = COPY_DIR + "/roles.json"
ROLES_KEY = "roles"
VERSION_KEY = "version"
TIER_KEY = "tier"
GATES_FILE = COPY_DIR + "/gates.json"
GATES_KEY = "gates"
# The role a session started from `brief` plays.
BRIEF_ROLE = "implementer"

APPROVED = "approved"
IN_PROGRESS = "in-progress"
TRACKING = "tracking"
REMOTE = "origin"
BASE = "main"
BRANCH_PREFIX = "issue/"
BRANCH_REF_RE = re.compile(r"^refs/heads/%s(\d+)$" % re.escape(BRANCH_PREFIX))
LIST_LIMIT = 1000
CLAIM_MARK = "Claimed on branch"
RELEASE_MARK = "Released "
# What an agent's own comment opens with, under the owner's account.
AGENT_MARK = "**Claude:**"
MERGED_FIELDS = "number,headRefName,headRefOid"
BLOCKED_BY_PATH = "repos/{owner}/{repo}/issues/%d/dependencies/blocked_by"
# GitHub caps a parent at 100 sub-issues, so one page holds them all.
SUB_ISSUES_PATH = "repos/{owner}/{repo}/issues/%d/sub_issues?per_page=100"
# The command that closes a finished plan.
PLAN_CLOSE = PROG + " plan close"
SUB_ISSUES_ADD_PATH = "repos/{owner}/{repo}/issues/%d/sub_issues"
ISSUE_PATH = "repos/{owner}/{repo}/issues/%d"
BRIEF_QUERY = """\
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    owner { login }
    issue(number: $number) {
      number title body url lastEditedAt
      labels(first: 100) { nodes { name } }
      timelineItems(itemTypes: LABELED_EVENT, last: 100) {
        nodes { ... on LabeledEvent { createdAt label { name } } }
      }
      comments(last: 100) { nodes { author { login } body createdAt } }
    }
  }
}
"""


# `plan`: what an issue's body opens with and the headings it holds. A
# tracking issue's body opens the same way.
OPENING = AGENT_MARK
HEADINGS = ("What's wrong", "Evidence", "Done when", "Requirements")
HEADING_RE = re.compile(r"^##[ \t]+(.*?)[ \t]*$", re.M)
KIND_LABELS = ("bug", "enhancement", "docs")
AREA_LABEL_RE = re.compile(r"^(?:repo|plugin:.+)$")
PLAN_KEYS = ("issues", "tracking")
ISSUE_KEYS = ("key", "title", "labels", "body", "blocked_by")
# An issue of the plan that is open on GitHub already, named by its number.
FILED_KEYS = ("key", "number", "blocked_by")
FILED_FIELDS = "number,title,state,labels,body,url"
TRACKING_KEYS = ("title", "plan")
# `plan draft`: the name of the file a run of the file-issue skill writes its plan to.
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
# `plan file` records what it has filed. The folder ignores itself.
PLAN_DIR = COPY_DIR + "/plan"
PLAN_REPORT = PLAN_DIR + "/report.md"
PLAN_LEDGER = PLAN_DIR + "/filed.json"
PLAN_IGNORE = PLAN_DIR + "/.gitignore"
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
Order section follows. A plan of one issue may leave "tracking" out, and is
filed as that issue alone. A body or the plan names an issue of the plan as
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
        if human:
            human()
        sys.stderr.write("".join("warning: %s\n" % w for w in warnings))
        sys.stderr.write("".join("%s\n" % e for e in errors))
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def project_root(start):
    """The top of the git working tree that holds start."""
    start = os.path.abspath(start)
    if not os.path.isdir(start):
        raise Fatal("%s is not a directory. Name a clone with -C." % start)
    try:
        out = subprocess.run(
            ["git", "--no-optional-locks", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise Fatal("git is not installed, or not on PATH. Install git, then run again.") from exc
    if out.returncode != 0:
        raise Fatal(
            "%s is not inside a git working tree. Run from inside a clone, or name one with -C."
            % start
        )
    return os.fsdecode(out.stdout.rstrip(b"\n"))


def in_copy():
    return os.path.basename(os.path.dirname(SCRIPT_PATH)) == COPY_DIR


def plugin_file(copied, shipped):
    """A file the script reads: beside it in the project's copy, else in the plugin."""
    here = os.path.dirname(SCRIPT_PATH)
    if in_copy():
        path = os.path.join(here, os.path.basename(copied))
    else:
        path = os.path.join(os.path.dirname(here), *shipped.split("/"))
    if not os.path.isfile(path):
        raise Fatal("%s is missing. Install the flywheel plugin again, then run its setup." % path)
    return path


def read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise Fatal(
            "cannot read %s: %s. Check its permissions, then run again." % (path, exc)
        ) from exc


def read_json(path):
    try:
        return json.loads(read_bytes(path).decode("utf-8"))
    except ValueError as exc:
        raise Fatal(
            "%s is not valid JSON: %s. Install the flywheel plugin again, then run its setup."
            % (path, exc)
        ) from exc


def read_project_json(root, rel, key):
    """The object under `key` in the project's file `rel`, or None when the
    file is missing."""
    path = os.path.join(root, *rel.split("/"))
    if not os.path.isfile(path):
        return None
    try:
        found = json.loads(read_bytes(path).decode("utf-8"))
    except ValueError as exc:
        raise Fatal("%s is not valid JSON: %s. Fix it, then run again." % (rel, exc)) from exc
    inner = found.get(key) if isinstance(found, dict) else None
    if not isinstance(inner, dict):
        raise Fatal('%s does not hold a "%s" object. Fix it, then run again.' % (rel, key))
    return inner


def write_bytes(root, rel, content):
    path = os.path.join(root, *rel.split("/"))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(content)
    except OSError as exc:
        raise Fatal(
            "cannot write %s: %s. Check its permissions, then run again." % (path, exc)
        ) from exc


def plugin_version():
    manifest = read_json(plugin_file(COPY_MANIFEST, SHIPPED_MANIFEST))
    version = manifest.get(VERSION_KEY) if isinstance(manifest, dict) else None
    if not isinstance(version, str):
        raise Fatal(
            "the plugin's %s does not give a version. Install the flywheel plugin again, then"
            " run its setup." % MANIFEST
        )
    return version


# --------------------------------------------------------------------------
# git and gh
# --------------------------------------------------------------------------


def run(root, cmd, check=True, stdin=None):
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, input=stdin)
    except OSError as exc:
        raise Fatal(
            "cannot run %s: %s. Install it, or put it on PATH, then run again." % (cmd[0], exc)
        ) from exc
    if check and proc.returncode != 0:
        # A multi-line argument, such as a GraphQL query, is left out.
        shown = " ".join("..." if "\n" in a else a for a in cmd)
        raise Fatal("`%s` failed: %s" % (shown, proc.stderr.strip()))
    return proc


def git(root, *args, check=True):
    return run(root, ["git", *args], check)


def gh(root, *args, stdin=None):
    """Run gh and return its stdout. Tests replace this."""
    return run(root, ["gh", *args], stdin=stdin).stdout


def gh_json(root, *args):
    out = gh(root, *args)
    try:
        return json.loads(out)
    except ValueError as exc:
        raise Fatal("gh %s did not return JSON: %s" % (args[0], exc)) from exc


def branch(number):
    return "%s%d" % (BRANCH_PREFIX, number)


def ref(number):
    return "refs/heads/" + branch(number)


def claims(root):
    """{issue number: commit} for every issue/<N> branch on origin."""
    out = git(root, "ls-remote", "--heads", REMOTE, BRANCH_PREFIX + "*").stdout
    held = {}
    for line in out.splitlines():
        sha, _, name = line.partition("\t")
        m = BRANCH_REF_RE.match(name)
        if m:
            held[int(m.group(1))] = sha
    return held


def issue(root, number):
    return gh_json(
        root, "issue", "view", str(number), "--json", "number,title,state,labels,comments"
    )


def labels(item):
    return {lbl.get("name", "").lower() for lbl in item.get("labels", [])}


def blockers(root, number):
    """The numbers of the open issues that block issue `number`."""
    listed = gh_json(root, "api", BLOCKED_BY_PATH % number)
    return sorted(b["number"] for b in listed if b.get("state") == "open")


def sub_issues(root, number):
    """Issue `number`'s sub-issues, in the order the issue lists them."""
    return gh_json(root, "api", SUB_ISSUES_PATH % number)


def is_open(item):
    # gh issue list says "OPEN"; the REST API says "open".
    return item.get("state", "").lower() == "open"


def summary(item):
    return {"number": item["number"], "title": item["title"]}


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------


# What setup copies, beside the .gitignore it writes.
COPIES = (COPY_SCRIPT, COPY_ROLES, COPY_MANIFEST)


def ignore_text():
    names = sorted(os.path.basename(rel) for rel in (*COPIES, COPY_IGNORE))
    return "".join(name + "\n" for name in names).encode("utf-8")


def cmd_setup(args):
    """Copy this script and what it reads into the project. The module
    docstring has why."""
    root = project_root(args.repo)
    sources = {
        COPY_SCRIPT: SCRIPT_PATH,
        COPY_ROLES: plugin_file(COPY_ROLES, SHIPPED_ROLES),
        COPY_MANIFEST: plugin_file(COPY_MANIFEST, SHIPPED_MANIFEST),
    }
    contents = [(rel, read_bytes(sources[rel])) for rel in COPIES]
    contents.append((COPY_IGNORE, ignore_text()))
    files = []
    for rel, content in contents:
        write_bytes(root, rel, content)
        files.append({"file": rel, "sha256": hashlib.sha256(content).hexdigest()})
    data = {"repo": root, "files": files, "prefix": COPY_PREFIX}

    def human():
        for f in files:
            print("wrote %s" % f["file"])
        print("\nfrom %s, start every command with:\n%s && " % (root, COPY_PREFIX))

    return emit(args, "setup", data, human=human)


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


def owner_fields(roles):
    """The path of each field the template leaves for the owner, in file order."""
    out = []
    for role, entry in roles.items():
        for key, value in entry.items():
            if value is None:
                out.append("%s.%s.%s" % (ROLES_KEY, role, key))
    return out


def cmd_config_init(args):
    """Write the roles file from the template, with the plugin's version."""
    root = project_root(args.repo)
    target = os.path.join(root, *ROLES_FILE.split("/"))
    if os.path.lexists(target):
        data = {"file": ROLES_FILE, "written": False, "owner_fields": []}
        error = (
            "%s already exists, so it was left as it is. Edit it to change a role, or delete"
            " it and run config init again to start from the template." % ROLES_FILE
        )
        return emit(args, "config init", data, errors=[error], human=lambda: None)

    template = read_json(plugin_file(COPY_ROLES, SHIPPED_ROLES))
    roles = template.get(ROLES_KEY) if isinstance(template, dict) else None
    if not isinstance(roles, dict) or not all(isinstance(e, dict) for e in roles.values()):
        raise Fatal(
            "the roles template does not hold a %r object of roles. Install the flywheel"
            " plugin again, then run its setup." % ROLES_KEY
        )
    version = plugin_version()
    for entry in roles.values():
        entry[VERSION_KEY] = version
    fields = owner_fields(roles)
    text = json.dumps(template, indent=2) + "\n"
    write_bytes(root, ROLES_FILE, text.encode("utf-8"))
    data = {"file": ROLES_FILE, "written": True, "owner_fields": fields}

    def human():
        print("wrote %s" % ROLES_FILE)
        if fields:
            print("\nthe owner fills in each of these:")
            for f in fields:
                print("  %s" % f)

    return emit(args, "config init", data, human=human)


# --------------------------------------------------------------------------
# queue
# --------------------------------------------------------------------------


def queue_data(found, blocked, plan, finished=False):
    """queue's data: the issues it names, without the titles its plain output prints."""

    def bare(entry):
        return None if entry is None else {k: v for k, v in entry.items() if k != "title"}

    return {
        "issues": [bare(f) for f in found],
        "blocked": [bare(b) for b in blocked],
        "tracking": bare(plan),
        "finished": finished,
    }


def print_issues(found):
    for item in found:
        print("#%d %s" % (item["number"], item["title"]))


def print_blocked(blocked):
    for item in blocked:
        print(
            "#%d %s, blocked by %s"
            % (item["number"], item["title"], ", ".join("#%d" % n for n in item["blocked_by"]))
        )


def cmd_queue(args):
    root = project_root(args.repo)
    if args.tracking is not None:
        return queue_in_plan(args, root, args.tracking)
    offer = free_issues(root, args.count)
    found, blocked, plan = offer["found"], offer["blocked"], offer["plan"]

    def human():
        print_issues(found)
        if len(found) == args.count:
            return
        other = "other " if found else ""
        if plan:
            print("#%d %s is an approved tracking issue." % (plan["number"], plan["title"]))
            print(
                "To take its next sub-issue, run: %s queue --tracking %d" % (PROG, plan["number"])
            )
        elif blocked:
            print("Every %sfree approved issue is blocked by an open issue:" % other)
            print_blocked(blocked)
        else:
            print("No %sapproved issue is free." % other)

    return emit(args, "queue", queue_data(found, blocked, plan), human=human)


def offer_of(found=None, blocked=None, plan=None, finished=False, errors=None, warnings=None):
    """What the queue offers: the issues found, and why it offers no more."""
    return {
        "found": found or [],
        "blocked": blocked or [],
        "plan": plan,
        "finished": finished,
        "errors": errors or [],
        "warnings": warnings or [],
    }


def free_issues(root, count):
    """Up to `count` of the oldest free approved issues, or the plan that comes first."""
    approved = gh_json(
        root,
        "issue",
        "list",
        "--state",
        "open",
        "--label",
        APPROVED,
        "--limit",
        str(LIST_LIMIT),
        "--json",
        "number,title,labels",
    )
    held = claims(root)
    # An approved plan's issues are taken only in the plan's order. The plan
    # takes its place at its lowest open number, which is never after any of
    # its sub-issues, and wins a tie, so it is named before one is offered.
    queue = []
    for item in approved:
        if TRACKING in labels(item):
            subs = [s["number"] for s in sub_issues(root, item["number"]) if is_open(s)]
            queue.append((min([item["number"], *subs]), item, True))
        elif item["number"] not in held:
            queue.append((item["number"], item, False))
    queue.sort(key=lambda entry: (entry[0], not entry[2]))

    found, plan, blocked = [], None, []
    for _, item, is_plan in queue:
        if len(found) == count:
            break
        if is_plan:
            plan = summary(item)
            break
        open_blockers = blockers(root, item["number"])
        if open_blockers:
            blocked.append(dict(summary(item), blocked_by=open_blockers))
        else:
            found.append(summary(item))
    return offer_of(found, blocked, plan)


def queue_in_plan(args, root, number):
    """`queue --tracking N`: #N's sub-issues to work, in #N's order."""
    offer = plan_issues(root, number, args.count)
    found, blocked, finished = offer["found"], offer["blocked"], offer["finished"]
    data = queue_data(found, blocked, offer["plan"], finished)
    if offer["errors"]:
        return emit(args, "queue", data, offer["errors"])

    def human():
        print_issues(found)
        if len(found) == args.count or offer["warnings"]:
            return
        other = "other " if found else ""
        if finished:
            print("Every sub-issue of #%d is closed, so its plan is finished." % number)
            print("To close #%d, run: %s %d" % (number, PLAN_CLOSE, number))
        elif blocked:
            print("Every %sfree sub-issue of #%d is blocked by an open issue:" % (other, number))
            print_blocked(blocked)
        else:
            print("No %ssub-issue of #%d is free." % (other, number))

    return emit(args, "queue", data, warnings=offer["warnings"], human=human)


def plan_issues(root, number, count):
    """Up to `count` of tracking issue #number's free sub-issues, in #number's order."""
    item = issue(root, number)
    plan = summary(item)
    problems = []
    if not is_open(item):
        problems.append("#%d is closed; its plan is finished" % number)
    if TRACKING not in labels(item):
        problems.append(
            "#%d is not labeled %s; run %s queue without --tracking" % (number, TRACKING, PROG)
        )
    if APPROVED not in labels(item):
        problems.append(
            "#%d is not labeled %s; ask the owner to approve the plan" % (number, APPROVED)
        )
    if problems:
        return offer_of(plan=plan, errors=problems)

    held = claims(root)
    subs = sub_issues(root, number)
    finished = bool(subs) and not any(is_open(s) for s in subs)
    found, blocked, stopped = [], [], []
    for sub in subs:
        n = sub["number"]
        if len(found) == count:
            break
        if not is_open(sub) or n in held:
            continue
        open_blockers = blockers(root, n)
        if open_blockers:
            blocked.append(dict(summary(sub), blocked_by=open_blockers))
            continue
        if APPROVED not in labels(sub):
            stopped.append(
                "#%d %s is next in #%d's order and is not labeled %s; "
                "ask the owner to approve it" % (n, sub["title"], number, APPROVED)
            )
            if not found:
                return offer_of(blocked=blocked, plan=plan, errors=stopped)
            break
        found.append(summary(sub))
    return offer_of(found, blocked, plan, finished, warnings=stopped)


# --------------------------------------------------------------------------
# claim and brief
# --------------------------------------------------------------------------


def cmd_claim(args):
    root = project_root(args.repo)
    if args.tracking is not None and not args.next:
        raise Fatal(
            "--tracking works only with --next. Run: %s claim --next --tracking %d"
            % (PROG, args.tracking)
        )
    if args.next:
        return claim_next(args, root)
    n = args.number
    errors, warnings, _ = take(args, root, n)
    data = {"number": n, "branch": branch(n)}
    human = None if errors else lambda: print_claimed(args, n)
    return emit(args, "claim", data, errors, warnings, human=human)


def claim_next(args, root):
    """`claim --next`: claim what `queue` offers, and on a lost race the next one."""
    lost = []
    while True:
        if args.tracking is None:
            offer = free_issues(root, len(lost) + 1)
        else:
            offer = plan_issues(root, args.tracking, len(lost) + 1)
        fresh = [f for f in offer["found"] if f["number"] not in lost]
        data = {"number": None, "branch": None, "lost": lost}
        if not fresh:
            errors = offer["errors"] or offer["warnings"]
            return emit(args, "claim", data, errors or [nothing_free(offer, args.tracking, lost)])
        n = fresh[0]["number"]
        errors, warnings, held = take(args, root, n)
        if held:
            lost.append(n)
            continue
        data.update(number=n, branch=branch(n))
        warnings = [
            "#%d is held by another agent, so the next free issue was taken" % m for m in lost
        ] + warnings
        human = None if errors else lambda claimed=n: print_claimed(args, claimed)
        return emit(args, "claim", data, errors, warnings, human=human)


def nothing_free(offer, tracking, lost):
    """Why `claim --next` found nothing to claim, and what to do next."""
    other = "other " if lost else ""
    plan, blocked = offer["plan"], offer["blocked"]
    if tracking is None and plan:
        return (
            "#%d %s is an approved tracking issue, and its plan comes first. Ask the owner "
            "whether to start on it, and on a yes run: %s claim --next --tracking %d"
            % (plan["number"], plan["title"], PROG, plan["number"])
        )
    if offer["finished"]:
        return (
            "Every sub-issue of #%d is closed, so its plan is finished. To close it, run: %s %d"
            % (
                tracking,
                PLAN_CLOSE,
                tracking,
            )
        )
    where = "approved issue" if tracking is None else "sub-issue of #%d" % tracking
    if blocked:
        return "Every %sfree %s is blocked by an open issue: %s" % (
            other,
            where,
            "; ".join(
                "#%d by %s" % (b["number"], ", ".join("#%d" % n for n in b["blocked_by"]))
                for b in blocked
            ),
        )
    return "No %s%s is free to claim" % (other, where)


def print_claimed(args, n):
    verb = "Would claim" if args.dry_run else "Claimed"
    print("%s #%d on branch %s" % (verb, n, branch(n)))


def take(args, root, n):
    """Claim issue n. Returns (errors, warnings, held), held when another agent has it."""
    item = issue(root, n)
    if item.get("state") != "OPEN":
        return ["#%d is closed" % n], [], False
    if APPROVED not in labels(item):
        return (
            [
                "#%d is not labeled %s. The owner approves an issue before it is worked on"
                % (n, APPROVED)
            ],
            [],
            False,
        )
    if n in claims(root):
        return [held_message(n)], [], True
    if args.dry_run:
        return [], [], False

    git(root, "fetch", "--quiet", REMOTE, BASE)
    tip = git(root, "rev-parse", "%s/%s" % (REMOTE, BASE)).stdout.strip()
    # The push is the lock. An empty lease ("ref:") refuses a branch that
    # exists at another commit, but a branch that already exists at this same
    # commit - two agents claiming off the same main - is "up to date" and
    # exits 0. So the claim is won only when porcelain output says this push
    # created the branch. --quiet would hide that line.
    push = git(
        root,
        "push",
        "--porcelain",
        "--force-with-lease=%s:" % ref(n),
        REMOTE,
        "%s:%s" % (tip, ref(n)),
        check=False,
    )
    if not created(push.stdout, ref(n)):
        if n in claims(root):
            return [held_message(n)], [], True
        raise Fatal("could not push %s: %s" % (branch(n), push.stderr.strip()))

    warnings = []
    track = "%s/%s" % (REMOTE, branch(n))
    git(root, "fetch", "--quiet", REMOTE, "%s:refs/remotes/%s" % (ref(n), track))
    switch = git(root, "switch", "--quiet", "-c", branch(n), "--track", track, check=False)
    if switch.returncode != 0:
        warnings.append(
            "claimed, but could not switch to %s: %s" % (branch(n), switch.stderr.strip())
        )
    body = "%s `%s`. `%s release %d` gives it up." % (CLAIM_MARK, branch(n), PROG, n)
    for step, cmd in (
        ("add the %s label" % IN_PROGRESS, ["edit", str(n), "--add-label", IN_PROGRESS]),
        ("comment", ["comment", str(n), "--body", body]),
    ):
        try:
            gh(root, "issue", *cmd)
        except Fatal as exc:
            warnings.append("claimed, but could not %s: %s" % (step, exc))
    return [], warnings, False


def created(porcelain, target):
    """Whether `git push --porcelain` output says it created `target`.

    Each ref gets a line "<flag>\\t<from>:<to>\\t<summary>"; the flag is "*"
    for a new ref and "=" for one already up to date.
    """
    for line in porcelain.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] == "*" and parts[1].endswith(":" + target):
            return True
    return False


def held_message(n):
    return "#%d is held: branch %s already exists on %s. Ask the owner before working on it" % (
        n,
        branch(n),
        REMOTE,
    )


def owners_comment(comment, owner, since):
    """Whether a comment is the owner's own, made after `since`."""
    author = (comment.get("author") or {}).get("login")
    body = comment.get("body") or ""
    if author != owner or body.startswith((AGENT_MARK, CLAIM_MARK, RELEASE_MARK)):
        return False
    return since is None or comment["createdAt"] > since


def quoted(text):
    """text as a markdown quote, so its own headings stay inside it."""
    return "\n".join(("> " + line).rstrip() for line in text.rstrip("\n").split("\n"))


def brief_text(data):
    """The first message of a session that works the issue."""
    role, gates = data["role"], data["gates"]
    out = [
        "Work issue #%d in %s, as the %s." % (data["number"], data["repository"], role["name"]),
        "",
    ]
    if role["tier"] is not None:
        out += ["The %s is tier %s in %s." % (role["name"], role["tier"], ROLES_FILE), ""]
    if gates:
        out.append("The gate commands, from %s:" % GATES_FILE)
        out += ["- %s: `%s`" % (name, command) for name, command in gates.items()]
        out.append("")
    if data["approved_at"]:
        out.append("The issue, as the owner approved it at %s:" % data["approved_at"])
    else:
        out.append("The issue, as the owner approved it:")
    out += ["", quoted("# %s\n\n%s" % (data["title"], data["body"])), ""]
    if data["comments"]:
        out += ["The owner's comments since approval:", ""]
        for c in data["comments"]:
            out += [quoted("**%s**\n\n%s" % (c["created_at"], c["body"])), ""]
    else:
        out += ["The owner has not commented since approval.", ""]
    return "\n".join(out)


def cmd_brief(args):
    root = project_root(args.repo)
    n = args.number
    found = gh_json(
        root,
        "api",
        "graphql",
        "-F",
        "owner={owner}",
        "-F",
        "name={repo}",
        "-F",
        "number=%d" % n,
        "-f",
        "query=" + BRIEF_QUERY,
    )
    repository = (found.get("data") or {}).get("repository") or {}
    item = repository.get("issue")
    if not item:
        raise Fatal("#%d is not an issue in this repository. Name an issue's number." % n)
    owner = repository["owner"]["login"]
    approvals = [
        e["createdAt"]
        for e in item["timelineItems"]["nodes"]
        if e and ((e.get("label") or {}).get("name") or "").lower() == APPROVED
    ]
    approved_at = max(approvals) if approvals else None
    edited_at = item.get("lastEditedAt")

    roles = read_project_json(root, ROLES_FILE, ROLES_KEY)
    gates = read_project_json(root, GATES_FILE, GATES_KEY)
    warnings = []
    entry = (roles or {}).get(BRIEF_ROLE)
    if not isinstance(entry, dict):
        warnings.append(
            "%s does not name the %s role, so the brief leaves out its tier. Run config init to"
            " write it." % (ROLES_FILE, BRIEF_ROLE)
        )
        entry = {}
    if gates is None:
        warnings.append(
            '%s is missing, so the brief names no gate commands. Write it with a "%s" object'
            " that maps each gate to its command." % (GATES_FILE, GATES_KEY)
        )

    data = {
        "number": n,
        "repository": repository["nameWithOwner"],
        "url": item["url"],
        "title": item["title"],
        "body": item.get("body") or "",
        "approved_at": approved_at,
        "edited_at": edited_at,
        "comments": [
            {"created_at": c["createdAt"], "body": c.get("body") or ""}
            for c in item["comments"]["nodes"]
            if c and owners_comment(c, owner, approved_at)
        ],
        "role": {"name": BRIEF_ROLE, "tier": entry.get(TIER_KEY)},
        "gates": gates or {},
        "prompt": None,
    }
    errors = []
    if APPROVED not in {lbl["name"].lower() for lbl in item["labels"]["nodes"]}:
        errors.append(
            "#%d is not labeled %s. The owner approves an issue before a session works it"
            % (n, APPROVED)
        )
    elif approved_at and edited_at and edited_at > approved_at:
        errors.append(
            "#%d was edited at %s, after `%s` was added at %s. The owner reads the edit and"
            " re-approves it by removing the label and adding it again."
            % (n, edited_at, APPROVED, approved_at)
        )
    if not errors:
        data["prompt"] = brief_text(data)

    def human():
        if data["prompt"]:
            sys.stdout.write(data["prompt"])

    return emit(args, "brief", data, errors, warnings, human=human)


# --------------------------------------------------------------------------
# release, stale, clear and sweep
# --------------------------------------------------------------------------


def cmd_release(args):
    root = project_root(args.repo)
    n = args.number
    data = {"number": n, "branch": branch(n)}
    item = issue(root, n)
    sha = claims(root).get(n)
    labeled = IN_PROGRESS in labels(item)
    if sha is None and not labeled:
        return emit(args, "release", data, ["#%d is not claimed" % n])
    if sha is not None:
        git(root, "fetch", "--quiet", REMOTE, BASE, ref(n))
        ahead = int(git(root, "rev-list", "--count", "%s/%s..%s" % (REMOTE, BASE, sha)).stdout)
        if ahead:
            return emit(
                args,
                "release",
                data,
                [
                    "%s has %d commit(s) not on %s. Keep the work on another branch, or delete "
                    "%s yourself; release does not throw work away"
                    % (branch(n), ahead, BASE, branch(n))
                ],
            )

    def human():
        verb = "Would release" if args.dry_run else "Released"
        print("%s #%d" % (verb, n))

    if args.dry_run:
        return emit(args, "release", data, human=human)

    if sha is not None:
        # Delete only the commit we checked, in case work was pushed since.
        lease = "--force-with-lease=%s:%s" % (ref(n), sha)
        delete = git(root, "push", "--quiet", lease, REMOTE, ":" + ref(n), check=False)
        if delete.returncode != 0:
            return emit(
                args,
                "release",
                data,
                ["%s changed while releasing; run release again" % branch(n)],
            )
    if labeled:
        gh(root, "issue", "edit", str(n), "--remove-label", IN_PROGRESS)
    gh(root, "issue", "comment", str(n), "--body", "%s%s." % (RELEASE_MARK, branch(n)))
    return emit(args, "release", data, human=human)


def cmd_stale(args):
    root = project_root(args.repo)
    held = claims(root)
    labeled = gh_json(
        root,
        "issue",
        "list",
        "--state",
        "all",
        "--label",
        IN_PROGRESS,
        "--limit",
        str(LIST_LIMIT),
        "--json",
        "number,state",
    )
    closed = {i["number"] for i in labeled if i.get("state") != "OPEN"}
    errors, rows = [], []
    for n in sorted(set(held) | {i["number"] for i in labeled}):
        rows.append({"number": n, "branch": branch(n)})
        if n not in held and n in closed:
            errors.append(
                "#%d is closed but still labeled %s; run release %d" % (n, IN_PROGRESS, n)
            )
            continue
        if n not in held:
            errors.append(
                "#%d is labeled %s but %s does not exist; run release %d"
                % (n, IN_PROGRESS, branch(n), n)
            )
            continue
        item = issue(root, n)
        if item.get("state") != "OPEN":
            errors.append("#%d is closed but %s still exists; run release %d" % (n, branch(n), n))
            continue
        if IN_PROGRESS not in labels(item):
            # claim warns and exits 0 when adding the label fails, so a held
            # issue can be left unlabeled.
            errors.append(
                "#%d has %s but is not labeled %s; run gh issue edit %d --add-label %s"
                % (n, branch(n), IN_PROGRESS, n, IN_PROGRESS)
            )

    def human():
        if not errors:
            print("No stale claims.")

    return emit(args, "stale", {"claims": rows}, errors, human=human)


def cmd_clear(args):
    root = project_root(args.repo)
    n = args.number
    data = {
        "number": n,
        "branch": branch(n),
        "pull_request": None,
        "worktrees": [],
        "cleared": False,
    }
    item = issue(root, n)
    if item.get("state") == "OPEN":
        return emit(
            args,
            "clear",
            data,
            ["#%d is still open. clear runs once its pull request has merged" % n],
        )
    local = git(root, "rev-parse", "--verify", "--quiet", ref(n), check=False)
    if local.returncode != 0:
        return emit(args, "clear", data, ["there is no local %s to clear" % branch(n)])
    sha = local.stdout.strip()
    base = "%s/%s" % (REMOTE, BASE)
    git(root, "fetch", "--quiet", REMOTE, BASE)
    data["pull_request"] = pull_holding(root, merged_pulls(root, branch(n)), sha)
    if data["pull_request"] is None and not in_base(root, base, sha):
        return emit(
            args,
            "clear",
            data,
            [
                "%s holds commits that every merged pull request from it lacks, and changes %s"
                " lacks. Merge or move them, or delete %s yourself; clear does not throw work"
                " away" % (branch(n), base, branch(n))
            ],
        )
    data["worktrees"] = checked_out(root, ref(n))
    dirty = [p for p in data["worktrees"] if git(p, "status", "--porcelain").stdout.strip()]
    if dirty:
        return emit(
            args,
            "clear",
            data,
            [
                "the worktree at %s has %s checked out and uncommitted changes. Commit or "
                "discard them there, then run clear %d again" % (path, branch(n), n)
                for path in dirty
            ],
        )

    def human():
        verb = "Would clear" if args.dry_run else "Cleared"
        print("%s %s" % (verb, branch(n)))
        for path in data["worktrees"]:
            print("  %s detached at %s" % (path, base))

    if args.dry_run:
        return emit(args, "clear", data, human=human)

    for path in data["worktrees"]:
        git(path, "switch", "--quiet", "--detach", base)
    git(root, "branch", "--quiet", "-D", branch(n))
    data["cleared"] = True
    return emit(args, "clear", data, human=human)


def merged_pulls(root, *head):
    """Merged pull requests, as {number, headRefName, headRefOid}, from branch `head` if given."""
    args = ["pr", "list", "--state", "merged"]
    if head:
        args += ["--head", head[0]]
    return gh_json(root, *args, "--limit", str(LIST_LIMIT), "--json", MERGED_FIELDS)


def pull_holding(root, pulls, sha):
    """The number of the first of `pulls` whose head holds `sha`, or None.

    The head is the branch as it merged, so this holds however far main has
    moved since. A head this clone lacks is fetched from the pull request's ref.
    """
    for pull in pulls:
        head = pull["headRefOid"]
        if git(root, "cat-file", "-e", head + "^{commit}", check=False).returncode != 0:
            git(root, "fetch", "--quiet", REMOTE, "refs/pull/%d/head" % pull["number"], check=False)
        if git(root, "merge-base", "--is-ancestor", sha, head, check=False).returncode == 0:
            return pull["number"]
    return None


def in_base(root, base, sha):
    """Whether merging `sha` into `base` would leave base's tree as it is."""
    proc = git(root, "merge-tree", "--write-tree", base, sha, check=False)
    if proc.returncode > 1:  # pragma: no cover - only a git without --write-tree, before 2.38
        raise Fatal(
            "`git merge-tree` failed: %s. Install git 2.38 or later, then run again."
            % proc.stderr.strip()
        )
    if proc.returncode == 1:  # conflicts: the branch changes what base has
        return False
    tree = git(root, "rev-parse", base + "^{tree}").stdout.strip()
    return proc.stdout.split("\n", 1)[0].strip() == tree


def worktrees(root):
    """{branch ref: path} for every worktree that has a branch checked out."""
    out, path = {}, None
    for line in git(root, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree ") :]
        elif line.startswith("branch "):
            out[line[len("branch ") :]] = path
    return out


def checked_out(root, target):
    """The path of every worktree that has the branch `target` checked out."""
    return [path for name, path in worktrees(root).items() if name == target]


def remote_branches(root):
    """The names of every branch on origin."""
    out = git(root, "ls-remote", "--heads", REMOTE).stdout
    return {line.partition("\trefs/heads/")[2] for line in out.splitlines()}


def cmd_sweep(args):
    root = project_root(args.repo)
    base = "%s/%s" % (REMOTE, BASE)
    git(root, "fetch", "--quiet", REMOTE, BASE)
    out = git(root, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/")
    local = [line.split(" ", 1) for line in out.stdout.splitlines() if line]
    on_origin = remote_branches(root)
    checked = worktrees(root)
    pulls = {}
    for pull in merged_pulls(root):
        pulls.setdefault(pull["headRefName"], []).append(pull)

    deleted, kept = [], []
    for name, sha in local:
        if name == BASE:
            continue
        if "refs/heads/" + name in checked:
            reason = "checked out in %s" % checked["refs/heads/" + name]
        elif name in on_origin:
            reason = "still on %s, where someone may be working on it" % REMOTE
        elif pull_holding(root, pulls.get(name, []), sha) is not None or in_base(root, base, sha):
            deleted.append(name)
            continue
        else:
            reason = "holds work %s lacks" % base
        kept.append({"branch": name, "reason": reason})

    if not args.dry_run:
        for name in deleted:
            git(root, "branch", "--quiet", "-D", name)

    def human():
        verb = "Would delete" if args.dry_run else "Deleted"
        for name in deleted:
            print("%s %s" % (verb, name))
        for k in kept:
            print("Kept %s: %s" % (k["branch"], k["reason"]))

    return emit(args, "sweep", {"deleted": deleted, "kept": kept}, human=human)


# --------------------------------------------------------------------------
# ids
# --------------------------------------------------------------------------


def table_cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def defined_ids(text):
    """Each id in the ID column of a table in text."""
    out = set()
    column = None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            column = None
            continue
        cells = table_cells(line)
        if column is None:
            column = cells.index(ID_HEADER) if ID_HEADER in cells else -1
        elif 0 <= column < len(cells) and METHOD_ID.fullmatch(cells[column]):
            out.add(cells[column])
    return out


def cited_ids(text):
    """(id, line) for each id the text cites as the method's, in order."""
    out = []
    for cite in CITATION.finditer(text):
        for tick in BACKTICKED.finditer(cite.group(1)):
            name = tick.group(1)
            if METHOD_ID.fullmatch(name):
                line = text.count("\n", 0, cite.start(1) + tick.start()) + 1
                out.append((name, line))
    return out


def files_under(root, rel):
    """Every file under root/rel, as a path relative to root, sorted."""
    out = []
    for top, dirs, names in os.walk(os.path.join(root, rel)):
        dirs.sort()
        for name in sorted(names):
            out.append(os.path.relpath(os.path.join(top, name), root).replace(os.sep, "/"))
    return out


def read_text(path):
    try:
        return read_bytes(path).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Fatal(
            "%s is not UTF-8 text: %s. Save it as UTF-8, then run again." % (path, exc)
        ) from exc


def cmd_ids(args):
    """Name each cited method id that the plugin's docs do not define."""
    if in_copy():
        raise Fatal(
            "ids reads the plugin's docs/, which %s/ does not hold. Run the plugin's own"
            " scripts/%s." % (COPY_DIR, SCRIPT_NAME)
        )
    root = project_root(args.repo)
    plugin = os.path.dirname(os.path.dirname(SCRIPT_PATH))
    defined = set()
    for rel in files_under(plugin, DOCS_DIR):
        if rel.endswith(".md"):
            defined |= defined_ids(read_text(os.path.join(plugin, rel)))
    if not defined:
        raise Fatal(
            "no document under %s defines a method id. Install the flywheel plugin again."
            % os.path.join(plugin, DOCS_DIR)
        )

    sources = [(rel, os.path.join(plugin, rel)) for rel in files_under(plugin, TEMPLATES_DIR)]
    sources += [(rel, os.path.join(plugin, rel)) for rel in files_under(plugin, SKILLS_DIR)]
    spec = os.path.join(root, *SPEC_FILE.split("/"))
    if os.path.isfile(spec):
        sources.append((SPEC_FILE, spec))
    unknown = []
    for rel, path in sources:
        for name, line in cited_ids(read_text(path)):
            if name not in defined:
                unknown.append({"id": name, "file": rel, "line": line})
    errors = [
        "%s:%d: `%s` is cited as the method's, and no document under %s/ defines it. Correct"
        " the citation, or define the id in the method's docs."
        % (u["file"], u["line"], u["id"], DOCS_DIR)
        for u in unknown
    ]
    data = {"files": [rel for rel, _ in sources], "unknown": unknown}

    def human():
        if not unknown:
            print("every method id cited in %d files is defined" % len(sources))

    return emit(args, "ids", data, errors=errors, human=human)


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


def gh_repository(repo):
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
    if "tracking" not in plan and len(issues) <= 1:
        # A plan of one issue is that issue alone, without a tracking issue.
        pass
    elif not (isinstance(tracking, dict) and all(is_text(tracking.get(k)) for k in TRACKING_KEYS)):
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
            under = ""
            if ledger.get("tracking"):
                under = ", under tracking issue #%d" % ledger["tracking"]["number"]
            return ledger, ["this plan was filed already%s; nothing is left to file" % under]
        return empty_ledger(name), []
    return ledger, []


def plan_dir(repo):
    """Make the folder plan writes to, with a .gitignore that keeps it all
    out of every commit."""
    write_bytes(repo, PLAN_IGNORE, b"*\n")


def write_ledger(repo, ledger):
    plan_dir(repo)
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
    tail = "and a tracking issue" if data["tracking"] else "without a tracking issue"
    out += ["", "%d issue(s), %s." % (len(data["issues"]), tail)]
    if data["token"]:
        out += ["", "%s`%s`" % (TOKEN_LABEL.capitalize(), data["token"])]
    return "\n".join(out) + "\n"


def checked_plan(args, repo):
    """Read and check the plan: (raw, repository, labels, rows, tracking,
    ledger, faults, warnings)."""
    raw, plan = read_plan(args.drafts)
    where = gh_repository(repo)
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


def cmd_plan_draft(args):
    project_root(args.repo)
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


def cmd_plan_report(args):
    repo = project_root(args.repo)
    raw, where, labels, rows, tracking, ledger, faults, warnings = checked_plan(args, repo)
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
    plan_dir(repo)
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


def issue_list(numbers):
    return ", ".join("#%d" % n for n in numbers) or "nothing"


def file_tracking(repo, ledger, tracking, rows, numbers):
    """The plan's tracking issue, filed now unless an earlier run filed it,
    with whether this run filed it."""
    t = ledger["tracking"]
    filed = t is None
    if filed:
        body = tracking_body(tracking, rows, numbers)
        number, url = create_issue(repo, tracking["title"], body, [TRACKING])
        t = {"number": number, "title": tracking["title"], "url": url}
        ledger["tracking"] = t
        write_ledger(repo, ledger)
    return dict(t, filed=filed)


def add_sub_issues(repo, tracking, rows, numbers, ids, data):
    """Add each of the plan's issues that tracking issue #tracking lacks, in order."""
    have = [s["number"] for s in sub_issues(repo, tracking)]
    for r in rows:
        n = numbers[r["key"]]
        if n in have:
            continue
        gh(
            repo,
            "api",
            "-X",
            "POST",
            SUB_ISSUES_ADD_PATH % tracking,
            "-F",
            "sub_issue_id=%d" % database_id(repo, n, ids),
        )
        data["sub_issues"].append({"issue": n, "tracking": tracking})


def cmd_plan_file(args):
    repo = project_root(args.repo)
    raw, where, labels, rows, tracking, ledger, faults, warnings = checked_plan(args, repo)
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
        if tracking:
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

        if tracking:
            data["tracking"] = file_tracking(repo, ledger, tracking, rows, numbers)
            add_sub_issues(repo, data["tracking"]["number"], rows, numbers, ids, data)
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
                % (n, issue_list(on), issue_list(want))
            )
    t = data["tracking"]
    if t:
        on = [s["number"] for s in sub_issues(repo, t["number"])]
        want = [numbers[r["key"]] for r in rows]
        if on != want:
            errors.append(
                "#%d lists its sub-issues as %s, and the plan's order is %s"
                % (t["number"], issue_list(on), issue_list(want))
            )
    if not errors:
        ledger["complete"] = True
        write_ledger(repo, ledger)
    return emit(args, "plan file", data, errors, warnings, human=human)


def cmd_plan_close(args):
    repo = project_root(args.repo)
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
                % (
                    n,
                    issue_list([s["number"] for s in still_open]),
                    "%s claim --next --tracking %d" % (PROG, n),
                )
            ],
        )

    comment = "Every sub-issue is closed: %s." % issue_list(data["sub_issues"])
    gh(repo, "issue", "close", str(n), "--reason", "completed", "--comment", comment)
    data["closed"] = True

    def human():
        print("Closed #%d. %s" % (n, comment))

    return emit(args, "plan close", data, human=human)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def positive(text):
    """argparse type: an integer of 1 or more."""
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError("%r is not a whole number of 1 or more" % text)
    return value


def build_parser():
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common = argparse.ArgumentParser(add_help=False, parents=[output])
    common.add_argument(
        "-C", "--repo", metavar="DIR", default=".", help="the clone to work in (default: here)"
    )
    preview = argparse.ArgumentParser(add_help=False)
    preview.add_argument("--dry-run", action="store_true", help="say what would change, and stop")
    numbered = argparse.ArgumentParser(add_help=False)
    numbered.add_argument("number", type=int, help="the issue's number")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Deterministic half of the flywheel plugin."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "setup",
        parents=[common],
        help="copy this script and what it reads into %s/, which git ignores" % COPY_DIR,
    )
    p.set_defaults(func=cmd_setup)

    config = sub.add_parser("config", help="write the files the owner sets for the loop")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    p = config_sub.add_parser(
        "init",
        parents=[common],
        help="write %s from the plugin's template, and name the fields the owner fills"
        % ROLES_FILE,
    )
    p.set_defaults(func=cmd_config_init)

    p = sub.add_parser(
        "queue", parents=[common], help="the oldest approved issues nobody holds, to work next"
    )
    p.add_argument(
        "--count", type=positive, default=1, metavar="N", help="offer up to N issues (default: 1)"
    )
    p.add_argument(
        "--tracking", type=int, metavar="N", help="take the next sub-issues of tracking issue N"
    )
    p.set_defaults(func=cmd_queue)

    p = sub.add_parser("claim", parents=[common, preview], help="take an issue")
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("number", type=int, nargs="?", help="the issue's number")
    which.add_argument(
        "--next",
        action="store_true",
        help="take the issue queue offers, and the next one if another agent wins it",
    )
    p.add_argument(
        "--tracking",
        type=int,
        metavar="N",
        help="with --next, take tracking issue N's next sub-issue",
    )
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser(
        "brief",
        parents=[common, numbered],
        help="print the first message of a session that works an issue",
    )
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("release", parents=[common, numbered, preview], help="give an issue up")
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("stale", parents=[common], help="labels and branches that disagree")
    p.set_defaults(func=cmd_stale)

    p = sub.add_parser(
        "clear", parents=[common, numbered, preview], help="delete a merged claim's local branch"
    )
    p.set_defaults(func=cmd_clear)

    p = sub.add_parser(
        "sweep", parents=[common, preview], help="delete local branches whose work is on main"
    )
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser(
        "ids",
        parents=[common],
        help="name each method id cited in the plugin or %s that %s/ does not define"
        % (SPEC_FILE, DOCS_DIR),
    )
    p.set_defaults(func=cmd_ids)

    p = sub.add_parser(
        "plan", help="file an issue, or a plan's issues under a tracking issue, and close a plan"
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
        parents=[common, drafts, preview],
        help="file the plan report showed: issues, links, tracking issue and sub-issues",
        epilog=PLAN_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--token", required=True, help="the approval token plan report printed")
    p.set_defaults(func=cmd_plan_file)

    p = plans.add_parser(
        "close",
        parents=[common, numbered],
        help="close an approved tracking issue once every sub-issue is closed",
    )
    p.set_defaults(func=cmd_plan_close)

    return ap


def main(argv=None):
    # stdout is flushed inside the try, where a closed pipe is caught, rather
    # than by Python at exit, where it would print a traceback and exit 120.
    try:
        try:
            args = build_parser().parse_args(argv)
        except SystemExit:
            # argparse exits here after printing --help.
            sys.stdout.flush()
            raise
        code = args.func(args)
        sys.stdout.flush()
        return code
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN
    except BrokenPipeError:
        silence_stdout()
        return OK


def silence_stdout():
    """Point stdout at the null device, so the flush at exit cannot fail.

    The output still buffered when the pipe closed stays in the buffer, and
    Python flushes it again at exit.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, sys.stdout.fileno())
    finally:
        os.close(devnull)


if __name__ == "__main__":
    sys.exit(main())

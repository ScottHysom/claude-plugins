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
    python3 flywheel.py brief 12
    python3 flywheel.py release 12
    python3 flywheel.py stale
    python3 flywheel.py clear 12
    python3 flywheel.py sweep --dry-run

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

Every command takes --json and -C/--repo; claim, release, clear and sweep take
--dry-run.

Exit codes: 0 clean, 1 ran and found problems (the issue is held or not
approved, or still open, the branch holds work, a label and a branch
disagree, the issue changed after approval, the roles file exists already),
2 could not run.

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

`setup` and `config init` write only under .flywheel/. `claim`, `release`,
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
# The command that closes a finished plan, until the plan commands move here.
PLAN_CLOSE = "issues.py plan close"
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


def run(root, cmd, check=True):
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
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


def gh(root, *args):
    """Run gh and return its stdout. Tests replace this."""
    return run(root, ["gh", *args]).stdout


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
        if len(found) == args.count:
            break
        if is_plan:
            plan = summary(item)
            break
        open_blockers = blockers(root, item["number"])
        if open_blockers:
            blocked.append(dict(summary(item), blocked_by=open_blockers))
        else:
            found.append(summary(item))

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


def queue_in_plan(args, root, number):
    """`queue --tracking N`: #N's sub-issues to work, in #N's order."""
    item = issue(root, number)
    found, blocked, plan = [], [], summary(item)
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
        return emit(args, "queue", queue_data(found, blocked, plan), problems)

    held = claims(root)
    subs = sub_issues(root, number)
    finished = bool(subs) and not any(is_open(s) for s in subs)
    stopped = []
    for sub in subs:
        n = sub["number"]
        if len(found) == args.count:
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
                return emit(args, "queue", queue_data(found, blocked, plan), stopped)
            break
        found.append(summary(sub))

    def human():
        print_issues(found)
        if len(found) == args.count or stopped:
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

    data = queue_data(found, blocked, plan, finished)
    return emit(args, "queue", data, warnings=stopped, human=human)


# --------------------------------------------------------------------------
# claim and brief
# --------------------------------------------------------------------------


def cmd_claim(args):
    root = project_root(args.repo)
    n = args.number
    data = {"number": n, "branch": branch(n)}
    item = issue(root, n)
    if item.get("state") != "OPEN":
        return emit(args, "claim", data, ["#%d is closed" % n])
    if APPROVED not in labels(item):
        return emit(
            args,
            "claim",
            data,
            [
                "#%d is not labeled %s. The owner approves an issue before it is worked on"
                % (n, APPROVED)
            ],
        )
    if n in claims(root):
        return emit(args, "claim", data, [held_message(n)])

    def human():
        verb = "Would claim" if args.dry_run else "Claimed"
        print("%s #%d on branch %s" % (verb, n, branch(n)))

    if args.dry_run:
        return emit(args, "claim", data, human=human)

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
            return emit(args, "claim", data, [held_message(n)])
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
    return emit(args, "claim", data, warnings=warnings, human=human)


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

    p = sub.add_parser("claim", parents=[common, numbered, preview], help="take an issue")
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

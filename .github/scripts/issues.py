#!/usr/bin/env python3
"""Choose, claim, release and clear issues, so two agents never work on the same one.

It also sweeps away the local branches that finished work leaves behind, and
files a plan's issues under a tracking issue once the owner approves the plan.

README.md, under "Issues", describes the process; this is the part of it that
keeps two agents off the same approved issue. The lock is a branch named
`issue/<N>` on origin. `claim` creates it with a push that the server refuses
when the branch already exists, so of two agents claiming at once exactly one
wins. The `in-progress` label and a comment then say so where people look. The
branch is the lock and the label is the signal: when they disagree the branch is
right, and `stale` reports the disagreement. `release` takes the label off a
claim given up; `.github/workflows/issue-closed.yml` takes it off an issue that
closes, which is how most claims end. `clear` then deletes the local claim
branch that the merge left behind. `sweep` deletes every local branch whose
work is on main, whatever its name, and `.claude/hooks/branch_sweep.py` runs it
when a Claude Code session starts.

Run from anywhere in a clone, with git and an authenticated gh on PATH:

    python3 .github/scripts/issues.py next
    python3 .github/scripts/issues.py next --tracking 347
    python3 .github/scripts/issues.py claim 12
    python3 .github/scripts/issues.py release 12
    python3 .github/scripts/issues.py stale
    python3 .github/scripts/issues.py clear 12
    python3 .github/scripts/issues.py sweep --dry-run
    python3 .github/scripts/issues.py plan report --drafts plan.json
    python3 .github/scripts/issues.py plan file --drafts plan.json --token 3f9a1c0e7b2d4a68

Commands:
    next        the oldest open approved issue nobody holds and no open issue
                blocks, or an approved tracking issue that comes first.
                With --tracking N, the next issue in tracking issue N's
                order instead. Changes nothing.
    claim N     take issue N: push issue/N, switch to it, label and comment.
    release N   give issue N up: delete issue/N if it holds no work, remove the
                label, comment.
    stale       claims idle for --days with no open pull request, and labels
                and branches that disagree, including a closed issue that
                still has the label and a held issue that lacks it.
    clear N     once issue N is closed, delete the local issue/N if a merged
                pull request or main has everything on it, first moving any
                worktree on it to a detached origin/main.
    sweep       delete every local branch but main whose work is on main,
                and name each branch kept with the reason.
    plan report check a plan's drafts, print the plan as it will be filed,
                ending with an approval token, and write the same report to
                .issues-plan/report.md.
    plan file   file the plan that report showed: its issues, their "blocked
                by" links, the tracking issue and its sub-issues, then read
                them back.

Every command takes --json and -C/--repo; claim, release, clear, sweep and
plan file take --dry-run.

Exit codes: 0 clean, 1 ran and found problems (the issue is held or not
approved, or still open, the branch holds work, a claim is stale, a plan is
refused or not filed as it says), 2 could not run.

Plans. The file-plan skill, at .claude/skills/file-plan/SKILL.md, drives the
two plan commands. `plan report --help` shows the shape of the plan file. The
model writes a plan's issues as JSON, each under a key of its own, and names
another issue of the plan in a body as {KEY}. `plan report` checks each draft
against CLAUDE.md's rules for issues, and checks the plan's keys and links.
It then orders the issues so each comes after the issues that block it, with
ties in the order the plan lists them. The tracking issue's body is the plan
text, after `**Claude:**`, then an Order section written from that order.
A refused plan's report holds the faults and no token.

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
- `next` exits 0 when nothing is free, or when every free issue is blocked. An
  empty queue is not a problem. `claim` ignores blockers, so the owner can
  still name a blocked issue.
- `next` never offers a sub-issue of an approved tracking issue, even the
  lowest-numbered free one. The plan's issues are taken in the plan's order,
  through `next --tracking N`, so `next` names the plan in their place.
- `next --tracking N` exits 1 on an unapproved sub-issue instead of skipping
  to a later approved one. Skipping would work the plan out of its order.
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
  the switch to origin/main would carry along. Changes nobody committed are
  for a person to keep or discard, not to move silently.
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
- A new claim branch points at main's tip, which may be an old commit, so
  `stale` counts idle time from the later of the tip's commit date and the most
  recent claim comment.
- `plan` reads a {KEY} outside code only, so a body can show the syntax in a
  code span or a fence. As a simplification, a fence is a line opening with
  three or more backticks or tildes, and a code span lies within one line.
- `plan file` checks that the plan's open blockers are open, and does not
  check the issues it filed in an earlier run. The record says it filed them.
- `plan file` adds a missing sub-issue at the end of the tracking issue's
  list. A run cut short adds them in order up to where it stopped, so the
  rest follow in order. A list put out of order some other way is reported by
  the read-back rather than reordered.
- When gh creates an issue and prints something that is not its address,
  `plan file` cannot record the number and stops. A re-run would file that
  issue again, so check the repository before running it again.

This script writes to git (a push, a branch switch, a branch deletion), and
`plan` writes files under .issues-plan/, so it is not for Cowork's device bridge, where a git write strands `.git/*.lock`
files. A Cowork session asks the owner to claim for it.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "issues.py"
APPROVED = "approved"
IN_PROGRESS = "in-progress"
REMOTE = "origin"
BASE = "main"
BRANCH_PREFIX = "issue/"
BRANCH_REF_RE = re.compile(r"^refs/heads/%s(\d+)$" % re.escape(BRANCH_PREFIX))
STALE_DAYS = 7
LIST_LIMIT = 1000
CLAIM_MARK = "Claimed on branch"
MERGED_FIELDS = "number,headRefName,headRefOid"
TRACKING = "tracking"
BLOCKED_BY_PATH = "repos/{owner}/{repo}/issues/%d/dependencies/blocked_by"
# GitHub caps a parent at 100 sub-issues, so one page holds them all.
SUB_ISSUES_PATH = "repos/{owner}/{repo}/issues/%d/sub_issues?per_page=100"
SUB_ISSUES_ADD_PATH = "repos/{owner}/{repo}/issues/%d/sub_issues"
ISSUE_PATH = "repos/{owner}/{repo}/issues/%d"

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
TRACKING_KEYS = ("title", "plan")
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
REFERENCE_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_-]*)\}")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
CODE_SPAN_RE = re.compile(r"(`+).*?\1")
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

example:
  {"issues": [
     {"key": "A", "title": "report() hides the token", "labels": ["bug", "repo"],
      "body": "**Claude:**\\n\\n## What's wrong\\n..."},
     {"key": "B", "title": "file() files twice", "labels": ["bug", "repo"],
      "blocked_by": ["A", 340], "body": "**Claude:**\\n\\n## What's wrong\\nAfter #{A}..."}],
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


def branch(number):
    return "%s%d" % (BRANCH_PREFIX, number)


def ref(number):
    return "refs/heads/" + branch(number)


def claims(repo):
    """{issue number: commit} for every issue/<N> branch on origin."""
    out = git(repo, "ls-remote", "--heads", REMOTE, BRANCH_PREFIX + "*").stdout
    held = {}
    for line in out.splitlines():
        sha, _, name = line.partition("\t")
        m = BRANCH_REF_RE.match(name)
        if m:
            held[int(m.group(1))] = sha
    return held


def issue(repo, number):
    return gh_json(
        repo, "issue", "view", str(number), "--json", "number,title,state,labels,comments"
    )


def labels(item):
    return {lbl.get("name", "").lower() for lbl in item.get("labels", [])}


def parse_time(text):
    # fromisoformat on 3.9 does not accept the "Z" GitHub writes.
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def blockers(repo, number):
    """The numbers of the open issues that block issue `number`."""
    listed = gh_json(repo, "api", BLOCKED_BY_PATH % number)
    return sorted(b["number"] for b in listed if b.get("state") == "open")


def sub_issues(repo, number):
    """Issue `number`'s sub-issues, in the order the issue lists them."""
    return gh_json(repo, "api", SUB_ISSUES_PATH % number)


def is_open(item):
    # gh issue list says "OPEN"; the REST API says "open".
    return item.get("state", "").lower() == "open"


def summary(item):
    return {"number": item["number"], "title": item["title"]}


def now():
    """The current time. Tests replace this."""
    return datetime.datetime.now(datetime.timezone.utc)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_next(args, repo):
    if args.tracking is not None:
        return next_in_plan(args, repo, args.tracking)
    approved = gh_json(
        repo,
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
    held = claims(repo)
    # An approved plan's issues are taken only in the plan's order. The plan
    # takes its place at its lowest open number, which is never after any of
    # its sub-issues, and wins a tie, so it is named before one is offered.
    queue = []
    for item in approved:
        if TRACKING in labels(item):
            subs = [s["number"] for s in sub_issues(repo, item["number"]) if is_open(s)]
            queue.append((min([item["number"], *subs]), item, True))
        elif item["number"] not in held:
            queue.append((item["number"], item, False))
    queue.sort(key=lambda entry: (entry[0], not entry[2]))

    found, plan, blocked = None, None, []
    for _, item, is_plan in queue:
        if is_plan:
            plan = summary(item)
            break
        open_blockers = blockers(repo, item["number"])
        if not open_blockers:
            found = summary(item)
            break
        blocked.append(dict(summary(item), blocked_by=open_blockers))

    def human():
        if found:
            print("#%d %s" % (found["number"], found["title"]))
        elif plan:
            print("#%d %s is an approved tracking issue." % (plan["number"], plan["title"]))
            print("To take its next sub-issue, run: %s next --tracking %d" % (PROG, plan["number"]))
        elif blocked:
            print("Every free approved issue is blocked by an open issue:")
            print_blocked(blocked)
        else:
            print("No approved issue is free.")

    data = {"issue": found, "blocked": blocked, "tracking": plan}
    return emit(args, "next", data, human=human)


def next_in_plan(args, repo, number):
    """`next --tracking N`: the first sub-issue of #N, in #N's order, to work."""
    item = issue(repo, number)
    data = {"issue": None, "blocked": [], "tracking": summary(item)}
    problems = []
    if not is_open(item):
        problems.append("#%d is closed; its plan is finished" % number)
    if TRACKING not in labels(item):
        problems.append(
            "#%d is not labeled %s; run %s next without --tracking" % (number, TRACKING, PROG)
        )
    if APPROVED not in labels(item):
        problems.append(
            "#%d is not labeled %s; ask the owner to approve the plan" % (number, APPROVED)
        )
    if problems:
        return emit(args, "next", data, problems)

    held = claims(repo)
    blocked = data["blocked"]
    for sub in sub_issues(repo, number):
        n = sub["number"]
        if not is_open(sub) or n in held:
            continue
        open_blockers = blockers(repo, n)
        if open_blockers:
            blocked.append(dict(summary(sub), blocked_by=open_blockers))
            continue
        if APPROVED not in labels(sub):
            return emit(
                args,
                "next",
                data,
                [
                    "#%d %s is next in #%d's order and is not labeled %s; "
                    "ask the owner to approve it" % (n, sub["title"], number, APPROVED)
                ],
            )
        data["issue"] = summary(sub)
        break

    def human():
        found = data["issue"]
        if found:
            print("#%d %s" % (found["number"], found["title"]))
        elif blocked:
            print("Every free sub-issue of #%d is blocked by an open issue:" % number)
            print_blocked(blocked)
        else:
            print("No sub-issue of #%d is free." % number)

    return emit(args, "next", data, human=human)


def print_blocked(blocked):
    for item in blocked:
        print(
            "#%d %s, blocked by %s"
            % (item["number"], item["title"], ", ".join("#%d" % n for n in item["blocked_by"]))
        )


def cmd_claim(args, repo):
    n = args.number
    data = {"number": n, "branch": branch(n), "claimed": False}
    item = issue(repo, n)
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
    if n in claims(repo):
        return emit(args, "claim", data, [held_message(n)])

    def human():
        verb = "Would claim" if args.dry_run else "Claimed"
        print("%s #%d on branch %s" % (verb, n, branch(n)))

    if args.dry_run:
        return emit(args, "claim", data, human=human)

    git(repo, "fetch", "--quiet", REMOTE, BASE)
    tip = git(repo, "rev-parse", "%s/%s" % (REMOTE, BASE)).stdout.strip()
    # The push is the lock. An empty lease ("ref:") refuses a branch that
    # exists at another commit, but a branch that already exists at this same
    # commit - two agents claiming off the same main - is "up to date" and
    # exits 0. So the claim is won only when porcelain output says this push
    # created the branch. --quiet would hide that line.
    push = git(
        repo,
        "push",
        "--porcelain",
        "--force-with-lease=%s:" % ref(n),
        REMOTE,
        "%s:%s" % (tip, ref(n)),
        check=False,
    )
    if not created(push.stdout, ref(n)):
        if n in claims(repo):
            return emit(args, "claim", data, [held_message(n)])
        raise Fatal("could not push %s: %s" % (branch(n), push.stderr.strip()))
    data["claimed"] = True

    warnings = []
    track = "%s/%s" % (REMOTE, branch(n))
    git(repo, "fetch", "--quiet", REMOTE, "%s:refs/remotes/%s" % (ref(n), track))
    switch = git(repo, "switch", "--quiet", "-c", branch(n), "--track", track, check=False)
    if switch.returncode != 0:
        warnings.append(
            "claimed, but could not switch to %s: %s" % (branch(n), switch.stderr.strip())
        )
    body = "%s `%s`. `issues.py release %d` gives it up." % (CLAIM_MARK, branch(n), n)
    for step, cmd in (
        ("add the %s label" % IN_PROGRESS, ["edit", str(n), "--add-label", IN_PROGRESS]),
        ("comment", ["comment", str(n), "--body", body]),
    ):
        try:
            gh(repo, "issue", *cmd)
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


def cmd_release(args, repo):
    n = args.number
    data = {"number": n, "branch": branch(n), "released": False}
    item = issue(repo, n)
    sha = claims(repo).get(n)
    labeled = IN_PROGRESS in labels(item)
    if sha is None and not labeled:
        return emit(args, "release", data, ["#%d is not claimed" % n])
    if sha is not None:
        git(repo, "fetch", "--quiet", REMOTE, BASE, ref(n))
        ahead = int(git(repo, "rev-list", "--count", "%s/%s..%s" % (REMOTE, BASE, sha)).stdout)
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
        delete = git(repo, "push", "--quiet", lease, REMOTE, ":" + ref(n), check=False)
        if delete.returncode != 0:
            return emit(
                args,
                "release",
                data,
                ["%s changed while releasing; run release again" % branch(n)],
            )
    if labeled:
        gh(repo, "issue", "edit", str(n), "--remove-label", IN_PROGRESS)
    gh(repo, "issue", "comment", str(n), "--body", "Released %s." % branch(n))
    data["released"] = True
    return emit(args, "release", data, human=human)


def cmd_clear(args, repo):
    n = args.number
    data = {
        "number": n,
        "branch": branch(n),
        "pull_request": None,
        "worktrees": [],
        "cleared": False,
    }
    item = issue(repo, n)
    if item.get("state") == "OPEN":
        return emit(
            args,
            "clear",
            data,
            ["#%d is still open. clear runs once its pull request has merged" % n],
        )
    local = git(repo, "rev-parse", "--verify", "--quiet", ref(n), check=False)
    if local.returncode != 0:
        return emit(args, "clear", data, ["there is no local %s to clear" % branch(n)])
    sha = local.stdout.strip()
    base = "%s/%s" % (REMOTE, BASE)
    git(repo, "fetch", "--quiet", REMOTE, BASE)
    data["pull_request"] = pull_holding(repo, merged_pulls(repo, branch(n)), sha)
    if data["pull_request"] is None and not in_base(repo, base, sha):
        return emit(
            args,
            "clear",
            data,
            [
                "%s holds commits no merged pull request from it has, and changes %s lacks. "
                "Merge or move them, or delete %s yourself; clear does not throw work away"
                % (branch(n), base, branch(n))
            ],
        )
    data["worktrees"] = checked_out(repo, ref(n))
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
    git(repo, "branch", "--quiet", "-D", branch(n))
    data["cleared"] = True
    return emit(args, "clear", data, human=human)


def merged_pulls(repo, *head):
    """Merged pull requests, as {number, headRefName, headRefOid}, from branch `head` if given."""
    args = ["pr", "list", "--state", "merged"]
    if head:
        args += ["--head", head[0]]
    return gh_json(repo, *args, "--limit", str(LIST_LIMIT), "--json", MERGED_FIELDS)


def pull_holding(repo, pulls, sha):
    """The number of the first of `pulls` whose head holds `sha`, or None.

    The head is the branch as it merged, so this holds however far main has
    moved since. A head this clone lacks is fetched from the pull request's ref.
    """
    for pull in pulls:
        head = pull["headRefOid"]
        if git(repo, "cat-file", "-e", head + "^{commit}", check=False).returncode != 0:
            git(repo, "fetch", "--quiet", REMOTE, "refs/pull/%d/head" % pull["number"], check=False)
        if git(repo, "merge-base", "--is-ancestor", sha, head, check=False).returncode == 0:
            return pull["number"]
    return None


def in_base(repo, base, sha):
    """Whether merging `sha` into `base` would leave base's tree as it is."""
    proc = git(repo, "merge-tree", "--write-tree", base, sha, check=False)
    if proc.returncode > 1:
        raise Fatal("`git merge-tree` failed: %s" % proc.stderr.strip())
    if proc.returncode == 1:  # conflicts: the branch changes what base has
        return False
    tree = git(repo, "rev-parse", base + "^{tree}").stdout.strip()
    return proc.stdout.split("\n", 1)[0].strip() == tree


def checked_out(repo, target):
    """The path of every worktree that has the branch `target` checked out."""
    out = git(repo, "worktree", "list", "--porcelain").stdout
    paths, path = [], None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree ") :]
        elif line == "branch " + target:
            paths.append(path)
    return paths


def cmd_sweep(args, repo):
    base = "%s/%s" % (REMOTE, BASE)
    git(repo, "fetch", "--quiet", REMOTE, BASE)
    out = git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/")
    local = [line.split(" ", 1) for line in out.stdout.splitlines() if line]
    on_origin = remote_branches(repo)
    worktrees = {}
    for line in git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree ") :]
        elif line.startswith("branch refs/heads/"):
            worktrees[line[len("branch refs/heads/") :]] = path
    pulls = {}
    for pull in merged_pulls(repo):
        pulls.setdefault(pull["headRefName"], []).append(pull)

    deleted, kept = [], []
    for name, sha in local:
        if name == BASE:
            continue
        if name in worktrees:
            reason = "checked out in %s" % worktrees[name]
        elif name in on_origin:
            reason = "still on %s, where someone may be working on it" % REMOTE
        elif pull_holding(repo, pulls.get(name, []), sha) is not None or in_base(repo, base, sha):
            deleted.append(name)
            continue
        else:
            reason = "holds work %s lacks" % base
        kept.append({"branch": name, "reason": reason})

    if not args.dry_run:
        for name in deleted:
            git(repo, "branch", "--quiet", "-D", name)

    def human():
        verb = "Would delete" if args.dry_run else "Deleted"
        for name in deleted:
            print("%s %s" % (verb, name))
        for k in kept:
            print("Kept %s: %s" % (k["branch"], k["reason"]))

    return emit(args, "sweep", {"deleted": deleted, "kept": kept}, human=human)


def remote_branches(repo):
    """The names of every branch on origin."""
    out = git(repo, "ls-remote", "--heads", REMOTE).stdout
    return {line.partition("\trefs/heads/")[2] for line in out.splitlines()}


def cmd_stale(args, repo):
    held = claims(repo)
    labeled = gh_json(
        repo,
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
    pulls = gh_json(
        repo, "pr", "list", "--state", "open", "--limit", str(LIST_LIMIT), "--json", "headRefName"
    )
    pr_branches = {p["headRefName"] for p in pulls}
    if held:
        git(repo, "fetch", "--quiet", REMOTE, *sorted(ref(n) for n in held))

    errors, rows = [], []
    for n in sorted(set(held) | {i["number"] for i in labeled}):
        row = {"number": n, "branch": branch(n), "pull_request": branch(n) in pr_branches}
        rows.append(row)
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
        item = issue(repo, n)
        if item.get("state") != "OPEN":
            errors.append("#%d is closed but %s still exists; run release %d" % (n, branch(n), n))
            continue
        if IN_PROGRESS not in labels(item):
            # claim warns and exits 0 when adding the label fails, so a held
            # issue can be left unlabeled however recent the claim.
            errors.append(
                "#%d has %s but is not labeled %s; run gh issue edit %d --add-label %s"
                % (n, branch(n), IN_PROGRESS, n, IN_PROGRESS)
            )
        if row["pull_request"]:
            continue
        last = parse_time(git(repo, "log", "-1", "--format=%cI", held[n]).stdout.strip())
        for c in item.get("comments", []):
            if CLAIM_MARK in (c.get("body") or ""):
                last = max(last, parse_time(c["createdAt"]))
        idle = (now() - last).days
        row["idle_days"] = idle
        if idle >= args.days:
            errors.append(
                "#%d: %s idle for %d days with no open pull request; ask its agent, or release %d"
                % (n, branch(n), idle, n)
            )

    def human():
        if not errors:
            print("No stale claims.")

    return emit(args, "stale", {"claims": rows}, errors, human=human)


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


def check_issue(index, item, known):
    """One issue of the plan as a row, or None, and the faults in it.

    `known` maps each of the repository's labels, in lower case, to its name.
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
    if not (
        isinstance(blocked_by, list)
        and all(
            isinstance(b, str) or (isinstance(b, int) and not isinstance(b, bool))
            for b in blocked_by
        )
    ):
        faults.append("%s's blocked_by is not a list of keys and issue numbers" % name)
        blocked_by = []
    deduped = []
    for b in blocked_by:
        if b not in deduped:
            deduped.append(b)
    row = {
        "key": key if not name.startswith("issue") else None,
        "name": name,
        "title": title if is_text(title) else "",
        "labels": [known.get(lbl.lower(), lbl) for lbl in labels],
        "body": body,
        "blocked_by": deduped,
    }
    return row, faults


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

    texts = [(r["name"] + "'s body", r["body"]) for r in rows]
    if tracking:
        texts.append(("the tracking issue's plan", tracking["plan"]))
    for where, text in texts:
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
        for _, _, ref in references(by_key[key]["body"]):
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


def cmd_plan_report(args, repo):
    raw, where, labels, rows, tracking, ledger, faults, warnings = checked(args, repo)
    numbers = {k: e["number"] for k, e in ledger["issues"].items()}
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
            {k: r[k] for k in ("key", "title", "labels", "body", "blocked_by")} for r in rows
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

    numbers = {k: e["number"] for k, e in ledger["issues"].items()}
    expected = {}

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
            entry = ledger["issues"].get(r["key"])
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
            entry = ledger["issues"].get(r["key"])
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


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(prog=PROG, description="Claim issues so agents do not collide.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("next", parents=[common], help="the oldest approved issue nobody holds")
    p.add_argument(
        "--tracking", type=int, metavar="N", help="take the next sub-issue of tracking issue N"
    )
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("claim", parents=[common], help="take an issue")
    p.add_argument("number", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser("release", parents=[common], help="give an issue up")
    p.add_argument("number", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("stale", parents=[common], help="claims nobody is working on")
    p.add_argument("--days", type=int, default=STALE_DAYS, help="idle days before a claim is stale")
    p.set_defaults(func=cmd_stale)

    p = sub.add_parser("clear", parents=[common], help="delete a merged claim's local branch")
    p.add_argument("number", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_clear)

    p = sub.add_parser(
        "sweep", parents=[common], help="delete local branches whose work is on main"
    )
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("plan", help="file a plan's issues under a tracking issue")
    plans = p.add_subparsers(dest="plan_command", required=True)
    drafts = argparse.ArgumentParser(add_help=False)
    drafts.add_argument("--drafts", required=True, metavar="FILE", help="the plan, as JSON")

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

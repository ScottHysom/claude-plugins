#!/usr/bin/env python3
"""Choose, claim, release and clear issues, so two agents never work on the same one.

It also sweeps away the local branches that finished work leaves behind.

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
    python3 .github/scripts/issues.py claim 12
    python3 .github/scripts/issues.py release 12 --reason "blocked on #9"
    python3 .github/scripts/issues.py stale
    python3 .github/scripts/issues.py clear 12
    python3 .github/scripts/issues.py sweep --dry-run

Commands:
    next        the oldest open approved issue nobody holds and no open issue
                blocks. Changes nothing.
    claim N     take issue N: push issue/N, switch to it, label and comment.
    release N   give issue N up: delete issue/N if it holds no work, remove the
                label, comment.
    stale       claims idle for --days with no open pull request, and labels
                and branches that disagree, including a closed issue that
                still has the label.
    clear N     once issue N is closed, delete the local issue/N if a merged
                pull request or main has everything on it, first moving any
                worktree on it to a detached origin/main.
    sweep       delete every local branch but main whose work is on main,
                and name each branch kept with the reason.

Every command takes --json and -C/--repo; claim, release, clear and sweep take
--dry-run.

Exit codes: 0 clean, 1 ran and found problems (the issue is held or not
approved, or still open, the branch holds work, a claim is stale), 2 could not
run.

Things that look like bugs and are not:
- `next` exits 0 when nothing is free, or when every free issue is blocked. An
  empty queue is not a problem. `claim` ignores blockers, so the owner can
  still name a blocked issue.
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

This script writes to git (a push, a branch switch, a branch deletion), so it
is not for Cowork's device bridge, where a git write strands `.git/*.lock`
files. A Cowork session asks the owner to claim for it.
"""

import argparse
import datetime
import json
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
BLOCKED_BY_PATH = "repos/{owner}/{repo}/issues/%d/dependencies/blocked_by"


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


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


def run(repo, cmd, check=True):
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    except OSError as exc:
        raise Fatal("cannot run %s: %s" % (cmd[0], exc)) from exc
    if check and proc.returncode != 0:
        raise Fatal("`%s` failed: %s" % (" ".join(cmd), proc.stderr.strip()))
    return proc


def git(repo, *args, check=True):
    return run(repo, ["git", *args], check)


def gh(repo, *args):
    """Run gh and return its stdout. Tests replace this."""
    return run(repo, ["gh", *args]).stdout


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


def now():
    """The current time. Tests replace this."""
    return datetime.datetime.now(datetime.timezone.utc)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_next(args, repo):
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
    free = sorted(
        (i for i in approved if IN_PROGRESS not in labels(i) and i["number"] not in held),
        key=lambda i: i["number"],
    )
    found = None
    blocked = []
    for item in free:
        open_blockers = blockers(repo, item["number"])
        if not open_blockers:
            found = {"number": item["number"], "title": item["title"]}
            break
        blocked.append(
            {"number": item["number"], "title": item["title"], "blocked_by": open_blockers}
        )

    def human():
        if found:
            print("#%d %s" % (found["number"], found["title"]))
        elif blocked:
            print("Every free approved issue is blocked by an open issue:")
            for item in blocked:
                print(
                    "#%d %s, blocked by %s"
                    % (
                        item["number"],
                        item["title"],
                        ", ".join("#%d" % n for n in item["blocked_by"]),
                    )
                )
        else:
            print("No approved issue is free.")

    return emit(args, "next", {"issue": found, "blocked": blocked}, human=human)


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
    body = "Released %s." % branch(n)
    if args.reason:
        body += " " + args.reason
    gh(repo, "issue", "comment", str(n), "--body", body)
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
            errors.append("#%d is closed but %s still exists" % (n, branch(n)))
            continue
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


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(prog=PROG, description="Claim issues so agents do not collide.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("next", parents=[common], help="the oldest approved issue nobody holds")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("claim", parents=[common], help="take an issue")
    p.add_argument("number", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser("release", parents=[common], help="give an issue up")
    p.add_argument("number", type=int)
    p.add_argument("--reason", default="", help="appended to the release comment")
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

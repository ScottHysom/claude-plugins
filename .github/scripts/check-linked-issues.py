#!/usr/bin/env python3
"""Fail a pull request that would close an issue Scott has not approved.

README.md, under "Issues", describes the process: an issue is worked on only
once Scott has added the `approved` label. Agents post as Scott, so nothing on
GitHub stops one from opening a pull request for an issue that was never
approved. This check does, for every surface agents run on, because it runs in
CI rather than in any one agent's hooks.

GitHub closes an issue when a pull request that names it with a closing keyword
merges into the default branch: "Closes #12", "fixes #12", "Resolves: #12". It
reads those from the pull request's title, its body, and its commit messages -
a squash merge carries the commit messages into the merged commit - so this
reads all three. A keyword inside a code span, a fenced block or an HTML comment
is not a link and is ignored, as GitHub ignores it.

A pull request that closes an issue must also come from that issue's claim
branch, `issue/<N>` in this repository, which `.github/scripts/issues.py claim`
makes. That is what stops an agent skipping the claim and colliding with
another. Any other issue it closes must not be claimed on a branch of its own.

A pull request that names no issue passes. Work Scott asks for directly needs
no issue.

Run by the validate workflow on pull_request events:

    python3 .github/scripts/check-linked-issues.py

It reads the event from $GITHUB_EVENT_PATH, the repository from
$GITHUB_REPOSITORY and a token from $GITHUB_TOKEN. When Scott approves an issue
after the pull request was opened, re-run the job.

Exit codes: 0 clean, 1 an issue is not approved or not claimed by this branch,
2 could not run.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

LABEL = "approved"
API = "https://api.github.com"
PER_PAGE = 100

# GitHub's closing keywords, an optional colon, then #N or owner/repo#N.
CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+"
    r"(?:(?P<repo>[\w.-]+/[\w.-]+))?#(?P<number>\d+)\b",
    re.I,
)
# The claim branch issues.py makes. Kept in step with BRANCH_PREFIX there.
CLAIM_BRANCH_RE = re.compile(r"^issue/(\d+)$")
# Text GitHub does not scan for links.
NOT_LINKED_RE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]*`|<!--.*?-->", re.S)


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


def linked_issues(text, repo):
    """Issue numbers in this repository that `text` would close, in order.

    A link to another repository is returned as (repo, number) so the caller
    can refuse it: approval here says nothing about an issue elsewhere.
    """
    text = NOT_LINKED_RE.sub(" ", text or "")
    ours, theirs = [], []
    for m in CLOSING_RE.finditer(text):
        other = m.group("repo")
        number = int(m.group("number"))
        if other and other.lower() != repo.lower():
            theirs.append((other, number))
        elif number not in ours:
            ours.append(number)
    return ours, theirs


def get(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer %s" % token,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise Fatal("GET %s failed: %s" % (url, exc)) from exc
    except (urllib.error.URLError, ValueError) as exc:
        raise Fatal("GET %s failed: %s" % (url, exc)) from exc


def commit_messages(repo, number, token, fetch):
    messages, page = [], 1
    while True:
        batch = fetch(
            "%s/repos/%s/pulls/%d/commits?per_page=%d&page=%d"
            % (API, repo, number, PER_PAGE, page),
            token,
        )
        if not batch:
            return messages
        messages.extend(c["commit"]["message"] for c in batch)
        if len(batch) < PER_PAGE:
            return messages
        page += 1


def problems(event, repo, token, fetch=get):
    """Every reason this pull request fails the check."""
    pr = event.get("pull_request")
    if not pr:
        raise Fatal("the event has no pull_request; run this on pull_request events")
    texts = [pr.get("title") or "", pr.get("body") or ""]
    texts.extend(commit_messages(repo, pr["number"], token, fetch))

    ours, theirs = [], []
    for text in texts:
        o, t = linked_issues(text, repo)
        ours.extend(n for n in o if n not in ours)
        theirs.extend(x for x in t if x not in theirs)

    out = []
    for other, number in theirs:
        out.append(
            "%s#%d is in another repository; this check cannot see whether it is approved"
            % (other, number)
        )
    for number in ours:
        issue = fetch("%s/repos/%s/issues/%d" % (API, repo, number), token)
        if issue is None:
            out.append("#%d does not exist" % number)
        elif "pull_request" in issue:
            out.append("#%d is a pull request, not an issue" % number)
        elif not any(lbl.get("name", "").lower() == LABEL for lbl in issue.get("labels", [])):
            out.append(
                "#%d is not labelled %s. Scott approves an issue before it is worked on; "
                "re-run this job once the label is added" % (number, LABEL)
            )
    out.extend(claim_problems(pr, ours, repo, token, fetch))
    return ours, out


def claim_problems(pr, ours, repo, token, fetch):
    """Reasons this pull request's branch is not the claim for what it closes."""
    if not ours:
        return []
    head = pr.get("head") or {}
    head_repo = (head.get("repo") or {}).get("full_name") or ""
    m = CLAIM_BRANCH_RE.match(head.get("ref") or "")
    claimed = int(m.group(1)) if m and head_repo.lower() == repo.lower() else None

    out = []
    if claimed not in ours:
        out.append(
            "this pull request closes %s from branch %s. Claim the issue with "
            "`.github/scripts/issues.py claim N` and open the pull request from the "
            "issue/N branch it makes"
            % (", ".join("#%d" % n for n in ours), head.get("label") or head.get("ref"))
        )
    for number in ours:
        if number == claimed:
            continue
        if fetch("%s/repos/%s/git/ref/heads/issue/%d" % (API, repo, number), token) is not None:
            out.append("#%d is claimed on its own branch, issue/%d" % (number, number))
    return out


def main(argv=None, environ=None, fetch=get):
    env = os.environ if environ is None else environ
    try:
        path, repo, token = (
            env.get(k) for k in ("GITHUB_EVENT_PATH", "GITHUB_REPOSITORY", "GITHUB_TOKEN")
        )
        if not (path and repo and token):
            raise Fatal("needs GITHUB_EVENT_PATH, GITHUB_REPOSITORY and GITHUB_TOKEN")
        try:
            with open(path, encoding="utf-8") as fh:
                event = json.load(fh)
        except (OSError, ValueError) as exc:
            raise Fatal("cannot read the event: %s" % exc) from exc
        linked, found = problems(event, repo, token, fetch)
    except Fatal as exc:
        sys.stderr.write("check-linked-issues.py: %s\n" % exc)
        return CANNOT_RUN

    if not linked and not found:
        print("No linked issues.")
        return OK
    for number in linked:
        print("#%d linked" % number)
    for p in found:
        sys.stderr.write("%s\n" % p)
    return PROBLEMS if found else OK


if __name__ == "__main__":
    sys.exit(main())

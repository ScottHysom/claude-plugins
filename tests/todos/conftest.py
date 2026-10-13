"""Shared fixtures for the todos.py suite.

The suite sits here, outside plugins/, because everything under plugins/<name>/
is copied verbatim into every install. README.md, under "Running the tests",
says why, and `.github/scripts/check-tests.py placement` fails the build if a
test moves back.

todos.py is a standalone script, not an installed package, so this file puts
the plugin's scripts directory on sys.path.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# tests/<plugin>/ mirrors plugins/<plugin>/scripts. A wrong depth would surface
# as `ModuleNotFoundError: No module named 'todos'` at collection, which reads
# as a missing dependency, so it is checked here instead.
PLUGIN, SCRIPT = "todos", "todos.py"
SCRIPTS = Path(__file__).resolve().parents[2] / "plugins" / PLUGIN / "scripts"
if not (SCRIPTS / SCRIPT).is_file():
    raise RuntimeError(
        "%s is not where %s lives. This file assumes tests/<plugin>/conftest.py, "
        "two directories below the repo root." % (SCRIPTS, SCRIPT)
    )
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import todos  # noqa: E402  - must follow the sys.path insert above

# Identity and signing on the command line, so a commit works whatever the
# machine's global git config says.
GIT_IDENTITY = [
    "-c",
    "user.name=test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
]


class TodoRepo:
    """A throwaway clone, and a way to run todos.py against it.

    Files are written as bytes, so a test controls every line ending.
    """

    def __init__(self, root, capsys):
        self.root = root
        self._capsys = capsys
        self.out = self.err = ""

    def git(self, *args):
        return subprocess.run(
            ["git", *GIT_IDENTITY, "-C", str(self.root), *args],
            check=True,
            capture_output=True,
        ).stdout

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        return path

    def commit(self, message="base"):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def head(self):
        return self.git("rev-parse", "HEAD").decode().strip()

    def run(self, *argv):
        """Run a todos.py command with --json. Returns (exit code, envelope).

        Driven through main() so the argparse defaults are the real ones. The
        envelope is None when nothing was printed; stderr is kept in self.err.
        """
        self._capsys.readouterr()
        code = todos.main([*argv, "-C", str(self.root), "--json"])
        captured = self._capsys.readouterr()
        self.out, self.err = captured.out, captured.err
        return code, json.loads(captured.out) if captured.out else None

    def human(self, *argv):
        """Run a command without --json. Returns (exit code, stdout, stderr)."""
        self._capsys.readouterr()
        code = todos.main([*argv, "-C", str(self.root)])
        captured = self._capsys.readouterr()
        return code, captured.out, captured.err

    def scan(self):
        """The TODOs scan reports, and its warnings."""
        code, env = self.run("scan")
        assert code == todos.OK, self.err
        return env["data"]["todos"], env["warnings"]

    @staticmethod
    def draft(todo, **fields):
        """A draft routing a TODO, as scan gave it, to an issue."""
        out = {
            "file": todo["file"],
            "line": todo["first"],
            "text": todo["text"],
            "route": "issue",
            "title": todo["title"],
            "body": todo["detail"],
            "labels": [],
        }
        out.update(fields)
        return out

    @staticmethod
    def comment(todo, issue, body="More detail.", **fields):
        """A draft routing a TODO, as scan gave it, to a comment on an issue."""
        out = {
            "file": todo["file"],
            "line": todo["first"],
            "text": todo["text"],
            "route": "comment",
            "issue": issue,
            "body": body,
        }
        out.update(fields)
        return out

    @staticmethod
    def skill(todo, skill="example:learn-prose-rules", **fields):
        """A draft routing a TODO, as scan gave it, to a skill."""
        out = {
            "file": todo["file"],
            "line": todo["first"],
            "text": todo["text"],
            "route": "skill",
            "skill": skill,
        }
        out.update(fields)
        return out

    def drafts(self, drafts):
        """Write drafts to a file outside the clone, and return its path."""
        path = self.root.parent / "drafts.json"
        path.write_text(json.dumps(drafts))
        return str(path)

    def draft_all(self):
        """A drafts file holding one draft for every pending TODO."""
        return self.drafts([self.draft(t) for t in self.scan()[0]])

    def token(self, drafts):
        """The token report prints for a drafts file, which must pass."""
        code, env = self.run("report", "--drafts", drafts)
        assert code == todos.OK, self.err
        return env["data"]["token"]

    def file(self, drafts, *extra):
        """Run file with the token report prints. Returns (exit code, envelope)."""
        return self.run("file", "--drafts", drafts, "--token", self.token(drafts), *extra)

    def read(self, rel):
        return (self.root / rel).read_bytes()


REPOSITORY = "owner/project"
REPOSITORY_URL = "https://github.com/" + REPOSITORY
LABELS = [
    {"name": "bug", "description": "Something is broken"},
    {"name": "enhancement", "description": "New behavior"},
    {"name": "plugin:todos", "description": ""},
]


class FakeGitHub:
    """gh, answering for one repository. Records every call.

    `fail` names the issue create and issue comment calls that fail, counting
    both from 1, and `printed` replaces what a successful one, or a reply,
    prints.
    `searches` maps a search's query to the issues it returns, and `existing`
    maps a number to the issue a lookup finds, as {number, title, state, url}.
    `pulls` maps a number to the pull request `gh pr view` finds, and
    `reviews` maps it to its review comments, as GitHub's REST API gives them,
    which GraphQL reads as threads. A comment with `pending` set is in the
    signed-in user's pending review, and `pending_reviews` maps a number to
    that review's Node ID. A reply joins its pull request's review comments,
    and `fail_replies` names the replies that fail, counting from 1, and
    `reply_gives` replaces the data a successful one gives. As GitHub does,
    a reply that does not name the pending review fails while there is one.
    """

    def __init__(self):
        self.repository = REPOSITORY
        self.labels = [dict(label) for label in LABELS]
        self.fail = ()
        self.printed = None
        self.searches = {}
        self.existing = {}
        self.pulls = {}
        self.reviews = {}
        self.pending_reviews = {}
        self.fail_replies = ()
        self.reply_gives = None
        self.replies = []
        self.calls = []
        self.queries = []
        self.issues = []
        self.comments = []

    def posts(self):
        return sum(1 for c in self.calls if c[:2] in (("issue", "create"), ("issue", "comment")))

    def __call__(self, root, *args, stdin=None):
        self.calls.append(args)
        if args[:2] == ("repo", "view"):
            url = "https://github.com/" + self.repository
            return json.dumps({"nameWithOwner": self.repository, "url": url})
        if args[:2] == ("label", "list"):
            return json.dumps(self.labels)
        if args[:2] == ("api", "graphql"):
            return self.graphql(json.loads(stdin)["query"])
        if args[:2] == ("pr", "view"):
            number = int(args[2])
            if number not in self.pulls:
                raise todos.GhFailed("`gh pr view` failed: no pull requests found")
            return json.dumps(self.pulls[number])
        if args[:2] == ("issue", "create"):
            if self.posts() in self.fail:
                raise todos.GhFailed("`gh issue create` failed: HTTP 502")
            number = len(self.issues) + 1
            labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
            self.issues.append(
                {
                    "title": args[args.index("--title") + 1],
                    "body": stdin,
                    "labels": labels,
                    "repo": args[args.index("--repo") + 1],
                }
            )
            if self.printed is not None:
                return self.printed
            return "Creating issue in %s\n\n%s/issues/%d\n" % (
                self.repository,
                "https://github.com/" + self.repository,
                number,
            )
        if args[:2] == ("issue", "comment"):
            if self.posts() in self.fail:
                raise todos.GhFailed("`gh issue comment` failed: HTTP 502")
            number = int(args[2])
            self.comments.append(
                {"issue": number, "body": stdin, "repo": args[args.index("--repo") + 1]}
            )
            if self.printed is not None:
                return self.printed
            return "%s/issues/%d#issuecomment-%d\n" % (
                "https://github.com/" + self.repository,
                number,
                100 + len(self.comments),
            )
        raise AssertionError("the fake gh does not answer %r" % (args,))

    def graphql(self, query):
        """Answer searches and issue lookups as GitHub does, with gh's exit 1
        and the data on stdout when an issue is not found."""
        self.queries.append(query)
        if "addPullRequestReviewThreadReply" in query:
            return self.reply(query)
        if "reviewThreads" in query:
            return self.threads(query)
        searches = re.findall(r'(s\d+): search\(query: ("(?:[^"\\]|\\.)*")', query)
        if searches:
            data = dict(
                (alias, {"nodes": self.searches.get(json.loads(q), [])}) for alias, q in searches
            )
            return json.dumps({"data": data})
        found, errors = {}, []
        for alias, number in re.findall(r"(i\d+): issue\(number: (\d+)\)", query):
            found[alias] = self.existing.get(int(number))
            if found[alias] is None:
                errors.append({"type": "NOT_FOUND", "path": ["repository", alias]})
        out = json.dumps(
            {"data": {"repository": found}, "errors": errors}
            if errors
            else {"data": {"repository": found}}
        )
        if errors:
            raise todos.GhFailed("`gh api graphql` failed: Could not resolve", out)
        return out

    def threads(self, query):
        """A page of a pull request's review threads, with its pending
        review, in the shape of GitHub's GraphQL API."""
        repository = "%s/%s" % tuple(
            json.loads(v) for v in re.findall(r'(?:owner|name): ("[^"]*")', query)
        )
        assert repository == self.repository
        number = int(re.search(r"pullRequest\(number: (\d+)\)", query).group(1))
        if number not in self.reviews:
            raise todos.GhFailed(
                "`gh api graphql` failed: Could not resolve to a PullRequest with the number of %d"
                % number
            )
        first, after = re.search(
            r"reviewThreads\(first: (\d+), after: (null|\"\d+\")\)", query
        ).groups()
        start = int(json.loads(after)) if after != "null" else 0
        comments = self.reviews[number]
        top = [c for c in comments if c.get("in_reply_to_id") is None]
        page = top[start : start + int(first)]
        nodes = []
        for head in page:
            thread = [head] + [c for c in comments if c.get("in_reply_to_id") == head["id"]]
            nodes.append(
                {
                    "id": "PRRT_%d" % head["id"],
                    "diffSide": head.get("side"),
                    "comments": {"nodes": [self.node(c) for c in thread]},
                }
            )
        end = start + len(page)
        pending = self.pending_reviews.get(number)
        pull = {
            "reviews": {"nodes": [{"id": pending}] if pending else []},
            "reviewThreads": {
                "pageInfo": {"hasNextPage": end < len(top), "endCursor": str(end)},
                "nodes": nodes,
            },
        }
        return json.dumps({"data": {"repository": {"pullRequest": pull}}})

    @staticmethod
    def node(c):
        commit = c.get("original_commit_id")
        return {
            "fullDatabaseId": str(c["id"]),
            "state": "PENDING" if c.get("pending") else "SUBMITTED",
            "body": c["body"],
            "path": c.get("path"),
            "originalLine": c.get("original_line"),
            "originalStartLine": c.get("original_start_line"),
            "originalCommit": {"oid": commit} if commit else None,
            "url": c["html_url"],
            "replyTo": None
            if c.get("in_reply_to_id") is None
            else {"fullDatabaseId": str(c["in_reply_to_id"])},
        }

    def reply(self, query):
        """A reply in a review thread, as addPullRequestReviewThreadReply
        makes it."""
        if len(self.replies) + 1 in self.fail_replies:
            raise todos.GhFailed("`gh api graphql` failed: HTTP 502")
        top = int(re.search(r'pullRequestReviewThreadId: "PRRT_(\d+)"', query).group(1))
        body = json.loads(re.search(r'body: ("(?:[^"\\]|\\.)*")', query).group(1))
        named = re.search(r'pullRequestReviewId: ("[^"]*")', query)
        review = json.loads(named.group(1)) if named else None
        number = next(n for n, cs in self.reviews.items() if any(c["id"] == top for c in cs))
        pending = self.pending_reviews.get(number)
        if pending is not None and review != pending:
            raise todos.GhFailed(
                "`gh api graphql` failed: user_id can only have one pending review per pull request"
            )
        made = {
            "id": 1000 + len(self.replies),
            "in_reply_to_id": top,
            "body": body,
            "pending": review is not None,
            "html_url": "%s/pull/%d#discussion_r%d"
            % (REPOSITORY_URL, number, 1000 + len(self.replies)),
        }
        self.replies.append(made)
        self.reviews[number].append(made)
        gives = {"addPullRequestReviewThreadReply": {"comment": {"url": made["html_url"]}}}
        return json.dumps({"data": gives if self.reply_gives is None else self.reply_gives})

    def add_pull(self, number, branch, comments=()):
        """A pull request from branch, holding review comments."""
        url = "https://github.com/%s/pull/%d" % (self.repository, number)
        self.pulls[number] = {"number": number, "url": url, "headRefName": branch}
        self.reviews[number] = list(comments)
        return self.pulls[number]

    def add_issue(self, number, title, state="OPEN"):
        """An issue a lookup finds."""
        url = "https://github.com/%s/issues/%d" % (self.repository, number)
        self.existing[number] = {"number": number, "title": title, "state": state, "url": url}
        return self.existing[number]


REAL_GH = todos.gh
GH_ON_PATH_TOOLS = ("git", "cat", "sleep")


@pytest.fixture(autouse=True)
def github(monkeypatch):
    """Every test talks to a fake gh, so none reaches GitHub."""
    fake = FakeGitHub()
    monkeypatch.setattr(todos, "gh", fake)
    return fake


@pytest.fixture
def gh_on_path(monkeypatch, tmp_path):
    """The script's own gh(), and a PATH holding git and a gh script.

    Call it with the body of a POSIX shell script, or None for a PATH with
    no gh on it.
    """
    monkeypatch.setattr(todos, "gh", REAL_GH)
    bin_dir = tmp_path / "gh-bin"
    bin_dir.mkdir()
    # git for the script, and the tools a gh script runs, each by a wrapper,
    # since the directory that holds them may hold gh too, as /usr/bin does
    # on GitHub's runners.
    for tool in GH_ON_PATH_TOOLS:
        (bin_dir / tool).write_text('#!/bin/sh\nexec "%s" "$@"\n' % shutil.which(tool))
        (bin_dir / tool).chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    def install(body):
        if body is not None:
            (bin_dir / "gh").write_text("#!/bin/sh\n" + body)
            (bin_dir / "gh").chmod(0o755)

    return install


def init(root):
    root.mkdir(parents=True, exist_ok=True)
    # capture_output so git's default-branch hint stays out of the CI log.
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)


def committed(root):
    """Build the repository the repo fixture starts from."""
    init(root)
    r = TodoRepo(root, None)
    r.write("README.md", "# Probe\n")
    r.commit()


@pytest.fixture
def repo(tmp_path, capsys, repo_copy):
    """A clone holding one commit, with nothing pending."""
    return TodoRepo(repo_copy(committed, tmp_path / "repo"), capsys)


@pytest.fixture
def bare_repo(tmp_path, capsys, git_init):
    """A clone with no commit yet."""
    return TodoRepo(git_init(tmp_path / "repo"), capsys)


# The branch the worktree fixture checks out.
WORKTREE_BRANCH = "review"


@pytest.fixture
def worktree(repo, tmp_path, capsys):
    """A second worktree of the repo, on WORKTREE_BRANCH, with nothing pending."""
    root = tmp_path / "other"
    repo.git("worktree", "add", "-q", "-b", WORKTREE_BRANCH, str(root))
    return TodoRepo(root, capsys)


@pytest.fixture
def todo_repo(capsys):
    """A TodoRepo for a working tree a test made some other way."""
    return lambda root: TodoRepo(root, capsys)


@pytest.fixture
def no_git(monkeypatch, tmp_path):
    """A PATH on which git cannot be found."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    return empty


@pytest.fixture
def script_path():
    return os.path.join(str(SCRIPTS), SCRIPT)

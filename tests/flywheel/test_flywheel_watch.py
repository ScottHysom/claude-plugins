"""`watch`: how a dispatcher learns that a pull request of its round changed.

GitHub is faked: `Hub` answers the REST reads with an ETag per path, as GitHub
does, and the fixture replaces the GraphQL thread read and `assess`.
"""

import json
import subprocess

import pytest

import flywheel

PULLS = "repos/{owner}/{repo}/pulls?state=open&per_page=100"


class Hub:
    """The REST reads `watch` makes, each answered with an ETag or a 304."""

    def __init__(self):
        self.bodies = {}
        self.versions = {}
        self.calls = []
        self.threads = {}
        self.thread_reads = []
        self.pulls = {}
        self.branches = {}
        self.list_pulls()

    def put(self, path, body):
        self.bodies[path] = body
        self.versions[path] = self.versions.get(path, 0) + 1

    def pull(self, number, branch, sha="a" * 40, checks=(), reviews=(), threads=()):
        self.pulls[number] = (branch, sha)
        self.branches[number] = branch
        self.threads[number] = list(threads)
        self.put(
            "repos/{owner}/{repo}/commits/%s/check-runs?per_page=100" % sha,
            {"check_runs": list(checks)},
        )
        self.put("repos/{owner}/{repo}/commits/%s/status" % sha, {"statuses": []})
        self.put("repos/{owner}/{repo}/pulls/%d/reviews?per_page=100" % number, list(reviews))
        self.put("repos/{owner}/{repo}/pulls/%d/comments?per_page=100" % number, [])
        self.list_pulls()

    def list_pulls(self):
        self.put(
            PULLS,
            [
                {"number": n, "head": {"ref": branch, "sha": sha}}
                for n, (branch, sha) in sorted(self.pulls.items())
            ],
        )

    def close(self, number):
        del self.pulls[number]
        self.list_pulls()

    def api_get(self, root, path, etag=None):
        self.calls.append((path, etag))
        tag = '"%d"' % self.versions[path]
        if etag == tag:
            return flywheel.NOT_MODIFIED, etag, None
        return 200, tag, self.bodies[path]

    def review_threads(self, root, number):
        self.thread_reads.append(number)
        return [
            {"id": tid, "resolved": resolved, "comments": [{}] * count}
            for tid, resolved, count in self.threads[number]
        ]


def run_of(name, conclusion="success", status="completed"):
    return {"name": name, "status": status, "conclusion": conclusion, "started_at": "t"}


@pytest.fixture
def hub(monkeypatch):
    found = Hub()
    found.sleeps = []
    found.on_sleep = lambda n: None
    found.merged = {}

    def sleep(seconds):
        found.sleeps.append(seconds)
        found.on_sleep(len(found.sleeps))

    def fake_gh(root, *args):
        if args[:2] == ("pr", "list") and args[args.index("--state") + 1] == "merged":
            return "[]"
        if args[:2] == ("pr", "list"):
            return json.dumps(
                [
                    {
                        "number": n,
                        "title": "pull %d" % n,
                        "url": "https://github.com/owner/project/pull/%d" % n,
                        "headRefName": branch,
                        "statusCheckRollup": [],
                        "reviewDecision": "",
                    }
                    for n, (branch, _) in sorted(found.pulls.items())
                ]
            )
        if args[:2] == ("pr", "view"):
            number = int(args[2])
            return json.dumps(
                {
                    "number": number,
                    "title": "pull %d" % number,
                    "url": "https://github.com/owner/project/pull/%d" % number,
                    "headRefName": found.branches[number],
                    "state": "MERGED" if number in found.merged else "CLOSED",
                    "mergedAt": found.merged.get(number),
                }
            )
        if args[0] == "api" and "/sub_issues" in args[1]:
            return json.dumps([{"number": 12, "state": "open"}])
        raise AssertionError("unexpected gh %r" % (args,))

    monkeypatch.setattr(flywheel, "gh", fake_gh)
    monkeypatch.setattr(flywheel, "api_get", found.api_get)
    monkeypatch.setattr(flywheel, "review_threads", found.review_threads)
    monkeypatch.setattr(flywheel, "sleep", sleep)
    monkeypatch.setattr(
        flywheel,
        "assess",
        lambda root, number: {
            "head": "abc1234",
            "verdict": "hold",
            "next": "wait",
            "reasons": [],
            "only_running_check": False,
        },
    )
    return found


def state_of(project):
    return project.run("events")[1]["data"]["state"]


@pytest.mark.spec("watch-cmd-exits-on-change")
class DescribeWatch:
    def it_exits_at_once_when_the_state_has_already_changed(self, project, hub):
        hub.pull(31, "issue/12", checks=[run_of("validate", status="in_progress", conclusion=None)])
        state = state_of(project)
        hub.pull(31, "issue/12", checks=[run_of("validate")])
        code, env = project.run("watch", "--state", state)
        assert code == flywheel.OK
        assert hub.sleeps == []
        assert env["data"]["changed"] == [31]
        assert [r["number"] for r in env["data"]["open"]] == [31]
        assert env["data"]["open"][0]["next"] == "wait"
        assert env["data"]["state"] != state

    def it_reads_again_after_waiting_until_a_head_changes(self, project, hub):
        hub.pull(31, "issue/12")
        state = state_of(project)

        def push(n):
            if n == 2:
                hub.pull(31, "issue/12", sha="b" * 40)

        hub.on_sleep = push
        code, env = project.run("watch", "--state", state)
        assert code == flywheel.OK
        assert len(hub.sleeps) == 2
        assert all(0 < s <= flywheel.WATCH_INTERVAL for s in hub.sleeps)
        assert env["data"]["changed"] == [31]

    def it_starts_from_the_state_it_finds_when_given_none(self, project, hub):
        hub.pull(31, "issue/12")

        def finish(n):
            if n == 1:
                hub.pull(31, "issue/12", checks=[run_of("validate")])

        hub.on_sleep = finish
        code, env = project.run("watch")
        assert code == flywheel.OK
        assert len(hub.sleeps) == 1
        assert env["data"]["changed"] == [31]

    @pytest.mark.parametrize(
        "change",
        [
            lambda h: h.pull(31, "issue/12", checks=[run_of("validate", conclusion="failure")]),
            lambda h: h.pull(31, "issue/12", reviews=[{"id": 1, "state": "COMMENTED"}]),
            lambda h: h.pull(31, "issue/12", threads=[("t1", False, 1)]),
        ],
        ids=["ci", "review", "thread"],
    )
    def it_exits_when_ci_a_review_or_a_thread_changes(self, project, hub, change):
        hub.pull(31, "issue/12")
        state = state_of(project)
        change(hub)
        code, env = project.run("watch", "--state", state)
        assert code == flywheel.OK
        assert env["data"]["changed"] == [31]

    def it_names_a_pull_request_that_opened_since_the_state(self, project, hub):
        state = state_of(project)
        hub.pull(33, "issue/14")
        _, env = project.run("watch", "--state", state)
        assert env["data"]["changed"] == [33]
        assert env["data"]["open"][0]["issue"] == 14

    def it_prints_a_merged_pull_request_with_its_merge_time(self, project, hub):
        hub.pull(31, "issue/12")
        state = state_of(project)
        hub.close(31)
        hub.merged[31] = "2026-10-29T21:00:00Z"
        _, env = project.run("watch", "--state", state)
        assert env["data"]["open"] == []
        assert env["data"]["merged"] == [
            {
                "number": 31,
                "issue": 12,
                "branch": "issue/12",
                "title": "pull 31",
                "url": "https://github.com/owner/project/pull/31",
                "merged_at": "2026-10-29T21:00:00Z",
            }
        ]
        code, out, _ = project.human("watch", "--state", state)
        assert "merged #31 issue/12 at 2026-10-29T21:00:00Z" in out

    def it_prints_a_pull_request_closed_without_a_merge(self, project, hub):
        hub.pull(31, "issue/12")
        state = state_of(project)
        hub.close(31)
        _, env = project.run("watch", "--state", state)
        assert env["data"]["merged"] == []
        assert [r["number"] for r in env["data"]["closed"]] == [31]
        _, out, _ = project.human("watch", "--state", state)
        assert out == "closed #31 issue/12\n"

    def it_does_not_wake_for_a_check_that_only_progresses(self, project, hub):
        hub.pull(31, "issue/12", checks=[run_of("validate", status="queued", conclusion=None)])
        state = state_of(project)

        def progress(n):
            if n == 1:
                hub.pull(
                    31,
                    "issue/12",
                    checks=[run_of("validate", status="in_progress", conclusion=None)],
                )
            if n == 2:
                hub.pull(31, "issue/12", checks=[run_of("validate")])

        hub.on_sleep = progress
        _, env = project.run("watch", "--state", state)
        assert len(hub.sleeps) == 2
        assert env["data"]["changed"] == [31]

    def it_leaves_out_pull_requests_of_other_rounds(self, project, hub):
        hub.pull(31, "issue/12")
        hub.pull(32, "issue/13")
        hub.pull(34, "feature/x")
        state = project.run("events", "--issue", "12")[1]["data"]["state"]
        assert state.startswith("31:")
        assert "32:" not in state

        def other(n):
            if n == 1:
                hub.pull(32, "issue/13", sha="c" * 40)
                hub.pull(34, "feature/x", sha="d" * 40)
            if n == 2:
                hub.pull(31, "issue/12", sha="b" * 40)

        hub.on_sleep = other
        _, env = project.run("watch", "--issue", "12", "--state", state)
        assert env["data"]["changed"] == [31]

    def it_takes_a_plan_as_events_does(self, project, hub):
        hub.pull(31, "issue/12")
        hub.pull(32, "issue/13")
        _, env = project.run("watch", "--plan", "9", "--state", "")
        assert env["data"]["changed"] == [31]

    def it_sends_the_etag_of_each_answer_back_on_the_next_read(self, project, hub):
        hub.pull(31, "issue/12")
        state = state_of(project)
        hub.calls.clear()

        def push(n):
            if n == 2:
                hub.pull(31, "issue/12", sha="b" * 40)

        hub.on_sleep = push
        project.run("watch", "--state", state)
        first, second = hub.calls[:5], hub.calls[5:10]
        assert [e for _, e in first] == [None] * 5
        assert all(e is not None for _, e in second)

    def it_reads_threads_again_only_when_a_review_or_comment_changed_or_on_the_backstop(
        self, project, hub
    ):
        hub.pull(31, "issue/12")
        state = state_of(project)
        hub.thread_reads.clear()

        def quiet(n):
            if n == flywheel.THREADS_BACKSTOP + 1:
                hub.pull(31, "issue/12", threads=[("t1", True, 1)])

        hub.on_sleep = quiet
        _, env = project.run("watch", "--state", state)
        assert env["data"]["changed"] == [31]
        # One read to learn the threads, none while the REST answers did not change,
        # and one on the backstop that found the resolved thread.
        assert len(hub.thread_reads) <= 3

    def it_finds_a_thread_resolved_on_the_backstop_when_no_REST_answer_changed(self, project, hub):
        hub.pull(31, "issue/12", threads=[("t1", False, 1)])
        state = state_of(project)

        def resolve(n):
            assert n <= flywheel.THREADS_BACKSTOP + 2, "the backstop never read the threads"
            if n == 1:
                hub.threads[31] = [("t1", True, 1)]

        hub.on_sleep = resolve
        _, env = project.run("watch", "--state", state)
        assert env["data"]["changed"] == [31]
        assert len(hub.sleeps) >= flywheel.THREADS_BACKSTOP - 1

    def it_refuses_a_state_it_cannot_read(self, project, hub):
        code, _, err = project.human("watch", "--state", "31")
        assert code == flywheel.CANNOT_RUN
        assert "is not a state" in err


class DescribeEventsState:
    @pytest.mark.spec("events-cmd-lists-claim-prs")
    def it_goes_on_with_a_null_state_when_a_state_read_fails(self, project, hub, monkeypatch):
        hub.pull(31, "issue/12")

        def fail(root, path, etag=None):
            raise flywheel.Fatal("`gh api %s` failed: HTTP 502" % path)

        monkeypatch.setattr(flywheel, "api_get", fail)
        code, env = project.run("events")
        assert code == flywheel.OK
        assert env["data"]["state"] is None
        assert [r["number"] for r in env["data"]["open"]] == [31]
        assert "could not read the state" in env["warnings"][0]

    @pytest.mark.spec("events-cmd-lists-claim-prs")
    def it_gives_the_state_a_watch_starts_from(self, project, hub):
        hub.pull(31, "issue/12")
        hub.pull(30, "issue/9")
        state = state_of(project)
        numbers = [part.split(":")[0] for part in state.split(",")]
        assert numbers == ["30", "31"]
        assert state_of(project) == state


@pytest.mark.spec("watch-cmd-exits-on-change")
def it_waits_by_sleeping(monkeypatch):
    slept = []
    monkeypatch.setattr(flywheel.time, "sleep", slept.append)
    flywheel.sleep(2.5)
    assert slept == [2.5]


@pytest.mark.spec("watch-cmd-exits-on-change")
class DescribeApiGet:
    def reply(self, monkeypatch, stdout, stderr="", code=0):
        def fake(root, cmd, check=True, stdin=None):
            self.cmd = cmd
            return subprocess.CompletedProcess(cmd, code, stdout, stderr)

        monkeypatch.setattr(flywheel, "run", fake)

    def it_returns_the_status_etag_and_body(self, monkeypatch):
        self.reply(monkeypatch, 'HTTP/2.0 200 OK\nETag: "abc"\r\nX: y\r\n\r\n[1, 2]')
        assert flywheel.api_get("/", "p") == (200, '"abc"', [1, 2])
        assert "If-None-Match" not in " ".join(self.cmd)

    def it_sends_the_etag_and_reads_a_304_though_gh_exits_1(self, monkeypatch):
        self.reply(monkeypatch, 'HTTP/2.0 304 Not Modified\nETag: "abc"\r\n\r\n', "gh: HTTP 304", 1)
        assert flywheel.api_get("/", "p", '"abc"') == (304, '"abc"', None)
        assert 'If-None-Match: "abc"' in self.cmd

    def it_names_the_failure_when_gh_prints_no_response(self, monkeypatch):
        self.reply(monkeypatch, "", "gh: not logged in", 4)
        with pytest.raises(flywheel.Fatal, match="not logged in"):
            flywheel.api_get("/", "p")

    def it_names_an_http_error(self, monkeypatch):
        self.reply(monkeypatch, "HTTP/2.0 404 Not Found\r\n\r\n{}", "gh: HTTP 404", 1)
        with pytest.raises(flywheel.Fatal, match="HTTP 404"):
            flywheel.api_get("/", "p")

    def it_refuses_a_body_that_is_not_json(self, monkeypatch):
        self.reply(monkeypatch, "HTTP/2.0 200 OK\r\nETag: x\r\n\r\nnot json")
        with pytest.raises(flywheel.Fatal, match="did not return JSON"):
            flywheel.api_get("/", "p")

    def it_accepts_an_answer_without_an_etag(self, monkeypatch):
        self.reply(monkeypatch, "HTTP/2.0 200 OK\r\n\r\n{}")
        assert flywheel.api_get("/", "p") == (200, None, {})

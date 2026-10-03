"""What `todos.py report` shows the author, and the drafts it refuses."""

import pytest

import todos


@pytest.fixture
def two(repo):
    """A clone with two pending TODOs in run.py, and one warning."""
    repo.write("run.py", "def run():\n    pass\n")
    repo.commit()
    repo.write(
        "run.py",
        "# TODO(bug): run hangs\n# no timeout\ndef run():\n    pass\n# TODO: tidy up\n"
        "x = 1  # TODO: trailing\n",
    )
    return repo


@pytest.mark.spec("report-cmd-names-target-repo")
class DescribeTheTargetRepository:
    def it_names_the_repository_gh_resolves(self, two, github):
        github.repository = "someone/fork"
        code, env = two.run("report", "--drafts", two.draft_all())
        assert code == todos.OK
        assert env["data"]["repository"] == "someone/fork"
        assert github.calls[0] == ("repo", "view", "--json", "nameWithOwner,url")

    def it_opens_the_text_report_with_it(self, two):
        code, out, _ = two.human("report", "--drafts", two.draft_all())
        assert code == todos.OK
        assert out.startswith("Filing in owner/project (https://github.com/owner/project).\n")


@pytest.mark.spec("report-cmd-shows-each-draft")
class DescribeEachDraft:
    def it_prints_the_draft_whole(self, two):
        found, _ = two.scan()
        drafts = two.drafts(
            [
                two.draft(
                    found[0], title="run() hangs", body="No timeout.\n\nAt all.", labels=["bug"]
                )
            ]
        )
        code, out, _ = two.human("report", "--drafts", drafts)
        assert code == todos.OK
        assert (
            "draft 1  run.py:1-2  issue\n"
            "  title   run() hangs\n"
            "  labels  bug\n"
            "  body\n"
            "    | No timeout.\n"
            "    |\n"
            "    | At all.\n"
            "\n"
            "1 draft(s).\n"
        ) in out

    def it_says_when_a_draft_has_no_labels(self, two):
        code, out, _ = two.human("report", "--drafts", two.draft_all())
        assert code == todos.OK
        assert "  labels  (none)\n" in out

    def it_gives_each_draft_in_json(self, two):
        found, _ = two.scan()
        drafts = two.drafts([two.draft(found[1], body="b", labels=["bug", "plugin:todos"])])
        _, env = two.run("report", "--drafts", drafts)
        assert env["data"]["drafts"] == [
            {
                "draft": 1,
                "file": "run.py",
                "first": 5,
                "last": 5,
                "route": "issue",
                "title": "tidy up",
                "body": "b",
                "labels": ["bug", "plugin:todos"],
            }
        ]


@pytest.mark.spec("report-cmd-lists-undrafted-todos")
class DescribeTodosLeftInPlace:
    def it_lists_a_todo_without_a_draft(self, two):
        found, _ = two.scan()
        drafts = two.drafts([two.draft(found[0])])
        code, out, _ = two.human("report", "--drafts", drafts)
        assert code == todos.OK
        assert "\nLeft in place, with no draft:\n  run.py:5  tidy up\n" in out
        _, env = two.run("report", "--drafts", drafts)
        assert [(t["file"], t["first"]) for t in env["data"]["left"]] == [("run.py", 5)]

    def it_lists_every_todo_when_there_are_no_drafts(self, two):
        _, env = two.run("report", "--drafts", two.drafts([]))
        assert [t["first"] for t in env["data"]["left"]] == [1, 5]


@pytest.mark.spec("report-cmd-lists-scan-warnings")
class DescribeScanWarnings:
    def it_lists_each_warning_with_its_file_and_line(self, two):
        code, out, err = two.human("report", "--drafts", two.draft_all())
        assert code == todos.OK
        assert "\nWarnings from scan:\n  run.py:6: a TODO is read only at the start" in out
        assert err == ""

    def it_leaves_the_heading_out_when_scan_gives_none(self, repo):
        repo.write("a.py", "# TODO: one\n")
        code, out, _ = repo.human("report", "--drafts", repo.draft_all())
        assert code == todos.OK
        assert "Warnings from scan" not in out


@pytest.mark.spec("report-cmd-prints-approval-token")
class DescribeTheToken:
    def it_ends_the_report_with_the_token(self, two):
        drafts = two.draft_all()
        code, out, _ = two.human("report", "--drafts", drafts)
        assert code == todos.OK
        last = out.rstrip("\n").split("\n")[-1]
        assert last == todos.TOKEN_LABEL + two.token(drafts)
        assert len(two.token(drafts)) == todos.TOKEN_LENGTH

    def it_prints_none_when_a_draft_is_refused(self, two):
        found, _ = two.scan()
        drafts = two.drafts([two.draft(found[0], labels=["nonsense"])])
        code, out, _ = two.human("report", "--drafts", drafts)
        assert code == todos.PROBLEMS
        assert todos.TOKEN_LABEL not in out
        _, env = two.run("report", "--drafts", drafts)
        assert env["data"]["token"] is None

    def it_changes_when_a_named_file_changes(self, two):
        drafts = two.draft_all()
        before = two.token(drafts)
        two.write("run.py", two.read("run.py") + b"y = 2\n")
        assert two.token(drafts) != before

    def it_changes_when_the_repository_changes(self, two, github):
        drafts = two.draft_all()
        before = two.token(drafts)
        github.repository = "someone/fork"
        assert two.token(drafts) != before

    def it_changes_when_the_last_commit_changes(self, two):
        drafts = two.draft_all()
        before = two.token(drafts)
        two.write("other.txt", "x\n")
        two.git("add", "other.txt")
        two.git("commit", "-q", "-m", "other", "--", "other.txt")
        assert two.token(drafts) != before


@pytest.mark.spec("report-cmd-stops-on-unreadable-drafts", "repo:script-exits-2-when-unrunnable")
class DescribeUnreadableDrafts:
    @pytest.mark.parametrize("command", [("report",), ("file", "--token", "x")])
    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_stops_when_the_file_is_missing(self, repo, tmp_path, command):
        missing = str(tmp_path / "missing.json")
        code, env = repo.run(*command, "--drafts", missing)
        assert (code, env) == (todos.CANNOT_RUN, None)
        assert "cannot read the drafts in %s" % missing in repo.err
        assert "Write them there, then run again." in repo.err

    @pytest.mark.parametrize("command", [("report",), ("file", "--token", "x")])
    def it_stops_when_the_file_is_not_json(self, repo, tmp_path, command):
        path = tmp_path / "drafts.json"
        path.write_text("[{")
        code, env = repo.run(*command, "--drafts", str(path))
        assert (code, env) == (todos.CANNOT_RUN, None)
        assert "%s is not JSON" % path in repo.err

    def it_stops_when_the_file_is_not_utf8(self, repo, tmp_path):
        path = tmp_path / "drafts.json"
        path.write_bytes(b'["\xff"]')
        code, _ = repo.run("report", "--drafts", str(path))
        assert code == todos.CANNOT_RUN
        assert "is not JSON" in repo.err

    def it_stops_when_the_json_is_not_an_array(self, repo, tmp_path):
        path = tmp_path / "drafts.json"
        path.write_text('{"file": "a.py"}')
        code, _ = repo.run("report", "--drafts", str(path))
        assert code == todos.CANNOT_RUN
        assert "holds JSON, but not an array of drafts" in repo.err


@pytest.mark.spec("repo:script-checks-every-answer")
class DescribeRefusals:
    def refused(self, repo, drafts):
        code, env = repo.run("report", "--drafts", repo.drafts(drafts))
        assert code == todos.PROBLEMS
        assert env["data"]["token"] is None
        return env["errors"]

    @pytest.mark.spec("report-cmd-refuses-stale-drafts")
    def it_refuses_a_draft_whose_line_holds_no_todo(self, two):
        found, _ = two.scan()
        errors = self.refused(two, [two.draft(found[0]), two.draft(found[1], line=3)])
        assert errors == [
            'draft 2: run.py:3 does not hold a pending TODO whose first line is "# TODO: tidy'
            ' up". Run scan again and redraft it'
        ]

    @pytest.mark.spec("report-cmd-refuses-stale-drafts")
    def it_refuses_a_draft_whose_text_has_changed(self, two):
        found, _ = two.scan()
        drafts = two.drafts([two.draft(found[1])])
        two.write("run.py", two.read("run.py").replace(b"tidy up", b"tidy it up"))
        code, env = two.run("report", "--drafts", drafts)
        assert code == todos.PROBLEMS
        assert env["errors"][0].startswith("draft 1: run.py:5 does not hold a pending TODO")

    @pytest.mark.spec("report-cmd-refuses-stale-drafts")
    def it_refuses_a_todo_committed_since(self, two):
        drafts = two.draft_all()
        two.commit()
        code, env = two.run("report", "--drafts", drafts)
        assert code == todos.PROBLEMS
        assert len(env["errors"]) == 2

    @pytest.mark.spec("report-cmd-refuses-repeated-todos")
    def it_refuses_both_drafts_of_one_todo(self, two):
        found, _ = two.scan()
        drafts = [two.draft(found[0]), two.draft(found[1]), two.draft(found[0], title="again")]
        code, env = two.run("report", "--drafts", two.drafts(drafts))
        assert code == todos.PROBLEMS
        assert env["errors"] == ["drafts 1, 3 name one TODO, run.py:1. Keep one of them"]
        assert [d["draft"] for d in env["data"]["drafts"]] == [2]

    @pytest.mark.spec("report-cmd-refuses-unknown-labels")
    def it_refuses_a_label_the_repository_lacks(self, two):
        found, _ = two.scan()
        errors = self.refused(two, [two.draft(found[0], labels=["bug", "Bug"])])
        assert errors == [
            "draft 1 names the label `Bug`, which owner/project does not have. Use one scan lists"
        ]

    @pytest.mark.spec("report-cmd-refuses-approved-label")
    @pytest.mark.parametrize("label", ["approved", "Approved", "APPROVED"])
    def it_refuses_the_owners_label_in_any_case(self, two, github, label):
        github.labels.append({"name": label, "description": "Only the owner adds this"})
        found, _ = two.scan()
        errors = self.refused(two, [two.draft(found[0], labels=[label])])
        assert errors == [
            "draft 1 carries the label `%s`, which only the owner adds. Take it off" % label
        ]

    def it_refuses_a_draft_that_is_not_an_object(self, two):
        assert self.refused(two, ["run.py:1"]) == ["draft 1 is not a JSON object"]

    @pytest.mark.parametrize("route", [None, "Comment", 3])
    def it_refuses_a_route_it_does_not_know(self, two, route):
        found, _ = two.scan()
        draft = two.draft(found[0], route=route)
        if route is None:
            del draft["route"]
        (error,) = self.refused(two, [draft])
        assert error.startswith("draft 1 has route ")
        assert error.endswith("and the routes are `issue` and `comment`")

    def it_names_each_missing_and_unknown_key(self, two):
        found, _ = two.scan()
        draft = two.draft(found[0], label="bug")
        del draft["labels"], draft["body"]
        assert self.refused(two, [draft]) == [
            "draft 1 lacks `body`",
            "draft 1 lacks `labels`",
            "draft 1 has `label`, which a draft does not take",
        ]

    @pytest.mark.parametrize(
        ("field", "value", "reason"),
        [
            ("line", "1", "has a `line` that is not a line number"),
            ("line", True, "has a `line` that is not a line number"),
            ("line", 0, "has a `line` that is not a line number"),
            ("file", 1, "has a `file` that is not a string"),
            ("text", None, "has a `text` that is not a string"),
            ("body", [], "has a `body` that is not a string"),
            ("title", "  ", "has a `title` that is not a string with words in it"),
            ("title", 5, "has a `title` that is not a string with words in it"),
            ("labels", "bug", "has `labels` that are not an array of strings"),
            ("labels", ["bug", 1], "has `labels` that are not an array of strings"),
        ],
    )
    def it_names_a_field_of_the_wrong_kind(self, two, field, value, reason):
        found, _ = two.scan()
        assert self.refused(two, [two.draft(found[0], **{field: value})]) == ["draft 1 " + reason]

    def it_checks_every_draft_before_it_stops(self, two):
        found, _ = two.scan()
        errors = self.refused(two, [two.draft(found[0], title=""), two.draft(found[1], line=2)])
        assert [e.split(" ")[1] for e in errors] == ["1", "2:"]

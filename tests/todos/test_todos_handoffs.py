"""What `todos.py` does with a draft routed to a skill: how report shows it,
and the hand-off file prints once its TODO is gone."""

import pytest

import todos

PROSE = "example:learn-prose-rules"
OTHER = "example:other-skill"
BASE = "# Title\n\nFirst line.\nSecond line.\n\nLast paragraph.\n"


@pytest.fixture
def doc(repo):
    """A clone whose README.md has a committed paragraph at lines 3-4."""
    repo.write("README.md", BASE)
    repo.commit()
    return repo


def handoffs(repo, drafts, *extra):
    code, env = repo.file(repo.drafts(drafts), *extra)
    assert code == todos.OK, repo.err
    return env["data"]["handoffs"]


@pytest.mark.spec("report-cmd-shows-each-draft")
class DescribeTheReport:
    def it_prints_the_skill_with_the_todos_title_and_detail(self, doc):
        doc.write(
            "README.md", BASE.replace("First", "<!-- TODO(prose): too long\nsplit it -->\nFirst")
        )
        found, _ = doc.scan()
        code, out, _ = doc.human("report", "--drafts", doc.drafts([doc.skill(found[0])]))
        assert code == todos.OK
        assert (
            "draft 1  README.md:3-4  skill\n"
            "  to      example:learn-prose-rules\n"
            "  title   too long\n"
            "  detail\n"
            "    | split it\n"
            "\n"
            "1 draft(s).\n"
        ) in out

    def it_leaves_out_an_empty_detail(self, doc):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        _, out, _ = doc.human("report", "--drafts", doc.drafts([doc.skill(found[0])]))
        assert "  title   too long\n\n1 draft(s).\n" in out

    def it_gives_the_skill_in_json(self, doc):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        _, env = doc.run("report", "--drafts", doc.drafts([doc.skill(found[0])]))
        (row,) = env["data"]["drafts"]
        assert (row["route"], row["skill"], row["title"], row["detail"]) == (
            "skill",
            PROSE,
            "too long",
            "",
        )
        assert "body" not in row


@pytest.mark.spec("repo:script-checks-every-answer")
class DescribeRefusals:
    @pytest.mark.parametrize("value", ["", "  ", 3, None])
    def it_refuses_a_skill_that_is_not_a_name(self, doc, value):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        code, env = doc.run("report", "--drafts", doc.drafts([doc.skill(found[0], skill=value)]))
        assert code == todos.PROBLEMS
        assert env["errors"] == ["draft 1 has a `skill` that is not a string with words in it"]

    def it_refuses_a_body_on_a_skill_draft(self, doc):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        drafts = doc.drafts([doc.skill(found[0], body="x")])
        code, env = doc.run("report", "--drafts", drafts)
        assert code == todos.PROBLEMS
        assert env["errors"] == ["draft 1 has `body`, which a draft does not take"]


@pytest.mark.spec("file-cmd-prints-handoffs")
class DescribeTheHandoff:
    def it_gives_the_title_detail_and_passage(self, doc):
        doc.write(
            "README.md", BASE.replace("First", "<!-- TODO(prose): too long\nsplit it -->\nFirst")
        )
        found, _ = doc.scan()
        assert handoffs(doc, [doc.skill(found[0])]) == [
            {
                "skill": PROSE,
                "todos": [
                    {
                        "draft": 1,
                        "title": "too long",
                        "detail": "split it",
                        "passage": {
                            "file": "README.md",
                            "first": 3,
                            "last": 4,
                            "changed": [],
                            "text": "First line.\nSecond line.",
                        },
                    }
                ],
            }
        ]

    @pytest.mark.spec("file-cmd-removes-handled-todos")
    def it_removes_the_todo_without_calling_github(self, doc, github):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        handoffs(doc, [doc.skill(found[0])])
        assert doc.read("README.md") == BASE.encode()
        assert github.posts() == 0

    def it_lists_the_lines_changed_since_the_last_commit(self, doc):
        doc.write(
            "README.md",
            BASE.replace("First line.", "<!-- TODO(prose): why -->\nFirst line, rewritten."),
        )
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        passage = handoff["todos"][0]["passage"]
        assert (passage["first"], passage["last"], passage["changed"]) == (3, 4, [3])
        assert passage["text"] == "First line, rewritten.\nSecond line."

    def it_numbers_the_passage_once_every_finished_todo_is_gone(self, doc):
        doc.write(
            "README.md",
            "<!-- TODO: an issue -->\n\n"
            + BASE.replace("First", "<!-- TODO(prose): one -->\n<!-- TODO(prose): two -->\nFirst"),
        )
        found, _ = doc.scan()
        drafts = [doc.draft(found[0]), doc.skill(found[1]), doc.skill(found[2])]
        (handoff,) = handoffs(doc, drafts)
        assert [t["title"] for t in handoff["todos"]] == ["one", "two"]
        for todo in handoff["todos"]:
            assert (todo["passage"]["first"], todo["passage"]["last"]) == (3, 4)
        assert doc.read("README.md") == BASE.encode()

    def it_stops_the_passage_at_a_todo_left_in_place(self, doc):
        doc.write(
            "README.md",
            BASE.replace(
                "First line.", "<!-- TODO: stays -->\nFirst line.\n<!-- TODO(prose): go -->"
            ),
        )
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[1])])
        passage = handoff["todos"][0]["passage"]
        assert (passage["first"], passage["last"], passage["text"]) == (
            4,
            5,
            "First line.\nSecond line.",
        )

    def it_takes_a_trailing_todos_own_line_into_the_passage(self, doc):
        doc.write("README.md", BASE.replace("Second line.", "Second line. <!-- TODO(prose): x -->"))
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        passage = handoff["todos"][0]["passage"]
        assert (passage["first"], passage["last"], passage["changed"]) == (3, 4, [])
        assert passage["text"] == "First line.\nSecond line."

    def it_gives_no_passage_for_a_todo_at_the_end_of_the_file(self, doc):
        doc.write("README.md", BASE + "\n<!-- TODO(prose): the end -->\n")
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        assert handoff["todos"][0]["passage"] is None

    def it_groups_the_todos_by_skill(self, doc):
        doc.write(
            "README.md",
            "<!-- TODO(prose): a -->\n"
            + BASE.replace("First", "<!-- TODO(prose): b -->\nFirst").replace(
                "Last", "<!-- TODO: c -->\nLast"
            ),
        )
        found, _ = doc.scan()
        drafts = [doc.skill(found[2], skill=OTHER), doc.skill(found[0]), doc.skill(found[1])]
        got = handoffs(doc, drafts)
        assert [(h["skill"], [t["title"] for t in h["todos"]]) for h in got] == [
            (PROSE, ["a", "b"]),
            (OTHER, ["c"]),
        ]

    def it_prints_each_handoff_in_text(self, doc):
        doc.write(
            "README.md",
            BASE.replace("First line.", "<!-- TODO(prose): too long\nsplit it -->\nFirst line!"),
        )
        found, _ = doc.scan()
        drafts = doc.drafts([doc.skill(found[0])])
        token = doc.token(drafts)
        code, out, err = doc.human("file", "--drafts", drafts, "--token", token)
        assert code == todos.OK, err
        assert out == (
            "handing to example:learn-prose-rules\n"
            "  and removed README.md:3-4\n"
            "\n"
            "hand-off to example:learn-prose-rules\n"
            "\n"
            "draft 1\n"
            "  title   too long\n"
            "  detail\n"
            "    | split it\n"
            "  passage README.md:3-4, changed since the last commit: 3\n"
            "  text\n"
            "    | First line!\n"
            "    | Second line.\n"
        )

    def it_says_in_text_when_there_is_no_passage(self, doc):
        doc.write("README.md", BASE + "\n<!-- TODO(prose): the end -->\n")
        found, _ = doc.scan()
        drafts = doc.drafts([doc.skill(found[0])])
        _, out, _ = doc.human("file", "--drafts", drafts, "--token", doc.token(drafts))
        assert out.endswith(
            "  title   the end\n  passage (none: the TODO was at the end of its file)\n"
        )

    def it_says_none_changed_in_text(self, doc):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): x -->\nFirst"))
        found, _ = doc.scan()
        drafts = doc.drafts([doc.skill(found[0])])
        _, out, _ = doc.human("file", "--drafts", drafts, "--token", doc.token(drafts))
        assert "changed since the last commit: none\n" in out

    @pytest.mark.spec("file-cmd-stops-at-failed-call")
    def it_leaves_out_a_todo_left_by_a_failed_call(self, doc, github):
        doc.write(
            "README.md",
            BASE.replace("First", "<!-- TODO(prose): early -->\nFirst").replace(
                "Last", "<!-- TODO: fails -->\nLast"
            ),
        )
        github.fail = (1,)
        found, _ = doc.scan()
        drafts = doc.drafts([doc.skill(found[0]), doc.draft(found[1])])
        code, env = doc.file(drafts)
        assert code == todos.PROBLEMS
        assert env["data"]["handoffs"] == []
        assert [r["draft"] for r in env["data"]["left"]] == [2, 1]


@pytest.mark.spec("file-cmd-never-posts-in-preview", "repo:command-never-writes-in-preview")
class DescribeTheDryRun:
    def it_gives_the_handoff_and_writes_nothing(self, doc):
        doc.write(
            "README.md",
            "<!-- TODO: an issue -->\n\n"
            + BASE.replace("First", "<!-- TODO(prose): one -->\nFirst"),
        )
        before = doc.read("README.md")
        found, _ = doc.scan()
        drafts = doc.drafts([doc.draft(found[0]), doc.skill(found[1])])
        token = doc.token(drafts)
        code, out, _ = doc.human("file", "--drafts", drafts, "--token", token, "--dry-run")
        assert code == todos.OK
        assert out.startswith(
            "would hand to example:learn-prose-rules\n"
            "  and remove README.md:5\n"
            "would file in owner/project: an issue  [no labels]\n"
            "  and remove README.md:1\n"
        )
        assert "  passage README.md:3-4, changed since the last commit: none\n" in out
        assert doc.read("README.md") == before

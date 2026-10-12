"""What `todos.py` does with a draft routed to a skill: how report shows it,
and the hand-off file prints once its TODO is marked."""

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
    def it_leaves_a_skill_draft_out_of_the_text(self, doc):
        doc.write(
            "README.md",
            "<!-- TODO: an issue -->\n\n"
            + BASE.replace("First", "<!-- TODO(prose): too long\nsplit it -->\nFirst"),
        )
        found, _ = doc.scan()
        drafts = doc.drafts([doc.skill(found[1]), doc.draft(found[0])])
        code, out, _ = doc.human("report", "--drafts", drafts)
        assert code == todos.OK
        assert "draft 2  README.md:1  issue\n" in out
        assert "draft 1" not in out
        assert "too long" not in out
        assert "\n1 draft(s).\n" in out

    def it_leaves_a_skill_draft_out_of_the_json(self, doc):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        _, env = doc.run("report", "--drafts", doc.drafts([doc.skill(found[0])]))
        assert env["data"]["drafts"] == []
        assert env["data"]["left"] == []

    @pytest.mark.spec("report-cmd-writes-report-file")
    def it_leaves_a_skill_draft_out_of_the_report_file(self, doc):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        doc.run("report", "--drafts", doc.drafts([doc.skill(found[0])]))
        text = (doc.root / todos.REPORT_FILE).read_text(encoding="utf-8")
        assert "## Draft" not in text
        assert "too long" not in text


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
                "checkout": None,
                "todos": [
                    {
                        "draft": 1,
                        "title": "too long",
                        "detail": "split it",
                        "passage": {
                            "file": "README.md",
                            "first": 5,
                            "last": 6,
                            "changed": [],
                            "text": "First line.\nSecond line.",
                            "line": 5,
                            "trailing": False,
                        },
                    }
                ],
                "arguments": (
                    todos.HANDOFF_LEAD + "\n"
                    "\n"
                    "## Note: too long\n"
                    "\n"
                    "> split it\n"
                    "\n"
                    "- **File:** `README.md`\n"
                    "- **Lines:** 5-6\n"
                    "- **Lines changed since the last commit:** none\n"
                    "- **The TODO sat:** above line 5\n"
                    "\n"
                    "```text\n"
                    "First line.\n"
                    "Second line.\n"
                    "```\n"
                ),
            }
        ]

    @pytest.mark.spec("file-cmd-marks-handled-todos")
    def it_marks_the_todo_with_the_skill_without_calling_github(self, doc, github):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        handoffs(doc, [doc.skill(found[0])])
        assert doc.read("README.md") == BASE.replace(
            "First", "<!-- TODO-HANDLED(%s): too long -->\nFirst" % PROSE
        ).encode("utf-8")
        assert github.posts() == 0

    def it_lists_the_lines_changed_since_the_last_commit(self, doc):
        doc.write(
            "README.md",
            BASE.replace("First line.", "<!-- TODO(prose): why -->\nFirst line, rewritten."),
        )
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        passage = handoff["todos"][0]["passage"]
        assert (passage["first"], passage["last"], passage["changed"]) == (4, 5, [4])
        assert passage["text"] == "First line, rewritten.\nSecond line."

    def it_numbers_the_passage_as_the_marked_file_reads(self, doc):
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
            assert (todo["passage"]["first"], todo["passage"]["last"]) == (7, 8)
        assert doc.read("README.md").count(b"TODO-HANDLED") == 3

    def it_stops_the_passage_at_a_todo_left_in_place(self, doc):
        doc.write(
            "README.md",
            BASE.replace("First line.", "<!-- TODO(prose): go -->\nFirst line.").replace(
                "Second", "<!-- TODO: stays -->\nSecond"
            ),
        )
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        passage = handoff["todos"][0]["passage"]
        assert (passage["first"], passage["last"], passage["text"]) == (4, 4, "First line.")

    @pytest.mark.spec("scan-cmd-skips-handled-todos")
    def it_stops_the_passage_at_a_marked_todo(self, doc):
        doc.write(
            "README.md",
            BASE.replace(
                "Second", "<!-- TODO-HANDLED(#3): old -->\n<!-- TODO(prose): go -->\nSecond"
            ),
        )
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        passage = handoff["todos"][0]["passage"]
        assert (passage["first"], passage["last"], passage["text"]) == (6, 6, "Second line.")

    def it_takes_a_trailing_todos_own_line_into_the_passage(self, doc):
        doc.write("README.md", BASE.replace("Second line.", "Second line. <!-- TODO(prose): x -->"))
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        passage = handoff["todos"][0]["passage"]
        assert (passage["first"], passage["last"], passage["changed"]) == (3, 4, [])
        assert passage["text"] == "First line.\nSecond line."

    def it_names_the_line_a_trailing_todo_was_at_the_end_of(self, doc):
        doc.write("README.md", BASE.replace("Second line.", "Second line. <!-- TODO(prose): x -->"))
        found, _ = doc.scan()
        drafts = doc.drafts([doc.skill(found[0])])
        code, env = doc.file(drafts)
        assert code == todos.OK, doc.err
        passage = env["data"]["handoffs"][0]["todos"][0]["passage"]
        assert (passage["line"], passage["trailing"]) == (4, True)

    def it_says_in_the_arguments_which_line_a_trailing_todo_was_at_the_end_of(self, doc):
        doc.write("README.md", BASE.replace("Second line.", "Second line. <!-- TODO(prose): x -->"))
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        assert "- **The TODO sat:** at the end of line 4\n" in handoff["arguments"]

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

    def it_gives_every_note_for_a_skill_in_one_block_of_arguments(self, doc):
        doc.write(
            "README.md",
            "<!-- TODO(prose): a -->\n"
            + BASE.replace("First", "<!-- TODO(prose): b -->\nFirst").replace(
                "Last", "<!-- TODO: c -->\nLast"
            ),
        )
        found, _ = doc.scan()
        drafts = [doc.skill(found[2], skill=OTHER), doc.skill(found[0]), doc.skill(found[1])]
        prose, other = handoffs(doc, drafts)
        assert prose["arguments"].count("## Note: ") == 2
        assert "## Note: a\n" in prose["arguments"]
        assert "## Note: b\n" in prose["arguments"]
        assert "## Note: c\n" in other["arguments"]
        assert prose["arguments"].count(todos.HANDOFF_LEAD) == 1

    def it_fences_the_passage_past_its_own_backticks(self, doc):
        doc.write("notes.txt", "Uses ```` here.\n")
        doc.commit()
        doc.write("notes.txt", "# TODO(prose): x\nUses ```` here.\n")
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        assert "\n`````text\nUses ```` here.\n`````\n" in handoff["arguments"]

    def it_says_in_the_arguments_when_there_is_no_passage(self, doc):
        doc.write("README.md", BASE + "\n<!-- TODO(prose): the end -->\n")
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        assert handoff["arguments"].endswith(
            "## Note: the end\n"
            "\n"
            "- **File:** `README.md`\n"
            "- **Passage:** none. The TODO sat at the end of the file.\n"
        )

    def it_names_the_lines_changed_in_the_arguments(self, doc):
        doc.write(
            "README.md",
            BASE.replace("First line.", "<!-- TODO(prose): x -->\nFirst line!"),
        )
        found, _ = doc.scan()
        (handoff,) = handoffs(doc, [doc.skill(found[0])])
        assert "- **Lines changed since the last commit:** 4\n" in handoff["arguments"]

    def it_prints_each_handoffs_arguments_in_text(self, doc):
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
            "  and marked README.md:3-4 as TODO-HANDLED(example:learn-prose-rules)\n"
            "\n"
            "hand-off to example:learn-prose-rules\n"
            "  arguments\n"
            "    | " + todos.HANDOFF_LEAD + "\n"
            "    |\n"
            "    | ## Note: too long\n"
            "    |\n"
            "    | > split it\n"
            "    |\n"
            "    | - **File:** `README.md`\n"
            "    | - **Lines:** 5-6\n"
            "    | - **Lines changed since the last commit:** 5\n"
            "    | - **The TODO sat:** above line 5\n"
            "    |\n"
            "    | ```text\n"
            "    | First line!\n"
            "    | Second line.\n"
            "    | ```\n"
        )

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


@pytest.mark.spec("file-cmd-requires-token")
class DescribeTheToken:
    @pytest.fixture
    def mixed(self, doc):
        """README.md holds a TODO for a skill, and a.py one for an issue."""
        doc.write("a.py", "x = 1\n")
        doc.commit()
        doc.write("a.py", "# TODO: an issue\nx = 1\n")
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        return doc, dict((t["file"], t) for t in found)

    def it_files_a_batch_of_only_handoffs_without_a_token(self, doc, github):
        doc.write("README.md", BASE.replace("First", "<!-- TODO(prose): too long -->\nFirst"))
        found, _ = doc.scan()
        code, env = doc.run("file", "--drafts", doc.drafts([doc.skill(found[0])]))
        assert code == todos.OK, doc.err
        assert [h["skill"] for h in env["data"]["handoffs"]] == [PROSE]
        assert github.posts() == 0

    def it_refuses_a_batch_with_an_issue_and_no_token(self, mixed, github):
        doc, found = mixed
        before = doc.read("README.md")
        drafts = doc.drafts([doc.skill(found["README.md"]), doc.draft(found["a.py"])])
        code, env = doc.run("file", "--drafts", drafts)
        assert code == todos.PROBLEMS
        assert env["errors"] == [todos.TOKEN_MISSING]
        assert github.posts() == 0
        assert doc.read("README.md") == before

    def it_keeps_the_token_when_a_handoff_changes(self, mixed):
        doc, found = mixed
        drafts = doc.drafts([doc.skill(found["README.md"]), doc.draft(found["a.py"])])
        token = doc.token(drafts)
        doc.drafts([doc.skill(found["README.md"], skill=OTHER), doc.draft(found["a.py"])])
        code, env = doc.run("file", "--drafts", drafts, "--token", token)
        assert code == todos.OK, doc.err
        assert [h["skill"] for h in env["data"]["handoffs"]] == [OTHER]

    def it_keeps_the_token_when_only_a_handoffs_file_changes(self, mixed):
        doc, found = mixed
        drafts = doc.drafts([doc.skill(found["README.md"]), doc.draft(found["a.py"])])
        token = doc.token(drafts)
        doc.write("README.md", doc.read("README.md").decode("utf-8") + "\nMore.\n")
        code, _ = doc.run("file", "--drafts", drafts, "--token", token)
        assert code == todos.OK, doc.err


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
            "  and mark README.md:5 as TODO-HANDLED(example:learn-prose-rules)\n"
            "would file in owner/project: an issue  [no labels]\n"
            "  and mark README.md:1 with the new issue's number\n"
        )
        assert "    | - **Lines:** 6-7\n" in out
        assert doc.read("README.md") == before


LIST = "Lead-in line.\n- First item,\n  wrapped.\n- Second item.\n  - Nested item.\n- Third item.\n"


def listed(repo, path, text, base=LIST):
    """The passage handed off for the one TODO in path, once base is
    committed there and text written over it."""
    repo.write(path, base)
    repo.commit()
    repo.write(path, text)
    found, _ = repo.scan()
    (handoff,) = handoffs(repo, [repo.skill(found[0])])
    passage = handoff["todos"][0]["passage"]
    return passage["first"], passage["last"], passage["text"]


@pytest.mark.spec("file-cmd-prints-handoffs")
class DescribeTheMarkdownPassage:
    def it_gives_the_list_item_a_trailing_todo_was_on(self, repo):
        text = LIST.replace("  wrapped.", "  wrapped. <!-- TODO(prose): x -->")
        assert listed(repo, "README.md", text) == (2, 3, "- First item,\n  wrapped.")

    def it_gives_the_list_item_a_todo_sat_above(self, repo):
        text = LIST.replace("- Second", "<!-- TODO(prose): x -->\n- Second")
        assert listed(repo, "README.md", text) == (5, 6, "- Second item.\n  - Nested item.")

    def it_takes_the_items_nested_in_the_item(self, repo):
        text = LIST.replace("- Second item.", "- Second item. <!-- TODO(prose): x -->")
        assert listed(repo, "README.md", text) == (4, 5, "- Second item.\n  - Nested item.")

    def it_gives_a_nested_item_alone(self, repo):
        text = LIST.replace("Nested item.", "Nested item. <!-- TODO(prose): x -->")
        assert listed(repo, "README.md", text) == (5, 5, "  - Nested item.")

    def it_gives_the_lines_before_the_first_item(self, repo):
        text = LIST.replace("Lead-in line.", "Lead-in line. <!-- TODO(prose): x -->")
        assert listed(repo, "README.md", text) == (1, 1, "Lead-in line.")

    @pytest.mark.parametrize("marker", ["*", "+", "1.", "2)"])
    def it_reads_each_list_marker(self, repo, marker):
        base = LIST.replace("- ", marker + " ")
        text = base.replace("Third item.", "Third item. <!-- TODO(prose): x -->")
        assert listed(repo, "README.md", text, base) == (6, 6, marker + " Third item.")

    def it_reads_a_file_ending_markdown(self, repo):
        text = LIST.replace("- Second", "<!-- TODO(prose): x -->\n- Second")
        assert listed(repo, "notes.markdown", text) == (5, 6, "- Second item.\n  - Nested item.")

    def it_does_not_read_an_item_in_a_code_fence(self, repo):
        base = "Lead-in.\n```\n- not an item\n```\n"
        text = base.replace("Lead-in.", "Lead-in. <!-- TODO(prose): x -->")
        assert listed(repo, "README.md", text, base) == (1, 4, base.rstrip("\n"))

    def it_keeps_the_whole_run_outside_markdown(self, repo):
        text = "# TODO(prose): x\nLead-in.\n- One.\n- Two.\n"
        assert listed(repo, "notes.txt", text, "") == (2, 4, "Lead-in.\n- One.\n- Two.")

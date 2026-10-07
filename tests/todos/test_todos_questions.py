"""questions writes do-todos's questions about TODOs that say too little to a
page the author reads whole, when one dialog cannot hold them.

The model hands it the questions as JSON. Each question names the TODOs it
asks about by file and first line, and the script takes each title from its
own scan.
"""

import io
import json
import subprocess

import pytest

import todos


@pytest.fixture
def two(repo):
    """A clone with two pending TODOs in run.py."""
    repo.write("run.py", "def run():\n    pass\n")
    repo.commit()
    repo.write(
        "run.py", "# TODO(bug): run hangs\n# no timeout\ndef run():\n    pass\n# TODO: tidy\n"
    )
    return repo


def question(*places, **overrides):
    record = {
        "question": "Is this a bug, or a change?",
        "options": [
            {"label": "Bug", "description": "run() should return."},
            {"label": "Change"},
        ],
        "todos": [{"file": f, "line": n} for f, n in places or [("run.py", 1)]],
    }
    record.update(overrides)
    return record


@pytest.mark.spec("questions-cmd-writes-page")
class DescribeTheQuestionsPage:
    def write(self, repo, questions, *extra):
        path = repo.root.parent / "questions.json"
        path.write_text(json.dumps(questions))
        code, env = repo.run("questions", "--batch", str(path), *extra)
        page = repo.root / todos.QUESTIONS_FILE
        assert env["data"]["page"] == str(page)
        return code, env, page.read_text(encoding="utf-8")

    def it_numbers_each_question_under_its_todos_with_its_options(self, two):
        asked = [question(), question(("run.py", 1), ("run.py", 5), question="Do these repeat?")]
        code, env, text = self.write(two, asked)
        assert code == todos.OK, two.err
        assert env["data"]["questions"] == 2
        assert text.startswith("# Questions from do-todos\n")
        assert (
            "## Question 1\n\n"
            "- `run.py:1` run hangs\n\n"
            "Is this a bug, or a change?\n\n"
            "Options:\n\n"
            "- **Bug**: run() should return.\n"
            "- **Change**\n"
        ) in text
        assert "## Question 2\n\n- `run.py:1` run hangs\n- `run.py:5` tidy\n\nDo these" in text

    def it_refuses_a_question_without_options(self, two):
        code, env, text = self.write(two, [question(), question(options=[])])
        assert code == todos.PROBLEMS
        assert env["errors"] == ["question 2 has no options"]
        assert "- question 2 has no options\n" in text

    def it_refuses_a_question_that_does_not_name_a_todo(self, two):
        code, env, _ = self.write(two, [question(todos=[])])
        assert code == todos.PROBLEMS
        assert env["errors"] == ["question 1 does not name a TODO"]

    def it_refuses_a_line_that_does_not_hold_a_pending_todo(self, two):
        code, env, _ = self.write(two, [question(("run.py", 2))])
        assert code == todos.PROBLEMS
        assert env["errors"] == [
            "question 1, TODO 1: run.py:2 does not hold a pending TODO. Run scan again and"
            " name the TODO by its file and first line"
        ]

    @pytest.mark.parametrize(
        ("record", "reason"),
        [
            ("Bug?", "question 1 is not a JSON object"),
            (question(question=" "), "question 1 has no question text"),
            (question(options=[{"description": "x"}]), "question 1, option 1 has no label"),
            (
                question(options=[{"label": "A", "description": 3}]),
                "question 1, option 1 has a description that is not text",
            ),
            (
                question(todos=[{"file": "run.py"}]),
                "question 1, TODO 1 does not give a `file` and a `line`",
            ),
        ],
    )
    def it_names_what_is_wrong_with_a_malformed_question(self, two, record, reason):
        code, env, _ = self.write(two, [record])
        assert code == todos.PROBLEMS
        assert env["errors"] == [reason]

    def it_writes_no_question_from_an_earlier_run_beside_a_refusal(self, two):
        self.write(two, [question()])
        _, env, text = self.write(two, [question(options=[])])
        assert "## Question" not in text
        assert env["data"]["questions"] == 0

    def it_reads_the_questions_from_stdin_given_a_dash(self, two, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([question()])))
        code, env = two.run("questions", "--batch", "-")
        assert code == todos.OK, two.err
        assert env["data"]["questions"] == 1

    @pytest.mark.parametrize(
        ("batch", "cause"),
        [("[]", "not a JSON array"), ('{"question": "Bug?"}', "not a JSON array"), ("[", "JSON")],
    )
    def it_cannot_run_without_an_array_of_questions(self, two, batch, cause):
        path = two.root.parent / "questions.json"
        path.write_text(batch)
        code, env = two.run("questions", "--batch", str(path))
        assert code == todos.CANNOT_RUN
        assert env is None
        assert cause in two.err

    def it_cannot_run_when_the_batch_cannot_be_read(self, two):
        code, _ = two.run("questions", "--batch", str(two.root.parent / "missing.json"))
        assert code == todos.CANNOT_RUN
        assert "cannot read the questions" in two.err

    def it_keeps_the_page_out_of_the_projects_commits(self, two):
        self.write(two, [question()])
        assert (two.root / todos.COPY_IGNORE).read_bytes() == todos.COPY_IGNORE_TEXT
        status = subprocess.run(
            ["git", "-C", str(two.root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert todos.COPY_DIR not in status

    def it_says_where_it_wrote_the_page(self, two):
        path = two.root.parent / "questions.json"
        path.write_text(json.dumps([question()]))
        code, out, _ = two.human("questions", "--batch", str(path))
        assert code == todos.OK
        assert out == "wrote %s\n" % (two.root / todos.QUESTIONS_FILE)

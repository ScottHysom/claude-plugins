"""questions writes update-prose-config's interview to a page the author reads
whole, when one dialog cannot hold it.

The model hands it the questions as JSON. Each question carries its options
and the evidence it rests on, and a question without either is refused.
"""

import io
import json
import subprocess

import pytest

import prose


def question(**overrides):
    record = {
        "question": "Was the em-dash cut for style, or to fix this one sentence?",
        "options": [
            {"label": "Style", "description": "Prefer a period over the em-dash."},
            {"label": "This sentence"},
        ],
        "evidence": ["guide.md:12\n- It holds — until it breaks.\n+ It holds. Then it breaks."],
    }
    record.update(overrides)
    return record


@pytest.mark.spec("questions-cmd-writes-page")
class DescribeTheQuestionsPage:
    def write(self, repo, questions):
        path = repo.root / "questions.json"
        path.write_text(json.dumps(questions))
        code, env = repo.run("questions", "--batch", str(path))
        page = repo.root / prose.QUESTIONS_FILE
        assert env["data"]["page"] == str(page)
        return code, env, page.read_text(encoding="utf-8")

    def it_numbers_each_question_with_its_options_and_evidence(self, prose_repo):
        code, env, text = self.write(prose_repo, [question(), question(question="Second?")])
        assert code == prose.OK
        assert env["data"]["questions"] == 2
        assert (
            "## Question 1\n\n"
            "Was the em-dash cut for style, or to fix this one sentence?\n\n"
            "Options:\n\n"
            "- **Style**: Prefer a period over the em-dash.\n"
            "- **This sentence**\n\n"
            "Evidence:\n\n"
            "```text\nguide.md:12\n- It holds — until it breaks.\n+ It holds. Then it breaks.\n```\n"
        ) in text
        assert "## Question 2\n\nSecond?\n" in text

    def it_shows_evidence_holding_a_fence_as_it_stands(self, prose_repo):
        evidence = "notes.md:3\n```sh\nls\n```"
        _, _, text = self.write(prose_repo, [question(evidence=[evidence])])
        assert "````text\n%s\n````\n" % evidence in text

    def it_refuses_a_question_without_options(self, prose_repo):
        code, env, text = self.write(prose_repo, [question(), question(options=[])])
        assert code == prose.PROBLEMS
        assert env["errors"] == ["question 2 has no options"]
        assert "- question 2 has no options\n" in text

    def it_refuses_a_question_without_evidence(self, prose_repo):
        code, env, _ = self.write(prose_repo, [question(evidence=[])])
        assert code == prose.PROBLEMS
        assert env["errors"] == ["question 1 has no evidence"]

    @pytest.mark.parametrize(
        ("record", "reason"),
        [
            ("Style?", "question 1 is not a JSON object"),
            (question(question=" "), "question 1 has no question text"),
            (question(options=[{"description": "x"}]), "question 1, option 1 has no label"),
            (
                question(options=[{"label": "A", "description": 3}]),
                "question 1, option 1 has a description that is not text",
            ),
            (question(evidence=[""]), "question 1 has evidence that is not text"),
        ],
    )
    def it_names_what_is_wrong_with_a_malformed_question(self, prose_repo, record, reason):
        code, env, _ = self.write(prose_repo, [record])
        assert code == prose.PROBLEMS
        assert env["errors"] == [reason]

    def it_writes_no_question_from_an_earlier_run_beside_a_refusal(self, prose_repo):
        self.write(prose_repo, [question()])
        _, env, text = self.write(prose_repo, [question(evidence=[])])
        assert "## Question" not in text
        assert env["data"]["questions"] == 0

    def it_reads_the_questions_from_stdin_given_a_dash(self, prose_repo, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([question()])))
        code, env = prose_repo.run("questions", "--batch", "-")
        assert code == prose.OK
        assert env["data"]["questions"] == 1

    @pytest.mark.parametrize("batch", ["[]", '{"question": "Style?"}'])
    def it_cannot_run_without_a_list_of_questions(self, prose_repo, batch):
        path = prose_repo.root / "questions.json"
        path.write_text(batch)
        code, env = prose_repo.run("questions", "--batch", str(path))
        assert code == prose.CANNOT_RUN
        assert env is None
        assert "not a JSON list" in prose_repo.err

    def it_keeps_the_page_out_of_the_projects_commits(self, prose_repo):
        self.write(prose_repo, [question()])
        ignore = prose_repo.root / prose.COPY_IGNORE
        assert ignore.read_bytes() == prose.COPY_IGNORE_TEXT
        status = subprocess.run(
            ["git", "-C", str(prose_repo.root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert prose.COPY_DIR not in status

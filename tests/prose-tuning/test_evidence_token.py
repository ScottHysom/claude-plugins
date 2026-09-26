"""tags insert tags only the tree that evidence read.

Every address in an insert batch is a line number from evidence. Before the
token, insert took a batch built from a tree that had changed since, and
tagged whatever now sat at those lines. evidence now prints a token over the
files in scope and the rules, and insert refuses any other.
"""

import json

import pytest

import prose

RECORD = {"file": "target.md", "kind": "q", "start": 8, "text": "earned?"}


def batch_file(prose_repo):
    path = prose_repo.root / "batch.json"
    path.write_text(json.dumps([RECORD]))
    return str(path)


def evidence_token(prose_repo):
    code, envelope = prose_repo.run("evidence")
    assert code == prose.OK, envelope["errors"]
    return envelope["data"]["token"]


def insert_with(prose_repo, token, *flags):
    return prose_repo.run(
        "tags", "insert", "--batch", batch_file(prose_repo), "--token", token, *flags
    )


class DescribeEvidenceToken:
    @pytest.mark.spec("insert-needs-token")
    def it_accepts_a_token_from_the_current_tree(self, prose_repo, target):
        prose_repo.commit()
        token = evidence_token(prose_repo)
        code, envelope = insert_with(prose_repo, token)
        assert code == prose.OK, envelope["errors"]
        assert '<q id="1">earned?</q>' in prose_repo.read()

    @pytest.mark.spec("evidence-token")
    def it_prints_the_token_as_the_last_line_of_its_human_output(self, prose_repo, capsys):
        prose_repo.commit()
        token = evidence_token(prose_repo)
        capsys.readouterr()
        code = prose.main(["evidence", "-C", str(prose_repo.root)])
        assert code == prose.OK
        out = capsys.readouterr().out
        assert out.rstrip("\n").split("\n")[-1] == prose.EVIDENCE_TOKEN_LABEL + token

    @pytest.mark.spec("insert-needs-token")
    def it_refuses_insert_without_a_token(self, prose_repo, target, capsys):
        path = batch_file(prose_repo)
        with pytest.raises(SystemExit) as exc:
            prose.main(["tags", "insert", "--batch", path, "-C", str(prose_repo.root)])
        assert exc.value.code == prose.CANNOT_RUN
        assert "--token" in capsys.readouterr().err
        assert prose_repo.read() == target

    @pytest.mark.spec("insert-needs-token")
    @pytest.mark.parametrize(
        "flags",
        [
            pytest.param((), id="whole-batch"),
            pytest.param(("--partial",), id="partial"),
            pytest.param(("--dry-run",), id="dry-run"),
        ],
    )
    def it_refuses_after_a_scoped_file_changes(self, prose_repo, target, flags):
        (prose_repo.root / "other.md").write_text("Other text.\n")
        prose_repo.commit()
        token = evidence_token(prose_repo)
        # other.md is in scope and named by no record, and still counts.
        (prose_repo.root / "other.md").write_text("Other text, edited.\n")
        code, envelope = insert_with(prose_repo, token, *flags)
        assert code == prose.PROBLEMS
        assert "run evidence again" in envelope["errors"][0]
        assert prose_repo.read() == target

    @pytest.mark.spec("insert-needs-token")
    def it_refuses_after_the_rules_change(self, prose_repo, target):
        prose_repo.commit()
        token = evidence_token(prose_repo)
        rules = prose_repo.root / prose.CONFIG_PATH
        rules.write_text(rules.read_text() + "\nOne more line.\n")
        code, envelope = insert_with(prose_repo, token)
        assert code == prose.PROBLEMS
        assert "run evidence again" in envelope["errors"][0]
        assert prose_repo.read() == target

    @pytest.mark.spec("evidence-token")
    def it_prints_no_token_when_the_markup_does_not_parse(self, prose_repo):
        prose_repo.commit()
        (prose_repo.root / "other.md").write_text("An <ins>open tag.\n")
        code, envelope = prose_repo.run("evidence")
        assert code == prose.PROBLEMS
        assert envelope["data"]["token"] is None

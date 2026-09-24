"""apply writes only the batch the author saw in a report.

Before the token, apply ran whether or not report had, and after the findings,
a document or the rules changed since the author approved. In the run behind
#73 the model dropped a finding from the file by hand and apply wrote the rest.
report now prints a token over what it read, and apply refuses any other.
"""

import pytest

import prose


def closing(prose_repo, target_lines, **overrides):
    record = dict(
        col_start=0,
        col_end=16,
        text="Final paragraph.",
        replacement="The closing paragraph.",
    )
    record.update(overrides)
    return prose_repo.finding(target_lines["last-paragraph"], **record)


def reported_token(prose_repo, findings, *flags):
    code, envelope = prose_repo.report(findings, *flags)
    assert code == prose.OK
    return envelope["data"]["token"]


def apply_with(prose_repo, token, *flags):
    path = str(prose_repo.root / "findings.json")
    return prose_repo.run("apply", "--findings", path, "--token", token, *flags)


def assert_refused(prose_repo, code, envelope, before):
    assert code == prose.PROBLEMS
    assert envelope["data"]["applied"] == []
    assert "run report again and show it to the author" in envelope["errors"][0]
    assert prose_repo.read() == before


class DescribeApprovalToken:
    def it_applies_with_the_token_report_printed(self, prose_repo, target_lines):
        token = reported_token(prose_repo, [closing(prose_repo, target_lines)])
        code, envelope = apply_with(prose_repo, token)
        assert code == prose.OK
        assert envelope["errors"] == []
        assert "The closing paragraph." in prose_repo.read()

    def it_refuses_apply_without_a_token(self, prose_repo, target_lines, capsys):
        path = prose_repo.findings_file([closing(prose_repo, target_lines)])
        before = prose_repo.read()
        with pytest.raises(SystemExit) as exc:
            prose.main(["apply", "--findings", path, "-C", str(prose_repo.root)])
        assert exc.value.code == prose.CANNOT_RUN
        assert "--token" in capsys.readouterr().err
        assert prose_repo.read() == before

    def it_refuses_after_the_findings_file_changes(self, prose_repo, target_lines):
        first = closing(prose_repo, target_lines)
        second = prose_repo.finding(target_lines["paragraph"])
        token = reported_token(prose_repo, [first, second])
        # The model drops a finding by hand after the author approved both.
        prose_repo.findings_file([first])
        before = prose_repo.read()
        code, envelope = apply_with(prose_repo, token)
        assert_refused(prose_repo, code, envelope, before)

    def it_refuses_after_a_document_changes(self, prose_repo, target_lines):
        (prose_repo.root / "other.md").write_text("Other text.\n")
        findings = [
            closing(prose_repo, target_lines),
            prose_repo.finding(1, file="other.md", text="Other text."),
        ]
        token = reported_token(prose_repo, findings)
        # other.md is outside the --file filter below and still counts.
        (prose_repo.root / "other.md").write_text("Other text, edited.\n")
        before = prose_repo.read()
        code, envelope = apply_with(prose_repo, token, "--file", "target.md")
        assert_refused(prose_repo, code, envelope, before)

    def it_refuses_after_prose_style_changes(self, prose_repo, target_lines):
        token = reported_token(prose_repo, [closing(prose_repo, target_lines)])
        config = prose_repo.root / prose.CONFIG_PATH
        config.write_text(config.read_text() + "\n")
        before = prose_repo.read()
        code, envelope = apply_with(prose_repo, token)
        assert_refused(prose_repo, code, envelope, before)

    def it_prints_no_token_when_report_fails(self, prose_repo, target_lines, capsys):
        refused = closing(prose_repo, target_lines, text="Not on this line.")
        code, envelope = prose_repo.report([refused])
        assert code == prose.PROBLEMS
        assert envelope["data"]["token"] is None

        path = prose_repo.findings_file([refused])
        capsys.readouterr()
        prose.main(["report", "--findings", path, "-C", str(prose_repo.root)])
        assert prose.TOKEN_LABEL not in capsys.readouterr().out

    def it_prints_the_token_as_the_last_line(self, prose_repo, target_lines, capsys):
        path = prose_repo.findings_file([closing(prose_repo, target_lines)])
        capsys.readouterr()
        code = prose.main(["report", "--findings", path, "-C", str(prose_repo.root)])
        out = capsys.readouterr().out.splitlines()
        assert code == prose.OK
        assert out[-1] == prose.TOKEN_LABEL + prose_repo.token()

    def it_keeps_the_token_under_only_and_file(self, prose_repo, target_lines):
        (prose_repo.root / "other.md").write_text("Other text.\n")
        findings = [
            closing(prose_repo, target_lines),
            prose_repo.finding(1, file="other.md", text="Other text."),
        ]
        whole = reported_token(prose_repo, findings)
        filtered = reported_token(
            prose_repo, findings, "--only", prose_repo.finding(1)["rule"], "--file", "target.md"
        )
        assert filtered == whole

        code, envelope = apply_with(prose_repo, whole, "--file", "target.md")
        assert code == prose.OK
        assert "The closing paragraph." in prose_repo.read()
        assert prose_repo.read("other.md") == "Other text.\n"

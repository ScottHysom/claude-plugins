"""preflight: what stops a skill before it reads or writes anything.

apply-prose waits while a teaching run is underway, and update-prose-config
refuses to start from markup or a rules file it cannot read.
"""

import pytest

import prose


@pytest.fixture
def committed(prose_repo):
    """prose_repo with its rules and its document committed, so nothing is dirty."""
    prose_repo.commit()
    return prose_repo


def errors_with(env, text):
    return [e for e in env["errors"] if text in e]


class DescribePreflightForApply:
    @pytest.mark.spec("preflight-blocks-apply")
    def it_passes_a_committed_project_with_no_markup(self, committed):
        code, env = committed.run("preflight", "--for", "apply")
        assert code == prose.OK, env["errors"]

    @pytest.mark.spec("preflight-blocks-apply")
    def it_blocks_on_markup_in_a_file_in_scope(self, committed):
        (committed.root / "target.md").write_text("A <ins>new</ins> word.\n")
        committed.commit()
        code, env = committed.run("preflight", "--for", "apply")
        assert code == prose.PROBLEMS
        assert errors_with(env, "target.md:1  markup is present")

    @pytest.mark.spec("preflight-blocks-apply")
    def it_blocks_on_an_uncommitted_file_in_scope(self, committed):
        (committed.root / "target.md").write_text("Edited by hand.\n")
        code, env = committed.run("preflight", "--for", "apply")
        assert code == prose.PROBLEMS
        assert errors_with(env, "target.md  uncommitted")

    @pytest.mark.spec("preflight-blocks-apply")
    def it_passes_an_uncommitted_rules_file(self, committed):
        rules = committed.root / prose.CONFIG_PATH
        rules.write_text(rules.read_text() + "\nA note on the rules.\n")
        code, env = committed.run("preflight", "--for", "apply")
        assert code == prose.OK, env["errors"]


class DescribePreflightForConfig:
    @pytest.mark.spec("teaching-starts-clean")
    def it_passes_markup_that_parses(self, committed):
        (committed.root / "target.md").write_text("A <ins>new</ins> word.\n")
        code, env = committed.run("preflight", "--for", "config")
        assert code == prose.OK, env["errors"]

    @pytest.mark.spec("teaching-starts-clean")
    def it_blocks_on_markup_that_does_not_parse(self, committed):
        (committed.root / "target.md").write_text("A <ins>new word.\n")
        code, env = committed.run("preflight", "--for", "config")
        assert code == prose.PROBLEMS
        assert errors_with(env, "target.md")

    @pytest.mark.spec("teaching-starts-clean")
    def it_blocks_on_a_rules_file_with_errors(self, committed):
        (committed.root / prose.CONFIG_PATH).write_text("no front matter\n")
        code, env = committed.run("preflight", "--for", "config")
        assert code == prose.PROBLEMS
        assert errors_with(env, "no front matter")

    @pytest.mark.spec("teaching-starts-clean")
    def it_reads_past_a_file_deleted_since_the_last_commit(self, committed):
        (committed.root / "target.md").unlink()
        code, env = committed.run("preflight", "--for", "config")
        assert code == prose.OK, env["errors"]


class DescribeNoRulesFile:
    @pytest.fixture
    def bare(self, prose_repo):
        (prose_repo.root / prose.CONFIG_PATH).unlink()
        return prose_repo

    @pytest.mark.spec("no-rules-names-init")
    def it_blocks_apply_and_names_config_init(self, bare):
        code, env = bare.run("preflight", "--for", "apply")
        assert code == prose.PROBLEMS
        assert errors_with(env, "run: prose.py config init")

    @pytest.mark.spec("no-rules-names-init")
    @pytest.mark.parametrize(
        "argv",
        [
            ["config", "lint"],
            ["config", "list"],
            ["config", "check-id", "--section", "sentences", "--name", "own-subject"],
        ],
    )
    def it_stops_a_config_command_and_names_config_init(self, bare, argv):
        code, env = bare.run(*argv)
        assert (code, env) == (prose.CANNOT_RUN, None)
        assert "run: prose.py config init" in bare.err


class DescribeOutsideARepository:
    @pytest.mark.spec("needs-a-repo")
    def it_names_a_folder_that_is_not_in_a_git_repository(self, tmp_path, capsys):
        code = prose.main(["status", "-C", str(tmp_path), "--json"])
        captured = capsys.readouterr()
        assert (code, captured.out) == (prose.CANNOT_RUN, "")
        assert "%s is not inside a git repository" % tmp_path in captured.err

    @pytest.mark.spec("needs-a-repo")
    def it_starts_from_the_folder_holding_a_file_it_is_given(self, tmp_path, capsys):
        loose = tmp_path / "loose.md"
        loose.write_text("x\n")
        code = prose.main(["status", "-C", str(loose)])
        assert code == prose.CANNOT_RUN
        assert "%s is not inside a git repository" % tmp_path in capsys.readouterr().err

    @pytest.mark.spec("needs-a-repo")
    def it_says_so_when_git_is_not_installed(self, prose_repo, monkeypatch):
        monkeypatch.setenv("PATH", "")
        code, env = prose_repo.run("scope")
        assert (code, env) == (prose.CANNOT_RUN, None)
        assert "git is not installed" in prose_repo.err

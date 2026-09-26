"""config init: where a project's prose-style.md comes from.

A project starts from the rules the plugin ships, so the shipped file has to
parse, and a copy of the script on Cowork's device has to find the rules
`stage` put beside it rather than anything else in the project.
"""

import shutil
import subprocess

import pytest

import prose

SHIPPED_ONLY = (
    "---\nname: Device\n---\n\n## Sentences\n\n### sentences-from-stage: Staged\n\nBody.\n"
)


def ids(path):
    return [r.id for r in prose.Config(str(path)).rules]


@pytest.fixture
def fresh_repo(prose_repo):
    """prose_repo with no prose-style.md yet."""
    (prose_repo.root / prose.CONFIG_PATH).unlink()
    return prose_repo


def git(cwd, *args):
    # An identity and no signing, so the commit works on any machine.
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    )


@pytest.fixture
def worktree_repo(fresh_repo, tmp_path):
    """fresh_repo seen from a linked worktree whose folder has another name.

    `git worktree add` needs a commit to check out, which prose_repo leaves
    out; this makes an empty one.
    """
    git(fresh_repo.root, "commit", "-q", "--allow-empty", "-m", "start")
    checkout = tmp_path / "issue-42-7fdf82"
    git(fresh_repo.root, "worktree", "add", "-q", str(checkout))
    return type(fresh_repo)(checkout, fresh_repo._capsys)


def install_copy(repo, monkeypatch):
    """Put a copy of the script where `stage` puts it on the device."""
    copy = repo.root / prose.COPY_SCRIPT
    copy.parent.mkdir()
    shutil.copyfile(prose.SCRIPT_PATH, str(copy))
    monkeypatch.setattr(prose, "SCRIPT_PATH", str(copy))


class DescribeShippedRules:
    @pytest.mark.spec("init-from-shipped")
    def it_parses_without_errors(self):
        config = prose.Config(prose.shipped_template())
        assert config.rules
        assert config.errors == []


class DescribeConfigInit:
    @pytest.mark.spec("init-from-shipped")
    def it_starts_a_project_from_the_shipped_rules(self, fresh_repo):
        code, env = fresh_repo.run("config", "init")
        assert code == prose.OK, env["errors"]
        assert ids(fresh_repo.root / prose.CONFIG_PATH) == ids(prose.shipped_template())

    @pytest.mark.spec("init-from-shipped")
    def it_names_the_project_where_the_shipped_rules_leave_a_slot(self, fresh_repo):
        fresh_repo.run("config", "init")
        text = fresh_repo.read(prose.CONFIG_PATH)
        assert prose.PROJECT_NAME_SLOT not in text
        assert "name: %s prose style" % fresh_repo.root.name in text

    @pytest.mark.spec("init-from-shipped")
    def it_writes_a_file_that_lints_clean(self, fresh_repo):
        fresh_repo.run("config", "init")
        code, env = fresh_repo.run("config", "lint")
        assert code == prose.OK, env["errors"]

    @pytest.mark.spec("init-from-or-empty")
    def it_copies_another_projects_file_with_from(self, fresh_repo, tmp_path):
        other = tmp_path / "other.md"
        other.write_text(SHIPPED_ONLY)
        code, _ = fresh_repo.run("config", "init", "--from", str(other))
        assert code == prose.OK
        assert fresh_repo.read(prose.CONFIG_PATH) == SHIPPED_ONLY

    @pytest.mark.spec("init-from-or-empty")
    def it_writes_a_skeleton_with_no_rules_when_asked_for_empty(self, fresh_repo):
        code, _ = fresh_repo.run("config", "init", "--empty")
        assert code == prose.OK
        assert ids(fresh_repo.root / prose.CONFIG_PATH) == []

    @pytest.mark.spec("init-from-or-empty")
    def it_refuses_from_and_empty_together(self, fresh_repo, tmp_path):
        with pytest.raises(SystemExit) as exc:
            fresh_repo.run("config", "init", "--empty", "--from", str(tmp_path / "x.md"))
        assert exc.value.code == prose.CANNOT_RUN

    @pytest.mark.spec("init-from-or-empty")
    def it_names_a_from_file_that_does_not_exist(self, fresh_repo, tmp_path):
        missing = tmp_path / "missing.md"
        code, env = fresh_repo.run("config", "init", "--from", str(missing))
        assert (code, env) == (prose.CANNOT_RUN, None)
        assert "%s does not exist" % missing in fresh_repo.err
        assert not (fresh_repo.root / prose.CONFIG_PATH).exists()

    @pytest.mark.spec("init-never-overwrites")
    def it_refuses_to_overwrite_an_existing_file(self, prose_repo):
        before = prose_repo.read(prose.CONFIG_PATH)
        code, _ = prose_repo.run("config", "init")
        assert code == prose.CANNOT_RUN
        assert prose_repo.read(prose.CONFIG_PATH) == before


class DescribeConfigInitInAWorktree:
    @pytest.mark.spec("init-project-name")
    def it_names_the_project_after_the_main_working_tree(self, worktree_repo):
        code, env = worktree_repo.run("config", "init")
        assert code == prose.OK, env["errors"]
        text = worktree_repo.read(prose.CONFIG_PATH)
        assert "name: repo prose style" in text
        assert "issue-42-7fdf82" not in text

    @pytest.mark.spec("init-project-name")
    def it_names_the_empty_skeleton_after_the_main_working_tree(self, worktree_repo):
        worktree_repo.run("config", "init", "--empty")
        text = worktree_repo.read(prose.CONFIG_PATH)
        assert "name: repo prose style" in text
        assert "issue-42-7fdf82" not in text

    @pytest.mark.spec("init-project-name")
    def it_names_a_bare_repository_without_its_git_suffix(self, fresh_repo, tmp_path):
        git(fresh_repo.root, "commit", "-q", "--allow-empty", "-m", "start")
        bare = tmp_path / "shared.git"
        git(tmp_path, "clone", "-q", "--bare", str(fresh_repo.root), str(bare))
        checkout = tmp_path / "issue-42-7fdf82"
        git(bare, "worktree", "add", "-q", str(checkout))
        code, env = type(fresh_repo)(checkout, fresh_repo._capsys).run("config", "init")
        assert code == prose.OK, env["errors"]
        assert "name: shared prose style" in (checkout / prose.CONFIG_PATH).read_text()


class DescribeConfigInitOnTheDevice:
    @pytest.mark.spec("init-reads-staged-rules")
    def it_reads_the_rules_staged_beside_the_copy(self, fresh_repo, monkeypatch):
        install_copy(fresh_repo, monkeypatch)
        (fresh_repo.root / prose.COPY_TEMPLATE).write_text(SHIPPED_ONLY)
        code, env = fresh_repo.run("config", "init")
        assert code == prose.OK, env["errors"]
        assert ids(fresh_repo.root / prose.CONFIG_PATH) == ["sentences-from-stage"]

    @pytest.mark.spec("init-reads-staged-rules")
    def it_never_takes_a_templates_folder_in_the_project_for_the_plugin(
        self, fresh_repo, monkeypatch
    ):
        install_copy(fresh_repo, monkeypatch)
        decoy = fresh_repo.root / prose.SHIPPED_TEMPLATE
        decoy.parent.mkdir()
        decoy.write_text(SHIPPED_ONLY)
        code, _ = fresh_repo.run("config", "init")
        assert code == prose.CANNOT_RUN
        assert "shipped rules not found" in fresh_repo.err
        assert not (fresh_repo.root / prose.CONFIG_PATH).exists()

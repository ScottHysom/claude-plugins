"""config init: where a project's prose-style.md comes from.

A project starts from the rules the plugin ships, so the shipped file has to
parse, and a copy of the script on Cowork's device has to find the rules
`stage` put beside it rather than anything else in the project.
"""

import shutil

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
    (prose_repo.root / prose.CONFIG_NAME).unlink()
    return prose_repo


def install_copy(repo, monkeypatch):
    """Put a copy of the script where `stage` puts it on the device."""
    copy = repo.root / prose.DEVICE_SCRIPT
    copy.parent.mkdir()
    shutil.copyfile(prose.SCRIPT_PATH, str(copy))
    monkeypatch.setattr(prose, "SCRIPT_PATH", str(copy))


class DescribeShippedRules:
    def it_parses_without_errors(self):
        config = prose.Config(prose.shipped_template())
        assert config.rules
        assert config.errors == []


class DescribeConfigInit:
    def it_starts_a_project_from_the_shipped_rules(self, fresh_repo):
        code, env = fresh_repo.run("config", "init")
        assert code == prose.OK, env["errors"]
        assert ids(fresh_repo.root / prose.CONFIG_NAME) == ids(prose.shipped_template())

    def it_names_the_project_where_the_shipped_rules_leave_a_slot(self, fresh_repo):
        fresh_repo.run("config", "init")
        text = fresh_repo.read(prose.CONFIG_NAME)
        assert prose.PROJECT_NAME_SLOT not in text
        assert "name: %s prose style" % fresh_repo.root.name in text

    def it_writes_a_file_that_lints_clean(self, fresh_repo):
        fresh_repo.run("config", "init")
        code, env = fresh_repo.run("config", "lint")
        assert code == prose.OK, env["errors"]

    def it_copies_another_projects_file_with_from(self, fresh_repo, tmp_path):
        other = tmp_path / "other.md"
        other.write_text(SHIPPED_ONLY)
        code, _ = fresh_repo.run("config", "init", "--from", str(other))
        assert code == prose.OK
        assert fresh_repo.read(prose.CONFIG_NAME) == SHIPPED_ONLY

    def it_writes_a_skeleton_with_no_rules_when_asked_for_empty(self, fresh_repo):
        code, _ = fresh_repo.run("config", "init", "--empty")
        assert code == prose.OK
        assert ids(fresh_repo.root / prose.CONFIG_NAME) == []

    def it_refuses_from_and_empty_together(self, fresh_repo, tmp_path):
        with pytest.raises(SystemExit) as exc:
            fresh_repo.run("config", "init", "--empty", "--from", str(tmp_path / "x.md"))
        assert exc.value.code == prose.CANNOT_RUN

    def it_refuses_to_overwrite_an_existing_file(self, prose_repo):
        before = prose_repo.read(prose.CONFIG_NAME)
        code, _ = prose_repo.run("config", "init")
        assert code == prose.CANNOT_RUN
        assert prose_repo.read(prose.CONFIG_NAME) == before


class DescribeConfigInitOnTheDevice:
    def it_reads_the_rules_staged_beside_the_copy(self, fresh_repo, monkeypatch):
        install_copy(fresh_repo, monkeypatch)
        (fresh_repo.root / prose.DEVICE_TEMPLATE).write_text(SHIPPED_ONLY)
        code, env = fresh_repo.run("config", "init")
        assert code == prose.OK, env["errors"]
        assert ids(fresh_repo.root / prose.CONFIG_NAME) == ["sentences-from-stage"]

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
        assert not (fresh_repo.root / prose.CONFIG_NAME).exists()

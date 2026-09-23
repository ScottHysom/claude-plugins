"""Where a project keeps its rules, and what happens to a copy left at the root.

The rules live in .claude/rules/, which Claude Code and Cowork both load into
every session. A copy at the project root is where they used to live: nothing
loads it, so preflight refuses it and `config move` copies it across.
"""

import pytest

import prose

LEGACY = "---\nname: Old\n---\n\n## Sentences\n\n### sentences-from-root: Root\n\nBody.\r\n"


@pytest.fixture
def legacy_repo(prose_repo):
    """A project whose only rules are at the root, as before the move."""
    config = prose_repo.root / prose.CONFIG_PATH
    config.unlink()
    config.parent.rmdir()
    config.parent.parent.rmdir()
    (prose_repo.root / prose.LEGACY_CONFIG_PATH).write_bytes(LEGACY.encode())
    return prose_repo


class DescribeConfigInitLocation:
    def it_creates_the_rules_folder_when_the_project_has_none(self, legacy_repo):
        (legacy_repo.root / prose.LEGACY_CONFIG_PATH).unlink()
        code, env = legacy_repo.run("config", "init")
        assert code == prose.OK, env["errors"]
        assert (legacy_repo.root / prose.CONFIG_PATH).is_file()


class DescribeConfigMove:
    def it_copies_the_root_file_byte_for_byte(self, legacy_repo):
        code, env = legacy_repo.run("config", "move")
        assert code == prose.OK, env["errors"]
        moved = (legacy_repo.root / prose.CONFIG_PATH).read_bytes()
        assert moved == LEGACY.encode()

    def it_leaves_the_root_file_for_the_author_to_delete(self, legacy_repo):
        _, env = legacy_repo.run("config", "move")
        assert (legacy_repo.root / prose.LEGACY_CONFIG_PATH).exists()
        assert env["data"]["next"] == "delete %s" % prose.LEGACY_CONFIG_PATH

    def it_writes_nothing_on_a_dry_run(self, legacy_repo):
        code, env = legacy_repo.run("config", "move", "--dry-run")
        assert code == prose.OK
        assert env["data"]["dry_run"] is True
        assert not (legacy_repo.root / prose.CONFIG_DIR).exists()

    def it_refuses_to_overwrite_rules_already_in_place(self, prose_repo):
        (prose_repo.root / prose.LEGACY_CONFIG_PATH).write_text(LEGACY)
        before = prose_repo.read(prose.CONFIG_PATH)
        code, _ = prose_repo.run("config", "move")
        assert code == prose.CANNOT_RUN
        assert "already exists" in prose_repo.err
        assert prose_repo.read(prose.CONFIG_PATH) == before

    def it_refuses_when_there_is_no_root_file(self, prose_repo):
        code, _ = prose_repo.run("config", "move")
        assert code == prose.CANNOT_RUN
        assert "nothing to move" in prose_repo.err


class DescribeConfigCommandsBeforeTheMove:
    def it_points_to_config_move_when_only_the_root_file_exists(self, legacy_repo):
        code, _ = legacy_repo.run("config", "lint")
        assert code == prose.CANNOT_RUN
        assert "config move" in legacy_repo.err


class DescribePreflightWithARootFile:
    @pytest.mark.parametrize("skill", ["config", "apply", "adopt"])
    def it_blocks_every_skill_until_the_rules_are_moved(self, legacy_repo, skill):
        code, env = legacy_repo.run("preflight", "--for", skill)
        assert code == prose.PROBLEMS
        assert any("config move" in e for e in env["errors"])
        assert not any("config init" in e for e in env["errors"])

    def it_blocks_while_both_copies_exist(self, prose_repo):
        (prose_repo.root / prose.LEGACY_CONFIG_PATH).write_text(LEGACY)
        code, env = prose_repo.run("preflight", "--for", "config")
        assert code == prose.PROBLEMS
        assert any("delete the one at the root" in e for e in env["errors"])

    def it_passes_once_the_root_copy_is_gone(self, legacy_repo):
        legacy_repo.run("config", "move")
        (legacy_repo.root / prose.LEGACY_CONFIG_PATH).unlink()
        code, env = legacy_repo.run("preflight", "--for", "config")
        assert code == prose.OK, env["errors"]


class DescribePathsKey:
    @pytest.mark.parametrize("line", ['paths: ["**/*.md"]', "paths: docs/**"])
    def it_rejects_a_paths_key_that_would_stop_the_file_loading(self, config_from, line):
        config = config_from("---\nname: X\n%s\n---\n" % line)
        assert any("loading in every session" in e for e in config.errors)


class DescribeDefaultScope:
    def it_leaves_out_a_root_copy_awaiting_deletion(self, prose_repo):
        (prose_repo.root / prose.LEGACY_CONFIG_PATH).write_text(LEGACY)
        _, env = prose_repo.run("scope", "--all")
        verdict = {v["path"]: v for v in env["data"]["files"]}[prose.LEGACY_CONFIG_PATH]
        assert verdict["included"] is False

    def it_leaves_out_everything_under_the_claude_folder(self, prose_repo):
        other = prose_repo.root / prose.CONFIG_DIR / "other.md"
        other.write_text("# Another rule file\n")
        _, env = prose_repo.run("scope", "--all")
        verdict = {v["path"]: v for v in env["data"]["files"]}[".claude/rules/other.md"]
        assert verdict["included"] is False
        assert verdict["reason"] == "excluded by .claude/**"

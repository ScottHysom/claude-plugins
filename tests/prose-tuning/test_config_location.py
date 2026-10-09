"""Where a project keeps its rules.

The rules live in .claude/rules/, which Claude Code and Cowork both load into
every session.
"""

import pytest

import prose


class DescribeConfigInitLocation:
    @pytest.mark.spec("init-cmd-writes-shipped-rules")
    def it_creates_the_rules_folder_when_the_project_has_none(self, prose_repo):
        config = prose_repo.root / prose.CONFIG_PATH
        config.unlink()
        config.parent.rmdir()
        config.parent.parent.rmdir()
        code, env = prose_repo.run("config", "init")
        assert code == prose.OK, env["errors"]
        assert config.is_file()


class DescribePathsKey:
    @pytest.mark.spec("lint-cmd-refuses-paths-key")
    @pytest.mark.parametrize("line", ['paths: ["**/*.md"]', "paths: docs/**"])
    def it_rejects_a_paths_key_that_would_stop_the_file_loading(self, config_from, line):
        config = config_from("---\nname: X\n%s\n---\n" % line)
        assert any("loading in every session" in e for e in config.errors)

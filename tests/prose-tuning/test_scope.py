"""Glob patterns in the rule file's scope block decide which files are
governed. A pattern that over-matches puts prose rules on a changelog; one
that under-matches silently governs nothing.
"""

import pytest

import prose


class DescribeGlobToRegex:
    @pytest.mark.spec("globs-match-whole-path")
    @pytest.mark.parametrize(
        ("pattern", "path", "matches"),
        [
            ("**/*.md", "a.md", True),
            ("**/*.md", "x/y/a.md", True),
            ("*.md", "x/a.md", False),
            ("skills/**", "skills/a/b.md", True),
            ("skills/**", "skill/a.md", False),
            ("**/README.md", "README.md", True),
            ("**/README.md", "docs/README.md", True),
            ("prose-style.md", "a/prose-style.md", False),
        ],
    )
    def it_matches_a_path_against_a_pattern(self, pattern, path, matches):
        assert bool(prose.glob_to_regex(pattern).match(path)) is matches


class DescribeScopeCommand:
    def scope(self, prose_repo, capsys, rules=None):
        """Run `scope --all` without --json, and return its lines by path."""
        if rules is not None:
            (prose_repo.root / prose.CONFIG_PATH).write_text(rules)
        (prose_repo.root / "docs").mkdir()
        (prose_repo.root / "docs" / "guide.md").write_text("# Guide\n")
        capsys.readouterr()
        code = prose.main(["scope", "--all", "-C", str(prose_repo.root)])
        assert code == prose.OK
        lines = [line.split(None, 2) for line in capsys.readouterr().out.splitlines()]
        return {parts[1]: (parts[0], parts[2]) for parts in lines if parts[:1] in (["+"], ["-"])}

    @pytest.mark.spec("scope-explains")
    def it_lists_every_markdown_file_with_the_pattern_behind_its_verdict(self, prose_repo, capsys):
        verdicts = self.scope(prose_repo, capsys)
        assert verdicts["target.md"] == ("+", "included by **/*.md")
        assert verdicts["docs/guide.md"] == ("+", "included by **/*.md")
        assert prose.CONFIG_PATH in verdicts

    @pytest.mark.spec("scope-block-read")
    def it_leaves_out_a_file_no_include_pattern_matches(self, prose_repo, capsys):
        rules = '---\nname: T\nscope:\n  include:\n    - "docs/**"\n---\n'
        verdicts = self.scope(prose_repo, capsys, rules)
        assert verdicts["docs/guide.md"] == ("+", "included by docs/**")
        assert verdicts["target.md"] == ("-", "no include pattern matched")

    @pytest.mark.spec("rules-file-never-scoped")
    def it_leaves_out_the_rules_file_whatever_the_scope_says(self, prose_repo, capsys):
        rules = '---\nname: T\nscope:\n  include:\n    - "**"\n---\n'
        verdicts = self.scope(prose_repo, capsys, rules)
        assert verdicts[prose.CONFIG_PATH] == ("-", "the config itself")

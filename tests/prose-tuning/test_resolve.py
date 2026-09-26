"""Accepting keeps the <ins> side and drops the <del> side; rejecting does the
reverse. Getting this backwards silently discards the author's text, so both
directions are asserted against the exact expected output rather than against
a property.
"""

import pytest

import prose

MARKED = (
    "Keep <del>cut this</del><ins>keep this</ins> here.\n"
    '<repl why="noun phrase"><del>old</del><ins>new</ins></repl>\n'
)


class DescribeResolveText:
    @pytest.mark.spec("resolve-accepts-edits")
    def it_keeps_the_insertion_on_accept(self):
        got, scanner = prose.resolve_text(prose.Text(MARKED), prose.ACCEPT, None, "t.md")
        assert scanner.errors == []
        assert got == "Keep keep this here.\nnew\n"

    @pytest.mark.spec("strip-reverts")
    def it_restores_the_original_on_reject(self):
        got, scanner = prose.resolve_text(prose.Text(MARKED), prose.REJECT, None, "t.md")
        assert scanner.errors == []
        assert got == "Keep cut this here.\nold\n"


CUT_MIDDLE = "One.\n\n<del>\nTwo\nlines.\n</del>\n\nThree.\n"


def accept(source):
    got, scanner = prose.resolve_text(prose.Text(source), prose.ACCEPT, None, "t.md")
    assert scanner.errors == []
    return got


def reject(source):
    got, scanner = prose.resolve_text(prose.Text(source), prose.REJECT, None, "t.md")
    assert scanner.errors == []
    return got


class DescribeResolvingAWholeBlockCut:
    @pytest.mark.spec("resolve-tidies-cuts")
    def it_leaves_one_blank_line_where_a_paragraph_was_cut(self):
        assert accept(CUT_MIDDLE) == "One.\n\nThree.\n"

    @pytest.mark.spec("resolve-tidies-cuts")
    def it_treats_a_repl_with_an_empty_insertion_as_a_cut(self):
        source = "One.\n\n<repl>\n<del>\nTwo\n</del>\n<ins>\n</ins>\n</repl>\n\nThree.\n"
        assert accept(source) == "One.\n\nThree.\n"

    @pytest.mark.spec("resolve-tidies-cuts")
    def it_leaves_no_blank_line_at_the_start_when_the_first_block_is_cut(self):
        assert accept("<del>\nTwo\n</del>\n\nThree.\n") == "Three.\n"

    @pytest.mark.spec("resolve-tidies-cuts")
    def it_leaves_no_blank_line_at_the_end_when_the_last_block_is_cut(self):
        assert accept("One.\n\n<del>\nTwo\n</del>\n") == "One.\n"

    @pytest.mark.spec("resolve-tidies-cuts")
    def it_adds_no_newline_to_a_file_that_ended_without_one(self):
        assert accept("One.\n\n<del>\nTwo\n</del>") == "One."

    @pytest.mark.spec("resolve-tidies-cuts")
    def it_leaves_one_blank_line_where_adjacent_paragraphs_were_cut(self):
        source = "One.\n\n<del>\nTwo\n</del>\n\n<del>\nThree\n</del>\n\nFour.\n"
        assert accept(source) == "One.\n\nFour.\n"

    @pytest.mark.spec("resolve-tidies-cuts")
    def it_keeps_the_blank_lines_around_an_inline_cut(self):
        assert accept("One <del>two</del>.\n\n\nThree.\n") == "One .\n\n\nThree.\n"

    @pytest.mark.spec("strip-reverts")
    def it_keeps_every_blank_line_on_strip(self):
        source = "One.\n\n<ins>\nTwo\n</ins>\n\nThree.\n"
        assert reject(source) == "One.\n\n\nThree.\n"


class DescribeTagsResolve:
    @pytest.mark.spec("resolve-tidies-cuts")
    def it_leaves_one_blank_line_where_a_paragraph_was_cut(self, prose_repo):
        (prose_repo.root / "target.md").write_text(CUT_MIDDLE)
        code, envelope = prose_repo.run("tags", "resolve", "target.md")
        assert code == prose.OK, envelope
        assert prose_repo.read() == "One.\n\nThree.\n"

    @pytest.mark.spec("resolve-list-warning")
    def it_warns_when_it_resolves_a_block_tag_inside_a_list(self, prose_repo):
        """A tag between two list items can end the list, which the author
        has to look at, so the warning names the line.
        """
        (prose_repo.root / "target.md").write_text("- one\n  <del>\n  cut\n  </del>\n- two\n")
        code, envelope = prose_repo.run("tags", "resolve")
        assert code == prose.OK, envelope
        assert [w.split("  ")[0] for w in envelope["warnings"]] == ["target.md:2"]
        assert prose_repo.read() == "- one\n- two\n"

    @pytest.mark.spec("resolve-refuses-bad-markup")
    @pytest.mark.parametrize("which", ["resolve", "strip"])
    def it_writes_no_file_when_any_files_markup_does_not_parse(self, prose_repo, which):
        (prose_repo.root / "good.md").write_text("Keep <del>this</del>.\n")
        (prose_repo.root / "target.md").write_text("<del>never closed\n")
        code, envelope = prose_repo.run("tags", which)
        assert code == prose.PROBLEMS
        assert any("never closed" in e for e in envelope["errors"])
        assert prose_repo.read("good.md") == "Keep <del>this</del>.\n"

    @pytest.mark.spec("repo:plain-output-streams")
    def it_prints_each_file_it_resolved_with_its_tag_count(self, prose_repo, capsys):
        (prose_repo.root / "target.md").write_text(CUT_MIDDLE)
        capsys.readouterr()
        assert prose.main(["tags", "resolve", "-C", str(prose_repo.root)]) == prose.OK
        assert capsys.readouterr().out == "target.md  1 tag(s) resolved\n"
        assert prose.main(["tags", "resolve", "-C", str(prose_repo.root)]) == prose.OK
        assert capsys.readouterr().out == "no markup found\n"

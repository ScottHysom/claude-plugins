"""Accepting keeps the <ins> side and drops the <del> side; rejecting does the
reverse. Getting this backwards silently discards the author's text, so both
directions are asserted against the exact expected output rather than against
a property.
"""

import prose

MARKED = (
    "Keep <del>cut this</del><ins>keep this</ins> here.\n"
    '<repl why="noun phrase"><del>old</del><ins>new</ins></repl>\n'
)


class DescribeResolveText:
    def it_keeps_the_insertion_on_accept(self):
        got, scanner = prose.resolve_text(prose.Text(MARKED), prose.ACCEPT, None, "t.md")
        assert scanner.errors == []
        assert got == "Keep keep this here.\nnew\n"

    def it_restores_the_original_on_reject(self):
        got, scanner = prose.resolve_text(prose.Text(MARKED), prose.REJECT, None, "t.md")
        assert scanner.errors == []
        assert got == "Keep cut this here.\nold\n"

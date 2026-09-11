"""Accepting keeps the <ins> side and drops the <del> side; rejecting does the
reverse. Getting this backwards silently discards the author's text, so both
directions are asserted against the exact expected output rather than against
a property.
"""
import prose

MARKED = ('Keep <del>cut this</del><ins>keep this</ins> here.\n'
          '<repl why="noun phrase"><del>old</del><ins>new</ins></repl>\n')


def test_accept_keeps_the_insertion():
    got, scanner = prose.resolve_text(
        prose.Text(MARKED), prose.ACCEPT, None, "t.md")
    assert scanner.errors == []
    assert got == "Keep keep this here.\nnew\n"


def test_reject_restores_the_original():
    got, scanner = prose.resolve_text(
        prose.Text(MARKED), prose.REJECT, None, "t.md")
    assert scanner.errors == []
    assert got == "Keep cut this here.\nold\n"

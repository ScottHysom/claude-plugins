"""Text is the layer everything else addresses spans through.

If it loses a byte, every rewrite downstream writes a corrupted file, so the
guarantee is stated as an equality rather than a tolerance: join(lines) is the
original string.
"""

import pytest

import prose


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("", id="empty"),
        pytest.param("a", id="one-char-no-newline"),
        pytest.param("a\n", id="one-line"),
        pytest.param("a\nb", id="last-line-unterminated"),
        pytest.param("a\r\nb\r\n", id="crlf"),
        pytest.param("no trailing newline", id="prose-no-newline"),
        pytest.param("trailing blank\n\n", id="trailing-blank"),
    ],
)
def test_lines_rejoin_to_the_original(source):
    assert "".join(prose.Text(source).lines) == source


def test_lines_rejoin_to_the_original_for_the_sample(sample):
    assert "".join(prose.Text(sample).lines) == sample

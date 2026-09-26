"""Text is the layer everything else addresses spans through.

If it loses a byte, every rewrite downstream writes a corrupted file, so the
guarantee is stated as an equality rather than a tolerance: join(lines) is the
original string.
"""

import pytest

import prose


class DescribeText:
    @pytest.mark.spec("lines-kept-exactly")
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
    def it_rejoins_lines_into_the_original(self, source):
        assert "".join(prose.Text(source).lines) == source

    @pytest.mark.spec("lines-kept-exactly")
    def it_rejoins_the_sample_document_into_the_original(self, sample):
        assert "".join(prose.Text(sample).lines) == sample

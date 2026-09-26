"""A batch of findings that cuts whole lines leaves the layout it found.

test_apply.py pins the shapes by example. This states the promise for any
document made of paragraphs and any batch of cuts and rewrites over it: no two
blank lines touch, the file starts and ends without a blank line, and every
line nobody cut survives in order. Before #75, cutting a passage broke the
first of these for every passage longer than a line.

The findings go straight to plan_findings, so hypothesis needs no repo.
tags resolve makes the same promise for paragraphs cut by a block-form <del>,
which it broke before #93.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

import prose

RULE = "sentences-own-subject"
LINE = st.text(alphabet="abc", min_size=1, max_size=6)
PARAGRAPH = st.lists(LINE, min_size=1, max_size=4)


def document(paragraphs, final_newline):
    body = "\n\n".join("\n".join(p) for p in paragraphs)
    return body + "\n" if final_newline else body


@st.composite
def batches(draw):
    """A document and findings over its prose lines.

    Each chosen line is cut whole, cut in two side-by-side halves, cut along
    with the next line of its paragraph by one finding, or has its first
    character rewritten. All but the last remove the line. A whole cut gives
    no columns, since its text starts nowhere else on its line.
    """
    source = document(draw(st.lists(PARAGRAPH, min_size=1, max_size=5)), draw(st.booleans()))
    text = prose.Text(source)
    findings, removed = [], set()
    for n in range(1, text.line_count() + 1):
        bare = text.bare(n)
        if not bare or n in removed:
            continue
        spans = n < text.line_count() and bool(text.bare(n + 1))
        how = draw(st.sampled_from(["keep", "cut", "halves", "span", "rewrite"]))
        if how == "span" and not spans:
            how = "cut"
        if how == "cut":
            findings.append(anchored(n, bare, ""))
            removed.add(n)
        elif how == "span":
            findings.append(anchored(n, bare + "\n" + text.bare(n + 1), ""))
            removed.update((n, n + 1))
        elif how == "halves":
            mid = draw(st.integers(0, len(bare)))
            findings.append(finding(n, 0, mid, bare[:mid], ""))
            findings.append(finding(n, mid, len(bare), bare[mid:], ""))
            removed.add(n)
        elif how == "rewrite":
            findings.append(finding(n, 0, 1, bare[0], "z"))
    return source, findings, removed


def finding(line, col_start, col_end, text, replacement):
    return {
        "file": "doc.md",
        "rule": RULE,
        "line": line,
        "col_start": col_start,
        "col_end": col_end,
        "text": text,
        "replacement": replacement,
    }


def anchored(line, text, replacement):
    return {"file": "doc.md", "rule": RULE, "line": line, "text": text, "replacement": replacement}


def plan(source, findings):
    text = prose.Text(source)
    return prose.plan_findings(text, prose.Blocks(text), "doc.md", findings)


class DescribeWholeLineCuts:
    @given(batch=batches())
    def it_leaves_no_two_blank_lines_together(self, batch):
        source, findings, _ = batch
        new, _, rejected = plan(source, findings)
        assert rejected == []
        assert "\n\n\n" not in new

    @given(batch=batches())
    def it_leaves_no_blank_line_at_either_end(self, batch):
        source, findings, _ = batch
        new, _, _ = plan(source, findings)
        assert not new.startswith("\n")
        assert not new.endswith("\n\n")

    @given(batch=batches())
    def it_keeps_every_line_nobody_cut_in_order(self, batch):
        source, findings, removed = batch
        new, _, _ = plan(source, findings)
        text = prose.Text(source)
        rewritten = {f["line"] for f in findings if f["replacement"]}
        expected = []
        for n in range(1, text.line_count() + 1):
            line = text.bare(n)
            if line and n not in removed:
                expected.append("z" + line[1:] if n in rewritten else line)
        assert [ln for ln in new.split("\n") if ln] == expected


@st.composite
def tagged_cuts(draw):
    """A document with some whole paragraphs wrapped in a block-form <del>.

    Returns the tagged source and the paragraphs left once the cuts are taken.
    """
    paragraphs = draw(st.lists(PARAGRAPH, min_size=1, max_size=5))
    cuts = draw(st.lists(st.booleans(), min_size=len(paragraphs), max_size=len(paragraphs)))
    blocks = [
        "<del>\n%s\n</del>" % "\n".join(p) if c else "\n".join(p) for p, c in zip(paragraphs, cuts)
    ]
    source = "\n\n".join(blocks) + ("\n" if draw(st.booleans()) else "")
    kept = [p for p, c in zip(paragraphs, cuts) if not c]
    return source, kept


def accept(source):
    got, scanner = prose.resolve_text(prose.Text(source), prose.ACCEPT, None, "doc.md")
    assert scanner.errors == []
    return got


class DescribeResolvedBlockCuts:
    @pytest.mark.spec("resolve-tidies-cuts")
    @given(batch=tagged_cuts())
    def it_leaves_no_two_blank_lines_together(self, batch):
        source, _ = batch
        assert "\n\n\n" not in accept(source)

    @pytest.mark.spec("resolve-tidies-cuts")
    @given(batch=tagged_cuts())
    def it_leaves_no_blank_line_at_either_end(self, batch):
        source, _ = batch
        new = accept(source)
        assert not new.startswith("\n")
        assert not new.endswith("\n\n")

    @pytest.mark.spec("resolve-tidies-cuts")
    @given(batch=tagged_cuts())
    def it_keeps_every_paragraph_nobody_cut_in_order(self, batch):
        source, kept = batch
        new = accept(source).rstrip("\n")
        assert new == "\n\n".join("\n".join(p) for p in kept)

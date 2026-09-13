"""An edit that only changed a number, a link or some whitespace is not a
prose decision. Classifying those keeps them out of the evidence the model is
asked to infer a rule from.
"""

import pytest

import prose


@pytest.mark.parametrize(
    ("before", "after", "signal"),
    [
        pytest.param("we saw 3 things", "we saw 4 things", "numeric-only", id="numeric"),
        pytest.param("a  b", "a b", "whitespace-only", id="whitespace"),
        pytest.param("see [x](/a)", "see [x](/b)", "link-only", id="link"),
        pytest.param("short line", "a longer line", None, id="real-edit"),
    ],
)
def test_signal_classification(before, after, signal):
    assert prose.classify_signal(before, after) == signal


class TestInferredEdits:
    """What `evidence` reports for edits the author made without tagging them.

    Those hunks are the evidence adopt-prose infers rules from, and each one
    names a line the author is sent to. A hunk at the wrong line, or one that
    covers the wrong lines, points the model at text that was never changed.
    """

    def edit(self, prose_repo, target, changes, insert_at=None, inserted=None):
        lines = target.split("\n")
        for index, line in changes.items():
            lines[index] = line
        if insert_at is not None:
            lines.insert(insert_at, inserted)
        (prose_repo.root / "target.md").write_text("\n".join(lines))

    def inferred(self, prose_repo, *flags):
        code, envelope = prose_repo.run("evidence", *flags)
        assert code == prose.OK, envelope["errors"]
        return envelope["data"]["inferred"]

    def test_a_replacement_and_an_insertion_since_the_last_commit(self, prose_repo, target):
        prose_repo.commit()
        self.edit(
            prose_repo,
            target,
            {
                6: "Curated with care, not collected. A resource earns a place here only after",
                7: "it has been used for something real.",
            },
            insert_at=20,
            inserted="A closing line nobody had written.",
        )
        assert self.inferred(prose_repo) == [
            {
                "file": "target.md",
                "start": 7,
                "end": 8,
                "change": "replace",
                "old_lines": [
                    "Curated, not collected. A resource earns a place here only after it has been",
                    "used for something.",
                ],
                "new_lines": [
                    "Curated with care, not collected. A resource earns a place here only after",
                    "it has been used for something real.",
                ],
                "signal": None,
            },
            {
                "file": "target.md",
                "start": 21,
                "end": 21,
                "change": "insert",
                "old_lines": [],
                "new_lines": ["A closing line nobody had written."],
                "signal": None,
            },
        ]

    def test_lines_are_numbered_as_the_author_sees_the_file(self, prose_repo, target):
        """Markup is taken out before the diff, so a question the author has
        not answered is not reported as an edit. The line numbers still have
        to be the working file's, with the question's line counted, or every
        hunk below it is reported one line early.
        """
        prose_repo.commit()
        self.edit(
            prose_repo,
            target,
            {19: "Final paragraph, now longer."},
            insert_at=7,
            inserted='<q id="1">does this earn its place?</q>',
        )
        hunks = self.inferred(prose_repo)
        assert [(h["start"], h["end"], h["new_lines"]) for h in hunks] == [
            (21, 21, ["Final paragraph, now longer."])
        ]

    def test_ignore_suppresses_one_hunk_by_its_file_and_line(self, prose_repo, target):
        prose_repo.commit()
        self.edit(
            prose_repo,
            target,
            {7: "used for something real.", 19: "Final paragraph, now longer."},
        )
        assert [h["start"] for h in self.inferred(prose_repo)] == [8, 20]
        assert [h["start"] for h in self.inferred(prose_repo, "--ignore", "target.md:8")] == [20]

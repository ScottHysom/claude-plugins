"""An edit that only changed a number, a link or some whitespace is not a
prose decision. Classifying those keeps them out of the evidence the model is
asked to infer a rule from.
"""

import pytest

import prose


class DescribeClassifySignal:
    @pytest.mark.spec("hunk-signal")
    @pytest.mark.parametrize(
        ("before", "after", "signal"),
        [
            pytest.param("we saw 3 things", "we saw 4 things", "numeric-only", id="numeric"),
            pytest.param("a  b", "a b", "whitespace-only", id="whitespace"),
            pytest.param("see [x](/a)", "see [x](/b)", "link-only", id="link"),
            pytest.param("short line", "a longer line", None, id="real-edit"),
        ],
    )
    def it_names_the_signal_an_edit_carries(self, before, after, signal):
        assert prose.classify_signal(before, after) == signal


class DescribeInferredEdits:
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

    @pytest.mark.spec("inferred-hunks")
    def it_reports_a_replacement_and_an_insertion_since_the_last_commit(self, prose_repo, target):
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

    @pytest.mark.spec("markup-not-evidence")
    def it_numbers_lines_as_the_author_sees_the_file(self, prose_repo, target):
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

    def it_suppresses_one_hunk_by_its_file_and_line(self, prose_repo, target):
        prose_repo.commit()
        self.edit(
            prose_repo,
            target,
            {7: "used for something real.", 19: "Final paragraph, now longer."},
        )
        assert [h["start"] for h in self.inferred(prose_repo)] == [8, 20]
        assert [h["start"] for h in self.inferred(prose_repo, "--ignore", "target.md:8")] == [20]

    @pytest.mark.spec("markup-not-evidence")
    def it_places_a_hunk_on_a_line_that_also_holds_markup(self, prose_repo, target):
        """With the markup taken out, the edited line no longer matches its
        working-file line, so the hunk is placed from the nearest line that
        does. The question above shifts every line below it by one.
        """
        prose_repo.commit()
        self.edit(
            prose_repo,
            target,
            {19: "Final <ins>short </ins>paragraph, now longer."},
            insert_at=7,
            inserted='<q id="1">does this earn its place?</q>',
        )
        assert [h["start"] for h in self.inferred(prose_repo)] == [21]


def evidence(prose_repo, body):
    """Commit the conftest's target, write body in its place, and run evidence."""
    prose_repo.commit()
    (prose_repo.root / "target.md").write_text(body)
    code, envelope = prose_repo.run("evidence")
    assert code == prose.OK, envelope["errors"]
    return envelope["data"]


def shape(record):
    return {k: record[k] for k in ("kind", "start", "old_text", "new_text", "why", "alt", "form")}


class DescribeExplicitRecords:
    """What `evidence` reports for markup the author wrote.

    The author has already said what each tagged edit means, so the model
    takes these records at face value. A lost `why` or `<alt>` is a reason the
    author gave that never reaches the rule.
    """

    @pytest.mark.spec("explicit-records", "bare-pair-is-replacement")
    def it_reports_a_bare_pair_as_one_replacement(self, prose_repo):
        data = evidence(
            prose_repo, "Intro.\n\n<del>Curated, not collected.</del><ins>Curated.</ins>\n"
        )
        assert [shape(r) for r in data["explicit"]] == [
            {
                "kind": "repl",
                "start": 3,
                "old_text": "Curated, not collected.",
                "new_text": "Curated.",
                "why": [],
                "alt": [],
                "form": "pair",
            }
        ]

    @pytest.mark.spec("explicit-records")
    def it_reports_a_replacement_with_its_reason_and_proposals(self, prose_repo):
        body = (
            "Intro.\n\n"
            "<repl>\n"
            "  <why>Three sentences carrying one claim.</why>\n"
            "  <alt>Keep the fact; cut the rest.</alt>\n"
            "  <alt>Curated.</alt>\n"
            "  <del>Curated, not collected.</del>\n"
            "  <ins>Curated.</ins>\n"
            "</repl>\n"
        )
        assert [shape(r) for r in evidence(prose_repo, body)["explicit"]] == [
            {
                "kind": "repl",
                "start": 3,
                "old_text": "Curated, not collected.",
                "new_text": "Curated.",
                "why": ["Three sentences carrying one claim."],
                "alt": ["Keep the fact; cut the rest.", "Curated."],
                "form": "block",
            }
        ]

    @pytest.mark.spec("explicit-records")
    def it_reports_a_lone_deletion_and_a_lone_insertion(self, prose_repo):
        body = 'Intro <del why="restates">again</del>.\n\nEnd<ins> here</ins>.\n'
        assert [shape(r) for r in evidence(prose_repo, body)["explicit"]] == [
            {
                "kind": "del",
                "start": 1,
                "old_text": "again",
                "new_text": "",
                "why": ["restates"],
                "alt": [],
                "form": "inline",
            },
            {
                "kind": "ins",
                "start": 3,
                "old_text": "",
                "new_text": "here",
                "why": [],
                "alt": [],
                "form": "inline",
            },
        ]


class DescribeAnswers:
    """An `<a>` the author writes in the document answers the `<q>` above it."""

    @pytest.mark.spec("answers-read")
    def it_pairs_each_answer_with_the_question_above_it(self, prose_repo):
        body = (
            "One.\n\n"
            '<q id="1">Fact or style?</q>\n'
            "<a>Style.</a>\n\n"
            '<q id="2">And this one?</q>\n\n'
            '<q id="3">Last?</q>\n'
            "<a>Yes.</a>\n"
        )
        questions = evidence(prose_repo, body)["questions"]
        assert [(q["id"], q["line"], q["answer"]) for q in questions] == [
            ("1", 3, "Style."),
            ("2", 6, None),
            ("3", 8, "Yes."),
        ]


class DescribePlainOutput:
    @pytest.mark.spec("repo:plain-output-streams")
    def it_prints_each_record_and_the_counts(self, prose_repo, target, capsys):
        prose_repo.commit()
        body = target.replace("Final paragraph.", "Final paragraph, now longer.").replace(
            "Curated, not collected.", '<del why="restates">Curated, not collected.</del>'
        )
        (prose_repo.root / "target.md").write_text(body + '<q id="1">why?</q>\n')
        capsys.readouterr()
        assert prose.main(["evidence", "-C", str(prose_repo.root)]) == prose.OK
        out = capsys.readouterr().out
        assert "  explicit target.md:7 [del] restates\n" in out
        assert "  inferred target.md:20 [replace]\n" in out
        assert "  question target.md:25 #1 OPEN\n" in out
        assert "explicit: 1  inferred: 1  unanswered: 1\n" in out

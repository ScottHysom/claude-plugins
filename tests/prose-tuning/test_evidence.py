"""An edit that only changed a number, a link or some whitespace is not a
prose decision. Classifying those keeps them out of the evidence the model is
asked to infer a rule from.
"""

import pytest

import prose


class DescribeClassifySignal:
    @pytest.mark.spec("evidence-cmd-marks-hunk-signals")
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

    Those hunks are the evidence update-prose-config infers rules from, and each one
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

    def inferred(self, prose_repo):
        code, envelope = prose_repo.run("evidence")
        assert code == prose.OK, envelope["errors"]
        return envelope["data"]["inferred"]

    @pytest.mark.spec("evidence-cmd-reports-inferred-hunks")
    def it_infers_nothing_from_a_file_that_has_no_copy_at_the_last_commit(self, prose_repo, target):
        prose_repo.commit()
        (prose_repo.root / "new.md").write_text("A page written since the last commit.\n")
        assert self.inferred(prose_repo) == []

    @pytest.mark.spec("evidence-cmd-reports-inferred-hunks")
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

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    def it_numbers_lines_as_the_author_sees_the_file(self, prose_repo, target):
        """Markup is taken out before the diff, so an `<alt>` the author has
        written on a line of its own is not reported as an edit. The line
        numbers still have to be the working file's, with the `<alt>`'s line
        counted, or every hunk below it is reported one line early.
        """
        prose_repo.commit()
        self.edit(
            prose_repo,
            target,
            {19: "Final paragraph, now longer."},
            insert_at=7,
            inserted="<alt>Cut a sentence that does not earn its place.</alt>",
        )
        hunks = self.inferred(prose_repo)
        assert [(h["start"], h["end"], h["new_lines"]) for h in hunks] == [
            (21, 21, ["Final paragraph, now longer."])
        ]

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    def it_places_a_hunk_on_a_line_that_also_holds_markup(self, prose_repo, target):
        """With the markup taken out, the edited line no longer matches its
        working-file line, so the hunk is placed from the nearest line that
        does. The `<alt>` above shifts every line below it by one.
        """
        prose_repo.commit()
        self.edit(
            prose_repo,
            target,
            {19: "Final <ins>short </ins>paragraph, now longer."},
            insert_at=7,
            inserted="<alt>Cut a sentence that does not earn its place.</alt>",
        )
        assert [h["start"] for h in self.inferred(prose_repo)] == [21]

    @pytest.mark.spec("evidence-cmd-diffs-without-markup")
    @pytest.mark.parametrize(
        "tag",
        [
            pytest.param("<why>Is this a fact fix?</why>", id="why"),
            pytest.param("<ins>A paragraph the author added.</ins>", id="ins"),
        ],
    )
    def it_reports_nothing_for_a_tag_set_apart_between_paragraphs(self, prose_repo, target, tag):
        """The tag needs a blank line below it as well as the one above, and
        only the one above was there before the author tagged the file.
        """
        prose_repo.commit()
        self.edit(prose_repo, target, {}, insert_at=9, inserted=tag + "\n")
        assert self.inferred(prose_repo) == []

    @pytest.mark.spec("evidence-cmd-skips-comment-hunks")
    @pytest.mark.parametrize(
        ("index", "line"),
        [
            pytest.param(None, "<!-- spec: some-requirement -->", id="own-line"),
            pytest.param(19, "Final <!-- FILL: say more --> paragraph.", id="inline"),
            pytest.param(None, "<!-- a note\n     over two lines -->", id="multi-line"),
            pytest.param(22, "A different note for the next editor.", id="inside-comment"),
        ],
    )
    def it_leaves_out_a_hunk_that_changed_only_comments(self, prose_repo, target, index, line):
        """The edit to line 8 stays, so a hunk that went missing for some
        other reason does not pass for one left out.
        """
        prose_repo.commit()
        changes = {7: "used for something real."}
        if index is None:
            self.edit(prose_repo, target, changes, insert_at=12, inserted="\n" + line)
        else:
            self.edit(prose_repo, target, {**changes, index: line})
        assert [h["start"] for h in self.inferred(prose_repo)] == [8]

    @pytest.mark.spec("evidence-cmd-skips-comment-hunks")
    def it_reports_a_hunk_that_changed_prose_beside_a_comment(self, prose_repo, target):
        prose_repo.commit()
        self.edit(prose_repo, target, {19: "Final <!-- FILL: say more --> words."})
        assert [h["new_lines"] for h in self.inferred(prose_repo)] == [
            ["Final <!-- FILL: say more --> words."]
        ]


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

    @pytest.mark.spec("evidence-cmd-reports-explicit-records", "scanner-pairs-del-and-ins")
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

    @pytest.mark.spec("evidence-cmd-reports-explicit-records")
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

    @pytest.mark.spec("evidence-cmd-reports-explicit-records")
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

    @pytest.mark.spec("evidence-cmd-reports-standalone-alts")
    def it_reports_an_alt_tied_to_no_passage(self, prose_repo):
        body = "# Doc\n\nA line.\n\n<alt>Headings never editorialize.</alt>\n"
        records = evidence(prose_repo, body)["explicit"]
        assert [shape(r) for r in records] == [
            {
                "kind": "alt",
                "start": 5,
                "old_text": "",
                "new_text": "",
                "why": [],
                "alt": ["Headings never editorialize."],
                "form": "block",
            }
        ]
        assert records[0]["file"] == "target.md"
        assert records[0]["heading_path"] == ["Doc"]


class DescribePlainOutput:
    @pytest.mark.spec("repo:command-splits-output-streams-without-json")
    def it_prints_each_record_and_the_counts(self, prose_repo, target, capsys):
        prose_repo.commit()
        body = target.replace("Final paragraph.", "Final paragraph, now longer.").replace(
            "Curated, not collected.", '<del why="restates">Curated, not collected.</del>'
        )
        (prose_repo.root / "target.md").write_text(body)
        capsys.readouterr()
        assert prose.main(["evidence", "-C", str(prose_repo.root)]) == prose.OK
        out = capsys.readouterr().out
        assert "  explicit target.md:7 [del] restates\n" in out
        assert "  inferred target.md:20 [replace]\n" in out
        assert "explicit: 1  inferred: 1  breaches: 0\n" in out


class DescribeRules:
    """The rules `evidence` reports beside the edits, which every candidate
    rule is checked against before it is drafted. A rewrite of one quotes its
    body to `config write` as `expect`, so the body is the one `config list`
    gives.
    """

    @pytest.mark.spec("evidence-gives-rules")
    def it_reports_each_rule_with_its_id_body_and_patterns(self, prose_repo):
        config = prose_repo.root / prose.CONFIG_PATH
        config.write_text(
            config.read_text()
            + "\n### sentences-no-in-order-to: Write to, not in order to\n\n"
            + "The two extra words carry nothing.\n\n"
            + "**Pattern.** `\\bin order to\\b`\n\n"
            + "> **Before.** Run it in order to check.\n"
            + "> **After.** Run it to check.\n"
        )
        prose_repo.commit()
        code, envelope = prose_repo.run("evidence")
        assert code == prose.OK, envelope["errors"]
        _, listed = prose_repo.run("config", "list")
        assert envelope["data"]["rules"] == [
            {"id": r["id"], "body": r["body"], "patterns": r["patterns"]}
            for r in listed["data"]["rules"]
        ]
        assert [(r["id"], r["patterns"]) for r in envelope["data"]["rules"]] == [
            ("sentences-own-subject", []),
            ("sentences-no-in-order-to", ["\\bin order to\\b"]),
        ]


BREACH_STYLE = """---
name: Probe
---

## Register

### register-plain-words: Say it plainly

**Pattern.** `(?i)in order to`

> **Before.** In order to run it.
> **After.** To run it.
"""

BREACH_RULE = "register-plain-words"

BREACH_BEFORE = """# Notes

We run it to check the build.

It keeps the notes short, and the lists shorter.
"""


class DescribeBreaches:
    """The edits whose new text a rule already written would flag. Each is an
    exception to the rule, a sign the rule is wrong, or a slip in the edit,
    and update-prose-config asks the author which before it learns from it.
    """

    def evidence(self, prose_repo, after, style=BREACH_STYLE, before=BREACH_BEFORE):
        (prose_repo.root / prose.CONFIG_PATH).write_text(style)
        (prose_repo.root / "target.md").write_text(before)
        prose_repo.commit()
        (prose_repo.root / "target.md").write_text(after)
        code, envelope = prose_repo.run("evidence")
        assert code == prose.OK, envelope["errors"]
        return envelope

    @pytest.mark.spec("evidence-cmd-marks-breaching-edits")
    def it_marks_an_edit_whose_new_text_a_pattern_matches(self, prose_repo):
        env = self.evidence(prose_repo, BREACH_BEFORE.replace("run it to", "run it in order to"))
        [edit] = env["data"]["breaches"]
        assert (edit["file"], edit["start"], edit["new_lines"]) == (
            "target.md",
            3,
            ["We run it in order to check the build."],
        )
        assert [(m["rule"], m["line"], m["text"]) for m in edit["matches"]] == [
            (BREACH_RULE, 3, "in order to")
        ]

    @pytest.mark.spec("evidence-cmd-marks-breaching-edits")
    def it_marks_a_paragraph_the_author_added(self, prose_repo):
        env = self.evidence(prose_repo, BREACH_BEFORE + "\nWe run it in order to see.\n")
        [edit] = env["data"]["breaches"]
        assert (edit["change"], edit["matches"][0]["text"]) == ("insert", "in order to")

    @pytest.mark.spec("evidence-cmd-marks-breaching-edits")
    def it_marks_a_cut_that_joins_text_into_a_match(self, prose_repo):
        before = BREACH_BEFORE.replace("run it to", "run it in order so as to")
        env = self.evidence(
            prose_repo, BREACH_BEFORE.replace("run it to", "run it in order to"), before=before
        )
        [edit] = env["data"]["breaches"]
        assert edit["matches"][0]["text"] == "in order to"

    @pytest.mark.spec("evidence-cmd-marks-breaching-edits")
    def it_reads_the_authors_markup_as_resolved(self, prose_repo):
        env = self.evidence(
            prose_repo, BREACH_BEFORE.replace("run it to", "run it <ins>in order </ins>to")
        )
        [edit] = env["data"]["breaches"]
        assert edit["new_lines"] == ["We run it in order to check the build."]
        assert [r["kind"] for r in env["data"]["explicit"]] == ["ins"]

    @pytest.mark.spec("evidence-cmd-marks-breaching-edits")
    def it_does_not_mark_an_edit_beside_a_match_it_did_not_make(self, prose_repo):
        """The line already broke the rule at the last commit, and the edit
        changed other words on it, so the author did not write the match.
        """
        before = BREACH_BEFORE.replace("run it to", "run it in order to")
        env = self.evidence(
            prose_repo, before.replace("the build", "the whole build"), before=before
        )
        assert env["data"]["breaches"] == []
        assert len(env["data"]["inferred"]) == 1

    @pytest.mark.spec("evidence-cmd-marks-breaching-edits")
    def it_does_not_mark_a_cut_at_the_edge_of_a_match(self, prose_repo):
        before = BREACH_BEFORE.replace("run it to", "run it in order to, again,")
        env = self.evidence(prose_repo, before.replace(", again,", ""), before=before)
        assert env["data"]["breaches"] == []

    @pytest.mark.spec("evidence-cmd-marks-breaching-edits")
    def it_does_not_mark_an_edit_that_removes_a_match(self, prose_repo):
        before = BREACH_BEFORE.replace("run it to", "run it in order to")
        env = self.evidence(prose_repo, BREACH_BEFORE, before=before)
        assert env["data"]["breaches"] == []

    @pytest.mark.spec("evidence-cmd-marks-breaching-edits")
    def it_warns_and_checks_nothing_when_the_rule_file_does_not_lint(self, prose_repo):
        """The pattern still compiles, and lint refuses it for matching the
        After example, so a check would have found the edit.
        """
        style = BREACH_STYLE.replace("**After.** To run it.", "**After.** In order to run it.")
        env = self.evidence(
            prose_repo, BREACH_BEFORE.replace("run it to", "run it in order to"), style=style
        )
        assert env["data"]["breaches"] == []
        assert any("does not lint" in w for w in env["warnings"])

    @pytest.mark.spec("repo:command-splits-output-streams-without-json")
    def it_prints_each_match_an_edit_makes(self, prose_repo, capsys):
        self.evidence(prose_repo, BREACH_BEFORE.replace("run it to", "run it in order to"))
        capsys.readouterr()
        assert prose.main(["evidence", "-C", str(prose_repo.root)]) == prose.OK
        out = capsys.readouterr().out
        assert "  breaches target.md:3 [%s] 'in order to'" % BREACH_RULE in out
        assert "explicit: 0  inferred: 1  breaches: 1" in out

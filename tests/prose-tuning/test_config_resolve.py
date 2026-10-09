"""config resolve writes the author's answer to each colliding and similar
pair into the target.

The model hands it the answers as JSON rather than editing the target, so
every answer is checked against both files as they are now, and a batch with
one bad answer writes nothing unless --partial is passed.
"""

import json

import pytest

import prose

HEAD = "---\nname: T\n---\n\n"

OWN_SUBJECT = (
    "### sentences-own-subject: Carries its own subject\n"
    "\n"
    "A sentence that borrows its subject\n"
    "   from the heading   above it is incomplete.\n"
    "\n"
    "**Pattern.** `^Able to`\n"
    "\n"
    "> **Before.** Able to state it.\n"
    "> **After.** A reader can state it.\n"
)
OWN_SUBJECT_THEIRS = (
    "### sentences-own-subject: Carries its own subject\n"
    "\n"
    "Every sentence names who or what it is about.\n"
    "\n"
    "> **Before.** Able to state it.\n"
    "> **After.** A reader can state it.\n"
)
CARRIES = (
    "### sentences-carries-subject: Names its subject\n"
    "\n"
    "A sentence that borrows its subject from the heading is incomplete.\n"
    "\n"
    "> **Before.** Able to read it.\n"
    "> **After.** A reader can read it.\n"
)
COUNT = (
    "### sentences-count-needs-list: A count needs a list\n"
    "\n"
    "A count needs its list nearby.\n"
    "\n"
    "> **Before.** Three rules apply.\n"
    "> **After.** These rules apply:\n"
)
TONE = (
    "### register-plain-words: Plain words\n"
    "\n"
    "Use plain words over jargon.\n"
    "\n"
    "> **Before.** Leverage it.\n"
    "> **After.** Use it.\n"
)


def files(prose_repo, source, target):
    src, tgt = prose_repo.root / "source.md", prose_repo.root / "target-style.md"
    src.write_text(HEAD + "## Sentences\n\n" + source)
    tgt.write_text(HEAD + "## Sentences\n\n" + target)
    return src, tgt


def body(path, rid):
    return prose.Config(str(path)).by_id()[rid].body_text()


def answer(src, tgt, source, target, resolution, **parts):
    rec = {
        "source": source,
        "target": target,
        "resolution": resolution,
        "expect": {"source": body(src, source), "target": body(tgt, target)},
    }
    rec.update(parts)
    return rec


def resolve(prose_repo, src, tgt, answers, *flags):
    path = prose_repo.root / "answers.json"
    path.write_text(json.dumps(answers))
    return prose_repo.run(
        "config", "resolve", "--file", str(src), "--to", str(tgt), "--answers", str(path), *flags
    )


COMBINED = {
    "title": "Names its subject",
    "body": "A sentence names its own subject, never the heading's.",
    "example": {"before": "Able to read it.", "after": "A reader can read it."},
}


class DescribeAnswersWritten:
    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_puts_the_source_rule_in_place_of_the_target_rule_on_take_source(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, OWN_SUBJECT_THEIRS + "\n" + COUNT)
        ans = answer(src, tgt, "sentences-own-subject", "sentences-own-subject", "take-source")
        code, _ = resolve(prose_repo, src, tgt, [ans])
        assert code == prose.OK
        assert tgt.read_text() == HEAD + "## Sentences\n\n" + OWN_SUBJECT + "\n" + COUNT

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_leaves_the_target_as_it_was_on_keep_target(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, OWN_SUBJECT_THEIRS)
        before = tgt.read_bytes()
        ans = answer(src, tgt, "sentences-own-subject", "sentences-own-subject", "keep-target")
        code, env = resolve(prose_repo, src, tgt, [ans])
        assert (code, env["data"]["resolved"][0]["resolution"]) == (prose.OK, "keep-target")
        assert tgt.read_bytes() == before

    @pytest.mark.spec("resolve-cmd-writes-answers", "adoptprose-keeps-target-id")
    def it_writes_a_combination_under_the_target_id(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES + "\n" + COUNT)
        ans = answer(
            src, tgt, "sentences-own-subject", "sentences-carries-subject", "combine", **COMBINED
        )
        code, _ = resolve(prose_repo, src, tgt, [ans])
        text = tgt.read_text()
        assert code == prose.OK
        assert "### sentences-carries-subject: Names its subject\n\nA sentence names" in text
        assert "sentences-own-subject" not in text
        assert text.endswith("A reader can read it.\n\n" + COUNT)

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_combines_a_collision_under_the_shared_id(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, OWN_SUBJECT_THEIRS)
        ans = answer(
            src,
            tgt,
            "sentences-own-subject",
            "sentences-own-subject",
            "combine",
            body="Every sentence names its own subject.",
        )
        code, _ = resolve(prose_repo, src, tgt, [ans])
        assert code == prose.OK
        assert body(tgt, "sentences-own-subject").startswith("Every sentence names its own")

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_copies_the_source_rule_in_beside_the_target_rule_on_keep_both(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES + "\n## Register\n\n" + TONE)
        ans = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "keep-both")
        code, _ = resolve(prose_repo, src, tgt, [ans])
        assert code == prose.OK
        assert "A reader can read it.\n\n" + OWN_SUBJECT + "\n## Register" in tgt.read_text()

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_leaves_the_source_rule_out_on_drop_source(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        before = tgt.read_bytes()
        ans = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "drop-source")
        code, _ = resolve(prose_repo, src, tgt, [ans])
        assert code == prose.OK
        assert tgt.read_bytes() == before

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_writes_every_answer_in_one_pass(self, prose_repo):
        src, tgt = files(
            prose_repo,
            OWN_SUBJECT + "\n" + COUNT.replace("nearby", "close by"),
            CARRIES + "\n" + COUNT,
        )
        answers = [
            answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "keep-both"),
            answer(
                src, tgt, "sentences-count-needs-list", "sentences-count-needs-list", "take-source"
            ),
        ]
        code, env = resolve(prose_repo, src, tgt, answers)
        assert code == prose.OK
        assert [r["resolution"] for r in env["data"]["resolved"]] == ["keep-both", "take-source"]
        assert body(tgt, "sentences-count-needs-list").startswith("A count needs its list close")
        assert "sentences-own-subject" in prose.Config(str(tgt)).by_id()

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_refuses_a_resolution_the_pair_does_not_offer(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES + "\n" + OWN_SUBJECT_THEIRS)
        answers = [
            answer(src, tgt, "sentences-own-subject", "sentences-own-subject", "keep-both"),
            answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "take-source"),
        ]
        _, env = resolve(prose_repo, src, tgt, answers, "--partial")
        reasons = [r["reason"] for r in env["data"]["refused"]]
        assert reasons[0] == (
            "keep-both does not settle a collision; it takes take-source, keep-target, combine"
        )
        assert reasons[1].startswith("take-source does not settle a pair under two ids")

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_refuses_a_source_rule_answered_twice(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES + "\n" + COUNT)
        answers = [
            answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "drop-source"),
            answer(src, tgt, "sentences-own-subject", "sentences-count-needs-list", "keep-both"),
        ]
        _, env = resolve(prose_repo, src, tgt, answers)
        assert env["data"]["refused"][0]["reason"] == (
            "sentences-own-subject is answered by answer 1 too"
        )

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_refuses_a_target_rule_written_twice(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT + "\n" + COUNT, CARRIES)
        answers = [
            answer(
                src,
                tgt,
                "sentences-own-subject",
                "sentences-carries-subject",
                "combine",
                **COMBINED,
            ),
            answer(
                src,
                tgt,
                "sentences-count-needs-list",
                "sentences-carries-subject",
                "combine",
                **COMBINED,
            ),
        ]
        _, env = resolve(prose_repo, src, tgt, answers)
        assert env["data"]["refused"][0]["reason"] == (
            "sentences-carries-subject is written by answer 1 too"
        )

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_refuses_to_keep_both_when_the_target_has_the_source_id(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES + "\n" + OWN_SUBJECT_THEIRS)
        ans = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "keep-both")
        _, env = resolve(prose_repo, src, tgt, [ans])
        assert env["data"]["refused"][0]["reason"] == (
            "target-style.md already has sentences-own-subject"
        )

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_refuses_parts_on_a_resolution_other_than_combine(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        ans = answer(
            src, tgt, "sentences-own-subject", "sentences-carries-subject", "keep-both", title="X"
        )
        _, env = resolve(prose_repo, src, tgt, [ans])
        assert env["data"]["refused"][0]["reason"] == "only combine takes title"

    @pytest.mark.spec("resolve-cmd-writes-answers")
    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            (lambda a: "not an object", "answer is not an object"),
            (lambda a: dict(a, extra=1), "unknown field extra; an answer takes"),
            (lambda a: {k: v for k, v in a.items() if k != "expect"}, "an answer needs expect"),
            (lambda a: dict(a, resolution=3), "source, target and resolution are not strings"),
            (lambda a: dict(a, expect="x"), "expect is not an object with source and target"),
            (lambda a: dict(a, source="sentences-nope"), "source.md has no rule sentences-nope"),
            (lambda a: dict(a, body="## Heading"), "body holds a heading: '## Heading'"),
            (lambda a: dict(a, patterns=["nowhere"]), "no pattern of sentences-carries-subject"),
        ],
    )
    def it_refuses_an_answer_it_cannot_write(self, prose_repo, change, reason):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        ans = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "combine")
        code, env = resolve(prose_repo, src, tgt, [change(ans)])
        assert code == prose.PROBLEMS
        assert env["data"]["refused"][0]["reason"].startswith(reason)

    @pytest.mark.spec("resolve-cmd-writes-answers")
    def it_cannot_run_on_answers_that_are_not_a_list(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        code, _ = resolve(prose_repo, src, tgt, {"source": "x"})
        assert code == prose.CANNOT_RUN
        assert "the answers are not a JSON list" in prose_repo.err

    @pytest.mark.spec("classify-cmd-names-missing-target")
    def it_refuses_a_missing_target_file(self, prose_repo):
        src, _ = files(prose_repo, OWN_SUBJECT, "")
        missing = prose_repo.root / "nowhere.md"
        code, env = resolve(prose_repo, src, missing, [])
        assert (code, env) == (prose.CANNOT_RUN, None)
        assert "nowhere.md does not exist" in prose_repo.err


class DescribeStaleAnswers:
    @pytest.mark.spec("resolve-cmd-refuses-stale")
    def it_refuses_an_answer_whose_source_body_changed(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, OWN_SUBJECT_THEIRS)
        ans = answer(src, tgt, "sentences-own-subject", "sentences-own-subject", "take-source")
        src.write_text(src.read_text().replace("incomplete", "unfinished"))
        before = tgt.read_bytes()
        code, env = resolve(prose_repo, src, tgt, [ans])
        assert code == prose.PROBLEMS
        assert env["data"]["refused"][0]["reason"].startswith(
            "the body of sentences-own-subject in source.md is not what expect holds"
        )
        assert tgt.read_bytes() == before

    @pytest.mark.spec("resolve-cmd-refuses-stale")
    def it_refuses_an_answer_whose_target_body_changed(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        ans = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "drop-source")
        tgt.write_text(tgt.read_text().replace("incomplete", "unfinished"))
        code, env = resolve(prose_repo, src, tgt, [ans])
        assert code == prose.PROBLEMS
        assert "in target-style.md is not what expect holds" in env["data"]["refused"][0]["reason"]


class DescribeAllOrNone:
    @pytest.mark.spec(
        "resolve-cmd-writes-nothing-unless-partial", "repo:command-applies-rest-if-partial"
    )
    def it_writes_nothing_when_one_answer_is_refused(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        before = tgt.read_bytes()
        good = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "keep-both")
        bad = dict(good, source="sentences-nope")
        code, env = resolve(prose_repo, src, tgt, [good, bad])
        assert (code, env["data"]["resolved"]) == (prose.PROBLEMS, [])
        assert env["errors"][-1] == "nothing was written; fix the answers named, or pass --partial"
        assert tgt.read_bytes() == before

    @pytest.mark.spec(
        "resolve-cmd-writes-nothing-unless-partial", "repo:command-applies-rest-if-partial"
    )
    def it_writes_the_rest_with_partial(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        good = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "keep-both")
        bad = dict(good, source="sentences-nope")
        code, env = resolve(prose_repo, src, tgt, [good, bad], "--partial")
        assert code == prose.PROBLEMS
        assert [r["source"] for r in env["data"]["refused"]] == ["sentences-nope"]
        assert "### sentences-own-subject" in tgt.read_text()


class DescribeTheResult:
    @pytest.mark.spec("resolve-cmd-lints-result")
    def it_leaves_a_target_that_lints_clean(self, prose_repo):
        src, tgt = files(
            prose_repo, OWN_SUBJECT + "\n" + COUNT, CARRIES + "\n" + OWN_SUBJECT_THEIRS
        )
        answers = [
            answer(src, tgt, "sentences-own-subject", "sentences-own-subject", "take-source"),
            answer(
                src, tgt, "sentences-count-needs-list", "sentences-carries-subject", "keep-both"
            ),
        ]
        code, _ = resolve(prose_repo, src, tgt, answers)
        lint, env = prose_repo.run("config", "lint", "--file", str(tgt))
        assert (code, lint, env["data"]["rules"]) == (prose.OK, prose.OK, 3)

    @pytest.mark.spec("resolve-cmd-lints-result")
    def it_writes_nothing_when_the_result_would_not_lint(self, prose_repo, monkeypatch):
        # Each answer is checked on its own, so only a fault in the joining
        # can reach this; a stand-in for place_blocks makes one.
        monkeypatch.setattr(prose, "place_blocks", lambda lines, spots, replaced: ["no front\n"])
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        before = tgt.read_bytes()
        ans = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "keep-both")
        code, env = resolve(prose_repo, src, tgt, [ans])
        assert code == prose.PROBLEMS
        assert env["errors"][-1] == "nothing was written; the result would not lint clean"
        assert tgt.read_bytes() == before

    @pytest.mark.spec("resolve-cmd-lints-result")
    def it_cannot_run_on_a_target_that_does_not_lint(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, "### sentences-01: Bad\n\nBody.\n")
        code, _ = resolve(prose_repo, src, tgt, [])
        assert code == prose.CANNOT_RUN
        assert "does not lint clean; run: prose.py config lint --file" in prose_repo.err


class DescribeTheCommitNote:
    @pytest.mark.spec("resolve-cmd-gives-commit-note")
    def it_names_each_rule_copied_whole_from_the_source(self, prose_repo):
        src, tgt = files(
            prose_repo, OWN_SUBJECT + "\n" + COUNT, OWN_SUBJECT_THEIRS + "\n" + CARRIES
        )
        answers = [
            answer(src, tgt, "sentences-own-subject", "sentences-own-subject", "take-source"),
            answer(
                src, tgt, "sentences-count-needs-list", "sentences-carries-subject", "keep-both"
            ),
        ]
        _, env = resolve(prose_repo, src, tgt, answers)
        assert env["data"]["commit_note"] == (
            "Adopted from repo: sentences-own-subject, sentences-count-needs-list"
        )

    @pytest.mark.spec("resolve-cmd-gives-commit-note")
    def it_gives_no_note_when_nothing_came_from_the_source(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        ans = answer(
            src, tgt, "sentences-own-subject", "sentences-carries-subject", "combine", **COMBINED
        )
        _, env = resolve(prose_repo, src, tgt, [ans])
        assert env["data"]["commit_note"] is None

    @pytest.mark.spec(
        "resolve-cmd-gives-commit-note", "repo:command-splits-output-streams-without-json"
    )
    def it_prints_each_answer_and_the_note_on_stdout_without_json(self, prose_repo):
        src, tgt = files(prose_repo, OWN_SUBJECT, CARRIES)
        good = answer(src, tgt, "sentences-own-subject", "sentences-carries-subject", "keep-both")
        path = prose_repo.root / "answers.json"
        path.write_text(json.dumps([good, dict(good, source="sentences-nope")]))
        prose_repo._capsys.readouterr()
        argv = ["config", "resolve", "--file", str(src), "--to", str(tgt)]
        argv += ["--answers", str(path), "--partial", "-C", str(prose_repo.root)]
        code = prose.main(argv)
        out, err = prose_repo._capsys.readouterr()
        assert code == prose.PROBLEMS
        assert out == (
            "keep-both  sentences-own-subject -> sentences-carries-subject  at line 14\n"
            "refused  answer 2  sentences-nope\n"
            "\nfor the commit description: Adopted from repo: sentences-own-subject\n"
        )
        assert "answer 2 (sentences-nope -> sentences-carries-subject)" in err

"""config write puts the rules the author approved into prose-style.md.

The model hands it records as JSON rather than editing the file, so every
record is checked against the file as it is now, and a batch with one bad
record writes nothing unless --partial is passed.
"""

import io
import json
import re

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

import prose

OWN_SUBJECT_BODY = (
    "A sentence that borrows its subject from the heading above it is incomplete.\n\n"
    "> **Before.** Curated, not collected.\n"
    "> **After.** The list is curated, not collected."
)

NEW_RULE = {
    "section": "sentences",
    "name": "no-in-order-to",
    "title": "Write to, not in order to",
    "body": "The two extra words carry nothing.",
    "example": {"before": "Run it in order to check.", "after": "Run it to check."},
    "patterns": [r"\bin order to\b"],
}

NEW_RULE_BLOCK = (
    "### sentences-no-in-order-to: Write to, not in order to\n"
    "\n"
    "The two extra words carry nothing.\n"
    "\n"
    "**Pattern.** `\\bin order to\\b`\n"
    "\n"
    "> **Before.** Run it in order to check.\n"
    "> **After.** Run it to check.\n"
)

VOICE_RULE = {
    "section": "voice",
    "name": "first-person-plural",
    "heading": "Voice",
    "title": "Write as we",
    "body": "The project speaks as a team.",
    "example": {"before": "I recommend it.", "after": "We recommend it."},
}


def new_rule(**overrides):
    record = dict(NEW_RULE)
    record.update(overrides)
    return {k: v for k, v in record.items() if v is not DROP}


def rewrite(**overrides):
    record = {"id": "sentences-own-subject", "expect": OWN_SUBJECT_BODY}
    record.update(overrides)
    return record


# Marks a field new_rule leaves out.
DROP = object()


def style(prose_repo):
    return prose_repo.read(prose.CONFIG_PATH)


def write(prose_repo, records, *flags):
    path = prose_repo.root / "batch.json"
    path.write_text(json.dumps(records))
    return prose_repo.run("config", "write", "--batch", str(path), *flags)


class DescribeConfigWrite:
    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_writes_a_new_rule_in_the_format_the_file_requires(self, prose_repo):
        start = style(prose_repo)
        code, env = write(prose_repo, [NEW_RULE])
        assert code == prose.OK
        assert style(prose_repo) == start + "\n" + NEW_RULE_BLOCK
        assert env["data"]["written"] == [
            {"id": "sentences-no-in-order-to", "change": prose.WRITTEN_NEW, "line": 14}
        ]

    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_writes_a_rule_with_no_example_or_pattern(self, prose_repo):
        code, _ = write(prose_repo, [new_rule(example=DROP, patterns=DROP)])
        assert code == prose.OK
        assert style(prose_repo).endswith(
            "\n### sentences-no-in-order-to: Write to, not in order to\n\n"
            "The two extra words carry nothing.\n"
        )

    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_fences_a_pattern_holding_a_backtick_so_lint_reads_it_back(self, prose_repo):
        record = new_rule(
            patterns=["`x`"], example={"before": "Run `x` now.", "after": "Run it now."}
        )
        code, _ = write(prose_repo, [record])
        rules = prose.Config(str(prose_repo.root / prose.CONFIG_PATH)).by_id()
        assert code == prose.OK
        assert [s for _l, s in rules["sentences-no-in-order-to"].patterns] == ["`x`"]

    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_reads_the_batch_from_stdin_given_a_dash(self, prose_repo, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([NEW_RULE])))
        code, _ = prose_repo.run("config", "write", "--batch", "-")
        assert code == prose.OK
        assert NEW_RULE_BLOCK in style(prose_repo)

    @pytest.mark.spec("write-cmd-writes-from-data", "repo:command-splits-output-streams")
    def it_prints_each_rule_it_wrote_without_json(self, prose_repo, capsys):
        path = prose_repo.root / "batch.json"
        path.write_text(json.dumps([NEW_RULE]))
        capsys.readouterr()
        argv = ["config", "write", "--batch", str(path), "-C", str(prose_repo.root)]
        code = prose.main(argv)
        out = capsys.readouterr().out
        assert code == prose.OK
        assert out == "wrote  sentences-no-in-order-to  new at line 14\n"

    @pytest.mark.spec("write-cmd-writes-from-data")
    @pytest.mark.parametrize(
        ("record", "reason"),
        [
            ("not a record", "record is not an object"),
            (new_rule(title=DROP), "a new rule needs title"),
            (new_rule(pattern=["x"]), "unknown field pattern"),
            (rewrite(heading="Voice", title="T"), "unknown field heading"),
            (rewrite(id=7), "id is not a string"),
            (new_rule(name=7), "section and name are not strings"),
            (new_rule(title="Two\nlines"), "title runs over more than one line"),
            (new_rule(title=""), "title is not a non-empty string"),
            (new_rule(body=" \n"), "body is not a non-empty string"),
            (new_rule(body="Text.\n### other-rule: X"), "body holds a heading"),
            (new_rule(body="Text.\n**Pattern.** `x`"), "body holds a **Pattern.** line"),
            (new_rule(body="Text.\n> **Before.** a"), "body holds a worked example"),
            (new_rule(body="<!-- prose-rule: source=x -->"), "body holds a prose-rule comment"),
            (new_rule(example={"before": "a"}), "example is not null or an object"),
            (new_rule(example={"before": "a", "after": ""}), "example after is not"),
            (new_rule(patterns="x"), "patterns is not a list of strings"),
            (new_rule(patterns=["("]), "does not compile"),
            (new_rule(patterns=["x*"]), "matches an empty string"),
            (dict(VOICE_RULE, heading="Two\nlines"), "heading runs over more than one line"),
        ],
    )
    def it_refuses_a_record_that_cannot_go_into_a_rule(self, prose_repo, record, reason):
        before = style(prose_repo)
        code, env = write(prose_repo, [record])
        assert code == prose.PROBLEMS
        assert reason in env["data"]["refused"][0]["reason"]
        assert style(prose_repo) == before

    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_names_each_refused_record_by_its_place_and_id(self, prose_repo):
        _, env = write(prose_repo, [NEW_RULE, new_rule(name="bad-01")])
        assert [(r["index"], r["id"]) for r in env["data"]["refused"]] == [(2, "sentences-bad-01")]
        assert env["errors"][0].startswith("record 2 (sentences-bad-01): ")

    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_refuses_an_id_written_twice(self, prose_repo):
        _, env = write(prose_repo, [NEW_RULE, NEW_RULE])
        assert env["data"]["refused"][0]["reason"] == (
            "sentences-no-in-order-to is written by record 1 too"
        )

    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_cannot_run_on_a_batch_that_is_not_a_list(self, prose_repo):
        code, env = write(prose_repo, NEW_RULE)
        assert (code, env) == (prose.CANNOT_RUN, None)
        assert "not a JSON list" in prose_repo.err


class DescribeLintingTheResult:
    @pytest.mark.spec("write-cmd-lints-clean")
    def it_leaves_the_file_linting_clean(self, prose_repo):
        code, _ = write(prose_repo, [NEW_RULE, VOICE_RULE, rewrite(patterns=["Curated"])])
        lint, env = prose_repo.run("config", "lint")
        assert (code, lint, env["warnings"]) == (prose.OK, prose.OK, [])

    @pytest.mark.spec("write-cmd-lints-clean")
    def it_refuses_a_pattern_that_misses_its_before_example(self, prose_repo):
        _, env = write(prose_repo, [new_rule(patterns=["nowhere"])])
        assert "finds anything in its Before example" in env["data"]["refused"][0]["reason"]

    @pytest.mark.spec("write-cmd-lints-clean")
    def it_refuses_a_pattern_that_matches_its_after_example(self, prose_repo):
        _, env = write(prose_repo, [new_rule(patterns=["Run it"])])
        assert "matches the After example" in env["data"]["refused"][0]["reason"]

    @pytest.mark.spec("write-cmd-lints-clean")
    def it_cannot_run_on_a_file_that_does_not_lint_clean(self, prose_repo):
        start = style(prose_repo)
        path = prose_repo.root / prose.CONFIG_PATH
        path.write_text(start + "\n### sentences-01: Positional\n\nBody.\n")
        code, _ = write(prose_repo, [NEW_RULE])
        assert code == prose.CANNOT_RUN
        assert "run: prose.py config lint" in prose_repo.err

    @pytest.mark.spec("write-cmd-lints-clean")
    def it_names_the_file_to_lint_when_given_one(self, prose_repo):
        start = style(prose_repo)
        other = prose_repo.root / "other.md"
        other.write_text(start + "\n### sentences-01: Positional\n\nBody.\n")
        code, _ = write(prose_repo, [NEW_RULE], "--file", str(other))
        assert code == prose.CANNOT_RUN
        assert "config lint --file %s" % other in prose_repo.err

    @pytest.mark.spec("write-cmd-lints-clean")
    def it_writes_nothing_when_the_result_would_not_lint(self, prose_repo, monkeypatch):
        # Each record lints on its own, so only a fault in the joining can
        # reach this; a stand-in for place_blocks makes one.
        monkeypatch.setattr(prose, "place_blocks", lambda lines, spots, replaced: ["no front\n"])
        before = style(prose_repo)
        code, env = write(prose_repo, [NEW_RULE])
        assert code == prose.PROBLEMS
        assert env["errors"][-1] == "nothing was written; the result would not lint clean"
        assert style(prose_repo) == before


class DescribeNewRuleNames:
    @pytest.mark.spec("write-cmd-vets-new-names")
    def it_refuses_a_malformed_name(self, prose_repo):
        _, env = write(prose_repo, [new_rule(name="a-b-c-d-e")])
        assert "has 5 words; at most 4" in env["data"]["refused"][0]["reason"]

    @pytest.mark.spec("write-cmd-vets-new-names")
    def it_refuses_a_name_already_taken(self, prose_repo):
        _, env = write(prose_repo, [new_rule(name="own-subject")])
        assert "already the id of the rule" in env["data"]["refused"][0]["reason"]


class DescribeAllOrNone:
    @pytest.mark.spec("write-cmd-writes-all-or-none")
    def it_writes_nothing_while_any_record_is_refused(self, prose_repo):
        before = style(prose_repo)
        code, env = write(prose_repo, [NEW_RULE, new_rule(name="bad-01")])
        assert code == prose.PROBLEMS
        assert env["data"]["written"] == []
        assert env["errors"][-1] == "nothing was written; fix the records named, or pass --partial"
        assert style(prose_repo) == before

    @pytest.mark.spec("write-cmd-writes-all-or-none")
    def it_writes_the_valid_records_given_partial(self, prose_repo):
        code, env = write(prose_repo, [new_rule(name="bad-01"), NEW_RULE], "--partial")
        assert code == prose.PROBLEMS
        assert [w["id"] for w in env["data"]["written"]] == ["sentences-no-in-order-to"]
        assert NEW_RULE_BLOCK in style(prose_repo)

    @pytest.mark.spec("write-cmd-writes-all-or-none")
    def it_writes_nothing_on_a_dry_run(self, prose_repo, capsys):
        start = style(prose_repo)
        path = prose_repo.root / "batch.json"
        path.write_text(json.dumps([new_rule(name="bad-01"), NEW_RULE]))
        capsys.readouterr()
        argv = ["config", "write", "--batch", str(path), "--dry-run", "--partial"]
        code = prose.main([*argv, "-C", str(prose_repo.root)])
        out = capsys.readouterr().out
        assert code == prose.PROBLEMS
        assert out == (
            "would write  sentences-no-in-order-to  new at line 14\n"
            "refused  record 1  sentences-bad-01\n"
        )
        assert style(prose_repo) == start


class DescribePlacement:
    @pytest.mark.spec("write-cmd-places-by-section")
    def it_puts_a_rule_after_the_last_rule_of_its_section(self, prose_repo):
        start = style(prose_repo)
        path = prose_repo.root / prose.CONFIG_PATH
        path.write_text(start + "\n## Headings\n\n### headings-noun-phrase: Noun\n\nBody.\n")
        write(prose_repo, [NEW_RULE])
        text = style(prose_repo)
        assert text.index("sentences-no-in-order-to") < text.index("## Headings")
        assert "> **After.** Run it to check.\n\n## Headings\n" in text

    @pytest.mark.spec("write-cmd-places-by-section")
    def it_opens_a_new_section_at_the_end_under_its_heading(self, prose_repo):
        start = style(prose_repo)
        second = dict(VOICE_RULE, name="active", title="Active", heading=DROP)
        second = {k: v for k, v in second.items() if v is not DROP}
        code, _ = write(prose_repo, [VOICE_RULE, second])
        text = style(prose_repo)
        assert code == prose.OK
        assert text.startswith(start + "\n## Voice\n\n### voice-first-person-plural:")
        assert text.index("voice-first-person-plural") < text.index("voice-active")
        assert text.count("## Voice") == 1

    @pytest.mark.spec("write-cmd-places-by-section")
    def it_refuses_a_rule_in_a_new_section_without_a_heading(self, prose_repo):
        record = {k: v for k, v in VOICE_RULE.items() if k != "heading"}
        _, env = write(prose_repo, [record])
        assert "give heading" in env["data"]["refused"][0]["reason"]

    @pytest.mark.spec("write-cmd-places-by-section")
    def it_refuses_a_heading_for_a_section_the_file_has(self, prose_repo):
        _, env = write(prose_repo, [new_rule(heading="Sentences")])
        assert "already has rules in sentences" in env["data"]["refused"][0]["reason"]


class DescribeRewrites:
    @pytest.mark.spec("write-cmd-keeps-unnamed-parts")
    def it_keeps_the_parts_a_rewrite_does_not_name(self, prose_repo):
        start = style(prose_repo)
        code, env = write(prose_repo, [rewrite(patterns=["Curated"])])
        assert code == prose.OK
        assert style(prose_repo) == start.replace(
            "incomplete.\n\n", "incomplete.\n\n**Pattern.** `Curated`\n\n"
        )
        assert env["data"]["written"][0]["change"] == prose.WRITTEN_REWRITE

    @pytest.mark.spec("write-cmd-keeps-unnamed-parts")
    def it_replaces_the_parts_a_rewrite_names(self, prose_repo):
        record = rewrite(title="Owns its subject", body="New body.", example=None)
        write(prose_repo, [record])
        assert style(prose_repo).endswith(
            "### sentences-own-subject: Owns its subject\n\nNew body.\n"
        )

    @pytest.mark.spec("write-cmd-keeps-unnamed-parts")
    def it_rewrites_a_rule_and_adds_one_after_it_in_one_batch(self, prose_repo):
        code, _ = write(prose_repo, [rewrite(body="New body."), NEW_RULE])
        text = style(prose_repo)
        assert code == prose.OK
        assert "\nNew body.\n\n> **Before.** Curated" in text
        assert text.endswith(
            "> **After.** The list is curated, not collected.\n\n" + NEW_RULE_BLOCK
        )

    @pytest.mark.spec("write-cmd-keeps-unnamed-parts")
    def it_keeps_the_blank_line_before_the_next_heading(self, prose_repo):
        start = style(prose_repo)
        path = prose_repo.root / prose.CONFIG_PATH
        path.write_text(start + "\n## Headings\n")
        write(prose_repo, [rewrite(body="New body.")])
        assert style(prose_repo).endswith(
            "> **After.** The list is curated, not collected.\n\n## Headings\n"
        )

    @pytest.mark.spec("write-cmd-keeps-unnamed-parts")
    def it_refuses_a_rewrite_that_names_no_part(self, prose_repo):
        _, env = write(prose_repo, [rewrite()])
        assert "names no part" in env["data"]["refused"][0]["reason"]

    @pytest.mark.spec("write-cmd-keeps-unnamed-parts")
    def it_drops_a_metadata_comment_an_earlier_version_wrote(self, prose_repo):
        start = style(prose_repo)
        path = prose_repo.root / prose.CONFIG_PATH
        path.write_text(start.replace("subject\n\n", "subject\n<!-- prose-rule: source=x -->\n\n"))
        code, _ = write(prose_repo, [rewrite(title="Carries its own subject")])
        assert code == prose.OK
        assert style(prose_repo) == start

    @given(
        title=st.from_regex(r"\A[A-Za-z][A-Za-z ]{0,20}[a-z]\Z"),
        body=st.lists(st.from_regex(r"\A[A-Za-z][A-Za-z .,]{0,30}\Z"), min_size=1, max_size=4),
        example=st.one_of(
            st.none(),
            st.just({"before": "In order to go.", "after": "To go."}),
        ),
        patterns=st.lists(st.sampled_from(["order", "`?order", "(?i)in order"]), max_size=2),
    )
    @pytest.mark.spec("write-cmd-keeps-unnamed-parts")
    def it_returns_a_rule_it_wrote_byte_for_byte_when_given_its_own_title(
        self, tmp_path_factory, title, body, example, patterns
    ):
        if example is None:
            patterns = []
        block = prose.rule_block("sentences-probe", title, body, patterns, example)
        path = tmp_path_factory.mktemp("w") / "prose-style.md"
        source = "---\nname: T\n---\n\n## Sentences\n\n" + "".join(block)
        path.write_text(source)
        config = prose.Config(str(path))
        rule = config.by_id()["sentences-probe"]
        record = {"id": rule.id, "expect": rule.body_text(), "title": title}
        out, written, refused = prose.plan_writes(config, prose.Text(source).lines, [record])
        assert (refused, "".join(out)) == ([], source)


class DescribeStaleRewrites:
    @pytest.mark.spec("write-cmd-refuses-stale")
    def it_refuses_a_rewrite_whose_rule_changed_since_it_was_read(self, prose_repo):
        _, env = write(prose_repo, [rewrite(expect="An older body.", body="New body.")])
        assert "changed since it was read" in env["data"]["refused"][0]["reason"]

    @pytest.mark.spec("write-cmd-refuses-stale")
    def it_refuses_a_rewrite_of_an_id_the_file_lacks(self, prose_repo):
        _, env = write(prose_repo, [rewrite(id="sentences-no-such-rule", body="B.")])
        assert re.search(r"has no rule sentences-no-such-rule", env["errors"][0])


class DescribePatternLine:
    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_fences_a_pattern_holding_a_backtick_in_two(self):
        assert prose.pattern_line("a`b") == "**Pattern.** ``a`b``\n"

    @given(st.text(min_size=1, max_size=12))
    @example(" ")
    @example("\t ")
    @pytest.mark.spec("write-cmd-writes-from-data")
    def it_writes_a_pattern_that_lint_reads_back_unchanged(self, source):
        line = prose.pattern_line(source)
        parsed, problem = prose.parse_pattern(line[len("**Pattern.**") : -1])
        assert problem or parsed == source

"""The shape of a pull request's description, and the commands that check one
and open it: `.flywheel/pr-template.md`, `pr draft`, `pr check` and `pr push`.
"""

import os

import pytest

import flywheel

TEMPLATE = flywheel.PR_TEMPLATE_FILE
SCENARIO = "## Scenario\n\nAn owner runs it.\n\n"
BEFORE = "### Before\n\nIt broke.\n\n"
AFTER = "### After\n\nIt works.\n\n"
CHANGE = "## Change\n\nFixes it.\n\n"
REQUIREMENTS = "## Requirements\n\nDoes not change any requirement.\n\n"
TESTS = "## Test plan\n\n- pytest ran.\n\n"
CLOSES = "Closes #12\n"
GOOD = SCENARIO + BEFORE + AFTER + CHANGE + REQUIREMENTS + TESTS + CLOSES
CUSTOM = (
    "Our pull requests.\n\n"
    "## Why\n\nThe reason for it.\n\n"
    "## Spec changes\n\n<!-- requirement-ids -->\nEach id it touches.\n\n"
    "### Added\n\nNew ids.\n"
)


def shape(project):
    return flywheel.pr_shape(str(project.root))


def headings(found):
    return [(s.heading, [h for h, _ in s.subsections], s.ids) for s in found]


@pytest.mark.spec("prtemplate-sets-shape")
class DescribeThePullRequestTemplate:
    def it_gives_the_house_shape_without_a_template(self, project):
        assert headings(shape(project)) == [
            ("Scenario", ["Before", "After"], False),
            ("Change", [], False),
            ("Requirements", [], True),
            ("Test plan", [], False),
        ]

    def it_reads_each_section_its_subsections_and_the_marked_one(self, project):
        project.write(TEMPLATE, CUSTOM)
        assert headings(shape(project)) == [("Why", [], False), ("Spec changes", ["Added"], True)]

    def it_keeps_the_guidance_under_each_heading_without_the_mark(self, project):
        project.write(TEMPLATE, CUSTOM)
        why, spec = shape(project)
        assert why.guidance == "The reason for it."
        assert spec.guidance == "Each id it touches."
        assert spec.subsections == (("Added", "New ids."),)

    def it_reads_a_heading_in_a_fence_as_guidance(self, project):
        project.write(TEMPLATE, CUSTOM + "\n```markdown\n## Not a section\n```\n")
        assert [s.heading for s in shape(project)] == ["Why", "Spec changes"]

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    @pytest.mark.parametrize(
        ("text", "says"),
        [
            ("Just prose.\n", "holds no `##` heading"),
            ("## Why\n\nThe reason.\n", "marks no section with `<!-- requirement-ids -->`"),
            (
                "## A\n<!-- requirement-ids -->\n## B\n<!-- requirement-ids -->\n",
                "marks `## A` and `## B` with `<!-- requirement-ids -->`",
            ),
            ("### Early\n\n## A\n<!-- requirement-ids -->\n", "puts `### Early` before"),
        ],
    )
    def it_stops_on_a_template_it_cannot_use(self, project, text, says):
        project.write(TEMPLATE, text)
        code, out = project.run("pr", "draft")
        assert code == flywheel.CANNOT_RUN
        assert out is None
        assert says in project.err


PROSE = "<!-- prose-rules: docs/style.md -->\n"


@pytest.mark.spec("prtemplate-names-prose-rules")
class DescribeTheProseRulesMark:
    def it_names_no_file_without_a_template(self, project):
        assert flywheel.pr_prose_rules(str(project.root)) == ()

    def it_names_each_marked_file_in_the_order_of_its_marks(self, project):
        project.write("docs/style.md", "# Style\n")
        project.write("rules.md", "# Rules\n")
        project.write(TEMPLATE, PROSE + CUSTOM + "\n<!-- prose-rules: rules.md -->\n")
        assert flywheel.pr_prose_rules(str(project.root)) == ("docs/style.md", "rules.md")

    def it_keeps_the_mark_out_of_the_guidance(self, project):
        project.write("docs/style.md", "# Style\n")
        project.write(TEMPLATE, CUSTOM.replace("New ids.\n", "New ids.\n" + PROSE))
        assert shape(project)[1].subsections == (("Added", "New ids."),)

    def it_reads_a_mark_in_a_fence_as_guidance(self, project):
        project.write(TEMPLATE, CUSTOM + "\n```markdown\n" + PROSE + "```\n")
        assert flywheel.pr_prose_rules(str(project.root)) == ()

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    @pytest.mark.parametrize("command", [("pr", "draft"), ("pr", "check", "--body-file", "x.md")])
    def it_stops_on_a_mark_that_names_a_missing_file(self, project, command):
        project.write("x.md", GOOD)
        project.write(TEMPLATE, PROSE + CUSTOM)
        code, out = project.run(*[str(project.root / a) if a == "x.md" else a for a in command])
        assert code == flywheel.CANNOT_RUN
        assert out is None
        assert "`<!-- prose-rules: docs/style.md -->`" in project.err


CHECK = "<!-- prose-check: style:check-file -->\n"


def prose_check(project):
    return flywheel.pr_template(str(project.root))[2]


@pytest.mark.spec("prtemplate-names-prose-check")
class DescribeTheProseCheckMark:
    def it_names_no_skill_without_a_template(self, project):
        assert prose_check(project) is None

    def it_names_the_skill_the_mark_gives(self, project):
        project.write("docs/style.md", "# Style\n")
        project.write(TEMPLATE, PROSE + CHECK + CUSTOM)
        assert prose_check(project) == "style:check-file"

    def it_keeps_the_mark_out_of_the_guidance(self, project):
        project.write("docs/style.md", "# Style\n")
        project.write(TEMPLATE, PROSE + CUSTOM.replace("New ids.\n", "New ids.\n" + CHECK))
        assert shape(project)[1].subsections == (("Added", "New ids."),)

    def it_reads_a_mark_in_a_fence_as_guidance(self, project):
        project.write(TEMPLATE, CUSTOM + "\n```markdown\n" + CHECK + "```\n")
        assert prose_check(project) is None

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    @pytest.mark.parametrize(
        ("marks", "says"),
        [
            (CHECK + "<!-- prose-check: other:skill -->\n", "`<!-- prose-check: other:skill -->`"),
            (CHECK, "`<!-- prose-rules: PATH -->`"),
            ("<!-- prose-check: -->\n", "`<!-- prose-check: -->`"),
        ],
    )
    @pytest.mark.parametrize("command", [("pr", "draft"), ("pr", "check", "--body-file", "x.md")])
    def it_stops_on_a_mark_it_cannot_use(self, project, command, marks, says):
        project.write("x.md", GOOD)
        project.write("docs/style.md", "# Style\n")
        rules = "" if marks == CHECK else PROSE
        project.write(TEMPLATE, rules + marks + CUSTOM)
        code, out = project.run(*[str(project.root / a) if a == "x.md" else a for a in command])
        assert code == flywheel.CANNOT_RUN
        assert out is None
        assert says in project.err


@pytest.fixture
def drafted(tmp_path):
    def write(text):
        path = tmp_path / "pr.md"
        path.write_text(text)
        return str(path)

    return write


def check(project, path):
    return project.run("pr", "check", "--body-file", path)


@pytest.mark.spec("prdraft-cmd-makes-own-file")
class DescribePrDraft:
    def it_makes_an_empty_file_that_no_other_run_is_given(self, project):
        code, first = project.run("pr", "draft")
        _, second = project.run("pr", "draft")
        assert code == flywheel.OK
        paths = [first["data"]["path"], second["data"]["path"]]
        try:
            assert paths[0] != paths[1]
            assert all(os.path.getsize(p) == 0 for p in paths)
        finally:
            for p in paths:
                os.remove(p)

    def it_gives_the_shape_to_draft_from(self, project):
        project.write(TEMPLATE, CUSTOM)
        _, out = project.run("pr", "draft")
        os.remove(out["data"]["path"])
        assert out["data"]["sections"] == [
            {"heading": "Why", "guidance": "The reason for it.", "subsections": [], "ids": False},
            {
                "heading": "Spec changes",
                "guidance": "Each id it touches.",
                "subsections": [{"heading": "Added", "guidance": "New ids."}],
                "ids": True,
            },
        ]

    def it_gives_the_prose_rules_files_the_template_names(self, project):
        project.write("docs/style.md", "# Style\n")
        project.write(TEMPLATE, PROSE + CUSTOM)
        _, out = project.run("pr", "draft")
        os.remove(out["data"]["path"])
        assert out["data"]["prose_rules"] == ["docs/style.md"]

    def it_gives_no_prose_rules_file_without_a_mark(self, project):
        _, out = project.run("pr", "draft")
        os.remove(out["data"]["path"])
        assert out["data"]["prose_rules"] == []

    def it_gives_the_skill_that_runs_the_patterns(self, project):
        project.write("docs/style.md", "# Style\n")
        project.write(TEMPLATE, PROSE + CHECK + CUSTOM)
        _, out = project.run("pr", "draft")
        os.remove(out["data"]["path"])
        assert out["data"]["prose_check"] == "style:check-file"

    def it_gives_no_skill_without_a_mark(self, project):
        _, out = project.run("pr", "draft")
        os.remove(out["data"]["path"])
        assert out["data"]["prose_check"] is None

    def it_prints_only_the_path_in_text(self, project):
        code, out, err = project.human("pr", "draft")
        path = out.strip()
        os.remove(path)
        assert code == flywheel.OK
        assert out == path + "\n"
        assert err == ""

    def it_stops_when_it_cannot_make_the_file(self, project, monkeypatch, tmp_path):
        monkeypatch.setattr(flywheel.tempfile, "tempdir", str(tmp_path / "missing"))
        code, out = project.run("pr", "draft")
        assert code == flywheel.CANNOT_RUN
        assert "Set TMPDIR" in project.err


@pytest.mark.spec("prcheck-cmd-requires-shape")
class DescribePrCheckOnTheShape:
    def it_passes_a_description_in_the_house_shape(self, project, drafted):
        code, out = check(project, drafted(GOOD))
        assert code == flywheel.OK
        assert out["errors"] == []
        assert out["data"]["ids_heading"] == "Requirements"

    def it_says_so_in_text(self, project, drafted):
        code, out, err = project.human("pr", "check", "--body-file", drafted(GOOD))
        assert code == flywheel.OK
        assert "follows the shape" in out
        assert err == ""

    @pytest.mark.parametrize(
        ("parts", "says"),
        [
            (
                (SCENARIO, BEFORE, AFTER, REQUIREMENTS, TESTS, CLOSES),
                "the description lacks the section `## Change`.",
            ),
            (
                (TESTS, SCENARIO, BEFORE, AFTER, CHANGE, REQUIREMENTS, CLOSES),
                "the description opens with `## Test plan`. It opens with `## Scenario` instead.",
            ),
            (
                (SCENARIO, BEFORE, AFTER, CHANGE, TESTS, REQUIREMENTS, CLOSES),
                "the description puts `## Test plan` before `## Requirements`.",
            ),
            (
                (SCENARIO, BEFORE, AFTER, "## Change\n\n", REQUIREMENTS, TESTS, CLOSES),
                "the section `## Change` is empty.",
            ),
            (
                (SCENARIO, AFTER, CHANGE, REQUIREMENTS, TESTS, CLOSES),
                "the section `## Scenario` lacks the subsection `### Before`.",
            ),
            (
                (SCENARIO, "### Before\n\n", AFTER, CHANGE, REQUIREMENTS, TESTS, CLOSES),
                "the subsection `### Before` is empty.",
            ),
            (
                (SCENARIO, AFTER, BEFORE, CHANGE, REQUIREMENTS, TESTS, CLOSES),
                "the section `## Scenario` puts `### After` before `### Before`.",
            ),
            (
                (SCENARIO, BEFORE, CHANGE, AFTER, REQUIREMENTS, TESTS, CLOSES),
                "the section `## Scenario` lacks the subsection `### After`.",
            ),
        ],
    )
    def it_names_each_fault_in_the_shape(self, project, drafted, parts, says):
        code, out = check(project, drafted("".join(parts)))
        assert code == flywheel.PROBLEMS
        assert [e for e in out["errors"] if e.startswith(says)], out["errors"]

    def it_reads_the_first_of_a_repeated_subsection(self, project, drafted):
        body = GOOD.replace(BEFORE, BEFORE + "### Before\n\nAgain.\n\n")
        assert check(project, drafted(body))[0] == flywheel.OK

    def it_names_each_fault_on_stderr_in_text(self, project, drafted):
        body = GOOD.replace(CHANGE, "")
        code, out, err = project.human("pr", "check", "--body-file", drafted(body))
        assert code == flywheel.PROBLEMS
        assert out == ""
        assert "the description lacks the section `## Change`." in err

    def it_reads_headings_in_a_fence_or_a_comment_as_text(self, project, drafted):
        body = GOOD.replace(
            "Fixes it.", "Fixes it.\n\n```markdown\n## Scenario\n```\n\n<!--\n## Test plan\n-->"
        )
        code, out = check(project, drafted(body))
        assert out["errors"] == []

    def it_allows_text_before_the_first_heading_and_sections_of_its_own(self, project, drafted):
        body = "Draft.\n\n" + GOOD.replace("## Test plan", "## Notes\n\nMore.\n\n## Test plan")
        code, out = check(project, drafted(body))
        assert code == flywheel.OK

    def it_checks_the_projects_own_shape(self, project, drafted):
        project.write(TEMPLATE, CUSTOM)
        code, out = check(
            project, drafted("## Why\n\nIt broke.\n\n## Spec changes\n\nNone.\n\nCloses #3\n")
        )
        assert code == flywheel.PROBLEMS
        assert out["errors"] == [
            "the section `## Spec changes` lacks the subsection `### Added`. Add it, with its"
            " text under it."
        ]
        assert out["data"]["ids_heading"] == "Spec changes"


@pytest.mark.spec("prcheck-cmd-refuses-split-lines")
class DescribePrCheckOnSplitLines:
    def it_names_each_line_that_continues_the_one_above(self, project, drafted):
        body = GOOD.replace("Fixes it.", "Fixes it\nacross two lines.")
        code, out = check(project, drafted(body))
        assert code == flywheel.PROBLEMS
        line = body.splitlines().index("across two lines.") + 1
        assert out["errors"] == [
            "line %d continues the paragraph or list item above it. GitHub renders the newline"
            " as a line break, so join the line to the one above." % line
        ]

    def it_leaves_lines_in_a_fence_and_list_items(self, project, drafted):
        body = GOOD.replace("Fixes it.", "Fixes it:\n- one\n- two\n\n```sh\na\nb\n```")
        assert check(project, drafted(body))[0] == flywheel.OK


@pytest.mark.spec("prcheck-cmd-requires-closes")
class DescribePrCheckOnTheIssue:
    def it_refuses_a_description_that_closes_no_issue(self, project, drafted):
        code, out = check(project, drafted(GOOD.replace("Closes #12\n", "")))
        assert code == flywheel.PROBLEMS
        assert out["errors"] == [
            "the description does not close an issue. End it with a line `Closes #N`, for the"
            " issue the branch works."
        ]

    @pytest.mark.parametrize("line", ["Fixes #12", "resolves #12", "Closes #12."])
    def it_takes_each_closing_keyword_github_reads(self, project, drafted, line):
        assert check(project, drafted(GOOD.replace("Closes #12", line)))[0] == flywheel.OK

    def it_does_not_read_a_closing_line_in_a_fence(self, project, drafted):
        body = GOOD.replace("Closes #12\n", "```text\nCloses #12\n```\n")
        assert check(project, drafted(body))[0] == flywheel.PROBLEMS

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable")
    def it_stops_on_a_file_it_cannot_read(self, project, tmp_path):
        code, out = check(project, str(tmp_path / "missing.md"))
        assert code == flywheel.CANNOT_RUN
        assert "cannot read the description at" in project.err


class FakePush:
    """git push, recording each call."""

    def __init__(self):
        self.calls = []

    def git(self, root, *args, check=True):
        self.calls.append(("git", *args))

        class Done:
            stdout = "issue/12\n"

        return Done()

    def gh(self, root, *args, stdin=None):
        self.calls.append(("gh", *args))
        return ""


@pytest.fixture
def pusher(monkeypatch):
    fake = FakePush()
    monkeypatch.setattr(flywheel, "git", fake.git)
    monkeypatch.setattr(flywheel, "gh", fake.gh)
    return fake


def push_pr(project, path):
    return project.run("pr", "push", "--body-file", path)


@pytest.mark.spec("prpush-cmd-pushes-checked-draft")
class DescribePrPushPushing:
    def it_pushes_the_branch_and_opens_nothing(self, project, drafted, pusher):
        code, out = push_pr(project, drafted(GOOD))
        assert code == flywheel.OK
        assert out["data"]["branch"] == "issue/12"
        assert pusher.calls[1] == ("git", "push", "-u", flywheel.REMOTE, "HEAD")
        assert [c for c in pusher.calls if c[0] == "gh"] == []

    def it_prints_nothing_in_text(self, project, drafted, pusher):
        code, out, _ = project.human("pr", "push", "--body-file", drafted(GOOD))
        assert (code, out) == (flywheel.OK, "")


@pytest.mark.spec("prpush-cmd-refuses-failing-draft")
class DescribePrPushRefusing:
    def it_prints_nothing_on_stdout_in_text(self, project, drafted, pusher):
        path = drafted(GOOD.replace(CLOSES, ""))
        code, out, err = project.human("pr", "push", "--body-file", path)
        assert (code, out) == (flywheel.PROBLEMS, "")
        assert "does not close an issue" in err

    def it_pushes_nothing_for_a_draft_that_fails_the_check(self, project, drafted, pusher):
        code, out = push_pr(project, drafted(GOOD.replace("Closes #12\n", "")))
        assert code == flywheel.PROBLEMS
        assert pusher.calls == []

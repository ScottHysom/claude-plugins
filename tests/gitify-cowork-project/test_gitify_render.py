"""render is the one command that writes. It turns the model's answers into the
files that land in a folder already holding someone's work, so each check here
is the last thing between a bad answer and a file that is wrong on arrival.

A rejected batch writes nothing. That is asserted as often as the rejection
itself, because a half-staged set of files copied to the device is worse than
none.
"""

import hashlib
import json
import re

import pytest

import gitify


def errors_of(env):
    """Rejections, minus the trailing line render appends."""
    return [e for e in env["errors"] if not e.startswith("nothing was")]


def assert_nothing_staged(runner):
    assert not runner.stage.exists() or not any(runner.stage.rglob("*"))


class DescribeACleanRender:
    def it_stages_every_file_with_no_placeholder_left(self, runner, make_answers, skill_rel):
        code, env = runner.render(make_answers())
        assert code == gitify.OK, env["errors"]
        rels = [f["file"] for f in env["data"]["files"]]
        assert rels == [".gitignore", "commit.sh", "setup.sh", "CLAUDE.md", skill_rel]
        for rel in rels:
            assert not gitify.LEFTOVER_RE.search(runner.staged(rel)), rel
        assert runner.staged(skill_rel).startswith("---\nname: foo-research-history\n")

    def it_checksums_the_bytes_it_staged(self, runner, make_answers):
        _, env = runner.render(make_answers())
        for f in env["data"]["files"]:
            with open(f["staged_path"], "rb") as fh:
                assert hashlib.sha256(fh.read()).hexdigest() == f["sha256"]

    def it_pairs_each_staged_file_with_its_device_path(self, runner, make_answers, project):
        _, env = runner.render(make_answers())
        data = env["data"]
        assert data["commit_files"] == [
            {"stagedPath": f["staged_path"], "devicePath": project["project"] + "/" + f["file"]}
            for f in data["files"]
        ]

    def it_computes_the_mount_and_path_placeholders(self, runner, make_answers, skill_rel, project):
        _, env = runner.render(make_answers())
        assert env["data"]["project_mount"] == "Projects/Foo Research"
        skill = runner.staged(skill_rel)
        assert "`%s`" % project["project"] in skill
        assert "$HOME/mnt/Projects/Foo Research/.commit-msg" in skill

    def it_allows_the_project_to_be_the_connected_folder_itself(
        self, runner, make_answers, project
    ):
        code, env = runner.render(make_answers(project_folder=None))
        assert code == gitify.OK, env["errors"]
        assert env["data"]["project_mount"] == "Projects"
        assert env["data"]["files"][0]["device_path"] == project["connected"] + "/.gitignore"

    def it_leaves_the_field_empty_when_the_project_is_the_connected_folder(
        self, runner, make_answers
    ):
        # Cowork loads the root CLAUDE.md itself; a pointer would only cost context.
        _, env = runner.render(make_answers(project_folder=None))
        assert env["data"]["field_pointer"] is None

    def it_tells_claude_to_read_the_file_when_the_project_is_a_subfolder(
        self, runner, make_answers, project
    ):
        # Cowork does not load a CLAUDE.md below the connected folder.
        _, env = runner.render(make_answers())
        pointer = env["data"]["field_pointer"]
        assert pointer.startswith("Before anything else, read CLAUDE.md")
        assert project["project"] in pointer
        assert "\n" not in pointer

    def it_says_to_leave_the_field_empty_in_its_plain_output(self, runner, make_answers):
        path = runner.tmp / "answers.json"
        path.write_text(json.dumps(make_answers(project_folder=None)))
        args = ("render", "--answers", str(path), "--stage", str(runner.stage))
        code, _ = runner.run(*args, json_output=False)
        assert code == gitify.OK
        assert "Project Instructions field:\n(leave it empty)" in runner.out

    def it_reports_and_writes_nothing_on_a_dry_run(self, runner, make_answers):
        code, env = runner.render(make_answers(), "--dry-run")
        assert code == gitify.OK
        assert env["data"]["dry_run"] is True
        assert len(env["data"]["files"]) == len(gitify.MANIFEST)
        assert not runner.stage.exists()

    def it_warns_about_a_stage_outside_the_outputs_root(self, runner, make_answers):
        _, env = runner.render(make_answers())
        assert any("device_commit_files will reject it" in w for w in env["warnings"])

    def it_sends_human_output_to_stdout_and_warnings_to_stderr(self, runner, make_answers):
        path = runner.tmp / "answers.json"
        path.write_text(json.dumps(make_answers()))
        code, _ = runner.run(
            "render", "--answers", str(path), "--stage", str(runner.stage), json_output=False
        )
        assert code == gitify.OK
        assert "precheck, through device_bash" in runner.out
        assert "Project Instructions field" in runner.out
        assert "warning:" in runner.err
        assert "warning:" not in runner.out

    def it_allows_rendering_again_into_the_same_stage(self, runner, make_answers):
        runner.render(make_answers())
        code, env = runner.render(make_answers())
        assert code == gitify.OK, env["errors"]


class DescribeTheInstructions:
    def it_writes_only_the_header_when_the_field_is_empty(self, runner, make_answers):
        runner.render(make_answers())
        text = runner.staged("CLAUDE.md")
        assert text.startswith("# Foo Research\n")
        assert "./commit.sh" in text

    def it_keeps_its_notes_for_people_out_of_claudes_context(self, runner, make_answers):
        # Block-level HTML comments in CLAUDE.md are stripped before it is
        # loaded, in Cowork as in Claude Code, so the header costs Claude one line.
        runner.render(make_answers())
        text = runner.staged("CLAUDE.md")
        loaded = re.sub(r"(?ms)^<!--.*?-->[ \t]*\n", "", text)
        assert loaded.split() == ["#", "Foo", "Research"]

    def it_copies_the_field_verbatim_after_the_header(self, runner, make_answers):
        field = "I am a {{PROJECT_NAME}} fan.\n\n- Budget: $500 <!-- a note -->\n"
        runner.render(make_answers())
        header = runner.staged("CLAUDE.md")
        runner.stage = runner.tmp / "stage2"
        code, env = runner.render(make_answers(instructions=field))
        assert code == gitify.OK, env["errors"]
        assert runner.staged("CLAUDE.md") == header + "\n" + field

    def it_ends_the_copied_field_with_a_newline(self, runner, make_answers):
        runner.render(make_answers(instructions="no newline at the end"))
        assert runner.staged("CLAUDE.md").endswith("\n\nno newline at the end\n")

    @pytest.mark.parametrize(
        ("value", "message"),
        [
            ("  \n", "pass null when the field is empty"),
            ("", "pass null when the field is empty"),
            (["a"], "must be the field's text"),
        ],
    )
    def it_rejects_instructions_that_are_not_text(self, runner, make_answers, value, message):
        code, env = runner.render(make_answers(instructions=value))
        assert code == gitify.PROBLEMS
        assert any(message in e for e in errors_of(env))
        assert_nothing_staged(runner)


class DescribeTheIgnorePatterns:
    def it_appends_them_under_their_own_heading(self, runner, make_answers):
        runner.render(make_answers(ignore=["exports/", "*.mov"]))
        text = runner.staged(".gitignore")
        assert text.endswith("Claude outputs/\n\n# This project\nexports/\n*.mov\n")

    def it_leaves_the_template_as_it_is_when_there_are_none(self, runner, make_answers):
        runner.render(make_answers(ignore=[]))
        template = (runner.templates_copy() / "gitignore").read_text()
        assert runner.staged(".gitignore") == template

    @pytest.mark.parametrize(
        ("value", "message"),
        [
            (["a\nb"], "must be one line"),
            ([" "], "not blank"),
            (["a", "a"], "repeats 'a'"),
            ("*.mov", "must be a list"),
        ],
    )
    def it_rejects_a_bad_pattern_and_writes_nothing(self, runner, make_answers, value, message):
        code, env = runner.render(make_answers(ignore=value))
        assert code == gitify.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)


VALUE_CASES = [
    ("SKILL_NAME", "Foo_History", "lower-case words joined by -"),
    ("SKILL_NAME", "a" * 65, "at most 64"),
    ("PROJECT_NAME", " Foo", "one line with no surrounding space"),
    ("PROJECT_NAME", "Foo {{X}}", "cannot contain {{ or }}"),
    ("DESCRIPTION", "Git: for Foo Research.", "would break the skill's front matter"),
    ("DESCRIPTION", "- Foo Research history.", "would break the skill's front matter"),
    ("DESCRIPTION", "Git history. Use when committing.", "must name the project"),
    ("DESCRIPTION", "Foo Research " + "x" * 1024, "at most 1024"),
]


class DescribeValidatingAValue:
    @pytest.mark.parametrize(("name", "value", "message"), VALUE_CASES)
    def it_rejects_a_bad_value_and_writes_nothing(self, runner, make_answers, name, value, message):
        data = make_answers()
        data["values"][name] = value
        code, env = runner.render(data)
        assert code == gitify.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)

    def it_accepts_a_description_naming_the_skill_instead_of_the_project(
        self, runner, make_answers
    ):
        data = make_answers()
        data["values"]["DESCRIPTION"] = "Use foo-research-history when committing."
        code, env = runner.render(data)
        assert code == gitify.OK, env["errors"]

    def it_names_an_unknown_value(self, runner, make_answers):
        data = make_answers()
        data["values"]["NOT_A_THING"] = "x"
        code, env = runner.render(data)
        assert code == gitify.PROBLEMS
        assert "values.NOT_A_THING is not a placeholder" in errors_of(env)

    def it_refuses_a_computed_value(self, runner, make_answers):
        data = make_answers()
        data["values"]["PROJECT_PATH"] = "/x"
        code, env = runner.render(data)
        assert code == gitify.PROBLEMS
        assert any("computed from the folders" in e for e in errors_of(env))

    def it_names_an_unknown_answers_key(self, runner, make_answers):
        code, env = runner.render(make_answers(extra={}))
        assert code == gitify.PROBLEMS
        assert "answers has unexpected keys: extra" in errors_of(env)


FOLDER_CASES = [
    ({"connected_folder": ""}, "connected_folder is required"),
    ({"connected_folder": "Projects"}, "must be absolute"),
    ({"connected_folder": "/a/../b"}, ". or .. segments"),
    ({"connected_folder": "/a\\b"}, "newline or backslash"),
    ({"connected_folder": "~", "project_folder": None}, "no folder name to mount"),
    ({"project_folder": "/elsewhere/Foo"}, "is not inside connected_folder"),
]


class DescribeValidatingTheFolders:
    @pytest.mark.parametrize(("change", "message"), FOLDER_CASES)
    def it_rejects_a_bad_folder(self, runner, make_answers, change, message):
        code, env = runner.render(make_answers(**change))
        assert code == gitify.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)

    def it_ignores_a_trailing_slash_on_a_folder(self, runner, make_answers, project):
        code, env = runner.render(make_answers(project_folder=project["project"] + "/"))
        assert code == gitify.OK, env["errors"]
        assert env["data"]["project_path"] == project["project"]


class DescribeRefusingToRun:
    def it_cannot_run_on_a_duplicate_key_in_the_answers(self, runner, make_answers):
        raw = json.dumps(make_answers())[:-1] + ', "ignore": []}'
        code, env = runner.render(None, raw=raw)
        assert code == gitify.CANNOT_RUN
        assert env is None
        assert "appears twice" in runner.err

    def it_cannot_run_on_answers_that_are_not_json(self, runner):
        code, _ = runner.render(None, raw="not json")
        assert code == gitify.CANNOT_RUN
        assert runner.err.startswith("gitify.py: cannot read answers")

    def it_refuses_a_stage_holding_a_foreign_file(self, runner, make_answers):
        runner.stage.mkdir()
        (runner.stage / "notes.txt").write_text("mine")
        code, _ = runner.render(make_answers())
        assert code == gitify.CANNOT_RUN
        assert "already holds notes.txt" in runner.err
        assert (runner.stage / "notes.txt").read_text() == "mine"


class DescribeLeftovers:
    def it_stops_render_when_a_template_placeholder_has_no_value(self, runner, make_answers):
        # preflight names an unknown placeholder; this is what stops one that
        # reached render anyway from landing in a project.
        templates = runner.templates_copy()
        with open(templates / "CLAUDE.md", "a") as fh:
            fh.write("{{NOT_A_THING}}\n")
        path = runner.tmp / "answers.json"
        path.write_text(json.dumps(make_answers()))
        code, env = runner.run(
            "render",
            "--answers",
            str(path),
            "--stage",
            str(runner.stage),
            "--templates",
            str(templates),
        )
        assert code == gitify.PROBLEMS
        assert "CLAUDE.md: output still contains {{, }}" in env["errors"]
        assert_nothing_staged(runner)

    @pytest.mark.parametrize("text", ["{{PROJECT_NAME}}", "a }} b", "{{ x"])
    def it_names_a_surviving_placeholder_or_brace(self, text):
        assert gitify.leftovers(text)

    def it_passes_text_with_no_braces(self):
        assert gitify.leftovers("# Foo\n") == []

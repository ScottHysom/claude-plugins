"""render is the one command that writes. It turns the model's answers into the
files that land in a folder already holding someone's work, so each check here
is the last thing between a bad answer and a file that is wrong on arrival.

A rejected batch writes nothing. That is asserted as often as the rejection
itself, because a half-staged set of files copied to the device is worse than
none.
"""

import json
import re
from pathlib import Path

import pytest

import gitify


def errors_of(env):
    """Rejections, minus the trailing line render appends."""
    return [e for e in env["errors"] if not e.startswith("nothing was")]


def assert_nothing_staged(runner):
    assert not runner.stage.exists() or not any(runner.stage.rglob("*"))


def loaded(text):
    """CLAUDE.md as Claude loads it. Block-level HTML comments are stripped
    before it is loaded, in Cowork as in Claude Code."""
    return re.sub(r"(?ms)^<!--.*?-->[ \t]*\n", "", text)


def foreign_file_in_stage(runner):
    runner.stage.mkdir(parents=True)
    (runner.stage / "notes.txt").write_text("mine")


def file_as_stage(runner):
    runner.stage.parent.mkdir(parents=True)
    runner.stage.write_text("mine")


class DescribeACleanRender:
    @pytest.mark.spec("render-cmd-stages-files", "render-cmd-refuses-leftover-placeholders")
    def it_stages_every_file_with_no_placeholder_left(self, runner, make_answers):
        code, env = runner.render(make_answers())
        assert code == gitify.OK, env["errors"]
        rels = [rel for rel, _ in runner.staged_files(env["data"])]
        assert rels == [".gitignore", "commit.sh", "setup.sh", "CLAUDE.md"]
        for rel in rels:
            assert not gitify.LEFTOVER_RE.search(runner.staged(rel)), rel

    @pytest.mark.spec("render-cmd-stages-files")
    def it_pairs_each_staged_file_with_its_device_path(self, runner, make_answers, project):
        _, env = runner.render(make_answers())
        assert env["data"]["commit_files"] == [
            {"stagedPath": str(runner.stage / rel), "devicePath": project["project"] + "/" + rel}
            for rel in (".gitignore", "commit.sh", "setup.sh", "CLAUDE.md")
        ]

    @pytest.mark.spec("render-cmd-stages-files")
    def it_allows_the_project_to_be_the_connected_folder_itself(
        self, runner, make_answers, project
    ):
        code, env = runner.render(make_answers(project_folder=None))
        assert code == gitify.OK, env["errors"]
        assert env["data"]["commit_files"][0]["devicePath"] == project["connected"] + "/.gitignore"

    @pytest.mark.spec("render-cmd-prints-field-pointer")
    def it_tells_claude_to_read_the_file_when_the_project_is_the_connected_folder(
        self, runner, make_answers, project
    ):
        # Cowork loads the root CLAUDE.md only from the second message on; the
        # field is all the first one sees. COWORK.md, "How instruction files load".
        _, env = runner.render(make_answers(project_folder=None))
        pointer = env["data"]["field_pointer"]
        assert pointer == gitify.FIELD_POINTER.format(path=project["connected"])
        assert "\n" not in pointer

    def it_tells_claude_to_read_the_file_when_the_project_is_a_subfolder(
        self, runner, make_answers, project
    ):
        # Cowork does not load a CLAUDE.md below the connected folder.
        _, env = runner.render(make_answers())
        pointer = env["data"]["field_pointer"]
        assert pointer.startswith("Before anything else, read CLAUDE.md")
        assert project["project"] in pointer
        assert "\n" not in pointer

    @pytest.mark.spec("render-cmd-prints-field-pointer")
    def it_keeps_documents_in_the_folder_when_the_session_lacks_it(
        self, runner, make_answers, project
    ):
        # A session started from the phone sees the field and not the folder.
        _, env = runner.render(make_answers())
        pointer = env["data"]["field_pointer"]
        assert "documents live only in that folder" in pointer
        assert "ask for access to it first" in pointer
        assert "never write project documents anywhere else" in pointer
        assert "\n" not in pointer

    @pytest.mark.spec("render-cmd-prints-field-pointer", "repo:command-splits-output-streams")
    def it_prints_the_pointer_in_its_plain_output(self, runner, make_answers, project):
        path = runner.tmp / "answers.json"
        path.write_text(json.dumps(make_answers(project_folder=None)))
        args = ("render", "--answers", str(path))
        code, _ = runner.run(*args, json_output=False)
        assert code == gitify.OK
        pointer = gitify.FIELD_POINTER.format(path=project["connected"])
        assert "Project Instructions field:\n%s\n" % pointer in runner.out

    @pytest.mark.spec("repo:command-never-writes-in-preview")
    def it_reports_and_writes_nothing_on_a_dry_run(self, runner, make_answers):
        code, env = runner.render(make_answers(), "--dry-run")
        assert code == gitify.OK
        assert len(env["data"]["commit_files"]) == len(gitify.MANIFEST)
        assert not runner.stage.exists()

    @pytest.mark.spec("repo:command-splits-output-streams")
    def it_sends_human_output_to_stdout_and_warnings_to_stderr(self, runner, make_answers):
        path = runner.tmp / "answers.json"
        path.write_text(json.dumps(make_answers()))
        code, _ = runner.run("render", "--answers", str(path), json_output=False)
        assert code == gitify.OK
        assert "precheck, through device_bash" in runner.out
        assert "Project Instructions field" in runner.out
        assert runner.err == ""

    @pytest.mark.spec("render-cmd-stages-files")
    def it_renders_again_into_the_stage_it_left(self, runner, make_answers):
        runner.render(make_answers())
        code, env = runner.render(make_answers())
        assert code == gitify.OK, env["errors"]

    @pytest.mark.spec("render-cmd-stages-files")
    @pytest.mark.parametrize(
        "arrange", [foreign_file_in_stage, file_as_stage], ids=["foreign file", "not a directory"]
    )
    def it_clears_whatever_was_left_at_the_stage(self, runner, make_answers, arrange):
        arrange(runner)
        code, env = runner.render(make_answers())
        assert code == gitify.OK, env["errors"]
        on_disk = sorted(str(p) for p in runner.stage.rglob("*") if p.is_file())
        assert on_disk == sorted(f["stagedPath"] for f in env["data"]["commit_files"])

    @pytest.mark.spec("repo:command-never-writes-in-preview")
    def it_leaves_the_stage_alone_on_a_dry_run(self, runner, make_answers):
        foreign_file_in_stage(runner)
        code, _ = runner.render(make_answers(), "--dry-run")
        assert code == gitify.OK
        assert (runner.stage / "notes.txt").read_text() == "mine"


class DescribeTheInstructions:
    @pytest.mark.spec("render-cmd-accepts-null-instructions")
    def it_writes_only_the_header_when_the_field_is_empty(self, runner, make_answers):
        runner.render(make_answers())
        text = runner.staged("CLAUDE.md")
        assert text.startswith("# Foo Research\n")
        assert "./commit.sh" in text

    @pytest.mark.spec("claudemd-hides-people-note")
    def it_keeps_its_notes_for_people_out_of_claudes_context(self, runner, make_answers):
        runner.render(make_answers())
        text = loaded(runner.staged("CLAUDE.md"))
        assert re.match(r"# Foo Research\n\s*## Where documents live\n", text)
        assert "This note" not in text

    @pytest.mark.spec("render-cmd-copies-instructions-verbatim")
    def it_copies_the_field_verbatim_after_the_header(self, runner, make_answers):
        field = "I am a {{PROJECT_NAME}} fan.\n\n- Budget: $500 <!-- a note -->\n"
        runner.render(make_answers())
        header = runner.staged("CLAUDE.md")
        code, env = runner.render(make_answers(instructions=field))
        assert code == gitify.OK, env["errors"]
        assert runner.staged("CLAUDE.md") == header + "\n" + field

    @pytest.mark.spec("render-cmd-copies-instructions-verbatim")
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
    @pytest.mark.spec("render-cmd-accepts-null-instructions")
    def it_rejects_instructions_that_are_not_text(self, runner, make_answers, value, message):
        code, env = runner.render(make_answers(instructions=value))
        assert code == gitify.PROBLEMS
        assert any(message in e for e in errors_of(env))
        assert_nothing_staged(runner)


class DescribeTheHistorySection:
    """What CLAUDE.md tells Claude about git. A rule inside an HTML comment
    never reaches Claude, so each test reads the file as Claude loads it."""

    @pytest.mark.spec("claudemd-holds-history-section")
    def it_keeps_change_records_out_of_the_documents(self, runner, make_answers):
        runner.render(make_answers())
        text = loaded(runner.staged("CLAUDE.md"))
        assert "Keep that record out of the documents" in text

    @pytest.mark.spec("claudemd-holds-history-section")
    def it_commits_through_a_message_file_and_the_users_terminal(self, runner, make_answers):
        runner.render(make_answers())
        text = loaded(runner.staged("CLAUDE.md"))
        assert "write the message into `.commit-msg`" in text
        assert "ask the user to run `./commit.sh`" in text
        assert "Never run `git commit` through the bridge" in text

    @pytest.mark.spec("claudemd-gives-history-commands")
    def it_reads_the_history_at_the_projects_mount(self, runner, make_answers):
        runner.render(make_answers())
        text = loaded(runner.staged("CLAUDE.md"))
        assert "Read-only git works through the bridge" in text
        assert 'cd "$HOME/mnt/Projects/Foo Research"\ngit log' in text

    @pytest.mark.spec("claudemd-gives-history-commands")
    def it_reads_the_history_at_the_connected_folders_mount(self, runner, make_answers):
        runner.render(make_answers(project_folder=None))
        text = loaded(runner.staged("CLAUDE.md"))
        assert 'cd "$HOME/mnt/Projects"\n' in text

    @pytest.mark.spec("claudemd-gives-field-rule")
    def it_moves_anything_else_in_the_field_into_the_file(self, runner, make_answers):
        runner.render(make_answers())
        text = loaded(runner.staged("CLAUDE.md"))
        assert "If\nit holds anything else, copy that into this file" in text
        assert "put the field back to the one line" in text

    @pytest.mark.spec("claudemd-keeps-documents-in-folder")
    def it_keeps_the_documents_in_the_folder(self, runner, make_answers):
        runner.render(make_answers())
        text = loaded(runner.staged("CLAUDE.md"))
        assert "## Where documents live\n" in text
        assert "This project's documents live only in this folder." in text
        assert "claude.ai Project's own\ndocuments" in text
        assert "`Claude outputs/`" in text


class DescribeTheIgnorePatterns:
    @pytest.mark.spec("render-cmd-appends-ignore-patterns")
    def it_appends_them_under_their_own_heading(self, runner, make_answers):
        runner.render(make_answers(ignore=["exports/", "*.mov"]))
        text = runner.staged(".gitignore")
        assert text.endswith("Claude outputs/\n\n# This project\nexports/\n*.mov\n")

    @pytest.mark.spec("render-cmd-appends-ignore-patterns")
    def it_leaves_the_template_as_it_is_when_there_are_none(self, runner, make_answers):
        runner.render(make_answers(ignore=[]))
        template = Path(gitify.TEMPLATES, "gitignore").read_text()
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
    @pytest.mark.spec("render-cmd-appends-ignore-patterns")
    def it_rejects_a_bad_pattern_and_writes_nothing(self, runner, make_answers, value, message):
        code, env = runner.render(make_answers(ignore=value))
        assert code == gitify.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)


VALUE_CASES = [
    ("PROJECT_NAME", None, "values.PROJECT_NAME is required"),
    ("PROJECT_NAME", " Foo", "one line with no surrounding space"),
    ("PROJECT_NAME", "Foo {{X}}", "cannot contain {{ or }}"),
]


class DescribeValidatingAValue:
    @pytest.mark.spec("repo:script-checks-every-answer")
    @pytest.mark.parametrize(("name", "value", "message"), VALUE_CASES)
    def it_rejects_a_bad_value_and_writes_nothing(self, runner, make_answers, name, value, message):
        data = make_answers()
        data["values"][name] = value
        code, env = runner.render(data)
        assert code == gitify.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)

    @pytest.mark.spec("repo:script-checks-every-answer")
    def it_names_an_unknown_value(self, runner, make_answers):
        data = make_answers()
        data["values"]["NOT_A_THING"] = "x"
        code, env = runner.render(data)
        assert code == gitify.PROBLEMS
        assert "values.NOT_A_THING is not a placeholder" in errors_of(env)

    @pytest.mark.spec("repo:script-checks-every-answer")
    def it_refuses_a_computed_value(self, runner, make_answers):
        data = make_answers()
        data["values"]["PROJECT_MOUNT"] = "x"
        code, env = runner.render(data)
        assert code == gitify.PROBLEMS
        assert any("computed from the folders" in e for e in errors_of(env))

    @pytest.mark.spec("repo:script-checks-every-answer")
    def it_rejects_values_that_are_not_an_object(self, runner, make_answers):
        code, env = runner.render(make_answers(values=["Foo Research"]))
        assert code == gitify.PROBLEMS
        assert "values must be an object" in errors_of(env)
        assert_nothing_staged(runner)

    @pytest.mark.spec("repo:command-splits-output-streams")
    def it_writes_its_rejections_to_stderr_in_plain_output(self, runner, make_answers):
        path = runner.tmp / "answers.json"
        path.write_text(json.dumps(make_answers(values={})))
        code, _ = runner.run("render", "--answers", str(path), json_output=False)
        assert code == gitify.PROBLEMS
        assert "values.PROJECT_NAME is required" in runner.err
        assert runner.out == ""

    @pytest.mark.spec("repo:script-checks-every-answer")
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
    ({"project_folder": "Foo"}, "project_folder must be absolute"),
    ({"project_folder": "/elsewhere/Foo"}, "is not inside connected_folder"),
]


class DescribeValidatingTheFolders:
    @pytest.mark.spec("repo:script-checks-every-answer")
    @pytest.mark.parametrize(("change", "message"), FOLDER_CASES)
    def it_rejects_a_bad_folder(self, runner, make_answers, change, message):
        code, env = runner.render(make_answers(**change))
        assert code == gitify.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)

    @pytest.mark.spec("render-cmd-stages-files")
    def it_ignores_a_trailing_slash_on_a_folder(self, runner, make_answers, project):
        code, env = runner.render(make_answers(project_folder=project["project"] + "/"))
        assert code == gitify.OK, env["errors"]
        assert env["data"]["commit_files"][0]["devicePath"] == project["project"] + "/.gitignore"


class DescribeRefusingToRun:
    @pytest.mark.spec("repo:script-checks-every-answer")
    def it_cannot_run_on_a_duplicate_key_in_the_answers(self, runner, make_answers):
        raw = json.dumps(make_answers())[:-1] + ', "ignore": []}'
        code, env = runner.render(None, raw=raw)
        assert code == gitify.CANNOT_RUN
        assert env is None
        assert "appears twice" in runner.err

    @pytest.mark.spec("repo:script-checks-every-answer")
    def it_cannot_run_on_answers_that_are_not_json(self, runner):
        code, _ = runner.render(None, raw="not json")
        assert code == gitify.CANNOT_RUN
        assert runner.err.startswith("gitify.py: cannot read answers")

    @pytest.mark.spec("repo:script-checks-every-answer")
    def it_cannot_run_on_answers_that_are_not_an_object(self, runner):
        code, _ = runner.render(None, raw="[]")
        assert code == gitify.CANNOT_RUN
        assert "answers must be a JSON object" in runner.err


def missing_templates(runner):
    runner.use_templates(runner.tmp / "nowhere")


def missing_template(runner):
    (runner.templates_copy() / "commit.sh").unlink()


def malformed_template(runner):
    (runner.templates_copy() / "gitignore").write_text("a stray }} brace\n")


class DescribeTheRemedyOnStopping:
    # SKILL.md reads every exit 2 from render the same way, so each message
    # has to carry the remedy for its own cause, and only that one.
    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    @pytest.mark.parametrize(
        "raw",
        ['{"ignore": [], "ignore": []}', "not json", "[]"],
        ids=["duplicate key", "not json", "not an object"],
    )
    def it_tells_the_caller_to_fix_unreadable_answers(self, runner, raw):
        code, _ = runner.render(None, raw=raw)
        assert code == gitify.CANNOT_RUN
        assert runner.err.rstrip().endswith(gitify.FIX_ANSWERS)
        assert gitify.PLUGIN_BUG not in runner.err

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    @pytest.mark.parametrize(
        "arrange",
        [missing_templates, missing_template, malformed_template],
        ids=["no templates directory", "missing template", "malformed template"],
    )
    def it_tells_the_caller_a_broken_template_is_a_plugin_bug(self, runner, make_answers, arrange):
        arrange(runner)
        code, _ = runner.render(make_answers())
        assert code == gitify.CANNOT_RUN
        assert runner.err.rstrip().endswith(gitify.PLUGIN_BUG)


class DescribeTheRemedyOnFindingProblems:
    # SKILL.md does not map exit 1 to a remedy either, so the last error of
    # each command that exits 1 says what to do next.
    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_tells_the_caller_to_fix_the_answers(self, runner, make_answers):
        code, env = runner.render(make_answers(values={}))
        assert code == gitify.PROBLEMS
        assert env["errors"][-1] == gitify.FIX_ANSWERS

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_tells_the_caller_a_malformed_template_is_a_plugin_bug(self, runner):
        malformed_template(runner)
        code, env = runner.run("preflight")
        assert code == gitify.PROBLEMS
        assert env["errors"][-1] == gitify.PLUGIN_BUG

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    @pytest.mark.parametrize("command", ["probe", "history"])
    def it_tells_the_caller_to_pass_the_folder_as_listed(self, runner, command):
        code, _ = runner.run(command, "--connected-folder", "Projects", json_output=False)
        assert code == gitify.PROBLEMS
        assert runner.err.rstrip().endswith(gitify.FIX_FOLDERS % command)


class DescribeLeftovers:
    @pytest.mark.spec("render-cmd-refuses-leftover-placeholders")
    def it_stops_render_when_a_template_placeholder_has_no_value(self, runner, make_answers):
        # preflight names an unknown placeholder; this is what stops one that
        # reached render anyway from landing in a project.
        templates = runner.templates_copy()
        with open(templates / "CLAUDE.md", "a") as fh:
            fh.write("{{NOT_A_THING}}\n")
        code, env = runner.render(make_answers())
        assert code == gitify.PROBLEMS
        assert "CLAUDE.md: output still contains {{, }}" in env["errors"]
        assert_nothing_staged(runner)

    @pytest.mark.spec("render-cmd-refuses-leftover-placeholders")
    @pytest.mark.parametrize("text", ["{{PROJECT_NAME}}", "a }} b", "{{ x"])
    def it_names_a_surviving_placeholder_or_brace(self, text):
        assert gitify.leftovers(text)

    @pytest.mark.spec("render-cmd-refuses-leftover-placeholders")
    def it_passes_text_with_no_braces(self):
        assert gitify.leftovers("# Foo\n") == []

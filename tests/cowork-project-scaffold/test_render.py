"""render is the one command that writes. It takes answers the model wrote and
turns them into the files that land in the user's project, so each check here
is the last thing between a miscopied digest or a malformed value and a
project that ships with a dangling marker or a skill whose front matter does
not parse.

A rejected batch writes nothing. That is asserted as often as the rejection
itself, because a half-staged project copied to the device is worse than none.
"""

import hashlib
import json
import os
import shutil
import subprocess

import pytest

import scaffold


def errors_of(env):
    """Rejections, minus the trailing advice line render appends."""
    return [e for e in env["errors"] if not e.startswith("nothing was")]


def assert_nothing_staged(runner):
    assert not runner.stage.exists() or not any(runner.stage.rglob("*"))


class DescribeACleanRender:
    def it_stages_every_file_with_no_marker_left(self, runner, make_answers, skill_rel):
        code, env = runner.render(make_answers())
        assert code == scaffold.OK, env["errors"]
        rels = [f["file"] for f in env["data"]["files"]]
        assert rels == [
            dest.replace("{SKILL_NAME}", "update-foo-research-docs")
            for _, dest in scaffold.MANIFEST
        ]
        for rel in rels:
            text = runner.staged(rel)
            assert not scaffold.LEFTOVER_RE.search(text), rel
        assert runner.staged(skill_rel).startswith("---\nname: update-foo-research-docs\n")

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
        assert code == scaffold.OK, env["errors"]
        assert env["data"]["project_mount"] == "Projects"
        assert env["data"]["files"][0]["device_path"] == project["connected"] + "/.gitignore"

    def it_reports_and_writes_nothing_on_a_dry_run(self, runner, make_answers):
        code, env = runner.render(make_answers(), "--dry-run")
        assert code == scaffold.OK
        assert env["data"]["dry_run"] is True
        assert len(env["data"]["files"]) == len(scaffold.MANIFEST)
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
        assert code == scaffold.OK
        assert "sha256sum --check" in runner.out
        assert "warning:" in runner.err
        assert "warning:" not in runner.out

    def it_allows_rendering_again_into_the_same_stage(self, runner, make_answers):
        runner.render(make_answers())
        code, env = runner.render(make_answers())
        assert code == scaffold.OK, env["errors"]


def with_resolution(make_answers, marker_id, **resolution):
    data = make_answers()
    data["markers"][marker_id].update(resolution)
    return data


class DescribeResolvingAMarker:
    def it_takes_the_heading_with_a_deleted_optional_section(
        self, runner, make_answers, markers, resolve, skill_rel
    ):
        data = make_answers(markers=resolve(markers, optional="delete"))
        code, env = runner.render(data)
        assert code == scaffold.OK, env["errors"]
        skill = runner.staged(skill_rel)
        for heading in ("## Diagrams", "## Section template", "## Source-quality flags"):
            assert heading not in skill
        assert "\n\n\n" not in skill

    def it_strips_only_the_markers_from_a_kept_optional_section(
        self, runner, make_answers, skill_rel
    ):
        _, env = runner.render(make_answers())
        skill = runner.staged(skill_rel)
        assert "## Diagrams" in skill
        assert "OPTIONAL SECTION" not in skill
        assert "\n\n\n" not in skill

    def it_removes_the_marker_and_one_blank_line_on_an_empty_fill(self, runner, make_answers):
        data = with_resolution(make_answers, "current-state.md:fill-6", text="")
        runner.render(data)
        assert "## Kill criteria\n\n## Decisions made" in runner.staged("current-state.md")

    def it_replaces_just_the_comment_on_an_inline_fill(self, runner, make_answers):
        data = with_resolution(make_answers, "current-state.md:fill-1", text="exploring")
        runner.render(data)
        assert "**Status:** exploring\n" in runner.staged("current-state.md")

    def it_substitutes_a_placeholder_in_fill_text(self, runner, make_answers):
        data = with_resolution(
            make_answers, "current-state.md:fill-3", text="Ship {{PROJECT_NAME}}."
        )
        runner.render(data)
        assert "Ship Foo Research.\n" in runner.staged("current-state.md")

    def it_keeps_and_reports_a_left_marker(self, runner, make_answers):
        data = make_answers()
        data["markers"]["current-state.md:fill-4"] = {
            "digest": data["markers"]["current-state.md:fill-4"]["digest"],
            "action": "leave",
        }
        code, env = runner.render(data)
        assert code == scaffold.OK, env["errors"]
        assert "<!-- FILL: the settled facts" in runner.staged("current-state.md")
        assert [x["id"] for x in env["data"]["left"]] == ["current-state.md:fill-4"]
        assert any("current-state.md:fill-4" in w for w in env["warnings"])


REJECTED_RESOLUTIONS = [
    ({"digest": "000000000000"}, "does not match the template"),
    # Found by test_properties_render.py: an unclosed fence made every later
    # heading in the file part of a code block.
    ({"text": "Example:\n```\nx = 1"}, "opens a code fence it does not close"),
    ({"action": "keep"}, "action must be one of fill, leave"),
    ({"text": "has FILL: inside"}, "marker words"),
    ({"text": "uses {{NOPE}}"}, "unknown placeholder"),
    ({"text": "a stray }} brace"}, "stray"),
    ({"text": 7}, "text must be a string"),
    ({"colour": "blue"}, "unexpected keys colour"),
]


class DescribeRejectingAResolution:
    @pytest.mark.parametrize(("change", "message"), REJECTED_RESOLUTIONS)
    def it_rejects_a_bad_resolution_and_writes_nothing(self, runner, make_answers, change, message):
        data = with_resolution(make_answers, "current-state.md:fill-3", **change)
        code, env = runner.render(data)
        assert code == scaffold.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)

    def it_refuses_an_inline_fill_spanning_lines(self, runner, make_answers):
        data = with_resolution(make_answers, "current-state.md:fill-1", text="one\ntwo")
        code, env = runner.render(data)
        assert code == scaffold.PROBLEMS
        assert any("must be one line" in e for e in errors_of(env))

    def it_rejects_text_on_a_leave(self, runner, make_answers):
        data = with_resolution(make_answers, "current-state.md:fill-3", action="leave")
        code, env = runner.render(data)
        assert code == scaffold.PROBLEMS
        assert any("only for action fill" in e for e in errors_of(env))

    def it_names_a_marker_with_no_resolution(self, runner, make_answers):
        data = make_answers()
        del data["markers"]["maintain-docs.md:fill-1"]
        code, env = runner.render(data)
        assert code == scaffold.PROBLEMS
        assert any("maintain-docs.md:fill-1 has no resolution" in e for e in errors_of(env))
        assert_nothing_staged(runner)

    def it_rejects_a_resolution_inside_a_deleted_section(self, runner, make_answers, markers):
        data = make_answers()
        section = next(
            m for m in markers if m["heading"] == "Source-quality flags" and m["kind"] == "optional"
        )
        data["markers"][section["id"]]["action"] = "delete"
        code, env = runner.render(data)
        assert code == scaffold.PROBLEMS
        assert any("which is deleted" in e for e in errors_of(env))

    def it_stops_everything_on_an_unknown_marker_id(self, runner, make_answers):
        data = make_answers()
        data["markers"]["gitignore:fill-9"] = {"digest": "x", "action": "fill", "text": ""}
        code, env = runner.render(data, "--partial")
        assert code == scaffold.PROBLEMS
        assert any("not a marker in the templates" in e for e in errors_of(env))
        assert_nothing_staged(runner)

    def it_stages_the_files_without_errors_on_partial(self, runner, make_answers):
        data = with_resolution(make_answers, "current-state.md:fill-3", digest="000000000000")
        code, env = runner.render(data, "--partial")
        assert code == scaffold.PROBLEMS
        staged = [f["file"] for f in env["data"]["files"]]
        assert "current-state.md" not in staged
        assert "prose-style.md" in staged
        assert not (runner.stage / "current-state.md").exists()
        assert (runner.stage / "prose-style.md").exists()


def with_value(make_answers, name, value):
    data = make_answers()
    data["values"][name] = value
    return data


REJECTED_VALUES = [
    ("SKILL_NAME", "Update_Docs", "lower-case words"),
    ("SKILL_NAME", "a" * 65, "at most 64"),
    ("ANCHOR_DOC", "docs/state.md", ".md file name"),
    ("ANCHOR_DOC", "state.txt", ".md file name"),
    ("PROJECT_NAME", "", "is required"),
    ("PROJECT_NAME", " Foo", "no surrounding space"),
    ("PROJECT_NAME", "Foo {{X}}", "cannot contain"),
    ("DESCRIPTION", "Foo Research rules: all of them", "front matter"),
    ("DESCRIPTION", "- Foo Research rules", "front matter"),
    ("DESCRIPTION", "Rules for Foo Research #1", "front matter"),
    ("DESCRIPTION", "Document rules for this project", "must name the project"),
    ("DESCRIPTION", "Foo Research " + "x" * 1024, "at most 1024"),
    ("DESCRIPTION", "Foo Research\nsecond line", "one line"),
    ("DESCRIPTION", "Rules for Foo Research <ins> markup", "looks like an XML tag"),
    ("DESCRIPTION", "Rules for Foo Research</b>", "looks like an XML tag"),
]


class DescribeValidatingAValue:
    @pytest.mark.parametrize(("name", "value", "message"), REJECTED_VALUES)
    def it_rejects_a_bad_value_and_writes_nothing(self, runner, make_answers, name, value, message):
        code, env = runner.render(with_value(make_answers, name, value), "--partial")
        assert code == scaffold.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)

    def it_accepts_a_description_naming_the_skill_instead_of_the_project(
        self, runner, make_answers
    ):
        data = with_value(make_answers, "DESCRIPTION", "Rules behind update-foo-research-docs.")
        code, env = runner.render(data)
        assert code == scaffold.OK, env["errors"]

    def it_accepts_a_description_with_a_less_than_sign_not_followed_by_a_name(
        self, runner, make_answers
    ):
        data = with_value(make_answers, "DESCRIPTION", "Foo Research rules, when a < b.")
        code, env = runner.render(data)
        assert code == scaffold.OK, env["errors"]

    def it_refuses_a_computed_value(self, runner, make_answers):
        code, env = runner.render(with_value(make_answers, "PROJECT_MOUNT", "x"))
        assert code == scaffold.PROBLEMS
        assert any("computed from the folders" in e for e in errors_of(env))

    def it_names_an_unknown_value(self, runner, make_answers):
        code, env = runner.render(with_value(make_answers, "COLOUR", "blue"))
        assert code == scaffold.PROBLEMS
        assert any("values.COLOUR is not a placeholder" in e for e in errors_of(env))


REJECTED_FOLDERS = [
    ({"connected_folder": ""}, "connected_folder is required"),
    ({"connected_folder": "Documents/x"}, "must be absolute"),
    ({"connected_folder": "/Users/owner/../x"}, ". or .. segments"),
    ({"project_folder": "/Users/owner/Elsewhere"}, "is not inside connected_folder"),
    ({"project_folder": "/Users/owner/Documents/ProjectsFoo"}, "is not inside connected_folder"),
    ({"project_folder": "/Users/owner/Documents/Projects/a\\b"}, "backslash"),
]


class DescribeValidatingTheFolders:
    @pytest.mark.parametrize(("change", "message"), REJECTED_FOLDERS)
    def it_rejects_a_bad_folder(self, runner, make_answers, change, message):
        code, env = runner.render(make_answers(**change))
        assert code == scaffold.PROBLEMS
        assert any(message in e for e in errors_of(env)), env["errors"]
        assert_nothing_staged(runner)

    def it_ignores_a_trailing_slash_on_a_folder(self, runner, make_answers, project):
        code, env = runner.render(make_answers(connected_folder=project["connected"] + "/"))
        assert code == scaffold.OK, env["errors"]
        assert env["data"]["project_mount"] == "Projects/Foo Research"


class DescribeRefusingToRun:
    def it_cannot_run_on_a_duplicate_key_in_the_answers(self, runner, make_answers):
        raw = json.dumps(make_answers())
        raw = raw.replace('"values": {', '"values": {"SKILL_NAME": "a", ', 1)
        code, env = runner.render(None, raw=raw)
        assert code == scaffold.CANNOT_RUN
        assert env is None
        assert "appears twice" in runner.err

    def it_cannot_run_on_answers_that_are_not_json(self, runner):
        code, _ = runner.render(None, raw="{not json")
        assert code == scaffold.CANNOT_RUN
        assert runner.err.startswith("scaffold.py: cannot read answers")

    def it_refuses_a_stage_holding_a_foreign_file(self, runner, make_answers):
        runner.stage.mkdir()
        (runner.stage / "notes.txt").write_text("mine")
        code, _ = runner.render(make_answers())
        assert code == scaffold.CANNOT_RUN
        assert "already holds notes.txt" in runner.err
        assert (runner.stage / "notes.txt").read_text() == "mine"


# --------------------------------------------------------------------------
# the device commands, run for real
#
# They run on the Cowork device's Linux VM. Running them under sh here, against
# a fake $HOME/mnt, is the closest a test gets to that.
# --------------------------------------------------------------------------


def fake_device(runner, env_data, project_sub="Foo Research", copy=True):
    home = runner.tmp / "home"
    folder = home / "mnt" / "Projects" / project_sub
    folder.mkdir(parents=True)
    if copy:
        for f in env_data["files"]:
            dst = folder / f["file"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f["staged_path"], dst)
    return home, folder


def run_sh(command, home):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(["sh", "-c", command], capture_output=True, text=True, env=env)


needs_sha256sum = pytest.mark.skipif(
    shutil.which("sha256sum") is None, reason="sha256sum is not installed here"
)


class DescribeTheDeviceCommands:
    def it_reports_clear_on_an_empty_folder(self, runner, make_answers):
        _, env = runner.render(make_answers())
        home, _ = fake_device(runner, env["data"], copy=False)
        result = run_sh(env["data"]["precheck_command"], home)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "clear"

    def it_names_a_file_that_would_be_overwritten(self, runner, make_answers):
        _, env = runner.render(make_answers())
        home, folder = fake_device(runner, env["data"], copy=False)
        (folder / "current-state.md").write_text("the owner's own notes")
        (folder / ".git").mkdir()
        result = run_sh(env["data"]["precheck_command"], home)
        assert result.returncode == 1
        assert "exists: Foo Research/current-state.md" in result.stdout
        assert "exists: Foo Research/.git" in result.stdout

    @needs_sha256sum
    def it_passes_when_every_file_arrived(self, runner, make_answers):
        _, env = runner.render(make_answers())
        home, _ = fake_device(runner, env["data"])
        result = run_sh(env["data"]["check_command"], home)
        assert result.returncode == 0, result.stdout + result.stderr

    @needs_sha256sum
    def it_fails_when_a_file_changed_on_the_way(self, runner, make_answers):
        _, env = runner.render(make_answers())
        home, folder = fake_device(runner, env["data"])
        with open(folder / "setup.sh", "a") as fh:
            fh.write("\n")
        result = run_sh(env["data"]["check_command"], home)
        assert result.returncode != 0
        assert "setup.sh: FAILED" in result.stdout


# --------------------------------------------------------------------------
# the last check before a file is staged
#
# Nothing a well-formed template and valid answers produce can reach it, which
# is the point of it, so it is tested directly.
# --------------------------------------------------------------------------


class DescribeLeftovers:
    def it_counts_fill_markers_against_those_left_on_purpose(self):
        text = "a <!-- FILL: one --> b\n<!-- FILL: two -->\n"
        assert scaffold.leftovers(text, 2) == []
        assert scaffold.leftovers(text, 1) == ["2 FILL marker(s) in the output, 1 left on purpose"]

    @pytest.mark.parametrize("text", ["{{PROJECT_NAME}}", "a }} b", "<!-- OPTIONAL SECTION. x -->"])
    def it_names_a_surviving_placeholder_or_section_marker(self, text):
        assert scaffold.leftovers(text, 0)

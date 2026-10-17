"""What `flywheel.py setup` puts in the project."""

import hashlib
import json

import pytest

import flywheel

COPIED = [
    ".flywheel/flywheel.py",
    ".flywheel/roles.template.json",
    ".flywheel/review-policy.template.md",
    ".flywheel/merge-policy.template.md",
    ".flywheel/plugin.json",
]


@pytest.mark.spec("setup-cmd-copies-script")
class DescribeTheCopy:
    def it_copies_the_script_byte_for_byte(self, project):
        code, _ = project.run("setup")
        assert code == flywheel.OK
        with open(flywheel.SCRIPT_PATH, "rb") as fh:
            assert project.read(".flywheel/flywheel.py") == fh.read()

    def it_copies_the_templates_and_manifest_the_copy_reads(self, project):
        project.run("setup")
        plugin = flywheel.os.path.dirname(flywheel.os.path.dirname(flywheel.SCRIPT_PATH))
        with open(plugin + "/templates/roles.json", "rb") as fh:
            assert project.read(".flywheel/roles.template.json") == fh.read()
        for name in ("review-policy", "merge-policy"):
            with open(plugin + "/templates/%s.md" % name, "rb") as fh:
                assert project.read(".flywheel/%s.template.md" % name) == fh.read()
        with open(plugin + "/.claude-plugin/plugin.json", "rb") as fh:
            assert project.read(".flywheel/plugin.json") == fh.read()

    def it_gives_the_prefix_that_reaches_the_copy(self, project):
        code, env = project.run("setup")
        assert code == flywheel.OK
        assert env["data"]["prefix"] == "FLYWHEEL=.flywheel/flywheel.py"
        assert env["data"]["repo"] == str(project.root.resolve())
        assert (project.root / env["data"]["prefix"].split("=", 1)[1]).is_file()

    def it_gives_the_prefix_in_text(self, project):
        code, out, err = project.human("setup")
        assert code == flywheel.OK
        assert out == (
            "wrote .flywheel/flywheel.py\nwrote .flywheel/roles.template.json\n"
            "wrote .flywheel/review-policy.template.md\nwrote .flywheel/merge-policy.template.md\n"
            "wrote .flywheel/plugin.json\nwrote .flywheel/.gitignore\n"
            "\nfrom %s, start every command with:\nFLYWHEEL=.flywheel/flywheel.py && \n"
            % project.root.resolve()
        )
        assert err == ""

    def it_overwrites_an_earlier_copy(self, project):
        project.write(".flywheel/flywheel.py", "old\n")
        code, _ = project.run("setup")
        assert code == flywheel.OK
        with open(flywheel.SCRIPT_PATH, "rb") as fh:
            assert project.read(".flywheel/flywheel.py") == fh.read()

    def it_gives_each_files_checksum(self, project):
        _, env = project.run("setup")
        assert [f["file"] for f in env["data"]["files"]] == [*COPIED, ".flywheel/.gitignore"]
        for f in env["data"]["files"]:
            assert f["sha256"] == hashlib.sha256(project.read(f["file"])).hexdigest()

    def it_works_from_a_folder_inside_the_clone(self, project, capsys):
        (project.root / "sub").mkdir()
        code = flywheel.main(["setup", "-C", str(project.root / "sub"), "--json"])
        assert code == flywheel.OK
        assert json.loads(capsys.readouterr().out)["data"]["repo"] == str(project.root.resolve())
        assert (project.root / ".flywheel" / "flywheel.py").is_file()


@pytest.mark.spec("setup-cmd-copies-script")
class DescribeIgnoringTheCopy:
    def it_leaves_nothing_for_git_to_commit(self, project):
        project.run("setup")
        assert project.git("status", "--porcelain", "--untracked-files=all") == b""

    def it_names_only_the_copies_and_itself(self, project):
        project.run("setup")
        assert project.read(".flywheel/.gitignore") == (
            b".gitignore\nflywheel.py\nmerge-policy.template.md\nplugin.json\n"
            b"review-policy.template.md\nroles.template.json\n"
        )

    def it_leaves_the_owners_files_for_git(self, project):
        project.run("setup")
        project.write(".flywheel/roles.json", "{}\n")
        assert project.git("status", "--porcelain", "--untracked-files=all") == (
            b"?? .flywheel/roles.json\n"
        )


@pytest.mark.spec("setup-cmd-copies-script")
class DescribeTheCopyRunning:
    def it_reads_its_files_beside_it(self, project, monkeypatch, capsys):
        project.run("setup")
        copy = project.root / ".flywheel" / "flywheel.py"
        monkeypatch.setattr(flywheel, "SCRIPT_PATH", str(copy))
        code = flywheel.main(["config", "init", "-C", str(project.root), "--json"])
        assert code == flywheel.OK, capsys.readouterr().err
        roles = json.loads(project.read(".flywheel/roles.json"))
        manifest = json.loads(project.read(".flywheel/plugin.json"))
        assert {e["version"] for e in roles["roles"].values()} == {manifest["version"]}

    def it_names_the_missing_file_when_setup_has_not_copied_it(self, project, monkeypatch):
        project.run("setup")
        (project.root / ".flywheel" / "roles.template.json").unlink()
        copy = project.root / ".flywheel" / "flywheel.py"
        monkeypatch.setattr(flywheel, "SCRIPT_PATH", str(copy))
        code, _ = project.run("config", "init")
        assert code == flywheel.CANNOT_RUN
        assert "roles.template.json is missing" in project.err
        assert "run its setup" in project.err

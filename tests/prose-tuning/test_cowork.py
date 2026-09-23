"""Running prose.py on Cowork's device: where, stage, and preflight's ignore check.

COWORK.md at the repo root says why the script is copied into the project and
why that copy has to stay out of the project's commits.
"""

import hashlib
import json
import shutil
import subprocess

import prose

FOLDER = "/Users/someone/Claude Projects/Notes"


def stage(capsys, *argv):
    """Run `prose.py stage --json`. Returns (exit code, envelope, stderr)."""
    capsys.readouterr()
    code = prose.main(["stage", *argv, "--json"])
    captured = capsys.readouterr()
    return code, json.loads(captured.out) if captured.out else None, captured.err


def entry(env, rel):
    return next(f for f in env["data"]["files"] if f["file"] == rel)


class DescribeStage:
    def it_stages_a_byte_identical_copy_of_the_running_script(self, tmp_path, capsys):
        code, env, _ = stage(capsys, "--folder", FOLDER, "--stage", str(tmp_path))
        assert code == prose.OK
        staged = entry(env, prose.DEVICE_SCRIPT)
        with open(prose.SCRIPT_PATH, "rb") as fh:
            original = fh.read()
        with open(staged["staged_path"], "rb") as fh:
            assert fh.read() == original
        assert staged["sha256"] == hashlib.sha256(original).hexdigest()

    def it_addresses_the_copy_to_the_project_folder_on_the_device(self, tmp_path, capsys):
        _, env, _ = stage(capsys, "--folder", FOLDER + "/", "--stage", str(tmp_path))
        assert [c["devicePath"] for c in env["data"]["commit_files"]] == [
            FOLDER + "/.prose-tuning/prose.py",
            FOLDER + "/.prose-tuning/.gitignore",
        ]
        assert [c["stagedPath"] for c in env["data"]["commit_files"]] == [
            f["staged_path"] for f in env["data"]["files"]
        ]

    def it_keeps_the_copied_folder_out_of_the_projects_commits(self, tmp_path, capsys):
        project = tmp_path / "project"
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        # Staging straight into a repo stands in for the copy device_commit_files makes.
        stage(capsys, "--folder", FOLDER, "--stage", str(project))
        status = subprocess.run(
            ["git", "-C", str(project), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert status.stdout == ""

    def it_starts_device_commands_in_the_mounted_project(self, tmp_path, capsys):
        _, env, _ = stage(capsys, "--folder", FOLDER, "--stage", str(tmp_path))
        assert env["data"]["device_setup"] == (
            'cd "$HOME/mnt"/Notes && PROSE=.prose-tuning/prose.py'
        )

    def it_mounts_a_project_below_the_connected_folder_under_its_path(self, tmp_path, capsys):
        _, env, _ = stage(
            capsys,
            "--connected",
            "/Users/someone/Claude Projects",
            "--folder",
            FOLDER,
            "--stage",
            str(tmp_path),
        )
        assert env["data"]["device_setup"].startswith("cd \"$HOME/mnt\"/'Claude Projects/Notes' ")

    def it_checks_every_staged_file_by_checksum_on_the_device(self, tmp_path, capsys):
        template = tmp_path / "prose-style.md"
        template.write_text("---\nname: T\n---\n")
        _, env, _ = stage(
            capsys, "--folder", FOLDER, "--template", str(template), "--stage", str(tmp_path / "s")
        )
        lines = env["data"]["check_command"].split("\n")
        assert lines[1:-1] == ["%s  %s" % (f["sha256"], f["file"]) for f in env["data"]["files"]]
        assert [f["file"] for f in env["data"]["files"]] == [
            prose.DEVICE_SCRIPT,
            prose.DEVICE_IGNORE,
            prose.DEVICE_TEMPLATE,
        ]

    def it_writes_nothing_on_a_dry_run(self, tmp_path, capsys):
        code, _, _ = stage(capsys, "--folder", FOLDER, "--stage", str(tmp_path / "s"), "--dry-run")
        assert code == prose.OK
        assert not (tmp_path / "s").exists()

    def it_warns_when_the_stage_is_where_device_commit_files_cannot_read(self, tmp_path, capsys):
        _, env, _ = stage(capsys, "--folder", FOLDER, "--stage", str(tmp_path))
        assert any(prose.OUTPUTS_ROOT in w for w in env["warnings"])

    def it_refuses_a_project_outside_the_connected_folder(self, tmp_path, capsys):
        code, env, err = stage(
            capsys,
            "--connected",
            "/Users/someone/Other",
            "--folder",
            FOLDER,
            "--stage",
            str(tmp_path),
        )
        assert code == prose.CANNOT_RUN
        assert env is None
        assert "is not inside" in err

    def it_refuses_a_relative_folder(self, tmp_path, capsys):
        code, _, err = stage(capsys, "--folder", "Notes", "--stage", str(tmp_path))
        assert code == prose.CANNOT_RUN
        assert "absolute path" in err


class DescribePreflightOnTheDevice:
    def install_copy(self, prose_repo, monkeypatch):
        copy = prose_repo.root / ".prose-tuning" / "prose.py"
        copy.parent.mkdir()
        shutil.copyfile(prose.SCRIPT_PATH, str(copy))
        monkeypatch.setattr(prose, "SCRIPT_PATH", str(copy))

    def it_blocks_a_copy_in_the_project_that_git_would_commit(self, prose_repo, monkeypatch):
        self.install_copy(prose_repo, monkeypatch)
        code, env = prose_repo.run("preflight", "--for", "config")
        assert code == prose.PROBLEMS
        assert any(e.startswith(".prose-tuning/prose.py  not ignored") for e in env["errors"])

    def it_accepts_a_copy_its_own_folder_ignores(self, prose_repo, monkeypatch):
        self.install_copy(prose_repo, monkeypatch)
        (prose_repo.root / prose.DEVICE_IGNORE).write_bytes(prose.DEVICE_IGNORE_TEXT)
        code, env = prose_repo.run("preflight", "--for", "config")
        assert code == prose.OK, env["errors"]

    def it_ignores_the_check_for_a_script_outside_the_project(self, prose_repo):
        code, env = prose_repo.run("preflight", "--for", "config")
        assert code == prose.OK, env["errors"]


class DescribeWhere:
    def where(self, capsys):
        capsys.readouterr()
        code = prose.main(["where", "--json"])
        return code, json.loads(capsys.readouterr().out)["data"]["surface"]

    def it_reports_cowork_inside_coworks_container(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(prose, "OUTPUTS_ROOT", str(tmp_path))
        assert self.where(capsys) == (prose.OK, "cowork")

    def it_reports_local_anywhere_else(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(prose, "OUTPUTS_ROOT", str(tmp_path / "absent"))
        assert self.where(capsys) == (prose.OK, "local")

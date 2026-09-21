"""The commands probe and render hand to device_bash, run for real under sh
against a fake $HOME/mnt.

These are what keep an existing folder safe. The folder is the point of this
plugin, so it holding unrelated documents must pass, while a folder that is
missing, is already a repo, or holds a file this would overwrite must stop the
run before anything is copied.
"""

import shutil

import pytest

import gitify

needs_sha256sum = pytest.mark.skipif(
    shutil.which("sha256sum") is None, reason="sha256sum is not installed here"
)


def probe(runner, project_folder="/Users/owner/Documents/Projects/Foo Research"):
    argv = ["probe", "--connected-folder", "/Users/owner/Documents/Projects"]
    if project_folder:
        argv += ["--project-folder", project_folder]
    code, env = runner.run(*argv)
    assert code == gitify.OK, env["errors"]
    return env["data"]["probe_command"]


class DescribeTheProbeCommand:
    def it_lists_a_folder_of_unrelated_documents_and_passes(self, runner, device):
        device.make()
        result = device.sh(probe(runner))
        assert result.returncode == 0, result.stdout + result.stderr
        lines = result.stdout.splitlines()
        assert "files: 2" in lines
        assert "entry: notes.md" in lines
        assert "entry: drafts" in lines

    def it_lists_hidden_entries_and_names_with_spaces(self, runner, device):
        folder = device.make(docs=False)
        (folder / ".env").write_text("SECRET=1\n")
        (folder / "My Notes.md").write_text("x\n")
        result = device.sh(probe(runner))
        assert "entry: .env" in result.stdout.splitlines()
        assert "entry: My Notes.md" in result.stdout.splitlines()

    def it_names_a_large_file(self, runner, device):
        folder = device.make()
        with open(folder / "film.mov", "wb") as fh:
            fh.truncate(11 * 1024 * 1024)
        result = device.sh(probe(runner))
        assert result.returncode == 0
        assert "large: film.mov" in result.stdout.splitlines()
        assert "large: notes.md" not in result.stdout

    def it_stops_on_a_folder_that_is_not_there(self, runner, device):
        device.connected.mkdir(parents=True)
        result = device.sh(probe(runner))
        assert result.returncode == 2
        assert result.stdout.startswith("missing: Projects/Foo Research")

    def it_refuses_a_folder_that_is_already_a_git_repo(self, runner, device):
        (device.make() / ".git").mkdir()
        result = device.sh(probe(runner))
        assert result.returncode == 1
        assert result.stdout.startswith("repo: Projects/Foo Research")
        assert "does not adopt an existing repo" in result.stdout
        assert "files:" not in result.stdout

    def it_probes_the_connected_folder_itself(self, runner, device):
        device.make()
        (device.connected / "top.md").write_text("x\n")
        result = device.sh(probe(runner, project_folder=None))
        assert result.returncode == 0
        assert "entry: top.md" in result.stdout.splitlines()

    def it_rejects_a_project_outside_the_connected_folder(self, runner):
        code, env = runner.run(
            "probe", "--connected-folder", "/a/Projects", "--project-folder", "/b/Foo"
        )
        assert code == gitify.PROBLEMS
        assert any("is not inside connected_folder" in e for e in env["errors"])


class DescribeThePrecheckCommand:
    def it_passes_a_folder_holding_unrelated_documents(self, runner, device, make_answers):
        _, env = runner.render(make_answers())
        device.make()
        result = device.sh(env["data"]["precheck_command"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == "clear"

    def it_refuses_a_folder_already_holding_git(self, runner, device, make_answers):
        _, env = runner.render(make_answers())
        (device.make() / ".git").mkdir()
        result = device.sh(env["data"]["precheck_command"])
        assert result.returncode == 1
        assert result.stdout.startswith("repo: ")

    def it_names_every_file_it_would_overwrite(self, runner, device, make_answers, skill_rel):
        _, env = runner.render(make_answers())
        folder = device.make()
        (folder / "CLAUDE.md").write_text("the owner's own instructions")
        (folder / skill_rel).parent.mkdir(parents=True)
        (folder / skill_rel).write_text("theirs")
        result = device.sh(env["data"]["precheck_command"])
        assert result.returncode == 1
        assert "exists: CLAUDE.md" in result.stdout.splitlines()
        assert "exists: %s" % skill_rel in result.stdout.splitlines()
        assert "clear" not in result.stdout

    def it_stops_on_a_folder_that_is_not_there(self, runner, device, make_answers):
        _, env = runner.render(make_answers())
        device.connected.mkdir(parents=True)
        result = device.sh(env["data"]["precheck_command"])
        assert result.returncode == 2
        assert result.stdout.startswith("missing: ")


class DescribeTheCheckCommand:
    @needs_sha256sum
    def it_passes_when_every_file_arrived(self, runner, device, make_answers):
        _, env = runner.render(make_answers(instructions="Be brief."))
        device.make()
        device.copy_in(env["data"])
        result = device.sh(env["data"]["check_command"])
        assert result.returncode == 0, result.stdout + result.stderr

    @needs_sha256sum
    def it_fails_when_a_file_changed_on_the_way(self, runner, device, make_answers):
        _, env = runner.render(make_answers())
        folder = device.make()
        device.copy_in(env["data"])
        with open(folder / "setup.sh", "a") as fh:
            fh.write("\n")
        result = device.sh(env["data"]["check_command"])
        assert result.returncode != 0
        assert "setup.sh: FAILED" in result.stdout

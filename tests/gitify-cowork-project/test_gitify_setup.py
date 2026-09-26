"""setup.sh and commit.sh as rendered, run with real git in a folder that
already holds someone's work.

The first commit takes the whole folder, so it must not happen until the user
has seen the list and had the chance to keep files out. A pattern added to
.gitignore after the first run has to take effect even though the file was
already staged, which plain `git add -A` does not do.
"""

import os
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed here")


@pytest.fixture
def folder(runner, make_answers, tmp_path):
    """A project folder with documents in it and the rendered files copied in."""
    _, env = runner.render(make_answers())
    folder = tmp_path / "Foo Research"
    (folder / "drafts").mkdir(parents=True)
    (folder / "notes.md").write_text("notes\n")
    (folder / "drafts" / "plan.md").write_text("# Plan\n")
    (folder / "film.mov").write_text("big\n")
    for f in env["data"]["files"]:
        dst = folder / f["file"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f["staged_path"], dst)
    return folder


def sh(folder, *argv):
    home = folder.parent / "home"
    home.mkdir(exist_ok=True)
    env = dict(
        os.environ,
        HOME=str(home),
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Owner",
        GIT_AUTHOR_EMAIL="owner@example.com",
        GIT_COMMITTER_NAME="Owner",
        GIT_COMMITTER_EMAIL="owner@example.com",
    )
    return subprocess.run(["sh", *argv], cwd=folder, capture_output=True, text=True, env=env)


def git(folder, *argv):
    return sh(folder, "-c", 'git "$@"', "git", *argv)


def has_commits(folder):
    return git(folder, "rev-parse", "--verify", "--quiet", "HEAD").returncode == 0


def committed(folder):
    return set(git(folder, "ls-files").stdout.split())


class DescribeSetup:
    @pytest.mark.spec("setup-stages-first")
    def it_stages_everything_and_commits_nothing_on_the_first_run(self, folder):
        result = sh(folder, "setup.sh")
        assert result.returncode == 0, result.stderr
        assert (folder / ".git").is_dir()
        assert not has_commits(folder)
        for rel in ("notes.md", "drafts/plan.md", "film.mov", "CLAUDE.md"):
            assert rel in result.stdout
        assert "sh setup.sh commit" in result.stdout

    @pytest.mark.spec("setup-late-ignore")
    def it_leaves_out_a_file_ignored_after_it_was_staged(self, folder):
        sh(folder, "setup.sh")
        with open(folder / ".gitignore", "a") as fh:
            fh.write("*.mov\n")
        shown = sh(folder, "setup.sh")
        assert "film.mov" not in shown.stdout
        result = sh(folder, "setup.sh", "commit")
        assert result.returncode == 0, result.stderr
        files = committed(folder)
        assert "film.mov" not in files
        assert {"notes.md", "drafts/plan.md", "CLAUDE.md", ".gitignore"} <= files

    @pytest.mark.spec("gitignore-defaults")
    def it_keeps_shared_editor_settings_in_history(self, folder):
        (folder / ".vscode").mkdir()
        (folder / ".vscode" / "settings.json").write_text("{}\n")
        (folder / ".idea").mkdir()
        (folder / ".idea" / "workspace.xml").write_text("<project/>\n")
        sh(folder, "setup.sh", "commit")
        files = committed(folder)
        assert ".vscode/settings.json" in files
        assert ".idea/workspace.xml" not in files

    @pytest.mark.spec("gitignore-defaults", "ignore-chat-outputs")
    def it_leaves_system_editor_and_chat_files_out_of_history(self, folder):
        kept_out = [
            ".DS_Store",
            "._notes.md",
            "drafts/.plan.md.swp",
            "notes.md~",
            "notes.md.bak",
            "Claude outputs/summary.md",
        ]
        for rel in kept_out:
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            (folder / rel).write_text("x\n")
        sh(folder, "setup.sh", "commit")
        # Split on lines, not whitespace: one of the paths has a space in it.
        files = set(git(folder, "ls-files").stdout.splitlines())
        assert "notes.md" in files
        assert files.isdisjoint(kept_out), files & set(kept_out)

    def it_names_the_plugin_in_the_first_commit(self, folder):
        sh(folder, "setup.sh", "commit")
        subject = git(folder, "log", "-1", "--format=%s").stdout.strip()
        assert "gitify-cowork-project" in subject
        assert "existing folder" in subject

    @pytest.mark.spec("setup-sets-exec-bits")
    def it_makes_both_scripts_executable(self, folder):
        sh(folder, "setup.sh")
        assert os.access(folder / "setup.sh", os.X_OK)
        assert os.access(folder / "commit.sh", os.X_OK)

    @pytest.mark.spec("setup-keeps-history")
    def it_does_nothing_to_a_repo_with_history(self, folder):
        sh(folder, "setup.sh", "commit")
        (folder / "new.md").write_text("new\n")
        result = sh(folder, "setup.sh", "commit")
        assert result.returncode == 0
        assert "Already a git repo with history" in result.stdout
        assert git(folder, "rev-list", "--count", "HEAD").stdout.strip() == "1"

    @pytest.mark.spec("setup-usage")
    def it_rejects_an_unknown_argument(self, folder):
        result = sh(folder, "setup.sh", "comit")
        assert result.returncode == 2
        assert not (folder / ".git").exists()


class DescribeCommit:
    @pytest.mark.spec("commit-refuses-first")
    def it_refuses_to_make_the_first_commit(self, folder):
        sh(folder, "setup.sh")
        result = sh(folder, "commit.sh", "chore: too early")
        assert result.returncode == 1
        assert "sh setup.sh" in result.stderr
        assert not has_commits(folder)

    @pytest.mark.spec("commit-after-first")
    def it_commits_after_the_first_one(self, folder):
        sh(folder, "setup.sh", "commit")
        (folder / "notes.md").write_text("more notes\n")
        result = sh(folder, "commit.sh", "docs: add to the notes")
        assert result.returncode == 0, result.stderr
        assert git(folder, "log", "-1", "--format=%s").stdout.strip() == "docs: add to the notes"

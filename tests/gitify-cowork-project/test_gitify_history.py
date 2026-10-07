"""The command history hands to device_bash, run for real under sh against a
fake $HOME/mnt.

The folder is someone else's repo, so the command may add the section and
nothing more: the user's CLAUDE.md keeps every byte, git's history is left
alone, and a second run changes nothing.
"""

import shutil
import subprocess

import pytest

import gitify

needs_sha256sum = pytest.mark.skipif(
    shutil.which("sha256sum") is None, reason="sha256sum is not installed here"
)
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed here")

CONNECTED = "/Users/owner/Documents/Projects"


def history(runner):
    code, env = runner.run("history", "--connected-folder", CONNECTED)
    assert code == gitify.OK, env["errors"]
    return env["data"]["history_command"]


def section(runner):
    """The section as the command appends it, cut from the command itself."""
    lines = history(runner).split("\n")
    start = lines.index("cat >> CLAUDE.md <<'%s'" % gitify.HEREDOC_END) + 1
    end = lines.index(gitify.HEREDOC_END)
    return "\n".join(lines[start:end]) + "\n"


def repo(device):
    """The connected folder, as a repo with one commit."""
    folder = device.connected
    folder.mkdir(parents=True)
    (folder / "notes.md").write_text("the owner's own notes\n")
    git = ["git", "-C", str(folder), "-c", "user.name=o", "-c", "user.email=o@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "first"], check=True)
    return folder


def git_out(folder, *argv):
    return subprocess.run(
        ["git", "-C", str(folder), *argv], capture_output=True, text=True, check=True
    ).stdout


def bare_repo(device):
    """The connected folder with an empty .git, for tests that do not need git."""
    device.connected.mkdir(parents=True)
    (device.connected / ".git").mkdir()
    return device.connected


@needs_sha256sum
class DescribeTheHistoryCommand:
    @pytest.mark.spec("history-cmd-appends-section")
    def it_appends_the_section_after_the_users_own_text(self, runner, device):
        folder = bare_repo(device)
        (folder / "CLAUDE.md").write_text("# Mine\n\nBe brief.\n")
        result = device.sh(history(runner))
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == "added: CLAUDE.md"
        text = (folder / "CLAUDE.md").read_text()
        assert text == "# Mine\n\nBe brief.\n\n" + section(runner)

    @pytest.mark.spec("history-cmd-appends-section")
    def it_ends_the_users_last_line_before_appending(self, runner, device):
        folder = bare_repo(device)
        (folder / "CLAUDE.md").write_text("Be brief.")
        result = device.sh(history(runner))
        assert result.returncode == 0, result.stdout + result.stderr
        assert (folder / "CLAUDE.md").read_text() == "Be brief.\n\n" + section(runner)

    @pytest.mark.spec("history-cmd-appends-section")
    def it_creates_claude_md_when_the_repo_has_none(self, runner, device):
        folder = bare_repo(device)
        result = device.sh(history(runner))
        assert result.returncode == 0, result.stdout + result.stderr
        assert (folder / "CLAUDE.md").read_text() == section(runner)

    @pytest.mark.spec("history-cmd-appends-section")
    @needs_git
    def it_leaves_the_repos_history_alone(self, runner, device):
        folder = repo(device)
        head = git_out(folder, "rev-parse", "HEAD")
        result = device.sh(history(runner))
        assert result.returncode == 0, result.stdout + result.stderr
        assert git_out(folder, "rev-parse", "HEAD") == head
        assert git_out(folder, "status", "--porcelain") == "?? CLAUDE.md\n"

    @pytest.mark.spec("history-cmd-keeps-existing-section")
    def it_changes_nothing_on_a_second_run(self, runner, device):
        folder = bare_repo(device)
        device.sh(history(runner))
        before = (folder / "CLAUDE.md").read_text()
        result = device.sh(history(runner))
        assert result.returncode == 1
        assert result.stdout.startswith("present: CLAUDE.md")
        assert (folder / "CLAUDE.md").read_text() == before

    @pytest.mark.spec("history-cmd-keeps-existing-section")
    def it_counts_the_section_a_full_setup_wrote(self, runner, device):
        folder = bare_repo(device)
        claude_md = (runner.templates_copy() / "CLAUDE.md").read_text()
        (folder / "CLAUDE.md").write_text(claude_md)
        result = device.sh(history(runner))
        assert result.returncode == 1
        assert result.stdout.startswith("present: ")
        assert (folder / "CLAUDE.md").read_text() == claude_md

    @pytest.mark.spec("history-cmd-refuses-non-repo")
    def it_refuses_a_folder_that_is_not_a_repo(self, runner, device):
        device.connected.mkdir(parents=True)
        result = device.sh(history(runner))
        assert result.returncode == 1
        assert result.stdout.startswith("not-repo: Projects")
        assert not (device.connected / "CLAUDE.md").exists()

    @pytest.mark.spec("history-cmd-refuses-non-repo")
    def it_stops_on_a_folder_that_is_not_there(self, runner, device):
        (device.home / "mnt").mkdir(parents=True)
        result = device.sh(history(runner))
        assert result.returncode == 2
        assert result.stdout.startswith("missing: Projects")

    @pytest.mark.spec("history-cmd-appends-section")
    def it_says_so_when_the_appended_bytes_do_not_match(self, runner, device, tmp_path):
        bare_repo(device)
        fake = tmp_path / "bin"
        fake.mkdir()
        (fake / "sha256sum").write_text("#!/bin/sh\necho 0000  -\n")
        (fake / "sha256sum").chmod(0o755)
        result = device.sh('PATH="%s:$PATH"\n%s' % (fake, history(runner)))
        assert result.returncode == 1
        assert result.stdout.startswith("failed: ")


class DescribeTheHistorySection:
    @pytest.mark.spec("historysection-leaves-history-to-git")
    def it_keeps_the_record_of_a_change_out_of_the_documents(self, runner):
        text = section(runner)
        assert text.startswith(gitify.HISTORY_HEADING + "\n")
        assert "Keep that record out of the documents" in text

    @pytest.mark.spec("historysection-leaves-history-to-git")
    def it_leaves_the_commit_to_the_users_terminal(self, runner):
        text = section(runner)
        assert "Never run `git commit`" in text
        assert "commit from their own terminal" in text
        assert "commit.sh" not in text

    @pytest.mark.spec("historysection-gives-history-commands")
    def it_reads_the_history_at_the_connected_folders_mount(self, runner):
        text = section(runner)
        assert 'cd "$HOME/mnt/Projects"' in text
        assert "git log --oneline -- <file>" in text
        assert "{{" not in text


class DescribeTheHistoryArguments:
    @pytest.mark.spec("repo:command-splits-output-streams")
    def it_prints_the_command_on_stdout_in_plain_output(self, runner):
        code, _ = runner.run("history", "--connected-folder", CONNECTED, json_output=False)
        assert code == gitify.OK
        assert runner.out.startswith("history, through device_bash:\n")
        assert runner.err == ""

    @pytest.mark.spec("repo:script-checks-every-answer")
    def it_rejects_a_relative_folder(self, runner):
        code, env = runner.run("history", "--connected-folder", "Projects")
        assert code == gitify.PROBLEMS
        assert any("must be absolute" in e for e in env["errors"])

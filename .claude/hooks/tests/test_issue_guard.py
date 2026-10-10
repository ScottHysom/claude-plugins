"""The hook is the only thing between an agent posting as the owner and the
label that says the owner approved the work. Each case below is a way an agent
would plausibly phrase the command, so a pattern that stops matching one fails
here.
"""

import importlib.util
import io
import json
import shlex
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "issue_guard.py"
_spec = importlib.util.spec_from_file_location("issue_guard", _PATH)
issue_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(issue_guard)

BLOCKED = [
    "gh issue edit 12 --add-label approved",
    "gh issue edit 12 --add-label bug,approved",
    "gh issue edit 12 --add-label 'bug, Approved'",
    "gh issue edit 12 --add-label=approved",
    "gh issue create --title x --body y --label approved",
    "gh issue create -t x -b y -l approved",
    "gh issue create -t x -b y -lapproved",
    "gh issue create -t x -b y -l=approved",
    "gh pr edit 3 -lbug,approved",
    "gh pr edit 3 --add-label approved",
    "gh pr create --fill --label repo --label approved",
    "cd repo && gh issue edit 12 --add-label approved",
    "gh issue list; gh issue edit 12 --add-label approved | cat",
    "GH_REPO=ScottHysom/claude-plugins gh issue edit 12 --add-label approved",
    "/opt/homebrew/bin/gh issue edit 12 --add-label approved",
    'bash -c "gh issue edit 12 --add-label approved"',
    "sh -c 'cd x && gh issue edit 12 --add-label approved'",
    "env GH_REPO=o/r gh issue edit 12 --add-label approved",
    "echo 12 | xargs gh issue edit --add-label approved",
    "(gh issue edit 12 --add-label approved)",
    "cd repo\ngh issue edit 12 --add-label approved",
    "cat <<'EOF' > notes.md\nsome text\nEOF\ngh issue edit 12 --add-label approved",
    "cat <<-EOF > notes.md\n\tsome text\n\tEOF\ngh issue edit 12 --add-label approved",
    "gh api repos/ScottHysom/claude-plugins/issues/12/labels -f 'labels[]=approved'",
    "gh api -X POST /repos/o/r/issues/12/labels --raw-field labels[]=approved",
    "gh label edit repo --name approved",
    "gh label edit repo -napproved",
    "gh label edit repo -n=approved",
    "gh label create approved --color 0e8a16",
    # shlex cannot split an unclosed quote, so the plain text match decides.
    "gh issue edit 12 --add-label approved 'unclosed",
]

ALLOWED = [
    "gh issue edit 12 --add-label bug",
    "gh issue create -t x -b y -lbug",
    "gh issue edit 12 --remove-label approved",
    "gh issue create --title 'Not approved yet' --body 'approved by nobody' --label bug",
    "gh issue list --label approved",
    "gh issue view 12 --json labels",
    "gh pr create --title x --body 'Closes #12, which is approved'",
    "gh label list",
    "gh label edit approved --description 'new words'",
    "gh api repos/o/r/issues/12 --jq .labels",
    "echo approved label",
    "git commit -m 'docs: explain the approved label'",
    # Text that quotes a blocked command is not running it.
    "git commit -m 'Scott runs gh issue edit N --add-label approved'",
    "git commit -F - <<'EOF'\ndocs: how to approve\n\ngh issue edit 12 --add-label approved\nEOF",
    "gh pr create --title x --body \"$(cat <<'EOF'\nRun gh issue edit 12 --add-label approved\nEOF\n)\"",
    "cat <<-EOF > notes.md\n\tgh issue edit 12 --add-label approved\n\tEOF\nls",
    "echo 'gh issue edit 12 --add-label approved'",
    "echo gh issue edit 12 --add-label approved",
    "",
]


def nested(command, depth):
    """The command run through `bash -c`, quoted inside itself depth times."""
    for _ in range(depth):
        command = "bash -c " + shlex.quote(command)
    return command


class DescribeCheck:
    @pytest.mark.parametrize("command", BLOCKED)
    @pytest.mark.spec("guard-blocks-approved-label")
    def it_blocks_a_command_adding_the_label(self, command):
        assert issue_guard.check(command), command

    @pytest.mark.spec("guard-blocks-approved-label")
    def it_blocks_the_label_however_deep_the_shells_nest(self):
        command = nested("cd x && gh issue edit 12 --add-label approved", 6)
        assert issue_guard.check(command), command

    @pytest.mark.parametrize("command", ALLOWED)
    @pytest.mark.spec("guard-allows-quoted-text")
    def it_allows_a_command_that_does_not_add_the_label(self, command):
        assert issue_guard.check(command) is None, command


def run_main(payload, capsys):
    code = issue_guard.main(io.StringIO(payload))
    return code, capsys.readouterr()


def event(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


class DescribeMain:
    @pytest.mark.spec("guard-blocks-approved-label")
    def it_blocks_with_exit_2_and_the_reason_on_stderr(self, capsys):
        code, out = run_main(event("gh issue edit 1 --add-label bug,approved"), capsys)
        assert code == issue_guard.BLOCK == 2
        assert "adds the approved label" in out.err
        assert out.out == ""

    @pytest.mark.spec("guard-allows-quoted-text")
    def it_allows_with_exit_0_and_says_nothing(self, capsys):
        code, out = run_main(event("gh issue edit 1 --add-label bug"), capsys)
        assert code == issue_guard.ALLOW == 0
        assert out.out == out.err == ""

    @pytest.mark.spec("guard-scans-unparsed-input")
    def it_matches_unreadable_input_as_text(self, capsys):
        code, _ = run_main("not json: gh issue edit 1 --add-label approved", capsys)
        assert code == issue_guard.BLOCK
        code, _ = run_main("not json at all", capsys)
        assert code == issue_guard.ALLOW

    @pytest.mark.spec("guard-scans-unparsed-input")
    def it_allows_a_command_it_cannot_split_that_names_no_label(self, capsys):
        code, out = run_main(event("echo 'unclosed"), capsys)
        assert code == issue_guard.ALLOW
        assert out.out == out.err == ""


class DescribeSimpleCommands:
    @pytest.mark.spec("guard-allows-quoted-text")
    def it_drops_heredoc_bodies_and_keeps_the_commands_around_them(self):
        words = ["cat", "<<", "EOF", "\n", "gh", "x", "\n", "EOF", "\n", "ls"]
        assert issue_guard.simple_commands(words) == [["cat", "<<", "EOF"], ["ls"]]


class DescribeRegistration:
    @pytest.mark.spec("settingsjson-registers-guard")
    def it_runs_before_every_bash_command(self):
        settings = json.loads((_PATH.parent.parent / "settings.json").read_text())
        hooks = [
            hook
            for entry in settings["hooks"]["PreToolUse"]
            if entry["matcher"] == "Bash"
            for hook in entry["hooks"]
        ]
        hook = next(h for h in hooks if "hooks/issue_guard.py" in h["command"])
        assert "$CLAUDE_PROJECT_DIR/.claude/hooks/issue_guard.py" in hook["command"]
        assert hook["timeout"] == 10

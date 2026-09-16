"""The hook is the only thing between an agent posting as Scott and the label
that says Scott approved the work. Each case below is a way an agent would
plausibly phrase the command, so a pattern that stops matching one fails here.
"""

import importlib.util
import io
import json
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
    "gh api repos/ScottHysom/claude-plugins/issues/12/labels -f 'labels[]=approved'",
    "gh api -X POST /repos/o/r/issues/12/labels --raw-field labels[]=approved",
    "gh label edit repo --name approved",
    "gh label create approved --color 0e8a16",
    # shlex cannot split an unclosed quote, so the plain text match decides.
    "gh issue edit 12 --add-label approved 'unclosed",
]

ALLOWED = [
    "gh issue edit 12 --add-label bug",
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
    "echo 'gh issue edit 12 --add-label approved'",
    "echo gh issue edit 12 --add-label approved",
    "",
]


class DescribeCheck:
    @pytest.mark.parametrize("command", BLOCKED)
    def it_blocks_a_command_adding_the_label(self, command):
        assert issue_guard.check(command), command

    @pytest.mark.parametrize("command", ALLOWED)
    def it_allows_a_command_that_does_not_add_the_label(self, command):
        assert issue_guard.check(command) is None, command


def run_main(payload, capsys):
    code = issue_guard.main(io.StringIO(payload))
    return code, capsys.readouterr()


def event(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


class DescribeMain:
    def it_blocks_with_exit_2_and_the_reason_on_stderr(self, capsys):
        code, out = run_main(event("gh issue edit 1 --add-label bug,approved"), capsys)
        assert code == issue_guard.BLOCK == 2
        assert "adds the approved label" in out.err
        assert out.out == ""

    def it_allows_with_exit_0_and_says_nothing(self, capsys):
        code, out = run_main(event("gh issue edit 1 --add-label bug"), capsys)
        assert code == issue_guard.ALLOW == 0
        assert out.out == out.err == ""

    def it_matches_unreadable_input_as_text(self, capsys):
        code, _ = run_main("not json: gh issue edit 1 --add-label approved", capsys)
        assert code == issue_guard.BLOCK
        code, _ = run_main("not json at all", capsys)
        assert code == issue_guard.ALLOW


class DescribeSimpleCommands:
    def it_drops_heredoc_bodies_and_keeps_the_commands_around_them(self):
        words = ["cat", "<<", "EOF", "\n", "gh", "x", "\n", "EOF", "\n", "ls"]
        assert issue_guard.simple_commands(words) == [["cat", "<<", "EOF"], ["ls"]]

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

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "plugins" / "flywheel" / "hooks"
_PATH = HOOKS / "issue_guard.py"
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
    "gh issue create -t x -b y -wlapproved",
    "gh issue create -t x -b y -wl approved",
    "gh issue create -t x -b y -wl=approved",
    "gh pr create -dflbug,approved",
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
    # shlex cannot split an unclosed quote, so the plain text match decides.
    "gh issue edit 12 --add-label approved 'unclosed",
]

ALLOWED = [
    "gh issue edit 12 --add-label bug",
    "gh issue create -t x -b y -lbug",
    "gh pr create -dlbug",
    "gh pr create -dl bug",
    "gh issue edit 12 --remove-label approved",
    "gh issue create --title 'Not approved yet' --body 'approved by nobody' --label bug",
    "gh issue list --label approved",
    "gh issue view 12 --json labels",
    "gh pr create --title x --body 'Closes #12, which is approved'",
    "gh label list",
    "gh label edit approved --description 'new words'",
    # The label exists, so GitHub refuses to create it again.
    "gh label create approved --color 0e8a16",
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
    @pytest.mark.spec("repo:guard-blocks-approved-label")
    def it_blocks_a_command_adding_the_label(self, command):
        assert issue_guard.check(command), command

    @pytest.mark.spec("repo:guard-blocks-approved-label")
    def it_blocks_the_label_however_deep_the_shells_nest(self):
        command = nested("cd x && gh issue edit 12 --add-label approved", 6)
        assert issue_guard.check(command), command

    @pytest.mark.parametrize("command", ALLOWED)
    @pytest.mark.spec("repo:guard-allows-quoted-text")
    def it_allows_a_command_that_does_not_add_the_label(self, command):
        assert issue_guard.check(command) is None, command


def run_main(payload, capsys):
    code = issue_guard.main(io.StringIO(payload))
    return code, capsys.readouterr()


def event(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


class DescribeMain:
    @pytest.mark.spec("repo:guard-blocks-approved-label")
    def it_blocks_with_exit_2_and_the_reason_on_stderr(self, capsys):
        code, out = run_main(event("gh issue edit 1 --add-label bug,approved"), capsys)
        assert code == issue_guard.BLOCK == 2
        assert "adds the approved label" in out.err
        assert out.out == ""

    @pytest.mark.spec("repo:guard-allows-quoted-text")
    def it_allows_with_exit_0_and_says_nothing(self, capsys):
        code, out = run_main(event("gh issue edit 1 --add-label bug"), capsys)
        assert code == issue_guard.ALLOW == 0
        assert out.out == out.err == ""

    @pytest.mark.spec("repo:guard-scans-unparsed-input")
    def it_matches_unreadable_input_as_text(self, capsys):
        code, _ = run_main("not json: gh issue edit 1 --add-label approved", capsys)
        assert code == issue_guard.BLOCK
        code, _ = run_main("not json at all", capsys)
        assert code == issue_guard.ALLOW

    @pytest.mark.spec("repo:guard-scans-unparsed-input")
    def it_allows_a_command_it_cannot_split_that_names_no_label(self, capsys):
        code, out = run_main(event("echo 'unclosed"), capsys)
        assert code == issue_guard.ALLOW
        assert out.out == out.err == ""


class DescribeSimpleCommands:
    @pytest.mark.spec("repo:guard-allows-quoted-text")
    def it_drops_heredoc_bodies_and_keeps_the_commands_around_them(self):
        words = ["cat", "<<", "EOF", "\n", "gh", "x", "\n", "EOF", "\n", "ls"]
        assert issue_guard.simple_commands(words) == [["cat", "<<", "EOF"], ["ls"]]


def bash_hooks(path):
    """Each hook the file at path runs before a Bash command."""
    settings = json.loads(path.read_text())
    return [
        hook
        for entry in settings["hooks"]["PreToolUse"]
        if entry["matcher"] == "Bash"
        for hook in entry["hooks"]
    ]


def guard_hook(path):
    return next(h for h in bash_hooks(path) if "hooks/issue_guard.py" in h["command"])


class DescribeRegistration:
    @pytest.mark.spec("repo:settingsjson-registers-guard")
    def it_runs_the_plugins_copy_before_every_bash_command_in_this_repo(self):
        hook = guard_hook(REPO / ".claude" / "settings.json")
        assert "$CLAUDE_PROJECT_DIR/plugins/flywheel/hooks/issue_guard.py" in hook["command"]
        assert hook["timeout"] == 10

    @pytest.mark.spec("hook-ships-with-plugin")
    def it_runs_before_every_bash_command_wherever_the_plugin_is_installed(self):
        hook = guard_hook(HOOKS / "hooks.json")
        assert hook["command"] == 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/issue_guard.py"'
        assert hook["timeout"] == 10
        assert _PATH.is_file()


def project(tmp_path, labels=None):
    """A project the session runs in, with labels as its .flywheel/labels.json text."""
    (tmp_path / ".git").mkdir(parents=True)
    if labels is not None:
        (tmp_path / ".flywheel").mkdir()
        (tmp_path / ".flywheel" / "labels.json").write_text(labels)
    sub = tmp_path / "src"
    sub.mkdir()
    return sub


def event_in(cwd, command):
    return json.dumps({"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": command}})


@pytest.mark.spec("guard-reads-approval-label")
class DescribeTheProjectsApprovalLabel:
    def it_blocks_the_approval_label_the_project_gives(self, tmp_path, capsys):
        cwd = project(tmp_path, json.dumps({"roles": {"approval": "ready"}}))
        code, out = run_main(event_in(cwd, "gh issue edit 1 --add-label bug,Ready"), capsys)
        assert code == issue_guard.BLOCK
        assert "adds the ready label" in out.err
        assert "Ask the owner to add `ready`." in out.err
        code, _ = run_main(event_in(cwd, "gh issue edit 1 --add-label approved"), capsys)
        assert code == issue_guard.ALLOW

    def it_blocks_approved_when_the_project_does_not_give_a_label(self, tmp_path, capsys):
        bare = tmp_path / "bare"
        bare.mkdir()
        roots = (
            project(tmp_path / "one"),
            project(tmp_path / "two", json.dumps({"roles": {}})),
            bare,
        )
        for cwd in roots:
            code, _ = run_main(event_in(cwd, "gh issue edit 1 --add-label approved"), capsys)
            assert code == issue_guard.BLOCK

    @pytest.mark.parametrize(
        "labels", ["not json", json.dumps([]), json.dumps({"roles": {"approval": ""}})]
    )
    def it_blocks_every_added_label_when_it_cannot_read_the_file(self, tmp_path, capsys, labels):
        cwd = project(tmp_path, labels)
        code, out = run_main(event_in(cwd, "gh issue edit 1 --add-label bug"), capsys)
        assert code == issue_guard.BLOCK
        assert "Fix %s" % issue_guard.LABELS_FILE in out.err
        code, _ = run_main(event_in(cwd, "gh issue list --label bug"), capsys)
        assert code == issue_guard.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            "gh issue create -t x -b y -l bug",
            "gh label edit bug --name urgent",
            "gh api repos/o/r/issues/1/labels -f labels[]=bug",
            "gh issue edit 1 --add-label bug 'unclosed",
        ],
    )
    def it_blocks_each_way_of_adding_a_label_when_any_label_counts(self, command):
        assert issue_guard.check(command, None), command

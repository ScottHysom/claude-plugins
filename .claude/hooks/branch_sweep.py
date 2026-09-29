"""Delete the local branches whose work is on main when a Claude Code session starts.

Runs as a SessionStart hook on startup, configured in .claude/settings.json. The
desktop app makes a branch for every session and never deletes it, and a
merged pull request leaves its branch behind locally, so without this they
pile up. `.github/scripts/issues.py sweep` does the deciding and the deleting;
its docstring says which branches it keeps and why. This hook only runs it and
reports.

What the hook prints on stdout, Claude Code adds to the session's context:
one line naming the branches deleted, or nothing when none were. When the
sweep cannot run (offline, gh not signed in, a slow network), the hook prints
one line saying so and naming the command to run by hand, and still exits 0.
A branch left for the next session costs nothing, and a session should never
start with an error because of one.
"""

import json
import os
import subprocess
import sys

ISSUES = os.path.join(".github", "scripts", "issues.py")
# Under the 30 seconds .claude/settings.json gives the hook, so the hook
# reports a slow sweep itself rather than being killed silently.
TIMEOUT = 25
BY_HAND = "python3 .github/scripts/issues.py sweep"


def sweep(root):
    """issues.py sweep's JSON envelope, or a string saying why it did not run."""
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(root, ISSUES), "sweep", "--json", "-C", root],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "it took longer than %s seconds" % TIMEOUT
    except OSError as exc:
        return str(exc)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        lines = proc.stderr.strip().splitlines()
        return lines[-1] if lines else "issues.py exited %d" % proc.returncode


def main():
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    result = sweep(root)
    if isinstance(result, str):
        print("The branch sweep did not run: %s. Run `%s` by hand." % (result, BY_HAND))
        return 0
    deleted = result["data"]["deleted"]
    if deleted:
        print(
            "The branch sweep deleted %d local branch(es) whose work is on main: %s."
            % (len(deleted), ", ".join(deleted))
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Format and lint a Python file with ruff after Claude Code edits it.

Runs as a PostToolUse hook, configured in .claude/settings.json, so a file an
agent writes comes out as ruff would leave it and any lint problem is reported
while the edit is fresh - the same thing an editor that formats on save and
lints as you type does for a person. CI checks both either way; this only saves
the round trip of a red build. README.md, under "Formatting and linting",
covers the rest.

Only import sorting is fixed automatically. Other lint fixes are reported, not
applied: an agent often adds an import in one edit and its first use in the
next, and a hook that removed "unused" imports would undo the first edit.

Uses the ruff in the repo's .venv, where README.md installs it, and falls back
to one on PATH. Exit code 2 hands stderr back to Claude, which is how it learns
that ruff is missing, that the file does not parse, or what the linter found.
"""

import json
import os
import shutil
import subprocess
import sys


def find_ruff(root):
    for name in ("ruff", "ruff.exe"):
        candidate = os.path.join(root, ".venv", "bin" if os.name != "nt" else "Scripts", name)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("ruff")


def ruff_run(ruff, root, *args):
    return subprocess.run([ruff, *args], cwd=root, capture_output=True, text=True, check=False)


def main():
    event = json.load(sys.stdin)
    path = (event.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".py") or not os.path.isfile(path):
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    ruff = find_ruff(root)
    if ruff is None:
        sys.stderr.write(
            "ruff is not installed, so %s was not formatted or linted. Install the "
            "contributor tools as README.md describes: pip install -r requirements-dev.txt\n" % path
        )
        return 2

    # --force-exclude applies ruff.toml's excludes to a path named on the command
    # line, which ruff otherwise checks regardless. Imports are sorted before
    # formatting, because sorting can leave lines the formatter would change.
    ruff_run(ruff, root, "check", "--select", "I", "--fix", "--force-exclude", path)

    # No --quiet: it also silences the parse error that is the point of
    # reporting a failure.
    formatted = ruff_run(ruff, root, "format", "--force-exclude", path)
    if formatted.returncode != 0:
        sys.stderr.write("ruff format failed on %s:\n%s" % (path, formatted.stderr))
        return 2

    linted = ruff_run(ruff, root, "check", "--force-exclude", "--output-format=concise", path)
    if linted.returncode != 0:
        sys.stderr.write("ruff check found problems in %s:\n%s" % (path, linted.stdout))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

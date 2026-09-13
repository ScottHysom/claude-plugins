"""Format a Python file with ruff after Claude Code edits it.

Runs as a PostToolUse hook, configured in .claude/settings.json, so a file an
agent writes comes out the way `ruff format` would leave it - the same result
as a person whose editor formats on save. CI checks the formatting either way;
this only saves the round trip of a red build. README.md, under "Formatting",
covers the rest.

Uses the ruff in the repo's .venv, where README.md installs it, and falls back
to one on PATH. Exit code 2 hands stderr back to Claude, which is how it learns
that ruff is missing or that the file it just wrote does not parse.
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


def main():
    event = json.load(sys.stdin)
    path = (event.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".py") or not os.path.isfile(path):
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    ruff = find_ruff(root)
    if ruff is None:
        sys.stderr.write(
            "ruff is not installed, so %s was not formatted. Install the contributor "
            "tools as README.md describes: pip install -r requirements-dev.txt\n" % path
        )
        return 2

    # --force-exclude applies ruff.toml's excludes to a path named on the command
    # line, which ruff otherwise formats regardless. No --quiet: it also silences
    # the parse error that is the point of reporting a failure.
    result = subprocess.run(
        [ruff, "format", "--force-exclude", path],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write("ruff format failed on %s:\n%s" % (path, result.stderr))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

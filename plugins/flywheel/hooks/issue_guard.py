"""Stop Claude Code from adding the approval label to an issue or pull request.

Runs as a PreToolUse hook on Bash. The flywheel plugin's hooks/hooks.json
registers it wherever the plugin is installed, and a project may also run it
from its own .claude/settings.json. The `approved` label is how the owner says
an issue may be worked on. Agents post as the owner, so GitHub cannot tell an
agent adding the label from the owner adding it. This hook is what can.

It catches a mistake, or an agent talked into approving its own work, not a
determined attempt: it sees only the command text, so `curl` with a token,
`gh api graphql` with a label id, or a script file that runs `gh` all get past
it. Cowork does not run project hooks at all. The owner adds the label in the
browser, or with `! gh issue edit N --add-label approved`, which runs in the
owner's own shell where no hook fires.

The approval label is `approved` unless the project's .flywheel/labels.json
gives another under `roles`, as `{"roles": {"approval": "ready"}}`. The
project is the git working tree that holds the session's directory, which
Claude Code passes as `cwd` in the hook's input. When that file is there and
cannot be read, the hook does not know which label approves, so it blocks
every command below that adds any label, and says to fix the file.

Blocked, where the label value names the approval label, alone or in a comma
list:
    gh issue|pr create|edit  --label/-l/--add-label
    gh label edit             renaming a label to approved
    gh api                    a request whose path mentions labels

`gh label create approved` goes through: the label already exists, so GitHub
refuses to create it again.

Only a `gh` that is actually run counts. A commit message or PR body that
quotes one of these commands is text, and goes through.

Exit code 2 blocks the command and hands stderr back to Claude. Anything the
hook cannot read - bad JSON, a command shlex cannot split - is checked by a
plain text match instead, which errs toward blocking.
"""

import json
import os
import re
import shlex
import sys

LABEL = "approved"
# The project's file that names its approval label, and where it keeps it.
LABELS_FILE = os.path.join(".flywheel", "labels.json")
ROLES_KEY, APPROVAL = "roles", "approval"
ALLOW, BLOCK = 0, 2

ADD_LABEL_FLAGS = ("--label", "-l", "--add-label")
LABEL_VERBS = {("issue", "create"), ("issue", "edit"), ("pr", "create"), ("pr", "edit")}
SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", "\n"}
PUNCTUATION = "();<>|&\n"
HEREDOC_OPS = ("<<",)
SHELLS = {"sh", "bash"}
WRAPPERS = {"env", "xargs"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class Unreadable(Exception):
    """The project's labels file is there and cannot be read."""


def project_label(cwd):
    """The approval label the project holding cwd gives, else LABEL.

    Raises Unreadable when the project's labels file cannot be read.
    """
    here = os.path.abspath(cwd or os.getcwd())
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            break
        up = os.path.dirname(here)
        if up == here:
            return LABEL
        here = up
    path = os.path.join(here, LABELS_FILE)
    if not os.path.isfile(path):
        return LABEL
    try:
        with open(path, encoding="utf-8") as fh:
            roles = json.load(fh).get(ROLES_KEY, {})
        name = roles.get(APPROVAL, LABEL)
    except (OSError, ValueError, AttributeError) as exc:
        raise Unreadable("%s: %s" % (path, exc)) from exc
    if not isinstance(name, str) or not name.strip():
        raise Unreadable("%s gives the approval role an empty label" % path)
    return name.strip()


def fallback_re(label):
    """The plain text match, used when the command cannot be split into words."""
    return re.compile(
        r"\bgh\b.*\blabel.*%s" % (r"\b%s\b" % re.escape(label) if label else ""), re.I | re.S
    )


def names_label(value, label):
    """Whether a label flag's value names the label, or any label when label is None."""
    if label is None:
        return bool(value.strip())
    return any(part.strip().lower() == label.lower() for part in value.split(","))


def flag_values(args, flags):
    """Values given to any of these flags, as `--flag value` or `--flag=value`.

    A short flag also takes its value attached, as gh reads it: `-lvalue` and
    `-l=value` both give `value`. gh reads `-wl value` as `-w -l value`, so a
    short flag counts after other short flags in one word too. When one of
    those takes a value, gh reads the rest of the word as that value rather
    than as `-l`, and the guard still counts `-l` there, erring toward
    blocking.
    """
    out = []
    for i, arg in enumerate(args):
        for flag in flags:
            if flag.startswith("--"):
                if arg == flag and i + 1 < len(args):
                    out.append(args[i + 1])
                elif arg.startswith(flag + "="):
                    out.append(arg[len(flag) + 1 :])
                continue
            if not arg.startswith("-") or arg.startswith("--"):
                continue
            group = arg[1:]
            at = group.find(flag[1:])
            # Only letters before the flag are other short flags.
            if at < 0 or (at > 0 and not group[:at].isalpha()):
                continue
            rest = group[at + 1 :]
            if rest:
                out.append(rest[1:] if rest.startswith("=") else rest)
            elif i + 1 < len(args):
                out.append(args[i + 1])
    return out


def gh_blocks(args, label):
    """The reason to block one `gh` invocation (its arguments after `gh`), or None.

    A label of None stands for any label.
    """
    what = label or "a"
    if len(args) >= 2 and (args[0], args[1]) in LABEL_VERBS:
        if any(names_label(v, label) for v in flag_values(args[2:], ADD_LABEL_FLAGS)):
            return "gh %s %s adds %s label" % (
                args[0],
                args[1],
                "the %s" % label if label else what,
            )
    if len(args) >= 2 and args[0] == "label" and args[1] == "edit":
        # edit names an existing label, and only --name renames it.
        if any(names_label(v, label) for v in flag_values(args[2:], ("--name", "-n"))):
            return "gh label edit would rename a label to %s" % (label or "another name")
    if args and args[0] == "api":
        if any("label" in a.lower() for a in args[1:]) and (
            label is None or any(re.search(r"\b%s\b" % re.escape(label), a, re.I) for a in args[1:])
        ):
            return "gh api touches labels%s" % (" and names %s" % label if label else "")
    return None


def command_args(words):
    """The arguments after `gh` when `gh` is the command this runs, else None.

    Only the command word counts, after any VAR=value assignments and wrappers
    such as env or xargs. `gh` appearing in an argument - a commit message or PR
    body that quotes the command - is text, not a command.
    """
    i = 0
    while i < len(words) and (ASSIGNMENT_RE.match(words[i]) or words[i] in WRAPPERS):
        i += 1
    if i < len(words) and (words[i] == "gh" or words[i].endswith("/gh")):
        return words[i + 1 :]
    return None


def simple_commands(words):
    """Words grouped into simple commands, with heredoc bodies dropped.

    A heredoc's body is text, however much it looks like a command. It starts
    on the line after the `<<` and ends at a line holding only its delimiter.
    """
    out, delimiters, i = [[]], [], 0
    while i < len(words):
        w = words[i]
        if w in HEREDOC_OPS and i + 1 < len(words) and words[i + 1] != "\n":
            delimiters.append(words[i + 1].lstrip("-"))
            out[-1].extend(words[i : i + 2])
            i += 2
            continue
        i += 1
        if w == "\n":
            out.append([])
            for delim in delimiters:
                while i < len(words):
                    end = words.index("\n", i) if "\n" in words[i:] else len(words)
                    line, i = words[i:end], end + 1
                    if line == [delim]:
                        break
            delimiters = []
        elif w in SEPARATORS or set(w) <= set(PUNCTUATION):
            out.append([])
        else:
            out[-1].append(w)
    return out


def check(command, label=LABEL):
    """The reason to block this shell command, or None.

    A label of None blocks any label the command adds.
    """
    try:
        # A newline ends a command just as ; does, so it is punctuation here
        # rather than whitespace.
        lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        if fallback_re(label).search(command):
            return "could not parse the command, and it looks like it adds %s label" % (
                "the %s" % label if label else "a"
            )
        return None

    simple = simple_commands(words)

    for cmd in simple:
        args = command_args(cmd)
        if args is not None:
            reason = gh_blocks(args, label)
            if reason:
                return reason
        # A shell run with -c takes its command as one quoted argument. That
        # argument is shorter than the command it came from, so the re-reading
        # ends however deep the nesting goes.
        if cmd and cmd[0].split("/")[-1] in SHELLS:
            for flag, script in zip(cmd, cmd[1:]):
                if flag == "-c":
                    reason = check(script, label)
                    if reason:
                        return reason
    return None


def approval_label(cwd):
    """The approval label to block, None for any label, and the remedy to name."""
    try:
        label = project_label(cwd)
    except Unreadable as exc:
        return None, "Fix %s (%s), then run again." % (LABELS_FILE, exc)
    return label, "Ask the owner to add `%s`." % label


def main(stdin=None):
    raw = (stdin or sys.stdin).read()
    try:
        payload = json.loads(raw)
        command = (payload.get("tool_input") or {}).get("command") or ""
        label, remedy = approval_label(payload.get("cwd"))
        reason = check(command, label)
    except (ValueError, AttributeError):
        label, remedy = approval_label(None)
        reason = (
            fallback_re(label).search(raw)
            and "could not read the hook input, and it mentions the label"
        )
    if not reason:
        return ALLOW
    sys.stderr.write(
        "Blocked: %s. Only the owner approves an issue, since agents post under the owner's"
        " account and GitHub cannot tell them apart. %s\n" % (reason, remedy)
    )
    return BLOCK


if __name__ == "__main__":
    sys.exit(main())

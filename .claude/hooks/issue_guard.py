"""Stop Claude Code from adding the `approved` label to an issue or pull request.

Runs as a PreToolUse hook on Bash, configured in .claude/settings.json. The
`approved` label is how Scott says an issue may be worked on; README.md, under
"Issues", describes the process. Agents post as Scott, so GitHub cannot tell
an agent adding the label from Scott adding it. This hook is what can.

It catches a mistake, or an agent talked into approving its own work, not a
determined attempt: it sees only the command text, so `curl` with a token,
`gh api graphql` with a label id, or a script file that runs `gh` all get past
it. Cowork does not run project hooks at all. Scott adds the label in the
browser, or with `! gh issue edit N --add-label approved`, which runs in Scott's
own shell where no hook fires.

Blocked, where the label value names `approved`, alone or in a comma list:
    gh issue|pr create|edit  --label/-l/--add-label
    gh label create|edit      creating a label named approved, or renaming one to it
    gh api                    a request whose path mentions labels

Only a `gh` that is actually run counts. A commit message or PR body that
quotes one of these commands is text, and goes through.

Exit code 2 blocks the command and hands stderr back to Claude. Anything the
hook cannot read - bad JSON, a command shlex cannot split - is checked by a
plain text match instead, which errs toward blocking.
"""

import json
import re
import shlex
import sys

LABEL = "approved"
ALLOW, BLOCK = 0, 2

ADD_LABEL_FLAGS = ("--label", "-l", "--add-label")
LABEL_VERBS = {("issue", "create"), ("issue", "edit"), ("pr", "create"), ("pr", "edit")}
SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", "\n"}
PUNCTUATION = "();<>|&\n"
HEREDOC_OPS = ("<<", "<<-")
# How far a quoted command inside a command (bash -c "...") is re-read.
NESTING_LIMIT = 3
SHELLS = {"sh", "bash", "zsh", "dash"}
WRAPPERS = {"env", "command", "exec", "sudo", "time", "nohup", "xargs"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Used when the command cannot be split into words.
FALLBACK_RE = re.compile(r"\bgh\b.*\blabel.*\b%s\b" % LABEL, re.I | re.S)


def names_label(value):
    return any(part.strip().lower() == LABEL for part in value.split(","))


def flag_values(args, flags):
    """Values given to any of these flags, as `--flag value` or `--flag=value`."""
    out = []
    for i, arg in enumerate(args):
        for flag in flags:
            if arg == flag and i + 1 < len(args):
                out.append(args[i + 1])
            elif arg.startswith(flag + "=") and flag.startswith("--"):
                out.append(arg[len(flag) + 1 :])
    return out


def gh_blocks(args):
    """The reason to block one `gh` invocation (its arguments after `gh`), or None."""
    if len(args) >= 2 and (args[0], args[1]) in LABEL_VERBS:
        if any(names_label(v) for v in flag_values(args[2:], ADD_LABEL_FLAGS)):
            return "gh %s %s adds the %s label" % (args[0], args[1], LABEL)
    if len(args) >= 2 and args[0] == "label" and args[1] in ("create", "edit"):
        # create names the new label; edit names an existing one, and only
        # --name renames it.
        named = [a for a in args[2:3] if not a.startswith("-")] if args[1] == "create" else []
        renamed = flag_values(args[2:], ("--name", "-n"))
        if any(v.strip().lower() == LABEL for v in named + renamed):
            return "gh label %s would create a label named %s" % (args[1], LABEL)
    if args and args[0] == "api":
        if any("label" in a.lower() for a in args[1:]) and any(
            re.search(r"\b%s\b" % LABEL, a, re.I) for a in args[1:]
        ):
            return "gh api touches labels and names %s" % LABEL
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


def check(command, depth=0):
    """The reason to block this shell command, or None."""
    try:
        # A newline ends a command just as ; does, so it is punctuation here
        # rather than whitespace.
        lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        if FALLBACK_RE.search(command):
            return "could not parse the command, and it looks like it adds the %s label" % LABEL
        return None

    simple = simple_commands(words)

    for cmd in simple:
        args = command_args(cmd)
        if args is not None:
            reason = gh_blocks(args)
            if reason:
                return reason
        # A shell run with -c takes its command as one quoted argument.
        if depth < NESTING_LIMIT and cmd and cmd[0].split("/")[-1] in SHELLS:
            for flag, script in zip(cmd, cmd[1:]):
                if flag == "-c":
                    reason = check(script, depth + 1)
                    if reason:
                        return reason
    return None


def main(stdin=None):
    raw = (stdin or sys.stdin).read()
    try:
        command = (json.loads(raw).get("tool_input") or {}).get("command") or ""
        reason = check(command)
    except (ValueError, AttributeError):
        reason = (
            FALLBACK_RE.search(raw) and "could not read the hook input, and it mentions the label"
        )
    if reason is None:
        return ALLOW
    sys.stderr.write(
        "Blocked: %s. Only Scott adds `%s`; README.md, under Issues, says why. "
        "Ask Scott to add it.\n" % (reason, LABEL)
    )
    return BLOCK


if __name__ == "__main__":
    sys.exit(main())

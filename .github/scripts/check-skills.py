#!/usr/bin/env python3
"""Check what a plugin's skills say, for what the other checks cannot see.

`repeats` keeps a plugin's skills sharing a step rather than each carrying a
copy. When two skills in one plugin need the same instructions, CLAUDE.md puts them
once in the plugin's reference/ and has each SKILL.md point there. A copy
pasted into a second SKILL.md reads fine in either file, and the two drift
apart the first time someone edits one of them. No diff shows the copy unless
the reviewer happens to have both files open. `repeats` is what notices.

`descriptions` keeps each skill uploadable to Cowork. Uploading a .plugin file
rejects a skill whose `description` holds anything that looks like an XML tag
("SKILL.md description cannot contain XML tags"). A marketplace install
accepts the same skill, and so does `claude plugin validate --strict`, so CI
stayed green while the upload failed. COWORK.md, under "How skills load",
records the difference.

`commands` keeps each command a skill runs one its script accepts. A SKILL.md
that names a subcommand or flag the script lacks passes review, and the model
meets the usage error part way through a run and falls back on doing the step
by hand. `commands` reads every shell fence in a plugin's SKILL.md files and
reference/ files, and puts each script invocation through that script's own
build_parser().

`fences` keeps a skill's shell fences to running the plugin's script. A fence
holding `python3 -c`, `grep` or `awk` tells the model to compute by hand what
the script should compute, and two runs of it need not agree. `fences` reads
the same files as `commands`. Every fence there must carry an info string, so
a shell block cannot pass for quoted markup. Every command in a shell fence
must be a script invocation or match an entry in ALLOWED, which gives each
entry's reason beside it.

Run from anywhere in the clone:

    python3 .github/scripts/check-skills.py repeats
    python3 .github/scripts/check-skills.py descriptions
    python3 .github/scripts/check-skills.py commands
    python3 .github/scripts/check-skills.py fences

Commands:

  repeats       no block of text appears in two SKILL.md files of the same
                plugin
  descriptions  no description in the front matter of a markdown file under
                plugins/ holds a `<` followed by a tag-like name
  commands      every `python3 <script> ...` in a skill's shell fences parses
                with that script's build_parser()
  fences        every fence has an info string, and every command in a shell
                fence runs a script or is on the ALLOWED list

Every command takes --json and -C/--repo.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

What counts as a block: a paragraph, a table, a fenced code block (blank lines
and all), or a single list item without its bullet or number. Whitespace is
collapsed before comparing, so rewrapping a copied paragraph does not hide it.

Things that look like bugs and are not, in `repeats`:

- The "Locate the script" section is skipped entirely. Every SKILL.md must carry
  it, because Cowork fills in ${CLAUDE_SKILL_DIR} only in SKILL.md itself, and
  reference/setup.md names that step as the one every skill starts from - so
  the pointer to setup.md at the end of it repeats by design, not only the
  fence that sets ROOT. The section's heading is the named exception,
  LOCATE_SECTION below.
- Headings are skipped. "## Step 1: refuse early" in two skills is two skills
  with the same shape, not a copied instruction.
- Each list item is its own block. Comparing whole lists would miss one bullet
  copied into a list that otherwise differs.
- Skills are compared only within a plugin. Each plugin installs on its own and
  cannot point at another's reference/, so text shared across plugins has
  nowhere to go.
- A paragraph repeated inside one SKILL.md is not reported. That is a matter of
  editing the one file, and has no reference/ to move to.
- It fails when it has scanned nothing: no SKILL.md at all, or one that yields
  no blocks. A check whose file pattern or parser has gone blind passes every
  pull request, so scanning nothing is an error rather than a clean run.

Things that look like bugs and are not, in `descriptions`:

- It reads every markdown file under plugins/ whose front matter has a
  description, not only SKILL.md. A generated-skill template, such as
  gitify-cowork-project's, is a skill too, once rendered. Its description is a
  placeholder the plugin script fills in and checks at runtime; this check
  keeps the template itself clean.
- A `<` on its own, as in `a < b` or `<3`, passes. Only `<` directly followed
  by a letter, or by `/` and a letter, reads as a tag.
- It fails when it finds no descriptions at all, for the same reason as
  `repeats`.

Things that look like bugs and are not, in `commands`:

- A variable is resolved from its assignment anywhere in the same plugin's
  files, not only earlier in the same file. reference/ files use the $PROSE
  that SKILL.md's "Locate the script" step sets, and never set it themselves.
- Only the file name of an assigned path counts. `$ROOT/scripts/prose.py`,
  `.prose-tuning/prose.py` and `/tmp/gitify/plugin/scripts/gitify.py` are all
  the plugin's own scripts/<name>, wherever a skill copies or links it. A
  literal path such as `.github/scripts/check-manifest-consistency.py` is read
  from the root of the clone.
- Only fences whose info string is sh, bash or shell are read. A text or
  markdown fence holds something the model does not run. `fences` fails a
  fence with no info string at all.
- A `<placeholder>` becomes one word, PLACEHOLDER, and is passed as that text.
  An argument with `type=` or `choices` therefore needs a real value in the
  fence. `[optional]` parts lose their brackets and are checked, so an
  optional flag must exist too.
- A heredoc's body is not read. It is data the command reads, not a command.
- `python3 -c` and commands other than python are not checked here. `fences`
  decides whether a shell fence may hold them at all.
- It fails when it finds no invocation at all, or a script with no
  build_parser(), for the same reason as `repeats`.

Things that look like bugs and are not, in `fences`:

- It judges each simple command, not each line. `cd "<dir>" && PROSE=... &&
  python3 "$PROSE" ...` passes because each of its parts does, and
  `python3 "$PROSE" segments | grep x` fails on the grep alone.
- An invocation is any `python3` followed by a variable or a .py path. Whether
  the script accepts the arguments is `commands`' job, not this one's.
- An ALLOWED entry holds only in its position. `cd` may open a line but not
  end one, and `echo` may only follow `ls "$VAR" ||`, so a bare
  `echo "$x" | cut -f1` still fails.
- A heredoc's body is not read, as in `commands`. The findings heredoc is
  allowed because its body is the model's judgment, written for the script
  to read.
- It fails when it finds no shell fence at all, for the same reason as
  `repeats`.

All commands:

- They only read. `repeats`, `descriptions` and `fences` read through git and nothing
  else. `commands` also imports each script a skill runs, from the working
  tree, and calls its build_parser(), since only the parser knows the
  commands the script accepts. The scripts run main() only under
  `if __name__ == "__main__":`, so importing one runs no command. None of the
  commands writes a file, so all are safe to run anywhere, including Cowork's
  device bridge, where a git write would strand a lock file.
"""

import argparse
import collections
import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import subprocess
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-skills.py"
PLUGINS = "plugins"
SKILLS = "skills"
SKILL_FILE = "SKILL.md"
REFERENCE = "reference"
LOCATE_SECTION = "Locate the script"
MARKDOWN = ".md"

FRONT_MATTER = "---"
# A fence opener: its indent, its run of backticks or tildes, and its info
# string, the first word after the marker ("sh" in ```sh).
FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>`{3,}|~{3,})[ \t]*(?P<info>[^`\s]*)")
HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.*?)[ \t#]*$")
LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
# How much of a repeated block an error quotes.
QUOTE_CHARS = 72
DESCRIPTION_RE = re.compile(r"^description:(.*)$")
# A continuation line of a folded or multi-line YAML value is indented.
CONTINUATION_RE = re.compile(r"^[ \t]+\S")
# A `<` directly followed by a tag-like name: <ins>, </del>, <br/>. Not `a < b`.
TAG_RE = re.compile(r"</?[A-Za-z][\w:.-]*")

# The fences `commands` reads. A fence with any other info string is not
# something the model runs.
SHELL_INFOS = ("sh", "bash", "shell")
PYTHONS = ("python3", "python")
SCRIPT_SUFFIX = ".py"
SCRIPTS = "scripts"
BUILD_PARSER = "build_parser"
# The start of a heredoc, and the word that ends it: <<'END', <<"END", <<END, <<-END.
HEREDOC_RE = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1")
# A <placeholder> the model fills in. Not the second `<` of `<<`.
PLACEHOLDER_RE = re.compile(r"(?<!<)<[A-Za-z][^<>]*>")
# What a placeholder becomes: one word, as the filled-in value would be.
PLACEHOLDER = "PLACEHOLDER"
# The brackets around an [optional] part. What is inside is still checked.
OPTIONAL_RE = re.compile(r"\[([^\[\]]*)\]")
ASSIGNMENT_RE = re.compile(r"^([A-Za-z_]\w*)=(.*)$")
VARIABLE_RE = re.compile(r"^\$(?:\{(\w+)\}|(\w+))$")
SEPARATORS = ("&&", "||", ";", "|")
REDIRECTIONS = ("<", "<<", ">", ">>")

# Where a command other than a script invocation may stand on its line.
ANYWHERE = "anywhere"
# In the run of LEADING commands that opens the line, each followed by `&&`,
# with something after the run.
LEADING = "leading"
# Followed by `||` and a FALLBACK command, which ends the line.
FALLIBLE = "fallible"
# Last, after `||` and a FALLIBLE command.
FALLBACK = "fallback"
# The only command on its line.
ALONE = "alone"

# The plugin root as every "Locate the script" step spells it.
PLUGIN_ROOT = r"\$\{CLAUDE_PLUGIN_ROOT:-\$\{CLAUDE_SKILL_DIR\}/\.\./\.\.\}"
# One assignment of a script path, or of the plugin root the path is built on.
PATH_ASSIGNMENT = r"[A-Za-z_]\w*=(?:\S*\%s|%s)" % (SCRIPT_SUFFIX, PLUGIN_ROOT)

Allowed = collections.namedtuple("Allowed", "name pattern position reason")

# What a shell fence may hold besides a script invocation `commands` resolves.
# Each pattern is matched against one simple command, its words joined by
# single spaces with the quotes gone. Anything else is the model computing by
# hand what the script should compute.
ALLOWED = (
    Allowed(
        "script path",
        re.compile(r"^%s(?: %s)*$" % (PATH_ASSIGNMENT, PATH_ASSIGNMENT)),
        ANYWHERE,
        "names the script the invocations after it run, and runs nothing itself",
    ),
    Allowed(
        "installed check",
        re.compile(r"^ls \$\w+$"),
        FALLIBLE,
        '"Locate the script" checks the script is there before the first step',
    ),
    Allowed(
        "not installed message",
        re.compile(r"^echo .+$"),
        FALLBACK,
        "says why the ls before it failed",
    ),
    Allowed(
        "findings heredoc",
        re.compile(r"^cat > \$\{TMPDIR:-/tmp\}/[\w.-]+ <<-? \w+$"),
        ALONE,
        "writes the model's findings to a file the script reads; the body is data, and unread",
    ),
    Allowed(
        "change directory",
        re.compile(r"^cd \S+$"),
        LEADING,
        "moves into the project folder, since each shell call starts afresh",
    ),
    Allowed(
        "link directory",
        re.compile(r"^mkdir -p /tmp/[\w.-]+$"),
        LEADING,
        "makes the folder gitify links the plugin into",
    ),
    Allowed(
        "plugin link",
        re.compile(r"^ln -sfn %s /tmp/[\w.-]+/plugin$" % PLUGIN_ROOT),
        LEADING,
        "links the plugin at a path short enough to repeat in every command",
    ),
)

WHERE_REPEATS = (
    'CLAUDE.md, under "Skills and scripts", says why a step shared by two skills '
    "lives once in the plugin's %s/." % REFERENCE
)
WHERE_DESCRIPTIONS = 'COWORK.md, under "How skills load", says why an upload rejects this.'
WHERE_FENCES = (
    'CLAUDE.md, under "Skills and scripts", says the script does whatever two runs '
    "should agree on. A shell fence that computes it with other tools has the model do it by hand."
)
WHERE_COMMANDS = (
    'CLAUDE.md, under "Skills and scripts", says a SKILL.md names the command for '
    "each step. A command the script rejects sends the model back to doing the step by hand."
)


Fence = collections.namedtuple("Fence", "line info body")


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def envelope(command, data, errors=None, warnings=None):
    errors = errors or []
    return {
        "version": ENVELOPE_VERSION,
        "command": command,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings or [],
        "data": data,
    }


def emit(args, command, data, errors=None, warnings=None, human=None, where=None):
    """Print JSON or human output, and return the exit code."""
    errors = errors or []
    warnings = warnings or []
    if args.json:
        print(json.dumps(envelope(command, data, errors, warnings), indent=2, sort_keys=True))
    else:
        if human:
            human()
        for w in warnings:
            sys.stderr.write("warning: %s\n" % w)
        for e in errors:
            sys.stderr.write("%s\n" % e)
        if errors and where:
            sys.stderr.write("%s\n" % where)
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# the clone
# --------------------------------------------------------------------------


def run(repo, cmd):
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    except OSError as exc:
        raise Fatal("cannot run %s: %s" % (cmd[0], exc)) from exc
    if proc.returncode != 0:
        raise Fatal("`%s` failed: %s" % (" ".join(cmd), proc.stderr.strip()))
    return proc


def toplevel(repo):
    if not os.path.isdir(repo):
        raise Fatal("no such directory: %s" % repo)
    return run(repo, ["git", "rev-parse", "--show-toplevel"]).stdout.strip()


def repo_files(root):
    """Every file git would carry: tracked, plus untracked it is not ignoring."""
    out = run(root, ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]).stdout
    return sorted(set(p for p in out.split("\0") if p))


def skill_files(files):
    """plugins/<plugin>/skills/<skill>/SKILL.md, as {plugin: [path, ...]}."""
    found = {}
    for path in files:
        parts = path.split("/")
        if len(parts) == 5 and parts[0] == PLUGINS and parts[2] == SKILLS:
            if parts[4] == SKILL_FILE:
                found.setdefault(parts[1], []).append(path)
    return found


# --------------------------------------------------------------------------
# splitting a SKILL.md into blocks
# --------------------------------------------------------------------------


def normalize(text):
    return " ".join(text.split())


def fence_end(lines, i, marker):
    """The index of the line closing the fence opened at lines[i].

    The last line, if the fence is never closed.
    """
    j = i + 1
    while j < len(lines):
        if lines[j].strip().startswith(marker):
            return j
        j += 1
    return len(lines) - 1


def fences(text):
    """Every fenced code block, as [Fence].

    A fence's body keeps its line numbers and loses the fence's own indent, so
    a fence nested in a list item reads the same as one at the margin.
    """
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        fence = FENCE_RE.match(lines[i])
        if not fence:
            i += 1
            continue
        end = fence_end(lines, i, fence.group("marker"))
        indent = len(fence.group("indent"))
        body = []
        for j in range(i + 1, end if end > i else i + 1):
            line = lines[j]
            if line[:indent].strip() == "":
                line = line[indent:]
            body.append((j + 1, line))
        out.append(Fence(i + 1, fence.group("info").lower(), body))
        i = end + 1
    return out


def blocks(text):
    """The comparable blocks of a SKILL.md, as [(line, normalized text)].

    Front matter, headings and the LOCATE_SECTION section are left out.
    """
    lines = text.splitlines()
    out = []
    current, start = [], 0
    exempt = False

    def flush():
        if current and not exempt:
            out.append((start, normalize("\n".join(current))))
        del current[:]

    i = 0
    if lines and lines[0].strip() == FRONT_MATTER:
        for j in range(1, len(lines)):
            if lines[j].strip() == FRONT_MATTER:
                i = j + 1
                break

    while i < len(lines):
        line = lines[i]
        number = i + 1
        fence = FENCE_RE.match(line)
        heading = HEADING_RE.match(line)
        if fence:
            flush()
            end = fence_end(lines, i, fence.group("marker"))
            current.extend(lines[i : end + 1])
            start = number
            i = end
            flush()
        elif heading:
            flush()
            exempt = heading.group(1).strip() == LOCATE_SECTION
        elif not line.strip():
            flush()
        elif LIST_ITEM_RE.match(line):
            flush()
            # Without its marker, so a bullet copied into a numbered list matches.
            current.append(LIST_ITEM_RE.sub("", line, count=1))
            start = number
        else:
            if not current:
                start = number
            current.append(line)
        i += 1
    flush()
    return out


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def skill_name(path):
    return path.split("/")[3]


def cmd_repeats(args, root):
    found = skill_files(repo_files(root))
    scanned, repeats, errors = [], [], []

    if not found:
        errors.append(
            "no file matched %s/*/%s/*/%s anywhere in the clone. This check is scanning "
            "nothing, which is exactly how a copied step gets through."
            % (PLUGINS, SKILLS, SKILL_FILE)
        )

    for plugin in sorted(found):
        places = {}
        for path in sorted(found[plugin]):
            try:
                with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
                    parsed = blocks(fh.read())
            except OSError as exc:
                raise Fatal("cannot read %s: %s" % (path, exc)) from exc
            scanned.append(path)
            if not parsed:
                errors.append(
                    "%s yielded no blocks to compare; the check has gone blind there." % path
                )
            for line, text in parsed:
                places.setdefault(text, []).append({"path": path, "line": line})
        for text, where in places.items():
            if len(set(skill_name(w["path"]) for w in where)) > 1:
                repeats.append({"plugin": plugin, "text": text, "places": where})

    for r in repeats:
        quote = r["text"]
        if len(quote) > QUOTE_CHARS:
            quote = quote[:QUOTE_CHARS] + "..."
        errors.append(
            "%s share a block: %r. Move it to %s/%s/%s/ and point to it from each skill."
            % (
                " and ".join("%s:%d" % (w["path"], w["line"]) for w in r["places"]),
                quote,
                PLUGINS,
                r["plugin"],
                REFERENCE,
            )
        )

    def human():
        if not errors:
            print(
                "%d %s files in %d plugins, no block repeated within a plugin."
                % (len(scanned), SKILL_FILE, len(found))
            )

    data = {"scanned": scanned, "repeats": repeats}
    return emit(args, "repeats", data, errors, None, human, WHERE_REPEATS)


def description_lines(lines):
    """The description's lines as (line number, text), or None if there is none.

    Only the front matter is read: the lines between a first line of `---` and
    the next `---`. The value is the rest of the `description:` line plus the
    indented lines after it.
    """
    if not lines or lines[0].strip() != FRONT_MATTER:
        return None
    found = None
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == FRONT_MATTER:
            break
        if found is None:
            m = DESCRIPTION_RE.match(line)
            if m:
                found = [(i, m.group(1))]
        elif CONTINUATION_RE.match(line):
            found.append((i, line))
        else:
            break
    return found


def cmd_descriptions(args, root):
    """No skill description holds something Cowork's upload reads as a tag."""
    errors, checked = [], []

    def human():
        if not errors:
            print("%d skill description(s) clear of XML-like tags." % len(checked))

    for path in repo_files(root):
        if not (path.startswith(PLUGINS + "/") and path.endswith(MARKDOWN)):
            continue
        try:
            with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
                found = description_lines(fh.read().splitlines())
        except OSError as exc:
            raise Fatal("cannot read %s: %s" % (path, exc)) from exc
        if found is None:
            continue
        checked.append(path)
        for number, text in found:
            for tag in TAG_RE.findall(text):
                errors.append(
                    "%s:%d: description contains an XML-like tag `%s`; "
                    "Cowork's .plugin upload rejects it" % (path, number, tag)
                )

    if not checked:
        errors.append(
            "found no markdown under %s/ with a description in its front matter; "
            "a check that scanned nothing has not passed" % PLUGINS
        )

    data = {"checked": checked}
    return emit(args, "descriptions", data, errors, None, human, WHERE_DESCRIPTIONS)


# --------------------------------------------------------------------------
# commands a skill runs
# --------------------------------------------------------------------------


def instruction_files(files):
    """Every file a skill's instructions live in, as {plugin: [path, ...]}.

    plugins/<plugin>/skills/<skill>/SKILL.md, and plugins/<plugin>/reference/*.md.
    """
    found = {}
    for path in files:
        parts = path.split("/")
        if not parts[0] == PLUGINS or len(parts) < 3:
            continue
        skill = len(parts) == 5 and parts[2] == SKILLS and parts[4] == SKILL_FILE
        reference = len(parts) == 4 and parts[2] == REFERENCE and parts[3].endswith(MARKDOWN)
        if skill or reference:
            found.setdefault(parts[1], []).append(path)
    return found


def shell_lines(fence):
    """The command lines of a shell fence, as [(line, text)].

    Continuation lines are joined onto the line they continue, and a heredoc's
    body is left out: it is data for the command, not a command.
    """
    out = []
    body = fence.body
    i = 0
    while i < len(body):
        number, text = body[i]
        while text.endswith("\\") and i + 1 < len(body):
            i += 1
            text = text[:-1] + " " + body[i][1].strip()
        out.append((number, text))
        heredoc = HEREDOC_RE.search(text)
        if heredoc:
            i += 1
            while i < len(body) and body[i][1].strip() != heredoc.group(2):
                i += 1
        i += 1
    return out


def chain(text):
    """The simple commands on one line, as [(words, separator after it)].

    Placeholders become one word, the brackets of an optional part go and
    comments go. Redirections stay as words, operand and all. The last
    command's separator is None.
    """
    text = PLACEHOLDER_RE.sub(PLACEHOLDER, text)
    while OPTIONAL_RE.search(text):
        text = OPTIONAL_RE.sub(r"\1", text)
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise Fatal("cannot split %r into words: %s" % (text, exc)) from exc
    out, current = [], []
    for token in tokens:
        if token in SEPARATORS:
            out.append((current, token))
            current = []
        else:
            current.append(token)
    out.append((current, None))
    return [(words, sep) for words, sep in out if words]


def simple_commands(text):
    """The simple commands on one line, each as a list of words.

    As chain(), with each redirection gone along with its operand.
    """
    commands = []
    for words, _ in chain(text):
        kept, skip = [], False
        for word in words:
            if skip:
                skip = False
            elif word in REDIRECTIONS:
                skip = True
            else:
                kept.append(word)
        if kept:
            commands.append(kept)
    return commands


def script_of(value, plugin):
    """The script an assigned value names, as a path in the clone, or None.

    Only the file name counts: `$ROOT/scripts/prose.py`, `.prose-tuning/prose.py`
    and `/tmp/gitify/plugin/scripts/gitify.py` are all the plugin's own
    scripts/ file of that name, wherever the skill has put it.
    """
    if not value.endswith(SCRIPT_SUFFIX):
        return None
    return "/".join((PLUGINS, plugin, SCRIPTS, value.rsplit("/", 1)[-1]))


def read_commands(root, paths):
    """Every simple command in the shell fences of these files.

    As [{"path", "line", "text", "words"}], in file order. `text` is the whole
    line as the fence has it, for quoting in an error.
    """
    out = []
    for path in paths:
        try:
            with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            raise Fatal("cannot read %s: %s" % (path, exc)) from exc
        for fence in fences(text):
            if fence.info not in SHELL_INFOS:
                continue
            for line, command in shell_lines(fence):
                for words in simple_commands(command):
                    out.append(
                        {"path": path, "line": line, "text": command.strip(), "words": words}
                    )
    return out


def assignments(commands, plugin, errors):
    """{variable: script path}, from every assignment in a plugin's files.

    A variable is read from the assignment wherever it is, since a reference
    file uses the variable that SKILL.md's "Locate the script" step sets.
    """
    table, where = {}, {}
    for c in commands:
        for word in c["words"]:
            m = ASSIGNMENT_RE.match(word)
            if not m:
                break
            script = script_of(m.group(2), plugin)
            if script is None:
                continue
            name = m.group(1)
            if name in table and table[name] != script:
                errors.append(
                    "%s:%d: $%s names %s, but %s names %s"
                    % (c["path"], c["line"], name, script, where[name], table[name])
                )
                continue
            table[name] = script
            where[name] = "%s:%d" % (c["path"], c["line"])
    return table


def load_parser(root, script, cache):
    """The script's build_parser(), or a string saying why there is none."""
    if script in cache:
        return cache[script]
    path = os.path.join(root, script)
    if not os.path.isfile(path):
        cache[script] = "%s does not exist" % script
        return cache[script]
    name = "check_skills_target_%d" % len(cache)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # a broken script is a finding, not a crash
        cache[script] = "%s fails to import: %s" % (script, exc)
        return cache[script]
    build = getattr(module, BUILD_PARSER, None)
    cache[script] = build if callable(build) else "%s has no %s()" % (script, BUILD_PARSER)
    return cache[script]


def parse(build, argv):
    """argparse's complaint about argv, or None if it parses."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            build().parse_args(argv)
    except SystemExit as exc:
        if exc.code:
            lines = err.getvalue().strip().splitlines()
            return lines[-1] if lines else "exit %s" % exc.code
    return None


def cmd_commands(args, root):
    """Every script a skill runs accepts the command the skill gives it."""
    found = instruction_files(repo_files(root))
    scanned, invocations, errors = [], [], []
    cache = {}

    for plugin in sorted(found):
        paths = sorted(found[plugin])
        scanned.extend(paths)
        commands = read_commands(root, paths)
        table = assignments(commands, plugin, errors)
        for c in commands:
            words = c["words"]
            while words and ASSIGNMENT_RE.match(words[0]):
                words = words[1:]
            if len(words) < 2 or words[0] not in PYTHONS or words[1].startswith("-"):
                continue
            target, argv = words[1], words[2:]
            variable = VARIABLE_RE.match(target)
            if variable:
                name = variable.group(1) or variable.group(2)
                script = table.get(name)
                if script is None:
                    errors.append(
                        "%s:%d: no assignment in %s/%s/ names a script for $%s"
                        % (c["path"], c["line"], PLUGINS, plugin, name)
                    )
                    continue
            else:
                script = os.path.normpath(target)
            entry = {"path": c["path"], "line": c["line"], "script": script, "argv": argv}
            invocations.append(entry)
            build = load_parser(root, script, cache)
            problem = build if isinstance(build, str) else parse(build, argv)
            entry["ok"] = problem is None
            if problem:
                errors.append("%s:%d: `%s`: %s" % (c["path"], c["line"], c["text"], problem))

    if not invocations:
        errors.append(
            "found no script invocation in a shell fence under %s/; "
            "a check that scanned nothing has not passed" % PLUGINS
        )

    def human():
        if not errors:
            print(
                "%d invocation(s) in %d file(s) resolve against their scripts."
                % (len(invocations), len(set(i["path"] for i in invocations)))
            )

    data = {"scanned": scanned, "invocations": invocations}
    return emit(args, "commands", data, errors, None, human, WHERE_COMMANDS)


# --------------------------------------------------------------------------
# what a shell fence may hold
# --------------------------------------------------------------------------

INVOCATION = "invocation"


def is_invocation(words):
    """Whether words run a script `commands` can resolve: python3 and a path."""
    while words and re.match("^%s$" % PATH_ASSIGNMENT, words[0]):
        words = words[1:]
    if len(words) < 2 or words[0] not in PYTHONS:
        return False
    return bool(VARIABLE_RE.match(words[1])) or words[1].endswith(SCRIPT_SUFFIX)


def matches(links, i, position):
    """Whether links[i] matches an ALLOWED entry held to this position."""
    text = " ".join(links[i][0])
    return any(a.position == position and a.pattern.match(text) for a in ALLOWED)


def placed(links, i, position):
    """Whether links[i] stands where an entry with this position may."""
    last = len(links) - 1
    sep = links[i][1]
    if position == ANYWHERE:
        return True
    if position == ALONE:
        return last == 0
    if position == LEADING:
        before = all(links[j][1] == "&&" and matches(links, j, LEADING) for j in range(i))
        return before and sep == "&&" and i < last
    if position == FALLIBLE:
        return sep == "||" and i + 1 == last and matches(links, last, FALLBACK)
    if position == FALLBACK:
        return i == last and i > 0 and links[i - 1][1] == "||" and matches(links, i - 1, FALLIBLE)
    raise Fatal("ALLOWED names an unknown position %r" % position)


def allowance(links, i):
    """The name of what lets links[i] stand in a shell fence, or None."""
    words = links[i][0]
    if is_invocation(words):
        return INVOCATION
    text = " ".join(words)
    for a in ALLOWED:
        if a.pattern.match(text) and placed(links, i, a.position):
            return a.name
    return None


def cmd_fences(args, root):
    """Every fence says what it holds, and a shell fence runs only the script."""
    found = instruction_files(repo_files(root))
    scanned, commands, errors = [], [], []
    shell = 0

    for plugin in sorted(found):
        for path in sorted(found[plugin]):
            scanned.append(path)
            try:
                with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError as exc:
                raise Fatal("cannot read %s: %s" % (path, exc)) from exc
            for fence in fences(text):
                if not fence.info:
                    errors.append(
                        "%s:%d: fence has no info string. Label it %s if the model runs it, "
                        "or with what it holds, such as markdown, text or json."
                        % (path, fence.line, SHELL_INFOS[0])
                    )
                    continue
                if fence.info not in SHELL_INFOS:
                    continue
                shell += 1
                for line, command in shell_lines(fence):
                    links = chain(command)
                    for i, (words, _) in enumerate(links):
                        allowed = allowance(links, i)
                        commands.append(
                            {"path": path, "line": line, "word": words[0], "allowed": allowed}
                        )
                        if allowed is None:
                            errors.append(
                                "%s:%d: `%s` in a shell fence: %s"
                                % (path, line, words[0], command.strip())
                            )

    if not shell:
        errors.append(
            "found no shell fence under %s/; a check that scanned nothing has not passed" % PLUGINS
        )

    def human():
        if not errors:
            print(
                "%d shell fence(s) in %d file(s) run only their scripts."
                % (shell, len(set(c["path"] for c in commands)))
            )

    data = {"scanned": scanned, "commands": commands}
    return emit(args, "fences", data, errors, None, human, WHERE_FENCES)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(prog=PROG, description="Check what a plugin's skills say.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "repeats", parents=[common], help="no block in two SKILL.md files of one plugin"
    )
    p.set_defaults(func=cmd_repeats)

    p = sub.add_parser(
        "descriptions", parents=[common], help="no skill description holds an XML-like tag"
    )
    p.set_defaults(func=cmd_descriptions)

    p = sub.add_parser(
        "commands", parents=[common], help="every command a skill runs, its script accepts"
    )
    p.set_defaults(func=cmd_commands)

    p = sub.add_parser(
        "fences", parents=[common], help="every fence is labeled; a shell fence runs only scripts"
    )
    p.set_defaults(func=cmd_fences)

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, toplevel(args.repo))
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN
    except BrokenPipeError:
        return OK


if __name__ == "__main__":
    sys.exit(main())

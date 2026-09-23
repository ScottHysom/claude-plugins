#!/usr/bin/env python3
"""Deterministic half of the gitify-project skill.

The skill uses the model for what needs judgement: running the interview,
naming the history skill and writing its description, deciding with the user
what to keep out of git. Everything else happens here - reading the templates,
checking the model's answers, filling in placeholders, laying the files out for
the bridge, writing the commands that check the folder on the device, and
comparing a project's skill with the template it came from.

Usage:
    python3 gitify.py <command> [options]
    python3 gitify.py --help

Commands:
    preflight   check the shipped templates are complete and well formed
    probe       a device command that checks the folder and lists what is in it
    render      fill the templates from an answers file into a stage directory
    drift       compare a project's generated skill with the current template

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

The device commands probe and render print have exit codes of their own, which
SKILL.md reads: 0 go on, 1 the folder holds something this would overwrite or
is already a git repo, 2 the folder is not there.

Where this runs: in Cowork's container, which can read the plugin but not the
user's folder. COWORK.md at the root of the claude-plugins repo says what
Cowork allows and how that was established. So render writes to a stage
directory under /mnt/user-data/outputs/ and prints the `files` list
`device_commit_files` takes, plus two commands for `device_bash`: a precheck
that nothing would be overwritten, and a sha256 check that everything arrived
intact.
probe and the precheck both refuse a folder that is not there, because the
copy would quietly create it. setup.sh sets its own execute bits, since they
do not survive the copy.

Things that look like bugs and are not:

1. Files are written in place with open(path, "w"), never via a temp file moved
   into position. Cowork's device bridge cannot delete files, and a script in
   this repo may end up running where that matters. Do not "fix" this.

2. Nothing here runs git, not even to read. A git write through the bridge
   strands .git/*.lock files that block every later write, and the folder is
   not a repo until the user runs setup.sh.

3. render refuses a stage directory holding files it did not plan. It cannot
   clean one up, for the same reason as 1.

4. `instructions` is copied into CLAUDE.md after placeholders are substituted
   and is never checked for them. It is the user's text, copied verbatim, and
   "{{" in it is theirs to keep.

Python 3.9 is the floor. No match statements, no X | Y unions.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import shlex
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PLUGIN = "gitify-cowork-project"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATES = os.path.join(
    os.path.dirname(SCRIPT_DIR), "skills", "gitify-project", "templates"
)

# Where device_commit_files accepts files from. A stage elsewhere still renders,
# with a warning, so the script can be run and tested off Cowork.
OUTPUTS_ROOT = "/mnt/user-data/outputs"
DEFAULT_STAGE_DIR = PLUGIN

# device_commit_files takes at most this many files in one call.
COMMIT_BATCH_LIMIT = 50

# Where each connected folder appears to device_bash.
DEVICE_MOUNT_ROOT = "$HOME/mnt"

# Files probe reports as large, because git keeps every version of them.
LARGE_FILE_SIZE = "+10M"

# Template file -> path in the project. Formatted with the placeholder values.
MANIFEST = [
    ("gitignore", ".gitignore"),
    ("commit.sh", "commit.sh"),
    ("setup.sh", "setup.sh"),
    ("CLAUDE.md", "CLAUDE.md"),
    ("history-skill.md", "skills/{SKILL_NAME}/SKILL.md"),
]
SKILL_TEMPLATE = "history-skill.md"
GITIGNORE_TEMPLATE = "gitignore"
INSTRUCTIONS_TEMPLATE = "CLAUDE.md"
GITIGNORE_HEADING = "# This project"

# What the user puts in the Project Instructions field in place of what was
# there. Cowork adds the field to every conversation in the project, so it
# carries only this line. The line stays even when the project is the connected
# folder, whose CLAUDE.md Cowork loads by itself: the field is the only project
# text the first message of a conversation sees. COWORK.md, under "How
# instruction files load", has what Cowork loads and when.
FIELD_POINTER = "Before anything else, read CLAUDE.md at the root of {path}."

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
# Anything that means a placeholder survived into the output, or was mistyped.
LEFTOVER_RE = re.compile(r"\{\{|\}\}")

SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_MAX = 64
DESCRIPTION_MAX = 1024
# The skill's front matter holds the description as a plain YAML scalar, which
# cannot contain ": " or " #", or start with one of these.
YAML_UNSAFE_START = "-?:,[]{}#&*!|>'\"%@`"
YAML_UNSAFE_INNER = (": ", " #")
# Cowork's .plugin upload rejects a skill whose description holds anything that
# looks like an XML tag: a `<` directly followed by a name, as in <ins> or </b>.
TAG_RE = re.compile(r"</?[A-Za-z][\w:.-]*")

# Placeholders the model supplies, and the ones computed from the folders.
SUPPLIED = ("PROJECT_NAME", "SKILL_NAME", "DESCRIPTION")
COMPUTED = ("PROJECT_PATH", "PROJECT_MOUNT")
ANSWER_KEYS = ("connected_folder", "project_folder", "values", "instructions", "ignore")

DIGEST_LEN = 12
HEADING_RE = re.compile(r"^(#{1,6}) +(.*?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
PREAMBLE = "(preamble)"


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


def emit(args, command, data, errors=None, warnings=None, human=None):
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
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------


def split_lines(s):
    """Lines with their endings, cut at "\\n" only.

    str.splitlines() also cuts at form feeds, U+2028 and others that no editor
    shows as a line break, which would number lines differently from what the
    author sees.
    """
    parts = s.split("\n")
    lines = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text(path, s):
    # In place, on purpose. See the module docstring.
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(s)


# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------


class Template:
    """A template file's text and the placeholders in it.

    Problems are collected in `errors` rather than raised, so preflight can
    report every one. Anything that fills a template in first calls
    `require_clean`.
    """

    def __init__(self, name, text):
        self.name = name
        self.text = text
        self.placeholders = sorted(set(PLACEHOLDER_RE.findall(text)))
        self.errors = []
        spans = [(m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(text)]
        # A brace outside a placeholder is a mistyped one, which would
        # otherwise be copied into a project unnoticed.
        for m in LEFTOVER_RE.finditer(text):
            if any(a <= m.start() < b for a, b in spans):
                continue
            line = text.count("\n", 0, m.start()) + 1
            self.errors.append("%s:%d  %r outside any placeholder" % (name, line, m.group(0)))

    @classmethod
    def load(cls, directory, name):
        path = os.path.join(directory, name)
        try:
            return cls(name, read_text(path))
        except OSError as exc:
            raise Fatal("cannot read template %s: %s" % (path, exc)) from exc

    def require_clean(self):
        if self.errors:
            raise Fatal("template is malformed: %s" % "; ".join(self.errors))


def load_templates(directory):
    if not os.path.isdir(directory):
        raise Fatal("templates directory not found: %s" % directory)
    return [Template.load(directory, name) for name, _ in MANIFEST]


def check_templates(directory):
    """Every problem with the shipped templates, as a list of messages."""
    errors = []
    if not os.path.isdir(directory):
        return ["templates directory not found: %s" % directory]
    expected = set(name for name, _ in MANIFEST)
    present = set(os.listdir(directory))
    for name in sorted(expected - present):
        errors.append("%s is in the manifest but not in %s" % (name, directory))
    for name in sorted(present - expected):
        errors.append(
            "%s is in %s but not in the manifest, so it would never ship" % (name, directory)
        )
    known = set(SUPPLIED) | set(COMPUTED)
    for name, _ in MANIFEST:
        if name not in present:
            continue
        t = Template.load(directory, name)
        errors.extend(t.errors)
        for p in t.placeholders:
            if p not in known:
                errors.append("%s  {{%s}} is not a known placeholder" % (name, p))
    return errors


# --------------------------------------------------------------------------
# answers
# --------------------------------------------------------------------------


def _no_duplicate_keys(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("key %r appears twice" % k)
        out[k] = v
    return out


def read_answers(path):
    try:
        if path == "-":
            raw = sys.stdin.read()
        else:
            raw = read_text(path)
        data = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError) as exc:
        raise Fatal("cannot read answers: %s" % exc) from exc
    if not isinstance(data, dict):
        raise Fatal("answers must be a JSON object")
    return data


def normalise_folder(value, field):
    """A device folder path as the model passed it, checked and without a
    trailing slash. Returns (path, error)."""
    if not isinstance(value, str) or not value:
        return None, "%s is required, as a path from get_device_info" % field
    path = value.rstrip("/")
    if not (path.startswith("/") or path == "~" or path.startswith("~/")):
        return None, "%s must be absolute or start with ~/: %r" % (field, value)
    if "\n" in path or "\\" in path:
        return None, "%s contains a newline or backslash: %r" % (field, value)
    if any(seg in (".", "..") for seg in path.split("/")):
        return None, "%s contains . or .. segments: %r" % (field, value)
    return path, None


class Folders:
    """Where the project is: on the device, and as device_bash mounts it."""

    def __init__(self, connected, project, sub, mount_name):
        self.connected = connected
        self.project = project
        self.sub = sub
        self.mount = posix_join(mount_name, sub)


def resolve_folders(connected_value, project_value):
    """(Folders, errors) from the two folder answers. Folders is None when
    there are errors."""
    errors = []
    connected, err = normalise_folder(connected_value, "connected_folder")
    if err:
        errors.append(err)
    project = connected
    if project_value is not None:
        project, err = normalise_folder(project_value, "project_folder")
        if err:
            errors.append(err)
    if errors:
        return None, errors
    if project == connected:
        sub = ""
    elif project.startswith(connected + "/"):
        sub = project[len(connected) + 1 :]
    else:
        return None, ["project_folder %r is not inside connected_folder %r" % (project, connected)]
    mount_name = connected.split("/")[-1] if connected != "~" else ""
    if not mount_name:
        return None, ["connected_folder has no folder name to mount"]
    return Folders(connected, project, sub, mount_name), []


def check_value(name, value, values):
    """Errors for one supplied placeholder value."""
    if not isinstance(value, str) or not value.strip():
        return ["values.%s is required" % name]
    errs = []
    if value != value.strip() or "\n" in value:
        errs.append("values.%s must be one line with no surrounding space" % name)
    if "{{" in value or "}}" in value:
        errs.append("values.%s cannot contain {{ or }}" % name)
    if name == "SKILL_NAME":
        if not SKILL_NAME_RE.match(value) or len(value) > SKILL_NAME_MAX:
            errs.append(
                "values.SKILL_NAME must be lower-case words joined by -, at most %d characters: %r"
                % (SKILL_NAME_MAX, value)
            )
    elif name == "DESCRIPTION":
        if len(value) > DESCRIPTION_MAX:
            errs.append(
                "values.DESCRIPTION is %d characters; at most %d" % (len(value), DESCRIPTION_MAX)
            )
        if value[0] in YAML_UNSAFE_START or any(s in value for s in YAML_UNSAFE_INNER):
            errs.append(
                "values.DESCRIPTION would break the skill's front matter: it cannot start with "
                "one of %s or contain ': ' or ' #'" % YAML_UNSAFE_START
            )
        tag = TAG_RE.search(value)
        if tag:
            errs.append(
                "values.DESCRIPTION contains something that looks like an XML tag (%r); "
                "Cowork's plugin upload rejects the skill" % tag.group(0)
            )
        names = [values.get("PROJECT_NAME"), values.get("SKILL_NAME")]
        if not any(isinstance(n, str) and n and n.lower() in value.lower() for n in names):
            errs.append(
                "values.DESCRIPTION must name the project, by PROJECT_NAME or SKILL_NAME; the "
                "description is the only thing keeping the skill out of unrelated conversations"
            )
    return errs


def check_instructions(value):
    """Errors for the Project Instructions text. It is copied verbatim, so the
    only rules are that it is text and that "nothing" is said with null."""
    if value is None:
        return []
    if not isinstance(value, str):
        return ["instructions must be the field's text, or null"]
    if not value.strip():
        return ["instructions is blank; pass null when the field is empty"]
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return ["instructions is not valid Unicode text"]
    return []


def check_ignore(value):
    """Errors for the extra .gitignore patterns."""
    if value is None:
        return []
    if not isinstance(value, list):
        return ["ignore must be a list of .gitignore patterns"]
    errs, seen = [], set()
    for i, p in enumerate(value):
        where = "ignore[%d]" % i
        if not isinstance(p, str) or not p.strip():
            errs.append("%s must be a pattern, not blank" % where)
            continue
        if "\n" in p or "\r" in p:
            errs.append("%s must be one line: %r" % (where, p))
        if p in seen:
            errs.append("%s repeats %r" % (where, p))
        seen.add(p)
    return errs


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def substitute(text, values):
    return PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def leftovers(text):
    """Errors if a placeholder or brace survived substitution."""
    stray = sorted(set(m.group(0) for m in LEFTOVER_RE.finditer(text)))
    return ["output still contains %s" % ", ".join(stray)] if stray else []


def add_instructions(header, instructions):
    """CLAUDE.md: the header, then the field's text exactly as given, ending in
    a newline."""
    if instructions is None:
        return header
    tail = "" if instructions.endswith("\n") else "\n"
    return header + "\n" + instructions + tail


def add_ignores(gitignore, patterns):
    if not patterns:
        return gitignore
    return gitignore + "\n" + GITIGNORE_HEADING + "\n" + "".join(p + "\n" for p in patterns)


def sh_quote_under(root, rel):
    """A path under a root that must expand, such as $HOME/mnt, quoted for sh."""
    return '"%s"/%s' % (root, shlex.quote(rel)) if rel else '"%s"' % root


def folder_guard(mount):
    """sh lines that cd into the project folder, or stop: exit 2 when it is not
    there, exit 1 when it is already a git repo."""
    return [
        "cd %s 2>/dev/null || { echo %s; exit 2; }"
        % (
            sh_quote_under(DEVICE_MOUNT_ROOT, mount),
            shlex.quote("missing: %s is not a folder on this device" % mount),
        ),
        "if [ -e .git ]; then echo %s; exit 1; fi"
        % shlex.quote(
            "repo: %s is already a git repo. %s establishes git and does not adopt "
            "an existing repo" % (mount, PLUGIN)
        ),
    ]


def probe_command(mount):
    lines = [
        *folder_guard(mount),
        'echo "files: $(find . -type f | wc -l | tr -d " ")"',
        "for f in * .[!.]* ..?*; do",
        '  if [ -e "$f" ] || [ -L "$f" ]; then echo "entry: $f"; fi',
        "done",
        "find . -type f -size %s | sed 's|^\\./|large: |'" % LARGE_FILE_SIZE,
        "exit 0",
    ]
    return "\n".join(lines)


def precheck_command(mount, rels):
    lines = [
        *folder_guard(mount),
        "found=0",
        "for f in %s; do" % " ".join(shlex.quote(r) for r in rels),
        '  if [ -e "$f" ]; then echo "exists: $f"; found=1; fi',
        "done",
        '[ "$found" = 0 ] && echo "clear"',
        'exit "$found"',
    ]
    return "\n".join(lines)


def check_command(mount, files):
    lines = [
        "cd %s && sha256sum --check --strict - <<'SUMS'" % sh_quote_under(DEVICE_MOUNT_ROOT, mount)
    ]
    for f in files:
        lines.append("%s  %s" % (sha256(f["content"]), f["file"]))
    lines.append("SUMS")
    return "\n".join(lines)


def posix_join(*parts):
    return "/".join(p for p in parts if p)


def cmd_render(args):
    answers = read_answers(args.answers)
    templates = load_templates(args.templates)
    for t in templates:
        t.require_clean()

    errors, warnings = [], []
    extra = set(answers) - set(ANSWER_KEYS)
    if extra:
        errors.append("answers has unexpected keys: %s" % ", ".join(sorted(extra)))

    folders, folder_errors = resolve_folders(
        answers.get("connected_folder"), answers.get("project_folder")
    )
    errors.extend(folder_errors)

    values = answers.get("values")
    if not isinstance(values, dict):
        errors.append("values must be an object")
        values = {}
    for name in COMPUTED:
        if name in values:
            errors.append("values.%s is computed from the folders; do not pass it" % name)
    for name in sorted(set(values) - set(SUPPLIED) - set(COMPUTED)):
        errors.append("values.%s is not a placeholder" % name)
    for name in SUPPLIED:
        errors.extend(check_value(name, values.get(name), values))

    instructions = answers.get("instructions")
    errors.extend(check_instructions(instructions))
    ignore = answers.get("ignore")
    errors.extend(check_ignore(ignore))

    if errors:
        errors.append("nothing was written")
        return emit(args, "render", None, errors=errors)

    full = dict((k, values[k]) for k in SUPPLIED)
    full["PROJECT_PATH"] = folders.project
    full["PROJECT_MOUNT"] = folders.mount

    planned = []
    for (name, dest), t in zip(MANIFEST, templates):
        rel = dest.format(**full)
        content = substitute(t.text, full)
        errors.extend("%s: %s" % (rel, e) for e in leftovers(content))
        # The user's own text goes in after the check, which it is not subject to.
        if name == INSTRUCTIONS_TEMPLATE:
            content = add_instructions(content, instructions)
        elif name == GITIGNORE_TEMPLATE:
            content = add_ignores(content, ignore)
        planned.append({"file": rel, "template": name, "content": content})

    if len(planned) > COMMIT_BATCH_LIMIT:
        errors.append(
            "%d files is more than device_commit_files takes in one call (%d)"
            % (len(planned), COMMIT_BATCH_LIMIT)
        )
    if errors:
        errors.append("nothing was written")
        return emit(args, "render", None, errors=errors)

    stage = os.path.abspath(
        args.stage or os.path.join(OUTPUTS_ROOT, DEFAULT_STAGE_DIR, values["SKILL_NAME"])
    )
    if not (stage + "/").startswith(OUTPUTS_ROOT + "/"):
        warnings.append(
            "stage %s is outside %s; device_commit_files will reject it" % (stage, OUTPUTS_ROOT)
        )
    check_stage(stage, [p["file"] for p in planned])

    files = []
    for p in planned:
        staged = os.path.join(stage, *p["file"].split("/"))
        if not args.dry_run:
            os.makedirs(os.path.dirname(staged), exist_ok=True)
            write_text(staged, p["content"])
        files.append(
            {
                "file": p["file"],
                "template": p["template"],
                "staged_path": staged,
                "device_path": posix_join(folders.project, p["file"]),
                "sha256": sha256(p["content"]),
            }
        )

    data = {
        "dry_run": args.dry_run,
        "stage": stage,
        "project_path": folders.project,
        "project_mount": folders.mount,
        "files": files,
        "commit_files": [
            {"stagedPath": f["staged_path"], "devicePath": f["device_path"]} for f in files
        ],
        "precheck_command": precheck_command(folders.mount, [f["file"] for f in files]),
        "check_command": check_command(folders.mount, planned),
        "field_pointer": FIELD_POINTER.format(path=folders.project),
    }

    def human():
        for f in files:
            print("%s  %s" % (f["sha256"][:DIGEST_LEN], f["file"]))
        print(
            "\n%d file(s) %s %s"
            % (len(files), "planned for" if args.dry_run else "staged in", stage)
        )
        print("\nprecheck, through device_bash:\n%s" % data["precheck_command"])
        print("\ncheck after copying, through device_bash:\n%s" % data["check_command"])
        print("\nfor the Project Instructions field:\n%s" % data["field_pointer"])

    return emit(args, "render", data, warnings=warnings, human=human)


def check_stage(stage, rels):
    """Refuse a stage holding anything this run would not write."""
    if not os.path.exists(stage):
        return
    if not os.path.isdir(stage):
        raise Fatal("stage %s exists and is not a directory" % stage)
    planned = set(rels)
    for root, _dirs, names in os.walk(stage):
        for n in names:
            rel = os.path.relpath(os.path.join(root, n), stage).replace(os.sep, "/")
            if rel not in planned:
                raise Fatal(
                    "stage %s already holds %s, which this run would not write; "
                    "pass a new --stage" % (stage, rel)
                )


# --------------------------------------------------------------------------
# drift
# --------------------------------------------------------------------------


def sections(text):
    """(heading, body) pairs split at level-2 headings outside code fences.

    The heading is the heading line's text; everything before the first one is
    PREAMBLE.
    """
    out = [[PREAMBLE, []]]
    in_fence = False
    for ln in split_lines(text):
        if FENCE_RE.match(ln):
            in_fence = not in_fence
        h = HEADING_RE.match(ln)
        if h and not in_fence and len(h.group(1)) == 2:
            out.append([h.group(2), [ln]])
        else:
            out[-1][1].append(ln)
    return [(h, "".join(b)) for h, b in out if h != PREAMBLE or "".join(b).strip()]


PLACEHOLDER_SENTINEL = "\x01"
WHITESPACE_RE = re.compile(r"\s+")


def pattern_for(template_text):
    """A regex matching any rendering of this template text.

    Whitespace is dropped from both sides before matching, so rewrapping is not
    drift. A placeholder matches any non-empty value.
    """
    s = PLACEHOLDER_RE.sub(PLACEHOLDER_SENTINEL, template_text)
    s = WHITESPACE_RE.sub("", s)
    out = []
    for part in s.split(PLACEHOLDER_SENTINEL):
        out.append(re.escape(part))
    return re.compile(".+?".join(out), re.S)


def cmd_drift(args):
    t = Template.load(args.templates, SKILL_TEMPLATE)
    t.require_clean()
    try:
        project_text = read_text(args.skill)
    except OSError as exc:
        raise Fatal("cannot read %s: %s" % (args.skill, exc)) from exc

    ours = sections(t.text)
    theirs = sections(project_text)
    heading_pattern = dict((h, pattern_for(h)) for h, _ in ours)

    claimed = set()
    report, errors = [], []
    for heading, body in ours:
        match = None
        for i, (ph, _) in enumerate(theirs):
            if i in claimed:
                continue
            if heading_pattern[heading].fullmatch(WHITESPACE_RE.sub("", ph)):
                match = i
                break
        if match is None:
            report.append({"heading": heading, "status": "missing"})
            errors.append("%s: section missing from the project's skill" % heading)
            continue
        claimed.add(match)
        pbody = theirs[match][1]
        if pattern_for(body).fullmatch(WHITESPACE_RE.sub("", pbody)):
            report.append(
                {"heading": heading, "status": "same", "project_heading": theirs[match][0]}
            )
            continue
        diff = "".join(
            difflib.unified_diff(split_lines(body), split_lines(pbody), "template", args.skill, n=1)
        )
        report.append(
            {
                "heading": heading,
                "status": "changed",
                "project_heading": theirs[match][0],
                "diff": diff,
            }
        )
        errors.append("%s: differs from the template" % heading)
    for i, (ph, _) in enumerate(theirs):
        if i not in claimed:
            report.append({"heading": ph, "status": "project-only"})

    def human():
        for r in report:
            print("%-13s %s" % (r["status"], r["heading"]))
            if r.get("diff"):
                sys.stdout.write(r["diff"])

    return emit(args, "drift", {"sections": report}, errors=errors, human=human)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_preflight(args):
    errors = check_templates(args.templates)
    data = {"templates": args.templates, "python": "%d.%d" % sys.version_info[:2]}

    def human():
        print("templates  %s" % args.templates)
        print("python     %s" % data["python"])
        if not errors:
            print("ok")

    return emit(args, "preflight", data, errors=errors, human=human)


def cmd_probe(args):
    folders, errors = resolve_folders(args.connected_folder, args.project_folder)
    if errors:
        return emit(args, "probe", None, errors=errors)
    data = {
        "project_path": folders.project,
        "project_mount": folders.mount,
        "probe_command": probe_command(folders.mount),
    }

    def human():
        print("probe, through device_bash:\n%s" % data["probe_command"])

    return emit(args, "probe", data, human=human)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument(
        "--templates",
        metavar="DIR",
        default=DEFAULT_TEMPLATES,
        help="templates directory (default: the one shipped with this plugin)",
    )

    ap = argparse.ArgumentParser(
        prog="gitify.py", description="Deterministic half of the gitify-project skill."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", parents=[common], help="check the shipped templates")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser(
        "probe", parents=[common], help="a device command that checks and lists the folder"
    )
    p.add_argument(
        "--connected-folder", required=True, metavar="PATH", help="as get_device_info lists it"
    )
    p.add_argument(
        "--project-folder",
        metavar="PATH",
        help="the project's folder inside it (default: the connected folder itself)",
    )
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("render", parents=[common], help="fill the templates into a stage directory")
    p.add_argument("--answers", required=True, metavar="FILE", help="answers JSON, or - for stdin")
    p.add_argument(
        "--stage",
        metavar="DIR",
        help="where to write (default: %s/%s/<SKILL_NAME>)" % (OUTPUTS_ROOT, DEFAULT_STAGE_DIR),
    )
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser(
        "drift", parents=[common], help="compare a project's skill with the template"
    )
    p.add_argument("--skill", required=True, metavar="FILE", help="the project's SKILL.md")
    p.set_defaults(func=cmd_drift)

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Fatal as exc:
        sys.stderr.write("gitify.py: %s\n" % exc)
        return CANNOT_RUN
    except BrokenPipeError:
        return OK


if __name__ == "__main__":
    sys.exit(main())

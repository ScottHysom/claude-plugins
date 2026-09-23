#!/usr/bin/env python3
"""Deterministic half of the new-cowork-project skill.

The skill uses the model for what needs judgement: running the interview,
writing the text that fills each marker, writing the maintenance skill's
description. Everything else happens here - reading the templates, finding
their markers, checking the model's answers, filling in placeholders, laying
the files out for the bridge, and comparing a project's skill with the
template it came from.

Usage:
    python3 scaffold.py <command> [options]
    python3 scaffold.py --help

Commands:
    preflight   check the shipped templates are complete and well formed
    markers     every marker the model has to resolve, and an answers skeleton
    render      fill the templates from an answers file into a stage directory
    drift       compare a project's generated skill with the current template

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Where this runs: in Cowork's container, which can read the plugin but not the
user's folder. COWORK.md at the root of the claude-plugins repo says what
Cowork allows and how that was established. So render writes to a stage
directory under /mnt/user-data/outputs/ and prints the `files` list
`device_commit_files` takes, plus two commands for `device_bash`: a precheck
that nothing would be overwritten, and a sha256 check that everything arrived
intact.
setup.sh sets its own execute bits, since they do not survive the copy.

Things that look like bugs and are not:

1. Files are written in place with open(path, "w"), never via a temp file moved
   into position. Cowork's device bridge cannot delete files, and a script in
   this repo may end up running where that matters. Do not "fix" this.

2. Nothing here runs git, not even to read. A git write through the bridge
   strands .git/*.lock files that block every later write, and the scaffold is
   not a repo until the user runs setup.sh.

3. render refuses a stage directory holding files it did not plan. It cannot
   clean one up, for the same reason as 1.

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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATES = os.path.join(
    os.path.dirname(SCRIPT_DIR), "skills", "new-cowork-project", "templates"
)

# Where device_commit_files accepts files from. A stage elsewhere still renders,
# with a warning, so the script can be run and tested off Cowork.
OUTPUTS_ROOT = "/mnt/user-data/outputs"
DEFAULT_STAGE_DIR = "cowork-project-scaffold"

# device_commit_files takes at most this many files in one call.
COMMIT_BATCH_LIMIT = 50

# Where each connected folder appears to device_bash.
DEVICE_MOUNT_ROOT = "$HOME/mnt"

# Template file -> path in the project. Formatted with the placeholder values.
MANIFEST = [
    ("gitignore", ".gitignore"),
    ("commit.sh", "commit.sh"),
    ("setup.sh", "setup.sh"),
    ("skills-README.md", "skills/README.md"),
    ("current-state.md", "current-state.md"),
    ("project-instructions.md", "project-instructions.md"),
    ("prose-style.md", "prose-style.md"),
    ("maintain-docs.md", "skills/{SKILL_NAME}/SKILL.md"),
]
SKILL_TEMPLATE = "maintain-docs.md"

FILL, OPTIONAL, END = "fill", "optional", "end"
ACTIONS = {FILL: ("fill", "leave"), OPTIONAL: ("keep", "delete")}

COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
FILL_PREFIX = "FILL:"
OPTIONAL_PREFIX = "OPTIONAL SECTION"
END_TEXT = "END OPTIONAL SECTION"
# Anything that means a marker or placeholder survived into the output.
LEFTOVER_RE = re.compile(r"\{\{|\}\}|FILL:|OPTIONAL SECTION")

SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_MAX = 64
DESCRIPTION_MAX = 1024
ANCHOR_DOC_RE = re.compile(r"^[^/]+\.md$")
# The skill's front matter holds the description as a plain YAML scalar, which
# cannot contain ": " or " #", or start with one of these.
YAML_UNSAFE_START = "-?:,[]{}#&*!|>'\"%@`"
YAML_UNSAFE_INNER = (": ", " #")
# Cowork's .plugin upload rejects a skill whose description holds anything that
# looks like an XML tag: a `<` directly followed by a name, as in <ins> or </b>.
TAG_RE = re.compile(r"</?[A-Za-z][\w:.-]*")

# Placeholders the model supplies, and the ones computed from the folders.
SUPPLIED = ("PROJECT_NAME", "SKILL_NAME", "ANCHOR_DOC", "DESCRIPTION")
COMPUTED = ("PROJECT_PATH", "PROJECT_MOUNT")

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


def line_starts(lines):
    starts, off = [], 0
    for ln in lines:
        starts.append(off)
        off += len(ln)
    return starts


def line_index(starts, offset):
    """0-indexed line containing an offset."""
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo


def is_blank(line):
    return not line.strip()


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:DIGEST_LEN]


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


class Marker:
    """One FILL or OPTIONAL SECTION marker in a template.

    `start`/`end` are offsets of the comment itself. A block marker stands on
    lines of its own; `line_start`/`line_end` then cover those whole lines,
    which is what gets removed or replaced. An OPTIONAL marker also carries
    its END comment, and the FILL markers inside it name it as `inside`.
    """

    def __init__(self, template, kind, n, start, end, text, lines, starts):
        self.template = template
        self.kind = kind
        self.id = "%s:%s-%d" % (template, kind, n)
        self.start, self.end = start, end
        self.text = text
        self.digest = digest(text)
        first, last = line_index(starts, start), line_index(starts, end - 1)
        self.line = first + 1
        before = lines[first][: start - starts[first]]
        after = lines[last][end - starts[last] :]
        self.block = is_blank(before) and is_blank(after)
        self.first, self.last = first, last
        self.inside = None
        self.end_marker = None
        self.heading = None

    def as_dict(self):
        return {
            "id": self.id,
            "template": self.template,
            "kind": self.kind,
            "line": self.line,
            "form": "block" if self.block else "inline",
            "digest": self.digest,
            "text": self.text,
            "heading": self.heading,
            "inside": self.inside,
        }


class Template:
    """A template file's text, its markers and its placeholders.

    Problems are collected in `errors` rather than raised, so preflight can
    report every one. Anything that fills a template in first calls
    `require_clean`.
    """

    def __init__(self, name, text):
        self.name = name
        self.text = text
        self.lines = split_lines(text)
        self.starts = line_starts(self.lines)
        self.errors = []
        self.markers = []
        self.placeholders = sorted(set(PLACEHOLDER_RE.findall(text)))
        self._parse()

    @classmethod
    def load(cls, directory, name):
        path = os.path.join(directory, name)
        try:
            return cls(name, read_text(path))
        except OSError as exc:
            raise Fatal("cannot read template %s: %s" % (path, exc)) from exc

    def _err(self, offset, msg):
        self.errors.append(
            "%s:%d  %s" % (self.name, line_index(self.starts, offset) + 1 if self.lines else 1, msg)
        )

    def _parse(self):
        counts = {FILL: 0, OPTIONAL: 0}
        open_section = None
        spans = []
        for m in COMMENT_RE.finditer(self.text):
            body = m.group(1).strip()
            if body.startswith(FILL_PREFIX):
                kind = FILL
            elif body == END_TEXT:
                kind = END
            elif body.startswith(OPTIONAL_PREFIX):
                kind = OPTIONAL
            else:
                continue
            spans.append((m.start(), m.end()))
            if kind == END:
                if open_section is None:
                    self._err(m.start(), "END OPTIONAL SECTION with no section open")
                    continue
                end = Marker(
                    self.name, END, 0, m.start(), m.end(), m.group(0), self.lines, self.starts
                )
                if not end.block:
                    self._err(m.start(), "END OPTIONAL SECTION must stand on its own line")
                open_section.end_marker = end
                open_section = None
                continue
            counts[kind] += 1
            mk = Marker(
                self.name,
                kind,
                counts[kind],
                m.start(),
                m.end(),
                m.group(0),
                self.lines,
                self.starts,
            )
            if kind == OPTIONAL:
                if open_section is not None:
                    self._err(m.start(), "OPTIONAL SECTION opened inside %s" % open_section.id)
                if not mk.block:
                    self._err(m.start(), "OPTIONAL SECTION must stand on lines of its own")
                open_section = mk
            elif open_section is not None:
                mk.inside = open_section.id
            self.markers.append(mk)
        if open_section is not None:
            self._err(open_section.start, "%s has no END OPTIONAL SECTION" % open_section.id)

        # Marker words and braces anywhere else mean a marker the parser did not
        # recognise, which would otherwise be copied into a project unnoticed.
        for m in LEFTOVER_RE.finditer(self.text):
            if any(a <= m.start() < b for a, b in spans):
                continue
            if m.group(0) in ("{{", "}}") and self._in_placeholder(m.start()):
                continue
            self._err(m.start(), "%r outside any marker or placeholder" % m.group(0))
        unclosed = self.text.rfind("<!--")
        if unclosed != -1 and self.text.find("-->", unclosed) == -1:
            self._err(unclosed, "comment is never closed")

        self._attach_headings()

    def _in_placeholder(self, offset):
        for m in PLACEHOLDER_RE.finditer(self.text):
            if m.start() <= offset < m.end():
                return True
        return False

    def _attach_headings(self):
        """Name the heading each marker sits under: the nearest one above, or
        for an OPTIONAL marker, the first heading inside its section."""
        headings = []
        in_fence = False
        for i, ln in enumerate(self.lines):
            if FENCE_RE.match(ln):
                in_fence = not in_fence
                continue
            h = HEADING_RE.match(ln)
            if h and not in_fence:
                headings.append((i, h.group(2)))
        for mk in self.markers:
            if mk.kind == OPTIONAL and mk.end_marker is not None:
                inner = [t for i, t in headings if mk.last < i < mk.end_marker.first]
                if inner:
                    mk.heading = inner[0]
                    continue
            above = [t for i, t in headings if i < mk.first]
            mk.heading = above[-1] if above else None

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


def check_value(name, value, values):
    """Errors for one supplied placeholder value."""
    if not isinstance(value, str) or not value.strip():
        return ["values.%s is required" % name]
    errs = []
    if value != value.strip() or "\n" in value:
        errs.append("values.%s must be one line with no surrounding space" % name)
    if "{{" in value or "}}" in value or "<!--" in value:
        errs.append("values.%s cannot contain {{, }} or <!--" % name)
    if name == "SKILL_NAME":
        if not SKILL_NAME_RE.match(value) or len(value) > SKILL_NAME_MAX:
            errs.append(
                "values.SKILL_NAME must be lower-case words joined by -, at most %d characters: %r"
                % (SKILL_NAME_MAX, value)
            )
    elif name == "ANCHOR_DOC":
        if not ANCHOR_DOC_RE.match(value):
            errs.append("values.ANCHOR_DOC must be a .md file name at the project root: %r" % value)
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


def check_text(text, where):
    """Errors for a model-written fill text."""
    if not isinstance(text, str):
        return ["%s: text must be a string" % where]
    errs = []
    if FILL_PREFIX in text or OPTIONAL_PREFIX in text:
        errs.append("%s: text cannot contain marker words (FILL:, OPTIONAL SECTION)" % where)
    for p in PLACEHOLDER_RE.findall(text):
        if p not in SUPPLIED and p not in COMPUTED:
            errs.append("%s: text uses unknown placeholder {{%s}}" % (where, p))
    stripped = PLACEHOLDER_RE.sub("", text)
    if "{{" in stripped or "}}" in stripped:
        errs.append("%s: text has a stray {{ or }}" % where)
    # An unclosed fence turns the rest of the file into one code block: every
    # heading after it stops being a heading, for a reader and for drift.
    if len([ln for ln in split_lines(text) if FENCE_RE.match(ln)]) % 2:
        errs.append("%s: text opens a code fence it does not close" % where)
    return errs


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def removal(t, first, last):
    """An edit removing lines first..last, plus the blank line after them when
    the line before is blank too, so removing a block leaves one blank line
    rather than two."""
    a = t.starts[first]
    b = t.starts[last] + len(t.lines[last])
    prev_blank = first == 0 or is_blank(t.lines[first - 1])
    if prev_blank and last + 1 < len(t.lines) and is_blank(t.lines[last + 1]):
        b += len(t.lines[last + 1])
    return a, b, ""


def plan_template(t, resolutions):
    """Edits for one template, and the errors that block it.

    Every edit is an (start, end, replacement) against the template as read, so
    no edit can shift the address of another. Returns (edits, left, errors).
    """
    edits, left, errors = [], [], []
    deleted = set()
    for mk in t.markers:
        if mk.kind == OPTIONAL and resolutions.get(mk.id, {}).get("action") == "delete":
            deleted.add(mk.id)

    for mk in t.markers:
        res = resolutions.get(mk.id)
        if mk.inside in deleted:
            if res is not None:
                errors.append("%s is inside %s, which is deleted; drop it" % (mk.id, mk.inside))
            continue
        if res is None:
            errors.append("%s has no resolution (%s, under %r)" % (mk.id, mk.kind, mk.heading))
            continue
        if not isinstance(res, dict):
            errors.append("%s: resolution must be an object" % mk.id)
            continue
        if res.get("digest") != mk.digest:
            errors.append(
                "%s: digest %r does not match the template (%s); run markers again"
                % (mk.id, res.get("digest"), mk.digest)
            )
            continue
        action = res.get("action")
        if action not in ACTIONS[mk.kind]:
            errors.append(
                "%s: action must be one of %s, not %r"
                % (mk.id, ", ".join(ACTIONS[mk.kind]), action)
            )
            continue
        extra = set(res) - {"digest", "action", "text"}
        if extra:
            errors.append("%s: unexpected keys %s" % (mk.id, ", ".join(sorted(extra))))
            continue
        if action == "fill":
            text = res.get("text")
            text_errs = check_text(text, mk.id)
            if not mk.block and isinstance(text, str) and "\n" in text:
                text_errs.append("%s: an inline marker's text must be one line" % mk.id)
            if text_errs:
                errors.extend(text_errs)
                continue
            if not mk.block:
                edits.append((mk.start, mk.end, text))
            elif text.strip():
                a = t.starts[mk.first]
                b = t.starts[mk.last] + len(t.lines[mk.last])
                edits.append((a, b, text.rstrip("\n") + "\n"))
            else:
                edits.append(removal(t, mk.first, mk.last))
            continue
        if "text" in res:
            errors.append("%s: text is only for action fill" % mk.id)
            continue
        if action == "leave":
            left.append({"id": mk.id, "line": mk.line, "heading": mk.heading})
        elif action == "keep":
            for part in (mk, mk.end_marker):
                edits.append(removal(t, part.first, part.last))
        elif action == "delete":
            edits.append(removal(t, mk.first, mk.end_marker.last))
    return edits, left, errors


def apply_edits(text, edits):
    out, pos = [], 0
    for a, b, new in sorted(edits):
        if a < pos:
            raise Fatal("overlapping edits at offset %d; this is a bug in scaffold.py" % a)
        out.append(text[pos:a])
        out.append(new)
        pos = b
    out.append(text[pos:])
    return "".join(out)


def substitute(text, values):
    return PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def leftovers(text, left_count):
    """Errors if markers or placeholders survived that should not have."""
    errs = []
    fills = len(
        [m for m in COMMENT_RE.finditer(text) if m.group(1).strip().startswith(FILL_PREFIX)]
    )
    if fills != left_count:
        errs.append("%d FILL marker(s) in the output, %d left on purpose" % (fills, left_count))
    stray = [m.group(0) for m in LEFTOVER_RE.finditer(text) if m.group(0) != FILL_PREFIX]
    if stray:
        errs.append("output still contains %s" % ", ".join(sorted(set(stray))))
    return errs


def sh_quote_under(root, rel):
    """A path under a root that must expand, such as $HOME/mnt, quoted for sh."""
    return '"%s"/%s' % (root, shlex.quote(rel)) if rel else '"%s"' % root


def precheck_command(mount_name, sub, rels):
    targets = [posix_join(sub, r) for r in [".git", *rels]]
    lines = [
        "cd %s || exit 2" % sh_quote_under(DEVICE_MOUNT_ROOT, mount_name),
        "found=0",
        "for f in %s; do" % " ".join(shlex.quote(p) for p in targets),
        '  if [ -e "$f" ]; then echo "exists: $f"; found=1; fi',
        "done",
        '[ "$found" = 0 ] && echo "clear"',
        'exit "$found"',
    ]
    return "\n".join(lines)


def check_command(mount_name, sub, files):
    lines = [
        "cd %s && sha256sum --check --strict - <<'SUMS'"
        % sh_quote_under(DEVICE_MOUNT_ROOT, mount_name)
    ]
    for f in files:
        lines.append(
            "%s  %s"
            % (hashlib.sha256(f["content"].encode("utf-8")).hexdigest(), posix_join(sub, f["file"]))
        )
    lines.append("SUMS")
    return "\n".join(lines)


def posix_join(*parts):
    return "/".join(p for p in parts if p)


def cmd_render(args):
    answers = read_answers(args.answers)
    templates = load_templates(args.templates)
    for t in templates:
        t.require_clean()
    by_id = {mk.id: mk for t in templates for mk in t.markers}

    errors, warnings = [], []
    extra = set(answers) - {"connected_folder", "project_folder", "values", "markers"}
    if extra:
        errors.append("answers has unexpected keys: %s" % ", ".join(sorted(extra)))

    connected, err = normalise_folder(answers.get("connected_folder"), "connected_folder")
    if err:
        errors.append(err)
    project = connected
    if answers.get("project_folder") is not None:
        project, err = normalise_folder(answers.get("project_folder"), "project_folder")
        if err:
            errors.append(err)
    sub = ""
    if connected and project:
        if project == connected:
            sub = ""
        elif project.startswith(connected + "/"):
            sub = project[len(connected) + 1 :]
        else:
            errors.append(
                "project_folder %r is not inside connected_folder %r" % (project, connected)
            )
            project = None

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

    resolutions = answers.get("markers")
    if not isinstance(resolutions, dict):
        errors.append("markers must be an object keyed by marker id")
        resolutions = {}
    for mid in sorted(set(resolutions) - set(by_id)):
        errors.append("markers.%s is not a marker in the templates; run markers again" % mid)

    if errors:
        # Without valid folders and values no file can be laid out, so these
        # stop the whole run even under --partial.
        errors.append("nothing was written")
        return emit(args, "render", None, errors=errors)

    mount_name = connected.split("/")[-1] if connected not in ("~",) else ""
    if not mount_name:
        return emit(args, "render", None, errors=["connected_folder has no folder name to mount"])
    full = dict((k, values[k]) for k in SUPPLIED)
    full["PROJECT_PATH"] = project
    full["PROJECT_MOUNT"] = posix_join(mount_name, sub)

    planned, left = [], []
    for (name, dest), t in zip(MANIFEST, templates):
        rel = dest.format(**full)
        mine = dict((k, v) for k, v in resolutions.items() if k.startswith(name + ":"))
        edits, file_left, file_errors = plan_template(t, mine)
        if not file_errors:
            content = substitute(apply_edits(t.text, edits), full)
            file_errors = ["%s: %s" % (rel, e) for e in leftovers(content, len(file_left))]
        if file_errors:
            errors.extend(file_errors)
            continue
        for item in file_left:
            item["file"] = rel
        left.extend(file_left)
        planned.append({"file": rel, "template": name, "content": content})

    if len(planned) > COMMIT_BATCH_LIMIT:
        errors.append(
            "%d files is more than device_commit_files takes in one call (%d)"
            % (len(planned), COMMIT_BATCH_LIMIT)
        )
    if errors and not args.partial:
        errors.append("nothing was written; pass --partial to stage the files without errors")
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
                "device_path": posix_join(project, p["file"]),
                "sha256": hashlib.sha256(p["content"].encode("utf-8")).hexdigest(),
            }
        )
    for item in left:
        warnings.append(
            "%s left unresolved in %s, under %r" % (item["id"], item["file"], item["heading"])
        )

    data = {
        "dry_run": args.dry_run,
        "stage": stage,
        "project_path": project,
        "project_mount": full["PROJECT_MOUNT"],
        "files": files,
        "commit_files": [
            {"stagedPath": f["staged_path"], "devicePath": f["device_path"]} for f in files
        ],
        "precheck_command": precheck_command(mount_name, sub, [f["file"] for f in files]),
        "check_command": check_command(mount_name, sub, planned),
        "left": left,
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

    return emit(args, "render", data, errors=errors, warnings=warnings, human=human)


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


FILL_SENTINEL, PLACEHOLDER_SENTINEL = "\x00", "\x01"
WHITESPACE_RE = re.compile(r"\s+")


def pattern_for(template_text):
    """A regex matching any rendering of this template text.

    Whitespace is dropped from both sides before matching, so rewrapping is not
    drift. A FILL marker matches anything, including nothing; a placeholder
    matches any non-empty value.
    """
    s = COMMENT_RE.sub(
        lambda m: FILL_SENTINEL if m.group(1).strip().startswith(FILL_PREFIX) else m.group(0),
        template_text,
    )
    s = PLACEHOLDER_RE.sub(PLACEHOLDER_SENTINEL, s)
    s = WHITESPACE_RE.sub("", s)
    out = []
    for ch in re.split("([%s%s])" % (FILL_SENTINEL, PLACEHOLDER_SENTINEL), s):
        if ch == FILL_SENTINEL:
            out.append(".*?")
        elif ch == PLACEHOLDER_SENTINEL:
            out.append(".+?")
        else:
            out.append(re.escape(ch))
    return re.compile("".join(out), re.S)


def strip_optional_markers(t):
    """The template text without OPTIONAL SECTION and END comments, and the
    headings of the sections that were optional."""
    edits, optional_headings = [], set()
    for mk in t.markers:
        if mk.kind != OPTIONAL:
            continue
        for part in (mk, mk.end_marker):
            edits.append(removal(t, part.first, part.last))
        inner = "".join(t.lines[mk.last + 1 : mk.end_marker.first])
        for h, _ in sections(inner):
            if h != PREAMBLE:
                optional_headings.add(h)
    return apply_edits(t.text, edits), optional_headings


def cmd_drift(args):
    t = Template.load(args.templates, SKILL_TEMPLATE)
    t.require_clean()
    try:
        project_text = read_text(args.skill)
    except OSError as exc:
        raise Fatal("cannot read %s: %s" % (args.skill, exc)) from exc

    template_text, optional = strip_optional_markers(t)
    ours = sections(template_text)
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
            status = "deleted-optional" if heading in optional else "missing"
            report.append({"heading": heading, "status": status})
            if status == "missing":
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
            print("%-17s %s" % (r["status"], r["heading"]))
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


def cmd_markers(args):
    templates = load_templates(args.templates)
    for t in templates:
        t.require_clean()
    markers = [mk.as_dict() for t in templates for mk in t.markers]
    skeleton = {
        "connected_folder": "",
        "project_folder": None,
        "values": dict((k, "") for k in SUPPLIED),
        "markers": dict((m["id"], {"digest": m["digest"], "action": None}) for m in markers),
    }
    data = {"markers": markers, "skeleton": skeleton}

    def human():
        for m in markers:
            print("%-40s line %-4d %-6s under %r" % (m["id"], m["line"], m["form"], m["heading"]))

    return emit(args, "markers", data, human=human)


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
        prog="scaffold.py", description="Deterministic half of the new-cowork-project skill."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", parents=[common], help="check the shipped templates")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("markers", parents=[common], help="the markers to resolve, and a skeleton")
    p.set_defaults(func=cmd_markers)

    p = sub.add_parser("render", parents=[common], help="fill the templates into a stage directory")
    p.add_argument("--answers", required=True, metavar="FILE", help="answers JSON, or - for stdin")
    p.add_argument(
        "--stage",
        metavar="DIR",
        help="where to write (default: %s/%s/<SKILL_NAME>)" % (OUTPUTS_ROOT, DEFAULT_STAGE_DIR),
    )
    p.add_argument("--partial", action="store_true", help="stage the files without errors")
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
        sys.stderr.write("scaffold.py: %s\n" % exc)
        return CANNOT_RUN
    except BrokenPipeError:
        return OK


if __name__ == "__main__":
    sys.exit(main())

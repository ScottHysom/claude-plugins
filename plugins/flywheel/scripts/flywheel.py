#!/usr/bin/env python3
"""Deterministic half of the flywheel plugin.

The issue loop takes an approved issue from claim to a merged pull request,
through sessions in the Claude desktop app that each play one role: the
dispatcher starts the others, an implementer works one issue, and a reviewer
reviews its pull request. This script does the loop's work that needs no
judgment. Its skills, which arrive in later versions, run it.

Usage:
    python3 flywheel.py <command> [options]
    python3 flywheel.py --help

Commands:
    setup        copy this script, the templates it reads and the plugin's
                 manifest into the project's .flywheel/, which git ignores
    config init  write .flywheel/roles.json from the plugin's template, and
                 name each field the owner fills in

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

The copy. Each shell call in Claude Code starts without the last one's
variables, and the plugin's own path is too long to repeat in every command,
so `setup` copies the script into the project and prints the prefix that
reaches it. It copies the roles template and plugin.json beside it, so the
copy can run `config init` and read the plugin's version without reaching
back into the plugin. A file is read beside the script when the script sits
in .flywheel/, and from the plugin otherwise.

What git ignores. .flywheel/ also holds what the owner sets and commits, such
as roles.json, so the .gitignore that `setup` writes names only the files it
copies, and itself, rather than `*`.

The roles file. One entry per role, each with its tier from the method's
roles.md, the model and the default effort, and the plugin version it was set
under. `config init` fills in the version. A field the template leaves null is
one only the owner can fill, such as the model behind a tier, and `config
init` names each one by its path in the file.

Only `setup` and `config init` write, and only under .flywheel/. Neither
writes to git. Neither takes --dry-run, since nothing reads a preview of
them.

Python 3.9 is the floor. No match statements, no X | Y unions.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

ENVELOPE_VERSION = 1

OK = 0
PROBLEMS = 1
CANNOT_RUN = 2

PROG = "flywheel.py"

SCRIPT_PATH = os.path.abspath(__file__)
SCRIPT_NAME = os.path.basename(SCRIPT_PATH)
MANIFEST = "plugin.json"
SHIPPED_MANIFEST = ".claude-plugin/" + MANIFEST
ROLES_TEMPLATE = "roles.json"
SHIPPED_ROLES = "templates/" + ROLES_TEMPLATE

COPY_DIR = ".flywheel"
COPY_SCRIPT = COPY_DIR + "/" + SCRIPT_NAME
COPY_MANIFEST = COPY_DIR + "/" + MANIFEST
COPY_ROLES = COPY_DIR + "/roles.template.json"
COPY_IGNORE = COPY_DIR + "/.gitignore"
COPY_PREFIX = "FLYWHEEL=" + COPY_SCRIPT

ROLES_FILE = COPY_DIR + "/roles.json"
ROLES_KEY = "roles"
VERSION_KEY = "version"


class Fatal(Exception):
    """Cannot run at all. Exits 2."""


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def envelope(command, data, errors, warnings):
    return {
        "version": ENVELOPE_VERSION,
        "command": command,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "data": data,
    }


def emit(args, command, data, errors=None, warnings=None, human=None):
    """Print JSON or human output, and return the exit code."""
    errors = errors or []
    warnings = warnings or []
    if args.json:
        print(json.dumps(envelope(command, data, errors, warnings), indent=2, sort_keys=True))
    else:
        human()
        sys.stderr.write("".join("warning: %s\n" % w for w in warnings))
        sys.stderr.write("".join("%s\n" % e for e in errors))
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def project_root(start):
    """The top of the git working tree that holds start."""
    start = os.path.abspath(start)
    if not os.path.isdir(start):
        raise Fatal("%s is not a directory. Name a clone with -C." % start)
    try:
        out = subprocess.run(
            ["git", "--no-optional-locks", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise Fatal("git is not installed, or not on PATH. Install git, then run again.") from exc
    if out.returncode != 0:
        raise Fatal(
            "%s is not inside a git working tree. Run from inside a clone, or name one with -C."
            % start
        )
    return os.fsdecode(out.stdout.rstrip(b"\n"))


def plugin_file(copied, shipped):
    """A file the script reads: beside it in the project's copy, else in the plugin."""
    here = os.path.dirname(SCRIPT_PATH)
    if os.path.basename(here) == COPY_DIR:
        path = os.path.join(here, os.path.basename(copied))
    else:
        path = os.path.join(os.path.dirname(here), *shipped.split("/"))
    if not os.path.isfile(path):
        raise Fatal("%s is missing. Install the flywheel plugin again, then run its setup." % path)
    return path


def read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise Fatal(
            "cannot read %s: %s. Check its permissions, then run again." % (path, exc)
        ) from exc


def read_json(path):
    try:
        return json.loads(read_bytes(path).decode("utf-8"))
    except ValueError as exc:
        raise Fatal(
            "%s is not valid JSON: %s. Install the flywheel plugin again, then run its setup."
            % (path, exc)
        ) from exc


def write_bytes(root, rel, content):
    path = os.path.join(root, *rel.split("/"))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(content)
    except OSError as exc:
        raise Fatal(
            "cannot write %s: %s. Check its permissions, then run again." % (path, exc)
        ) from exc


def plugin_version():
    manifest = read_json(plugin_file(COPY_MANIFEST, SHIPPED_MANIFEST))
    version = manifest.get(VERSION_KEY) if isinstance(manifest, dict) else None
    if not isinstance(version, str):
        raise Fatal(
            "the plugin's %s does not give a version. Install the flywheel plugin again, then"
            " run its setup." % MANIFEST
        )
    return version


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------


# What setup copies, beside the .gitignore it writes.
COPIES = (COPY_SCRIPT, COPY_ROLES, COPY_MANIFEST)


def ignore_text():
    names = sorted(os.path.basename(rel) for rel in (*COPIES, COPY_IGNORE))
    return "".join(name + "\n" for name in names).encode("utf-8")


def cmd_setup(args):
    """Copy this script and what it reads into the project. The module
    docstring has why."""
    root = project_root(args.repo)
    sources = {
        COPY_SCRIPT: SCRIPT_PATH,
        COPY_ROLES: plugin_file(COPY_ROLES, SHIPPED_ROLES),
        COPY_MANIFEST: plugin_file(COPY_MANIFEST, SHIPPED_MANIFEST),
    }
    contents = [(rel, read_bytes(sources[rel])) for rel in COPIES]
    contents.append((COPY_IGNORE, ignore_text()))
    files = []
    for rel, content in contents:
        write_bytes(root, rel, content)
        files.append({"file": rel, "sha256": hashlib.sha256(content).hexdigest()})
    data = {"repo": root, "files": files, "prefix": COPY_PREFIX}

    def human():
        for f in files:
            print("wrote %s" % f["file"])
        print("\nfrom %s, start every command with:\n%s && " % (root, COPY_PREFIX))

    return emit(args, "setup", data, human=human)


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


def owner_fields(roles):
    """The path of each field the template leaves for the owner, in file order."""
    out = []
    for role, entry in roles.items():
        for key, value in entry.items():
            if value is None:
                out.append("%s.%s.%s" % (ROLES_KEY, role, key))
    return out


def cmd_config_init(args):
    """Write the roles file from the template, with the plugin's version."""
    root = project_root(args.repo)
    target = os.path.join(root, *ROLES_FILE.split("/"))
    if os.path.lexists(target):
        data = {"file": ROLES_FILE, "written": False, "owner_fields": []}
        error = (
            "%s already exists, so it was left as it is. Edit it to change a role, or delete"
            " it and run config init again to start from the template." % ROLES_FILE
        )
        return emit(args, "config init", data, errors=[error], human=lambda: None)

    template = read_json(plugin_file(COPY_ROLES, SHIPPED_ROLES))
    roles = template.get(ROLES_KEY) if isinstance(template, dict) else None
    if not isinstance(roles, dict) or not all(isinstance(e, dict) for e in roles.values()):
        raise Fatal(
            "the roles template does not hold a %r object of roles. Install the flywheel"
            " plugin again, then run its setup." % ROLES_KEY
        )
    version = plugin_version()
    for entry in roles.values():
        entry[VERSION_KEY] = version
    fields = owner_fields(roles)
    text = json.dumps(template, indent=2) + "\n"
    write_bytes(root, ROLES_FILE, text.encode("utf-8"))
    data = {"file": ROLES_FILE, "written": True, "owner_fields": fields}

    def human():
        print("wrote %s" % ROLES_FILE)
        if fields:
            print("\nthe owner fills in each of these:")
            for f in fields:
                print("  %s" % f)

    return emit(args, "config init", data, human=human)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build_parser():
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common = argparse.ArgumentParser(add_help=False, parents=[output])
    common.add_argument(
        "-C", "--repo", metavar="DIR", default=".", help="the clone to work in (default: here)"
    )

    ap = argparse.ArgumentParser(
        prog=PROG, description="Deterministic half of the flywheel plugin."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "setup",
        parents=[common],
        help="copy this script and what it reads into %s/, which git ignores" % COPY_DIR,
    )
    p.set_defaults(func=cmd_setup)

    config = sub.add_parser("config", help="write the files the owner sets for the loop")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    p = config_sub.add_parser(
        "init",
        parents=[common],
        help="write %s from the plugin's template, and name the fields the owner fills"
        % ROLES_FILE,
    )
    p.set_defaults(func=cmd_config_init)

    return ap


def main(argv=None):
    # stdout is flushed inside the try, where a closed pipe is caught, rather
    # than by Python at exit, where it would print a traceback and exit 120.
    try:
        try:
            args = build_parser().parse_args(argv)
        except SystemExit:
            # argparse exits here after printing --help.
            sys.stdout.flush()
            raise
        code = args.func(args)
        sys.stdout.flush()
        return code
    except Fatal as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return CANNOT_RUN
    except BrokenPipeError:
        silence_stdout()
        return OK


def silence_stdout():
    """Point stdout at the null device, so the flush at exit cannot fail.

    The output still buffered when the pipe closed stays in the buffer, and
    Python flushes it again at exit.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, sys.stdout.fileno())
    finally:
        os.close(devnull)


if __name__ == "__main__":
    sys.exit(main())

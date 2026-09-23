#!/usr/bin/env python3
"""Check that marketplace.json, each plugin.json and the directory layout agree.

`claude plugin validate` checks each manifest in isolation. It cannot see that
two manifests disagree with each other, so it passed cleanly while
marketplace.json said 0.1.0 and plugin.json said 0.2.0.

Every rule here is one the README already states, under "Adding a plugin" and
"Versioning". Run from anywhere in the clone:

    python3 .github/scripts/check-manifest-consistency.py check

Commands:

  check  every marketplace entry is complete, kebab-case, and points at a
         directory of the same name whose plugin.json agrees with it on name
         and version; and every plugin directory has an entry

Every command takes --json and -C/--repo.

Exit codes: 0 clean, 1 ran and found problems, 2 could not run.

Things that look like bugs and are not:

- A missing marketplace.json, or one that lists no plugins, exits 1 rather
  than 2. The check ran; what it found is a repo with nothing installable.
  A manifest that is not valid JSON does exit 2, since nothing can be checked.
- A plugin with any error is left out of the list of consistent plugins, even
  when its versions agree. That list is what "agrees" means, not a roll call.
- A directory under plugins/ with no plugin.json is not reported as missing an
  entry. It is not a plugin yet, and `claude plugin validate` has nothing to
  say about it either.
- It only reads, and the only thing it asks git is where the clone's root is,
  so it is safe to run anywhere - including Cowork's device bridge, where a
  git write would strand a lock file.
"""

import argparse
import json
import os
import re
import subprocess
import sys

ENVELOPE_VERSION = 1

OK, PROBLEMS, CANNOT_RUN = 0, 1, 2

PROG = "check-manifest-consistency.py"
MARKETPLACE = os.path.join(".claude-plugin", "marketplace.json")
PLUGIN_JSON = os.path.join(".claude-plugin", "plugin.json")
PLUGINS = "plugins"
# README: name, source, description and version are all required. The name is
# checked on its own first, since every other message is prefixed with it.
REQUIRED_FIELDS = ("source", "description", "version")
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


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
        if errors:
            sys.stderr.write("Found %d consistency error(s):\n" % len(errors))
        for e in errors:
            sys.stderr.write("  - %s\n" % e)
    return PROBLEMS if errors else OK


# --------------------------------------------------------------------------
# reading
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


def load_json(root, path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise Fatal("cannot read %s: %s" % (os.path.relpath(path, root), exc)) from exc


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def check_entry(root, entry, errors):
    """Check one marketplace entry. Return its name, or None if it has none."""
    name = entry.get("name")
    if not name:
        errors.append("a marketplace entry has no name")
        return None

    for field in REQUIRED_FIELDS:
        if not entry.get(field):
            errors.append("%s: marketplace entry is missing `%s`" % (name, field))

    # README: kebab-case
    if not KEBAB_RE.match(name):
        errors.append("%s: marketplace entry name is not kebab-case" % name)

    source = entry.get("source")
    if not source:
        return name

    plugin_dir = os.path.realpath(os.path.join(root, source))
    if not os.path.isdir(plugin_dir):
        errors.append("%s: source `%s` is not a directory" % (name, source))
        return name

    # README: the directory name matches the plugin name
    if os.path.basename(plugin_dir) != name:
        errors.append(
            "%s: source directory is `%s`, which does not match the entry name"
            % (name, os.path.basename(plugin_dir))
        )

    manifest = os.path.join(plugin_dir, PLUGIN_JSON)
    if not os.path.isfile(manifest):
        errors.append("%s: no plugin.json at %s" % (name, os.path.relpath(manifest, root)))
        return name

    plugin = load_json(root, manifest)

    if plugin.get("name") != name:
        errors.append(
            "%s: plugin.json name is `%s`, which does not match the marketplace entry"
            % (name, plugin.get("name"))
        )

    # README: "Keep them the same"
    if entry.get("version") != plugin.get("version"):
        errors.append(
            "%s: version drift. marketplace.json says `%s`, plugin.json says `%s`"
            % (name, entry.get("version"), plugin.get("version"))
        )
    return name


def cmd_check(args, root):
    """Every rule the README states about how the manifests agree."""
    errors, plugins = [], []

    def human():
        for p in plugins:
            print("  %s: %s (marketplace and plugin agree)" % (p["name"], p["version"]))
        if not errors:
            print("\nAll %d plugin(s) consistent." % len(plugins))

    marketplace = os.path.join(root, MARKETPLACE)
    if not os.path.isfile(marketplace):
        errors.append("missing %s" % MARKETPLACE)
        return emit(args, "check", {"plugins": plugins}, errors, human=human)

    entries = load_json(root, marketplace).get("plugins", [])
    if not entries:
        errors.append("marketplace.json lists no plugins")
        return emit(args, "check", {"plugins": plugins}, errors, human=human)

    cataloged = set()
    for entry in entries:
        before = len(errors)
        name = check_entry(root, entry, errors)
        if name is None:
            continue
        cataloged.add(name)
        # Only report a plugin as consistent if it raised nothing above.
        if len(errors) == before:
            plugins.append({"name": name, "version": entry.get("version")})

    # The inverse drift: a plugin directory that was never cataloged. Without
    # an entry it is unreachable through the marketplace.
    plugins_dir = os.path.join(root, PLUGINS)
    if os.path.isdir(plugins_dir):
        for d in sorted(os.listdir(plugins_dir)):
            if not os.path.isfile(os.path.join(plugins_dir, d, PLUGIN_JSON)):
                continue
            if d not in cataloged:
                errors.append(
                    "%s: has a plugin.json but no marketplace.json entry, "
                    "so it cannot be installed" % d
                )

    return emit(args, "check", {"plugins": plugins}, errors, human=human)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable envelope on stdout")
    common.add_argument("-C", "--repo", metavar="DIR", default=".", help="a directory in the clone")

    ap = argparse.ArgumentParser(
        prog=PROG, description="Check the marketplace and plugin manifests agree."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", parents=[common], help="the manifests and directories agree")
    p.set_defaults(func=cmd_check)

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

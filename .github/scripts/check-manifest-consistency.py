#!/usr/bin/env python3
"""Check that marketplace.json, each plugin.json and the directory layout agree.

`claude plugin validate` checks each manifest in isolation. It cannot see that
two manifests disagree with each other, so it passed cleanly while
marketplace.json said 0.1.0 and plugin.json said 0.2.0.

Every rule here is one the README already states, under "Adding a plugin" and
"Versioning". Run it from the repo root:

    python3 .github/scripts/check-manifest-consistency.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGINS_DIR = ROOT / "plugins"
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

errors = []
checked = []


def fail(msg):
    errors.append(msg)


def main():
    if not MARKETPLACE.is_file():
        fail(f"missing {MARKETPLACE.relative_to(ROOT)}")
        return

    catalog = json.loads(MARKETPLACE.read_text())
    entries = catalog.get("plugins", [])
    if not entries:
        fail("marketplace.json lists no plugins")
        return

    catalogued = set()

    for entry in entries:
        errors_before = len(errors)
        name = entry.get("name")
        if not name:
            fail("a marketplace entry has no name")
            continue
        catalogued.add(name)

        # README: name, source, description and version are all required
        for field in ("source", "description", "version"):
            if not entry.get(field):
                fail(f"{name}: marketplace entry is missing `{field}`")

        # README: kebab-case
        if not KEBAB.match(name):
            fail(f"{name}: marketplace entry name is not kebab-case")

        source = entry.get("source")
        if not source:
            continue

        plugin_dir = (ROOT / source).resolve()
        if not plugin_dir.is_dir():
            fail(f"{name}: source `{source}` is not a directory")
            continue

        # README: the directory name matches the plugin name
        if plugin_dir.name != name:
            fail(
                f"{name}: source directory is `{plugin_dir.name}`, "
                f"which does not match the entry name"
            )

        manifest = plugin_dir / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            fail(f"{name}: no plugin.json at {manifest.relative_to(ROOT)}")
            continue

        plugin = json.loads(manifest.read_text())

        if plugin.get("name") != name:
            fail(
                f"{name}: plugin.json name is `{plugin.get('name')}`, "
                f"which does not match the marketplace entry"
            )

        # README: "Keep them the same"
        cat_version, plug_version = entry.get("version"), plugin.get("version")
        if cat_version != plug_version:
            fail(
                f"{name}: version drift. marketplace.json says "
                f"`{cat_version}`, plugin.json says `{plug_version}`"
            )

        # Only report a plugin as consistent if it raised nothing above.
        if len(errors) == errors_before:
            checked.append((name, plug_version))

    # The inverse drift: a plugin directory that was never catalogued. Without
    # an entry it is unreachable through the marketplace.
    if PLUGINS_DIR.is_dir():
        for d in sorted(PLUGINS_DIR.iterdir()):
            if not (d / ".claude-plugin" / "plugin.json").is_file():
                continue
            if d.name not in catalogued:
                fail(
                    f"{d.name}: has a plugin.json but no marketplace.json "
                    f"entry, so it cannot be installed"
                )


main()

for name, version in checked:
    print(f"  {name}: {version} (marketplace and plugin agree)")
sys.stdout.flush()

if errors:
    print(f"\nFound {len(errors)} consistency error(s):", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    sys.exit(1)

print(f"\nAll {len(checked)} plugin(s) consistent.")

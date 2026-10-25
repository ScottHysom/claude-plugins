"""The project settings every Claude Code session in this repository loads.

This repository opens pull requests through flywheel's open-pr skill, whose
cold reader is flywheel's own agent. Both resolve only in a session that has
the plugin, so the settings enable it from the marketplace this repository is.
"""

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SETTINGS = _ROOT / ".claude" / "settings.json"
_MARKETPLACE = _ROOT / ".claude-plugin" / "marketplace.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.spec("settings-enables-flywheel")
class DescribeTheProjectSettings:
    def it_names_this_repository_as_a_directory_marketplace(self):
        name = read(_MARKETPLACE)["name"]
        entry = read(_SETTINGS)["extraKnownMarketplaces"][name]
        assert entry["source"]["source"] == "directory"
        assert (_ROOT / entry["source"]["path"]).resolve() == _ROOT

    def it_enables_flywheel_from_that_marketplace(self):
        name = read(_MARKETPLACE)["name"]
        assert "flywheel" in [p["name"] for p in read(_MARKETPLACE)["plugins"]]
        assert read(_SETTINGS)["enabledPlugins"]["flywheel@%s" % name] is True

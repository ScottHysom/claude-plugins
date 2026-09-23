"""The rules that keep marketplace.json, plugin.json and the layout in step.

The script is a required CI gate, and every rule it enforces fails by
absence: a rule that stops matching lets the drift it exists to catch
through, and the gate stays green. So each rule gets a repo that breaks it
and a test that the check says so.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-manifest-consistency.py"
_spec = importlib.util.spec_from_file_location("check_manifest_consistency", _PATH)
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)

MARKETPLACE = ".claude-plugin/marketplace.json"


def entry(name="foo", source=None, version="0.1.0", description="Does foo."):
    e = {"name": name, "description": description, "version": version}
    e["source"] = source if source is not None else "./plugins/%s" % name
    return e


def plugin(name="foo", version="0.1.0"):
    return {"name": name, "version": version}


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Keep the developer's git config (signing, hooks, default branch) out."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def make_repo(tmp_path):
    """A throwaway clone with the given catalog and plugin manifests.

    `plugins` maps a directory under plugins/ to its plugin.json, or to None
    for a directory with no plugin.json in it.
    """

    def build(entries, plugins=None):
        root = tmp_path / "repo"
        root.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        if entries is not None:
            path = root / MARKETPLACE
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"name": "m", "plugins": entries}))
        for d, manifest in (plugins or {}).items():
            pdir = root / "plugins" / d
            pdir.mkdir(parents=True, exist_ok=True)
            if manifest is not None:
                (pdir / ".claude-plugin").mkdir()
                (pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest))
        return root

    return build


@pytest.fixture
def run(capsys):
    """Drive a command through main() so argparse defaults are the real ones."""

    def go(*argv):
        capsys.readouterr()
        code = cm.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


class DescribeImport:
    def it_does_no_work_when_imported(self, capsys):
        spec = importlib.util.spec_from_file_location("again", _PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert not hasattr(mod, "errors")
        assert not hasattr(mod, "checked")


class DescribeCheck:
    def it_passes_a_repo_whose_manifests_agree(self, make_repo, run):
        root = make_repo([entry()], {"foo": plugin()})
        code, out, err = run("check", "-C", str(root))
        assert code == cm.OK
        assert "foo: 0.1.0 (marketplace and plugin agree)" in out
        assert "All 1 plugin(s) consistent." in out
        assert err == ""

    def it_reports_version_drift_between_the_manifests(self, make_repo, run):
        root = make_repo([entry(version="0.1.0")], {"foo": plugin(version="0.2.0")})
        code, out, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "foo: version drift" in err
        assert "`0.1.0`" in err
        assert "`0.2.0`" in err
        assert "agree" not in out

    def it_rejects_a_name_that_is_not_kebab_case(self, make_repo, run):
        root = make_repo(
            [entry("Foo_Bar", source="./plugins/Foo_Bar")], {"Foo_Bar": plugin("Foo_Bar")}
        )
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "Foo_Bar: marketplace entry name is not kebab-case" in err

    def it_rejects_a_source_that_is_not_a_directory(self, make_repo, run):
        root = make_repo([entry(source="./plugins/missing")])
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "foo: source `./plugins/missing` is not a directory" in err

    def it_rejects_a_directory_named_differently_from_its_entry(self, make_repo, run):
        root = make_repo([entry(source="./plugins/bar")], {"bar": plugin("foo")})
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "foo: source directory is `bar`" in err

    def it_reports_a_plugin_directory_with_no_plugin_json(self, make_repo, run):
        root = make_repo([entry()], {"foo": None})
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "foo: no plugin.json at plugins/foo/.claude-plugin/plugin.json" in err

    def it_reports_a_plugin_directory_with_no_catalog_entry(self, make_repo, run):
        root = make_repo([entry()], {"foo": plugin(), "stray": plugin("stray")})
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "stray: has a plugin.json but no marketplace.json entry" in err

    def it_ignores_a_plugin_directory_that_has_no_plugin_json_yet(self, make_repo, run):
        root = make_repo([entry()], {"foo": plugin(), "draft": None})
        code, _, _ = run("check", "-C", str(root))
        assert code == cm.OK

    @pytest.mark.parametrize("field", cm.REQUIRED_FIELDS)
    def it_reports_an_entry_missing_a_required_field(self, make_repo, run, field):
        e = entry()
        del e[field]
        root = make_repo([e], {"foo": plugin()})
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "foo: marketplace entry is missing `%s`" % field in err

    def it_reports_an_entry_with_no_name(self, make_repo, run):
        e = entry()
        del e["name"]
        root = make_repo([e])
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "a marketplace entry has no name" in err

    def it_reports_a_plugin_json_whose_name_differs_from_its_entry(self, make_repo, run):
        root = make_repo([entry()], {"foo": plugin("other")})
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "foo: plugin.json name is `other`" in err

    def it_reports_a_catalog_that_lists_no_plugins(self, make_repo, run):
        root = make_repo([])
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "marketplace.json lists no plugins" in err

    def it_reports_a_missing_catalog(self, make_repo, run):
        root = make_repo(None)
        code, _, err = run("check", "-C", str(root))
        assert code == cm.PROBLEMS
        assert "missing .claude-plugin/marketplace.json" in err

    def it_does_not_carry_errors_from_one_run_into_the_next(self, make_repo, run):
        root = make_repo([entry(version="0.1.0")], {"foo": plugin(version="0.2.0")})
        first = json.loads(run("check", "--json", "-C", str(root))[1])
        second = json.loads(run("check", "--json", "-C", str(root))[1])
        assert len(first["errors"]) == 1
        assert second["errors"] == first["errors"]


class DescribeJson:
    def it_prints_one_envelope_and_nothing_on_stderr(self, make_repo, run):
        root = make_repo([entry()], {"foo": plugin(version="0.2.0")})
        code, out, err = run("check", "--json", "-C", str(root))
        assert code == cm.PROBLEMS
        assert err == ""
        env = json.loads(out)
        assert set(env) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert env["version"] == cm.ENVELOPE_VERSION
        assert env["command"] == "check"
        assert env["ok"] is False
        assert any("version drift" in e for e in env["errors"])
        assert env["data"] == {"plugins": []}

    def it_lists_the_consistent_plugins_in_data(self, make_repo, run):
        root = make_repo([entry()], {"foo": plugin()})
        code, out, _ = run("check", "--json", "-C", str(root))
        assert code == cm.OK
        env = json.loads(out)
        assert env["ok"] is True
        assert env["data"] == {"plugins": [{"name": "foo", "version": "0.1.0"}]}


class DescribeMain:
    def it_exits_cannot_run_for_a_directory_that_does_not_exist(self, tmp_path, run):
        code, out, err = run("check", "-C", str(tmp_path / "nope"))
        assert code == cm.CANNOT_RUN
        assert out == ""
        assert err.startswith("%s: no such directory" % cm.PROG)

    def it_exits_cannot_run_for_a_catalog_that_is_not_json(self, make_repo, run):
        root = make_repo(None)
        (root / ".claude-plugin").mkdir()
        (root / MARKETPLACE).write_text("{not json")
        code, out, err = run("check", "-C", str(root))
        assert code == cm.CANNOT_RUN
        assert out == ""
        assert err.startswith("%s: cannot read .claude-plugin/marketplace.json" % cm.PROG)

    def it_requires_a_subcommand(self, run):
        with pytest.raises(SystemExit) as exc:
            run()
        assert exc.value.code == cm.CANNOT_RUN

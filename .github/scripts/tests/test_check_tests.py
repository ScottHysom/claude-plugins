"""The two silent failures this script exists to make loud.

A test file under plugins/ ships to every user and nothing says so; a test on
pytest's default prefixes is collected by nothing and the suite stays green.
Both are absences, so the tests here assert that the check speaks up - and that
it refuses to pass when it has scanned nothing, which is how the grep it
replaced went blind.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-tests.py"
_spec = importlib.util.spec_from_file_location("check_tests", _PATH)
ct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ct)

REPO_ROOT = Path(__file__).resolve().parents[3]

PYTEST_INI = "[pytest]\ntestpaths = tests .github/scripts/tests\n"
A_TEST = "class DescribeThing:\n    def it_works(self):\n        assert True\n"
OLD_TEST = "class TestThing:\n    def test_works(self):\n        assert True\n"


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Keep the developer's git config (signing, hooks, default branch) out."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def make_repo(tmp_path):
    """A throwaway clone holding exactly the files a test names."""

    def build(files, track=True):
        root = tmp_path / "repo"
        root.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        if track:
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
        return root

    return build


@pytest.fixture
def run(capsys):
    """Drive a command through main() so argparse defaults are the real ones."""

    def go(*argv):
        capsys.readouterr()
        code = ct.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


SHIPPED = {
    "pytest.ini": PYTEST_INI,
    "plugins/foo/scripts/foo.py": "x = 1\n",
    "plugins/foo/scripts/tests/test_foo.py": A_TEST,
    "tests/.keep": "",
}

MOVED = {
    "pytest.ini": PYTEST_INI,
    "plugins/foo/scripts/foo.py": "x = 1\n",
    "tests/foo/test_foo.py": A_TEST,
    "tests/foo/conftest.py": "",
}


class DescribePlacement:
    def it_names_the_destination_for_a_suite_left_under_plugins(self, make_repo, run):
        root = make_repo(SHIPPED)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "plugins/foo/scripts/tests/test_foo.py" in err
        assert "tests/foo/test_foo.py" in err

    def it_says_a_shipped_test_reaches_every_user(self, make_repo, run):
        root = make_repo(SHIPPED)
        _, _, err = run("placement", "-C", str(root))
        assert "copied into every install" in err

    def it_rejects_a_support_module_that_is_not_a_test_file(self, make_repo, run):
        files = dict(SHIPPED)
        files["plugins/foo/scripts/tests/foo_samples.py"] = "SAMPLE = 'x'\n"
        root = make_repo(files)
        _, _, err = run("placement", "-C", str(root))
        assert "plugins/foo/scripts/tests/foo_samples.py" in err

    def it_rejects_a_plugin_script_that_imports_a_contributor_dependency(self, make_repo, run):
        files = dict(MOVED)
        files["plugins/foo/scripts/helper.py"] = "import pytest\n"
        root = make_repo(files)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "plugins/foo/scripts/helper.py" in err

    def it_sees_a_stray_that_is_not_yet_tracked(self, make_repo, run):
        root = make_repo(MOVED)
        (root / "plugins/foo/scripts/tests").mkdir(parents=True)
        (root / "plugins/foo/scripts/tests/test_stray.py").write_text(A_TEST)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "test_stray.py" in err

    def it_ignores_what_git_ignores(self, make_repo, run):
        files = dict(MOVED)
        files[".gitignore"] = "__pycache__/\n"
        root = make_repo(files)
        (root / "plugins/foo/scripts/__pycache__").mkdir(parents=True)
        (root / "plugins/foo/scripts/__pycache__/test_cached.py").write_text(A_TEST)
        code, _, _ = run("placement", "-C", str(root))
        assert code == ct.OK

    def it_rejects_a_test_file_no_root_collects(self, make_repo, run):
        files = dict(MOVED)
        files["scripts/test_loose.py"] = A_TEST
        root = make_repo(files)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "scripts/test_loose.py" in err
        assert "nothing runs it" in err

    def it_accepts_a_tree_whose_tests_sit_outside_plugins(self, make_repo, run):
        root = make_repo(MOVED)
        code, out, _ = run("placement", "-C", str(root))
        assert code == ct.OK
        assert "No test file under plugins/" in out

    def it_warns_when_a_plugin_script_has_no_suite(self, make_repo, run):
        files = {k: v for k, v in MOVED.items() if not k.startswith("tests/")}
        files["tests/.keep"] = ""
        root = make_repo(files)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.OK
        assert "has a script but no suite" in err


class DescribeNaming:
    def it_names_the_file_and_line_of_an_old_style_test(self, make_repo, run):
        files = dict(MOVED)
        files["tests/foo/test_foo.py"] = OLD_TEST
        root = make_repo(files)
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "tests/foo/test_foo.py:1" in err

    def it_finds_an_indented_method(self, make_repo, run):
        files = dict(MOVED)
        files["tests/foo/test_foo.py"] = (
            "class DescribeThing:\n    def test_works(self):\n        pass\n"
        )
        root = make_repo(files)
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "tests/foo/test_foo.py:2" in err

    def it_accepts_names_pytest_collects(self, make_repo, run):
        root = make_repo(MOVED)
        code, out, _ = run("naming", "-C", str(root))
        assert code == ct.OK
        assert "on the names pytest collects" in out

    def it_fails_when_no_test_file_matches_at_all(self, make_repo, run):
        root = make_repo({"pytest.ini": PYTEST_INI, "README.md": "nothing here\n"})
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "scanning nothing" in err

    def it_fails_when_a_configured_root_contributes_nothing(self, make_repo, run):
        files = dict(MOVED)
        files[".github/scripts/tests/.keep"] = ""
        root = make_repo(files)
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "gone blind there" in err

    def it_ignores_a_root_that_does_not_exist(self, make_repo, run):
        root = make_repo(MOVED)
        code, _, _ = run("naming", "-C", str(root))
        assert code == ct.OK

    def it_accepts_the_repo_as_it_stands(self, run):
        code, _, _ = run("naming", "-C", str(REPO_ROOT))
        assert code == ct.OK


class DescribeMain:
    @pytest.mark.parametrize("command", ["placement", "naming"])
    def it_prints_the_same_envelope_for_every_command(self, make_repo, run, command):
        root = make_repo(MOVED)
        code, out, _ = run(command, "-C", str(root), "--json")
        assert code == ct.OK
        body = json.loads(out)
        assert set(body) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert body["command"] == command
        assert body["ok"] is True

    def it_reports_problems_in_the_envelope_rather_than_on_stderr(self, make_repo, run):
        root = make_repo(SHIPPED)
        code, out, err = run("placement", "-C", str(root), "--json")
        assert code == ct.PROBLEMS
        body = json.loads(out)
        assert body["ok"] is False
        assert body["errors"]
        assert err == ""

    def it_cannot_run_outside_a_clone(self, tmp_path, run):
        code, _, err = run("placement", "-C", str(tmp_path))
        assert code == ct.CANNOT_RUN
        assert err.startswith(ct.PROG + ":")

    def it_cannot_run_without_a_pytest_ini(self, make_repo, run):
        root = make_repo({"README.md": "no config\n"})
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.CANNOT_RUN
        assert ct.PYTEST_INI in err

    def it_cannot_run_when_pytest_ini_names_no_roots(self, make_repo, run):
        root = make_repo({"pytest.ini": "[pytest]\naddopts = -ra\n"})
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.CANNOT_RUN
        assert ct.TESTPATHS in err

    def it_rejects_an_unknown_command(self, run):
        with pytest.raises(SystemExit) as exc:
            run("nonsense")
        assert exc.value.code == ct.CANNOT_RUN

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
def make_repo(tmp_path, git_init):
    """A throwaway clone holding exactly the files a test names."""

    def build(files, track=True):
        root = tmp_path / "repo"
        if not root.exists():
            git_init(root)
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
    @pytest.mark.spec("placement-cmd-names-test-destination")
    def it_names_the_destination_for_a_suite_left_under_plugins(self, make_repo, run):
        root = make_repo(SHIPPED)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "plugins/foo/scripts/tests/test_foo.py" in err
        assert "tests/foo/test_foo.py" in err

    @pytest.mark.spec("placement-cmd-names-test-destination")
    def it_says_a_shipped_test_reaches_every_user(self, make_repo, run):
        root = make_repo(SHIPPED)
        _, _, err = run("placement", "-C", str(root))
        assert "copied into every install" in err

    @pytest.mark.spec("placement-cmd-names-test-destination")
    def it_rejects_a_support_module_that_is_not_a_test_file(self, make_repo, run):
        files = dict(SHIPPED)
        files["plugins/foo/scripts/tests/foo_samples.py"] = "SAMPLE = 'x'\n"
        root = make_repo(files)
        _, _, err = run("placement", "-C", str(root))
        assert "plugins/foo/scripts/tests/foo_samples.py" in err

    @pytest.mark.spec("placement-cmd-names-test-destination")
    def it_rejects_a_plugin_script_that_imports_a_contributor_dependency(self, make_repo, run):
        files = dict(MOVED)
        files["plugins/foo/scripts/helper.py"] = "import pytest\n"
        root = make_repo(files)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "plugins/foo/scripts/helper.py" in err

    @pytest.mark.spec("placement-cmd-names-test-destination")
    def it_rejects_a_conftest_left_under_plugins(self, make_repo, run):
        files = dict(MOVED)
        files["plugins/foo/conftest.py"] = ""
        root = make_repo(files)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "plugins/foo/conftest.py" in err
        assert "tests/foo/conftest.py" in err

    @pytest.mark.spec("placement-cmd-names-test-destination")
    def it_passes_the_files_a_plugin_ships(self, make_repo, run):
        files = dict(MOVED)
        files["plugins/foo/skills/foo/SKILL.md"] = "---\nname: foo\n---\n"
        files["plugins/foo/.claude-plugin/plugin.json"] = "{}\n"
        root = make_repo(files)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.OK
        assert err == ""

    @pytest.mark.spec("placement-cmd-reads-git")
    def it_sees_a_stray_that_is_not_yet_tracked(self, make_repo, run):
        root = make_repo(MOVED)
        (root / "plugins/foo/scripts/tests").mkdir(parents=True)
        (root / "plugins/foo/scripts/tests/test_stray.py").write_text(A_TEST)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "test_stray.py" in err

    @pytest.mark.spec("placement-cmd-reads-git")
    def it_ignores_what_git_ignores(self, make_repo, run):
        files = dict(MOVED)
        files[".gitignore"] = "__pycache__/\n"
        root = make_repo(files)
        (root / "plugins/foo/scripts/__pycache__").mkdir(parents=True)
        (root / "plugins/foo/scripts/__pycache__/test_cached.py").write_text(A_TEST)
        code, _, _ = run("placement", "-C", str(root))
        assert code == ct.OK

    @pytest.mark.spec("placement-cmd-fails-tests-outside-roots")
    def it_rejects_a_test_file_no_root_collects(self, make_repo, run):
        files = dict(MOVED)
        files["scripts/test_loose.py"] = A_TEST
        root = make_repo(files)
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "scripts/test_loose.py" in err
        assert "nothing runs it" in err

    @pytest.mark.spec("placement-cmd-names-test-destination")
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
    @pytest.mark.spec("naming-cmd-fails-old-test-names")
    def it_names_the_file_and_line_of_an_old_style_test(self, make_repo, run):
        files = dict(MOVED)
        files["tests/foo/test_foo.py"] = OLD_TEST
        root = make_repo(files)
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "tests/foo/test_foo.py:1" in err

    @pytest.mark.spec("naming-cmd-fails-old-test-names")
    def it_finds_an_indented_method(self, make_repo, run):
        files = dict(MOVED)
        files["tests/foo/test_foo.py"] = (
            "class DescribeThing:\n    def test_works(self):\n        pass\n"
        )
        root = make_repo(files)
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "tests/foo/test_foo.py:2" in err

    @pytest.mark.spec("naming-cmd-fails-old-test-names")
    def it_accepts_names_pytest_collects(self, make_repo, run):
        root = make_repo(MOVED)
        code, out, _ = run("naming", "-C", str(root))
        assert code == ct.OK
        assert "on the names pytest collects" in out

    @pytest.mark.spec("naming-cmd-scans-something")
    def it_fails_when_no_test_file_matches_at_all(self, make_repo, run):
        root = make_repo({"pytest.ini": PYTEST_INI, "README.md": "nothing here\n"})
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "scanning nothing" in err

    @pytest.mark.spec("naming-cmd-scans-something")
    def it_fails_when_a_configured_root_contributes_nothing(self, make_repo, run):
        files = dict(MOVED)
        files[".github/scripts/tests/.keep"] = ""
        root = make_repo(files)
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.PROBLEMS
        assert "gone blind there" in err

    @pytest.mark.spec("naming-cmd-scans-something")
    def it_ignores_a_root_that_does_not_exist(self, make_repo, run):
        root = make_repo(MOVED)
        code, _, _ = run("naming", "-C", str(root))
        assert code == ct.OK

    @pytest.mark.spec("naming-cmd-fails-old-test-names")
    def it_accepts_the_repo_as_it_stands(self, run):
        code, _, _ = run("naming", "-C", str(REPO_ROOT))
        assert code == ct.OK


class DescribeMain:
    @pytest.mark.parametrize("command", ["placement", "naming"])
    @pytest.mark.spec("command-prints-json-envelope")
    def it_prints_the_same_envelope_for_every_command(self, make_repo, run, command):
        root = make_repo(MOVED)
        code, out, _ = run(command, "-C", str(root), "--json")
        assert code == ct.OK
        body = json.loads(out)
        assert set(body) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert body["command"] == command
        assert body["ok"] is True

    @pytest.mark.spec("command-prints-json-envelope")
    def it_reports_problems_in_the_envelope_rather_than_on_stderr(self, make_repo, run):
        root = make_repo(SHIPPED)
        code, out, err = run("placement", "-C", str(root), "--json")
        assert code == ct.PROBLEMS
        body = json.loads(out)
        assert body["ok"] is False
        assert body["errors"]
        assert err == ""

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_outside_a_clone(self, tmp_path, run):
        code, _, err = run("placement", "-C", str(tmp_path))
        assert code == ct.CANNOT_RUN
        assert err.startswith(ct.PROG + ":")

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_without_a_pytest_ini(self, make_repo, run):
        root = make_repo({"README.md": "no config\n"})
        code, _, err = run("naming", "-C", str(root))
        assert code == ct.CANNOT_RUN
        assert ct.PYTEST_INI in err

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_when_pytest_ini_names_no_roots(self, make_repo, run):
        root = make_repo({"pytest.ini": "[pytest]\naddopts = -ra\n"})
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.CANNOT_RUN
        assert ct.TESTPATHS in err

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_when_testpaths_is_empty(self, make_repo, run):
        root = make_repo({"pytest.ini": "[pytest]\ntestpaths =\n"})
        code, _, err = run("placement", "-C", str(root))
        assert code == ct.CANNOT_RUN
        assert "sets %s to nothing" % ct.TESTPATHS in err

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_on_a_directory_that_does_not_exist(self, tmp_path, run):
        code, out, err = run("placement", "-C", str(tmp_path / "nope"))
        assert code == ct.CANNOT_RUN
        assert out == ""
        assert err.startswith("%s: no such directory" % ct.PROG)

    @pytest.mark.spec("script-ignores-closed-pipe")
    def it_exits_ok_when_its_reader_closes_the_pipe(self, make_repo, capsys, closed_pipe):
        root = make_repo(MOVED)
        closed_pipe()
        assert ct.main(["placement", "-C", str(root)]) == ct.OK
        assert capsys.readouterr().err == ""

    @pytest.mark.spec("script-ignores-closed-pipe")
    @pytest.mark.parametrize(
        "command", [["placement"], ["naming"], ["--help"], ["naming", "--help"]]
    )
    def it_exits_ok_without_a_traceback_when_its_reader_has_gone(
        self, make_repo, closed_pipe_child, command
    ):
        root = make_repo(MOVED)
        assert closed_pipe_child(_PATH, *command, "-C", str(root)) == (ct.OK, "")

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_rejects_an_unknown_command(self, run):
        with pytest.raises(SystemExit) as exc:
            run("nonsense")
        assert exc.value.code == ct.CANNOT_RUN


# A clone whose main branch holds `add`, and a test of it, for a branch to add
# tests to. The conftest puts the clone's root on sys.path, so a test imports
# thing.py the way the repo's suites import their scripts.
BASE_PYTEST_INI = (
    "[pytest]\n"
    "testpaths = tests\n"
    "python_functions = it_*\n"
    "python_classes = Describe*\n"
    "markers =\n"
    "    passes_on_base(reason): a new test that passes on the base, and why\n"
)
BASE = {
    "pytest.ini": BASE_PYTEST_INI,
    "thing.py": "def add(a, b):\n    return a + b\n",
    "tests/conftest.py": (
        "import pathlib, sys\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n"
    ),
    "tests/test_add.py": (
        "import thing\n\n\nclass DescribeAdd:\n"
        "    def it_adds(self):\n        assert thing.add(1, 2) == 3\n"
    ),
}
WITH_MUL = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
PASSES_ON_BASE = (
    "import pytest\nimport thing\n\n\nclass DescribeMore:\n"
    "    def it_adds_zero(self):\n        assert thing.add(1, 0) == 1\n"
)
FAILS_ON_BASE = (
    "import thing\n\n\nclass DescribeMul:\n"
    "    def it_multiplies(self):\n        assert thing.mul(2, 3) == 6\n"
)
IMPORTS_NEW_NAME = (
    "from thing import mul\n\n\nclass DescribeMul:\n"
    "    def it_multiplies(self):\n        assert mul(2, 3) == 6\n"
)
NEW_ID = "tests/test_more.py::DescribeMore::it_adds_zero"


def git(root, *argv):
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *argv],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def branch(make_repo):
    """A clone on a branch off main: main holds BASE, the branch `changes`."""

    def build(changes):
        root = make_repo(BASE)
        git(root, "checkout", "-q", "-b", "main")
        git(root, "commit", "-q", "-m", "base")
        git(root, "checkout", "-q", "-b", "work")
        make_repo(changes)
        git(root, "commit", "-q", "-m", "work")
        return root

    return build


class DescribeFailsOnBase:
    @pytest.mark.spec("failsonbase-cmd-fails-passing-new-test")
    def it_fails_a_new_test_that_passes_on_the_base(self, branch, run):
        root = branch({"tests/test_more.py": PASSES_ON_BASE})
        code, _, err = run("fails-on-base", "-C", str(root), "--base", "main")
        assert code == ct.PROBLEMS
        assert NEW_ID in err
        assert "passes_on_base" in err

    @pytest.mark.spec("failsonbase-cmd-fails-passing-new-test")
    def it_passes_a_new_test_that_fails_on_the_base(self, branch, run):
        root = branch({"thing.py": WITH_MUL, "tests/test_mul.py": FAILS_ON_BASE})
        code, _, err = run("fails-on-base", "-C", str(root), "--base", "main")
        assert (code, err) == (ct.OK, "")

    @pytest.mark.spec("failsonbase-cmd-fails-passing-new-test")
    def it_counts_a_new_test_that_cannot_import_on_the_base_as_failing(self, branch, run):
        root = branch({"thing.py": WITH_MUL, "tests/test_mul.py": IMPORTS_NEW_NAME})
        code, out, _ = run("fails-on-base", "-C", str(root), "--base", "main", "--json")
        assert code == ct.OK
        assert json.loads(out)["data"]["new"] == ["tests/test_mul.py::DescribeMul::it_multiplies"]

    @pytest.mark.spec("failsonbase-cmd-fails-passing-new-test")
    def it_counts_a_new_suite_whose_conftest_cannot_load_on_the_base_as_failing(self, branch, run):
        root = branch(
            {
                "thing.py": WITH_MUL,
                "tests/mul/conftest.py": "import thing\n\nMUL = thing.mul\n",
                "tests/mul/test_mul.py": FAILS_ON_BASE,
                "tests/test_more.py": PASSES_ON_BASE,
            }
        )
        code, out, _ = run("fails-on-base", "-C", str(root), "--base", "main", "--json")
        assert code == ct.PROBLEMS
        outcomes = json.loads(out)["data"]["outcomes"]
        assert outcomes == {
            "tests/mul/test_mul.py::DescribeMul::it_multiplies": "error",
            NEW_ID: "passed",
        }

    @pytest.mark.spec("failsonbase-cmd-fails-passing-new-test")
    def it_counts_a_test_skipped_on_the_base_as_not_passing(self, branch, run):
        skipped = PASSES_ON_BASE.replace(
            "    def it_adds_zero",
            "    @pytest.mark.skipif(not hasattr(thing, 'mul'), reason='no mul')\n"
            "    def it_adds_zero",
        )
        root = branch({"thing.py": WITH_MUL, "tests/test_more.py": skipped})
        assert run("fails-on-base", "-C", str(root), "--base", "main")[0] == ct.OK

    @pytest.mark.spec("failsonbase-cmd-runs-only-new-tests")
    def it_runs_only_the_tests_the_branch_adds(self, branch, run):
        # The new test sits in the file beside one the base already has.
        beside = BASE["tests/test_add.py"] + FAILS_ON_BASE.replace("import thing\n", "")
        root = branch({"thing.py": WITH_MUL, "tests/test_add.py": beside})
        _, out, _ = run("fails-on-base", "-C", str(root), "--base", "main", "--json")
        data = json.loads(out)["data"]
        assert data["new"] == ["tests/test_add.py::DescribeMul::it_multiplies"]
        assert data["ran"] == data["new"]

    @pytest.mark.spec("failsonbase-cmd-runs-only-new-tests")
    def it_passes_a_branch_that_adds_no_test(self, branch, run):
        root = branch({"thing.py": WITH_MUL})
        code, out, _ = run("fails-on-base", "-C", str(root), "--base", "main", "--json")
        assert code == ct.OK
        assert json.loads(out)["data"]["new"] == []

    @pytest.mark.spec("failsonbase-cmd-excuses-marked-test")
    def it_excuses_a_marked_test_and_warns_with_its_reason(self, branch, run):
        marked = PASSES_ON_BASE.replace(
            "    def it_adds_zero",
            "    @pytest.mark.passes_on_base('pins add before a refactor')\n    def it_adds_zero",
        )
        root = branch({"tests/test_more.py": marked})
        code, _, err = run("fails-on-base", "-C", str(root), "--base", "main")
        assert code == ct.OK
        assert NEW_ID in err
        assert "pins add before a refactor" in err

    @pytest.mark.spec("failsonbase-cmd-excuses-marked-test")
    def it_excuses_every_test_in_a_marked_module(self, branch, run):
        marked = PASSES_ON_BASE.replace(
            "import thing\n",
            "import thing\n\npytestmark = pytest.mark.passes_on_base('moved from test_add.py')\n",
        )
        root = branch({"tests/test_more.py": marked})
        code, _, err = run("fails-on-base", "-C", str(root), "--base", "main")
        assert code == ct.OK
        assert "moved from test_add.py" in err

    @pytest.mark.spec("failsonbase-cmd-excuses-marked-test")
    @pytest.mark.parametrize("args", ["", "''", "'  '"])
    def it_fails_a_marker_that_gives_no_reason(self, branch, run, args):
        marked = PASSES_ON_BASE.replace(
            "    def it_adds_zero",
            "    @pytest.mark.passes_on_base(%s)\n    def it_adds_zero" % args,
        )
        root = branch({"tests/test_more.py": marked})
        code, _, err = run("fails-on-base", "-C", str(root), "--base", "main")
        assert code == ct.PROBLEMS
        assert NEW_ID in err
        assert "reason" in err

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_against_a_base_that_does_not_exist(self, branch, run):
        root = branch({"tests/test_more.py": PASSES_ON_BASE})
        code, _, err = run("fails-on-base", "-C", str(root), "--base", "nope")
        assert code == ct.CANNOT_RUN
        assert err.startswith("%s: " % ct.PROG)
        assert "nope" in err

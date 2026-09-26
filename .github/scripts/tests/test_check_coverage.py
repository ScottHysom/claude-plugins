"""What check-coverage.py promises about a plugin script's coverage.

The coverage report here is written by hand rather than measured, so each test
states exactly which lines ran. The clone is a throwaway git repo, since the
floors' history and the added lines both come from git.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-coverage.py"
_spec = importlib.util.spec_from_file_location("check_coverage", _PATH)
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

SCRIPT = "plugins/foo/scripts/foo.py"
OTHER = "plugins/bar/scripts/bar.py"
SOURCE = "def f(x):\n    if x:\n        return 1\n    return 2\n"


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Keep the developer's git config (signing, hooks, default branch) out."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def git(root, *argv):
    subprocess.run(["git", "-C", str(root), *argv], check=True, capture_output=True)


def write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def commit(root, message="c"):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)


def floors(values):
    return json.dumps(values)


def report(files, branch=True):
    """A coverage.py JSON report: {path: (percent, missing_lines)}."""
    return json.dumps(
        {
            "meta": {"branch_coverage": branch},
            "files": {
                path: {"summary": {"percent_covered": pct}, "missing_lines": missing}
                for path, (pct, missing) in files.items()
            },
        }
    )


@pytest.fixture
def repo(tmp_path):
    """A clone with one plugin script committed on `main`, at a floor of 80."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write(
        root,
        {
            SCRIPT: SOURCE,
            cc.FLOORS_FILE: floors({SCRIPT: 80.0}),
            cc.DEFAULT_REPORT: report({SCRIPT: (80.0, [])}),
        },
    )
    commit(root)
    return root


@pytest.fixture
def run(capsys):
    """Drive a command through main() so argparse defaults are the real ones."""

    def go(*argv):
        capsys.readouterr()
        code = cc.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


class DescribeFloors:
    def it_passes_a_script_at_its_floor(self, repo, run):
        code, out, err = run("floors", "-C", str(repo))
        assert code == cc.OK
        assert SCRIPT in out
        assert err == ""

    def it_fails_a_script_below_its_floor(self, repo, run):
        write(repo, {cc.DEFAULT_REPORT: report({SCRIPT: (79.99, [3])})})
        code, out, err = run("floors", "-C", str(repo))
        assert code == cc.PROBLEMS
        assert "below its floor of 80.00%" in err
        assert out == ""

    def it_warns_with_the_figure_to_raise_a_floor_to(self, repo, run):
        write(repo, {cc.DEFAULT_REPORT: report({SCRIPT: (91.2345, [])})})
        code, _, err = run("floors", "-C", str(repo))
        assert code == cc.OK
        assert "warning:" in err
        assert "Raise the floor in %s to 91.23" % cc.FLOORS_FILE in err

    def it_fails_a_script_with_no_floor(self, repo, run):
        write(
            repo,
            {OTHER: SOURCE, cc.DEFAULT_REPORT: report({SCRIPT: (80.0, []), OTHER: (50.0, [])})},
        )
        code, _, err = run("floors", "-C", str(repo))
        assert code == cc.PROBLEMS
        assert "%s has no floor" % OTHER in err
        assert "at 50.00" in err

    def it_fails_a_script_the_report_left_out(self, repo, run):
        write(repo, {OTHER: SOURCE, cc.FLOORS_FILE: floors({SCRIPT: 80.0, OTHER: 1.0})})
        code, _, err = run("floors", "-C", str(repo))
        assert code == cc.PROBLEMS
        assert "%s is not in the coverage report" % OTHER in err

    def it_fails_a_floor_for_a_script_that_is_gone(self, repo, run):
        write(repo, {cc.FLOORS_FILE: floors({SCRIPT: 80.0, OTHER: 70.0})})
        code, _, err = run("floors", "-C", str(repo))
        assert code == cc.PROBLEMS
        assert "%s has a floor" % OTHER in err

    def it_fails_a_floor_lowered_since_the_base(self, repo, run):
        git(repo, "checkout", "-q", "-b", "work")
        write(repo, {cc.FLOORS_FILE: floors({SCRIPT: 75.0})})
        code, out, err = run("floors", "-C", str(repo), "--base", "main", "--json")
        assert code == cc.PROBLEMS
        assert json.loads(out)["data"]["lowered"] == [SCRIPT]

    def it_allows_a_floor_raised_since_the_base(self, repo, run):
        git(repo, "checkout", "-q", "-b", "work")
        write(
            repo,
            {cc.FLOORS_FILE: floors({SCRIPT: 85.0}), cc.DEFAULT_REPORT: report({SCRIPT: (85, [])})},
        )
        code, _, _ = run("floors", "-C", str(repo), "--base", "main")
        assert code == cc.OK

    def it_refuses_a_report_measured_without_branches(self, repo, run):
        write(repo, {cc.DEFAULT_REPORT: report({SCRIPT: (80.0, [])}, branch=False)})
        code, _, err = run("floors", "-C", str(repo))
        assert code == cc.CANNOT_RUN
        assert "without branch coverage" in err

    def it_says_how_to_make_a_missing_report(self, repo, run):
        (repo / cc.DEFAULT_REPORT).unlink()
        code, _, err = run("floors", "-C", str(repo))
        assert code == cc.CANNOT_RUN
        assert "pytest --cov" in err

    def it_says_how_to_fetch_a_base_that_is_missing(self, repo, run):
        code, _, err = run("floors", "-C", str(repo), "--base", "origin/nope")
        assert code == cc.CANNOT_RUN
        assert "git fetch" in err


class DescribeDiff:
    def it_passes_an_added_line_a_test_runs(self, repo, run):
        git(repo, "checkout", "-q", "-b", "work")
        write(repo, {SCRIPT: SOURCE + "X = 1\n", cc.DEFAULT_REPORT: report({SCRIPT: (80, [])})})
        code, out, _ = run("diff", "-C", str(repo), "--base", "main")
        assert code == cc.OK
        assert "1 added lines" in out

    def it_names_an_added_line_no_test_runs(self, repo, run):
        git(repo, "checkout", "-q", "-b", "work")
        write(repo, {SCRIPT: SOURCE + "X = 1\n", cc.DEFAULT_REPORT: report({SCRIPT: (80, [5])})})
        code, _, err = run("diff", "-C", str(repo), "--base", "main")
        assert code == cc.PROBLEMS
        assert "%s:5: no test runs this new line: `X = 1`" % SCRIPT in err

    def it_ignores_an_unrun_line_the_branch_did_not_add(self, repo, run):
        git(repo, "checkout", "-q", "-b", "work")
        write(repo, {SCRIPT: SOURCE + "X = 1\n", cc.DEFAULT_REPORT: report({SCRIPT: (80, [3])})})
        code, _, _ = run("diff", "-C", str(repo), "--base", "main")
        assert code == cc.OK

    def it_ignores_a_line_only_the_base_changed_since_the_branch_left(self, repo, run):
        git(repo, "checkout", "-q", "-b", "work")
        write(repo, {SCRIPT: SOURCE + "X = 1\n"})
        commit(repo)
        git(repo, "checkout", "-q", "main")
        write(repo, {SCRIPT: SOURCE.replace("if x:", "if x is not None:")})
        commit(repo)
        git(repo, "checkout", "-q", "work")
        write(repo, {cc.DEFAULT_REPORT: report({SCRIPT: (80, [2])})})
        code, _, _ = run("diff", "-C", str(repo), "--base", "main")
        assert code == cc.OK

    def it_treats_every_line_of_a_new_script_as_added(self, repo, run):
        git(repo, "checkout", "-q", "-b", "work")
        write(
            repo,
            {OTHER: SOURCE, cc.DEFAULT_REPORT: report({SCRIPT: (80, []), OTHER: (50, [3])})},
        )
        code, _, err = run("diff", "-C", str(repo), "--base", "main")
        assert code == cc.PROBLEMS
        assert "%s:3:" % OTHER in err

    def it_fails_added_lines_in_a_script_the_report_left_out(self, repo, run):
        git(repo, "checkout", "-q", "-b", "work")
        write(repo, {OTHER: SOURCE})
        code, _, err = run("diff", "-C", str(repo), "--base", "main")
        assert code == cc.PROBLEMS
        assert "%s adds 4 lines and is not in the coverage report" % OTHER in err


class DescribePragmas:
    def it_passes_a_pragma_that_gives_its_reason(self, repo, run):
        write(repo, {SCRIPT: "x = 1  # pragma: no cover - only on Windows\n"})
        code, out, _ = run("pragmas", "-C", str(repo))
        assert code == cc.OK
        assert "1 pragmas" in out

    def it_fails_a_pragma_with_no_reason(self, repo, run):
        write(repo, {SCRIPT: "x = 1\ny = 2  # pragma: no cover\n"})
        code, _, err = run("pragmas", "-C", str(repo))
        assert code == cc.PROBLEMS
        assert "%s:2:" % SCRIPT in err

    def it_sees_the_spellings_coverage_itself_accepts(self, repo, run):
        write(repo, {SCRIPT: "x = 1  #pragma no cover\n"})
        code, _, _ = run("pragmas", "-C", str(repo))
        assert code == cc.PROBLEMS


class DescribeScanningNothing:
    @pytest.mark.parametrize("command", ["floors", "diff", "pragmas"])
    def it_refuses_to_pass_a_clone_with_no_plugin_script(self, tmp_path, run, command):
        root = tmp_path / "empty"
        root.mkdir()
        git(root, "init", "-q")
        argv = [command, "-C", str(root)] + (["--base", "HEAD"] if command == "diff" else [])
        code, _, err = run(*argv)
        assert code == cc.CANNOT_RUN
        assert "scans nothing" in err

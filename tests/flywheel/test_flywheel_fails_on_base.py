"""What `flywheel.py fails-on-base` finds when a branch adds tests.

The projects here run a test runner of their own, runner.py, so the check is
driven only through the commands in .flywheel/gates.json, as it is in a
project of any language. A test in a `.t` file names a file and a text, and
passes when the file holds the text. Its list ends with a blank line and a
count, as pytest's does. A file the test names that is missing
makes its run stop with a traceback, as a test that errors does.
"""

import json
import shlex
import subprocess
import sys

import pytest

import flywheel

GATES = ".flywheel/gates.json"
EXCUSES = ".flywheel/passes-on-base.json"
PYTHON = shlex.quote(sys.executable)

RUNNER = """\
import pathlib
import sys


def tests():
    for path in sorted(pathlib.Path("tests").glob("*.t")):
        for line in path.read_text().splitlines():
            name, _, rest = line.partition(":")
            target, text = rest.split(None, 1)
            yield "%s::%s" % (path.as_posix(), name.strip()), target, text


if sys.argv[1] == "list":
    ids = [test_id for test_id, _, _ in tests()]
    for test_id in ids:
        print(test_id)
    # A summary that differs between the branch and the base, as pytest's does.
    print()
    print("%d listed" % len(ids))
elif pathlib.Path("tests/pass-all").exists():
    # Stands in for a conftest.py that changes how every test runs.
    sys.exit(0)
else:
    for test_id, target, text in tests():
        if test_id == sys.argv[2]:
            sys.exit(0 if text in pathlib.Path(target).read_text() else 1)
    sys.exit(4)
"""

TESTS = {
    "list": "%s runner.py list" % PYTHON,
    "run": "%s runner.py run {id}" % PYTHON,
    "paths": ["tests"],
}


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def commit(root, message):
    git(root, "add", "-A")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "--quiet",
        "-m",
        message,
    )


def base_project(root):
    """main holds app.txt saying "old", the runner and one test of it."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    (root / "runner.py").write_text(RUNNER)
    (root / "app.txt").write_text("old\n")
    (root / "tests").mkdir()
    (root / "tests" / "a.t").write_text("keeps: app.txt old\n")
    commit(root, "base")
    git(root, "switch", "--quiet", "-c", "work")


@pytest.fixture
def work(project, repo_copy, tmp_path):
    """A project on branch `work`, off main, with the test commands in its gates file."""
    project.root = repo_copy(base_project, tmp_path / "work")
    project.write(GATES, json.dumps({"gates": {}, "tests": TESTS}))
    return project


def add_tests(project, name, *lines):
    project.write("tests/%s" % name, "".join(line + "\n" for line in lines))


def change_app(project, text):
    project.write("app.txt", text + "\n")


def gates(project, **tests):
    project.write(GATES, json.dumps({"gates": {}, "tests": dict(TESTS, **tests)}))


@pytest.mark.spec("failsonbase-cmd-fails-test-passing-on-base")
class DescribeANewTest:
    def it_fails_one_that_passes_on_the_base(self, work):
        add_tests(work, "b.t", "still: app.txt old")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.PROBLEMS
        assert env["data"]["outcomes"] == {"tests/b.t::still": "passed"}
        assert "tests/b.t::still passes against the code at the merge base" in env["errors"][0]
        assert EXCUSES in env["errors"][0]

    def it_passes_one_that_fails_on_the_base(self, work):
        change_app(work, "new")
        add_tests(work, "b.t", "changed: app.txt new")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.OK
        assert env["data"]["outcomes"] == {"tests/b.t::changed": "failed"}

    def it_counts_a_run_that_errors_on_the_base_as_failing(self, work):
        work.write("added.txt", "here\n")
        add_tests(work, "b.t", "reads: added.txt here")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.OK
        assert env["data"]["outcomes"] == {"tests/b.t::reads": "failed"}

    def it_runs_only_the_tests_the_branch_adds(self, work):
        change_app(work, "old new")
        add_tests(work, "b.t", "changed: app.txt new")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.OK
        assert env["data"]["new"] == ["tests/b.t::changed"]

    def it_passes_a_branch_that_adds_no_test(self, work):
        change_app(work, "old new")
        code, out, _ = work.human("fails-on-base", "--base", "main")
        assert code == flywheel.OK
        assert "0 new test(s)" in out

    def it_prints_nothing_on_stdout_for_a_failing_test(self, work):
        add_tests(work, "b.t", "still: app.txt old")
        code, out, err = work.human("fails-on-base", "--base", "main")
        assert code == flywheel.PROBLEMS
        assert out == ""
        assert "tests/b.t::still passes against the code at the merge base" in err

    def it_names_the_base_in_text(self, work):
        change_app(work, "new")
        add_tests(work, "b.t", "changed: app.txt new")
        code, out, _ = work.human("fails-on-base", "--base", "main")
        assert code == flywheel.OK
        assert "1 new test(s) against the merge base" in out


@pytest.mark.spec("failsonbase-cmd-reads-gates-test-commands")
class DescribeTheTestCommands:
    def it_copies_the_test_paths_from_the_branch_over_the_base(self, work):
        add_tests(work, "a.t", "keeps: app.txt old", "again: app.txt old")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.PROBLEMS
        assert env["data"]["outcomes"] == {"tests/a.t::again": "passed"}

    def it_drops_a_file_the_branch_deletes_from_the_test_paths(self, work):
        git(work.root, "switch", "--quiet", "main")
        work.write("tests/pass-all", "")
        commit(work.root, "pass everything")
        git(work.root, "switch", "--quiet", "-c", "drop")
        (work.root / "tests" / "pass-all").unlink()
        change_app(work, "new")
        add_tests(work, "b.t", "changed: app.txt new")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.OK
        assert env["data"]["outcomes"] == {"tests/b.t::changed": "failed"}

    def it_copies_a_file_named_in_the_paths_over_the_base(self, work):
        gates(work, paths=["tests", "app.txt"])
        change_app(work, "new")
        add_tests(work, "b.t", "changed: app.txt new")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.PROBLEMS
        assert env["data"]["outcomes"] == {"tests/b.t::changed": "passed"}

    def it_runs_the_list_command_it_is_given(self, work):
        gates(work, list="%s runner.py list && echo tests/z.t::extra" % PYTHON)
        add_tests(work, "b.t", "still: app.txt old")
        code, env = work.run("fails-on-base", "--base", "main")
        assert env["data"]["new"] == ["tests/b.t::still"]

    def it_reads_a_list_that_ends_without_a_blank_line(self, work):
        gates(work, list="%s runner.py list | grep ::" % PYTHON)
        add_tests(work, "b.t", "still: app.txt old")
        code, env = work.run("fails-on-base", "--base", "main")
        assert env["data"]["new"] == ["tests/b.t::still"]

    @pytest.mark.parametrize("field", ["list", "run", "paths"])
    def it_stops_when_the_gates_file_lacks_a_field(self, work, field):
        tests = dict(TESTS)
        del tests[field]
        work.write(GATES, json.dumps({"gates": {}, "tests": tests}))
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.CANNOT_RUN
        assert "`tests.%s`" % field in work.err

    def it_stops_when_the_run_command_has_no_place_for_the_id(self, work):
        gates(work, run="%s runner.py run" % PYTHON)
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.CANNOT_RUN
        assert "`tests.run`" in work.err

    def it_stops_when_the_paths_are_not_a_list(self, work):
        gates(work, paths="tests")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.CANNOT_RUN
        assert "`tests.paths`" in work.err

    def it_stops_without_a_gates_file(self, work):
        (work.root / GATES).unlink()
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.CANNOT_RUN
        assert "`tests.list`" in work.err

    def it_stops_when_the_list_command_fails(self, work):
        gates(work, list="%s runner.py list && exit 3" % PYTHON)
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.CANNOT_RUN
        assert "exited 3 at the branch" in work.err

    def it_stops_on_a_base_it_cannot_find(self, work):
        code, env = work.run("fails-on-base", "--base", "nowhere")
        assert code == flywheel.CANNOT_RUN
        assert "Pass --base the ref the branch merges into" in work.err


@pytest.mark.spec("failsonbase-cmd-refuses-failing-branch-run")
class DescribeANewTestThatFailsAtTheBranch:
    def it_stops_and_names_the_run_command(self, work):
        add_tests(work, "b.t", "wrong: app.txt never")
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.CANNOT_RUN
        assert "tests/b.t::wrong" in work.err
        assert TESTS["run"] in work.err


@pytest.mark.spec("failsonbase-cmd-excuses-listed-test")
class DescribeAnExcusedTest:
    def it_passes_one_whose_id_has_a_reason(self, work):
        add_tests(work, "b.t", "still: app.txt old")
        work.write(EXCUSES, json.dumps({"tests": {"tests/b.t::still": "pins what stays"}}))
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.OK
        assert env["data"]["excused"] == {"tests/b.t::still": "pins what stays"}
        assert env["warnings"] == ["tests/b.t::still passes on the base, excused: pins what stays"]

    def it_fails_one_whose_reason_is_empty(self, work):
        add_tests(work, "b.t", "still: app.txt old")
        work.write(EXCUSES, json.dumps({"tests": {"tests/b.t::still": " "}}))
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.PROBLEMS
        assert "without a reason" in env["errors"][0]

    def it_ignores_an_excuse_for_a_test_that_fails_on_the_base(self, work):
        change_app(work, "new")
        add_tests(work, "b.t", "changed: app.txt new")
        work.write(EXCUSES, json.dumps({"tests": {"tests/b.t::changed": "unneeded"}}))
        code, env = work.run("fails-on-base", "--base", "main")
        assert code == flywheel.OK
        assert env["warnings"] == []

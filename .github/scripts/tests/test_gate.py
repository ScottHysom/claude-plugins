"""The gates a contributor and CI run as one command each.

The steps run nothing real here. `execute` is replaced by a recorder that
answers each command with the exit code a test gives it, so a test sees which
commands a gate ran and in what order. git still runs, since the gates read
the clone's file list through it.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "gate.py"
_spec = importlib.util.spec_from_file_location("gate", _PATH)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

FLOORS_HERE = tuple(sys.version_info[:2])
ELSEWHERE = (2, 7)

CLONE = {
    "plugins/foo/.claude-plugin/plugin.json": '{"name": "foo"}\n',
    "plugins/foo/scripts/setup.sh": "#!/bin/sh\nset -e\n",
    "README.md": "a clone\n",
}

LOCAL_CHECKS = [
    "manifests",
    "consistency",
    "drift",
    "descriptions",
    "repeats",
    "commands",
    "steps",
    "fences",
    "placement",
    "naming",
    "pragmas",
    "floors",
    "trace",
    "surface",
]
CHECK = ["format", "ruff", "shell", "suite", *LOCAL_CHECKS]
PULL_REQUEST_CHECKS = ["linked-issues", "description", "changes"]


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Keep the developer's git config (signing, hooks, default branch) out."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def make_repo(tmp_path, git_init):
    """A throwaway clone holding exactly the files a test names, all tracked."""

    def build(files=None):
        root = tmp_path / "repo"
        git_init(root)
        for rel, text in (CLONE if files is None else files).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        gate.subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        return root

    return build


def names(argv, word):
    """Whether a command holds `word` as an argument, or as a file's name."""
    return any(a == word or a.endswith("/" + word) for a in argv)


class Recorder:
    """Stands in for gate.execute: records each command, and answers it."""

    def __init__(self, real):
        self.real = real
        self.calls = []
        self.answers = {}

    def answer(self, word, code):
        """Exit with `code` from any command that holds `word`."""
        self.answers[word] = code

    def __call__(self, argv, cwd, env, capture):
        if argv[0] == "git":
            return self.real(argv, cwd, env, capture)
        self.calls.append(argv)
        for word, code in self.answers.items():
            if names(argv, word):
                return code, "out of %s\n" % word, "err of %s\n" % word
        return gate.OK, "", ""

    def ran(self, word):
        return [argv for argv in self.calls if names(argv, word)]


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder(gate.execute)
    monkeypatch.setattr(gate, "execute", rec)
    monkeypatch.setattr(gate, "have_module", lambda name: True)
    monkeypatch.setattr(gate, "find_executable", lambda name, path: "/bin/%s" % name)
    monkeypatch.setattr(gate, "floors_python", lambda: FLOORS_HERE)
    return rec


@pytest.fixture
def run(capsys):
    """Drive a command through main() so argparse defaults are the real ones."""

    def go(*argv, environ=None):
        capsys.readouterr()
        env = {"PATH": os.environ["PATH"]} if environ is None else environ
        code = gate.main(list(argv), environ=env)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


@pytest.fixture
def pull_request_event(tmp_path):
    """The environment of a pull_request run, with an event holding `body`."""

    def build(body="## Scenario\n"):
        event = tmp_path / "event.json"
        event.write_text(json.dumps({"pull_request": {"body": body}}), encoding="utf-8")
        return {
            "PATH": os.environ["PATH"],
            gate.EVENT_NAME_ENV: gate.PULL_REQUEST_EVENT,
            gate.EVENT_PATH_ENV: str(event),
        }

    return build


def steps_of(out):
    return [step["name"] for step in json.loads(out)["data"]["steps"]]


class DescribeBuild:
    @pytest.mark.spec("build-cmd-builds-nothing")
    def it_says_there_is_nothing_to_build(self, make_repo, recorder, run):
        root = make_repo()
        code, out, _ = run("build", "-C", str(root))
        assert code == gate.OK
        assert "nothing to build" in out
        assert recorder.calls == []


class DescribeTest:
    @pytest.mark.spec("test-cmd-runs-suite-without-coverage")
    def it_runs_the_suite_without_coverage(self, make_repo, recorder, run):
        root = make_repo()
        code, _, _ = run("test", "-C", str(root))
        assert code == gate.OK
        assert recorder.calls == [[sys.executable, "-m", "pytest"]]

    @pytest.mark.spec("test-cmd-runs-suite-without-coverage")
    def it_exits_1_when_the_suite_fails(self, make_repo, recorder, run):
        root = make_repo()
        recorder.answer("pytest", gate.PROBLEMS)
        code, _, err = run("test", "-C", str(root))
        assert code == gate.PROBLEMS
        assert "test stopped at suite" in err


class DescribeCheck:
    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_runs_lint_then_the_suite_under_coverage_then_every_local_check(
        self, make_repo, recorder, run
    ):
        root = make_repo()
        code, out, _ = run("check", "-C", str(root), "--json")
        assert code == gate.OK
        assert steps_of(out) == CHECK
        (suite,) = recorder.ran("pytest")
        assert "--cov" in suite
        assert gate.COVERAGE_REPORT in suite

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    @pytest.mark.parametrize(
        ("script", "command"),
        [
            ("check-manifest-consistency.py", "check"),
            ("check-prose-rules.py", "drift"),
            ("check-skills.py", "descriptions"),
            ("check-skills.py", "repeats"),
            ("check-skills.py", "commands"),
            ("check-skills.py", "steps"),
            ("check-skills.py", "fences"),
            ("check-tests.py", "placement"),
            ("check-tests.py", "naming"),
            ("check-coverage.py", "pragmas"),
            ("check-coverage.py", "floors"),
            ("check-specs.py", "trace"),
            ("check-specs.py", "surface"),
        ],
    )
    def it_runs_each_repo_check_that_reads_only_the_clone(
        self, make_repo, recorder, run, script, command
    ):
        root = make_repo()
        assert run("check", "-C", str(root))[0] == gate.OK
        assert [a[2:] for a in recorder.ran(script) if a[2] == command] == [[command]]

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_lints_python_and_every_tracked_shell_script(self, make_repo, recorder, run):
        root = make_repo()
        assert run("check", "-C", str(root))[0] == gate.OK
        ruff = [a[3:] for a in recorder.ran("ruff")]
        assert ruff == [["format", "--check", "--diff", "."], ["check", "."]]
        assert ["sh", "-n", "plugins/foo/scripts/setup.sh"] in recorder.calls
        assert ["/bin/shellcheck", "plugins/foo/scripts/setup.sh"] in recorder.calls

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_validates_the_marketplace_and_every_plugin_manifest(self, make_repo, recorder, run):
        root = make_repo()
        assert run("check", "-C", str(root))[0] == gate.OK
        assert recorder.ran("/bin/claude") == [
            ["/bin/claude", "--version"],
            ["/bin/claude", "plugin", "validate", "--strict", "."],
            ["/bin/claude", "plugin", "validate", "--strict", "plugins/foo"],
        ]

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_stops_at_the_first_step_that_fails_and_exits_1(self, make_repo, recorder, run):
        root = make_repo()
        recorder.answer("drift", gate.PROBLEMS)
        code, out, err = run("check", "-C", str(root), "--json")
        assert code == gate.PROBLEMS
        assert steps_of(out)[-1] == "drift"
        assert recorder.ran("trace") == []
        assert "check stopped at drift" in json.loads(out)["errors"][0]
        assert err == ""

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_stops_a_step_at_its_first_failing_command(self, make_repo, recorder, run):
        root = make_repo()
        recorder.answer("sh", gate.PROBLEMS)
        code, out, _ = run("check", "-C", str(root), "--json")
        assert code == gate.PROBLEMS
        assert recorder.ran("/bin/shellcheck") == []
        assert steps_of(out)[-1] == "shell"

    @pytest.mark.spec("check-cmd-runs-every-local-check", "script-names-remedy-on-stop")
    def it_says_what_to_run_again_when_a_step_fails(self, make_repo, recorder, run):
        root = make_repo()
        recorder.answer("ruff", gate.PROBLEMS)
        code, _, err = run("check", "-C", str(root))
        assert code == gate.PROBLEMS
        assert "run `gate.py check` again" in err

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_exits_2_when_a_step_could_not_run(self, make_repo, recorder, run):
        root = make_repo()
        recorder.answer("surface", gate.CANNOT_RUN)
        assert run("check", "-C", str(root))[0] == gate.CANNOT_RUN

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_fails_when_it_finds_no_shell_script(self, make_repo, recorder, run):
        files = dict(CLONE)
        del files["plugins/foo/scripts/setup.sh"]
        root = make_repo(files)
        code, _, err = run("check", "-C", str(root))
        assert code == gate.PROBLEMS
        assert "found no shell script" in err
        assert recorder.ran("pytest") == []

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_fails_when_it_finds_no_plugin_manifest(self, make_repo, recorder, run):
        files = dict(CLONE)
        del files["plugins/foo/.claude-plugin/plugin.json"]
        root = make_repo(files)
        code, _, err = run("check", "-C", str(root))
        assert code == gate.PROBLEMS
        assert "found no plugin manifest" in err

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_prints_its_chain_before_its_first_step(self, make_repo, recorder, run):
        root = make_repo()
        _, out, err = run("check", "-C", str(root))
        first = err.splitlines()[0]
        assert first.startswith("check: lint (format, ruff, shell), test (suite), checks (")
        assert "check passed" in out

    @pytest.mark.spec("check-cmd-runs-every-local-check")
    def it_does_not_pass_a_base_to_floors(self, make_repo, recorder, run):
        root = make_repo()
        run("check", "-C", str(root))
        (floors,) = recorder.ran("floors")
        assert floors[2:] == ["floors"]


class DescribeVerify:
    @pytest.mark.spec("verify-cmd-runs-check-first")
    def it_runs_check_and_then_diff_against_the_base(self, make_repo, recorder, run):
        root = make_repo()
        code, out, _ = run("verify", "-C", str(root), "--json")
        assert code == gate.OK
        assert steps_of(out) == [*CHECK, "diff", "fails-on-base"]
        (diff,) = recorder.ran("diff")
        assert diff[2:] == ["diff", "--base", gate.DEFAULT_BASE]
        (new_tests,) = recorder.ran("fails-on-base")
        assert new_tests[1].endswith("/plugins/flywheel/scripts/flywheel.py")
        assert new_tests[2:] == ["fails-on-base", "--base", gate.DEFAULT_BASE]

    @pytest.mark.spec("verify-cmd-runs-check-first")
    def it_holds_the_floors_to_the_base(self, make_repo, recorder, run):
        root = make_repo()
        run("verify", "-C", str(root), "--base", "origin/trunk")
        (floors,) = recorder.ran("floors")
        assert floors[2:] == ["floors", "--base", "origin/trunk"]

    @pytest.mark.spec("verify-cmd-runs-check-first")
    def it_runs_the_pull_request_checks_on_a_pull_request_event(
        self, make_repo, recorder, run, pull_request_event
    ):
        root = make_repo()
        code, out, _ = run("verify", "-C", str(root), "--json", environ=pull_request_event())
        assert code == gate.OK
        assert steps_of(out) == [*CHECK, "diff", "fails-on-base", *PULL_REQUEST_CHECKS]
        (changes,) = recorder.ran("changes")
        assert changes[2:] == ["changes", "--base", gate.DEFAULT_BASE]

    @pytest.mark.spec("verify-cmd-checks-description-with-flywheel")
    def it_checks_the_description_with_flywheels_pr_check(
        self, make_repo, recorder, run, pull_request_event
    ):
        root = make_repo()
        body = "## Scenario\n\nThe owner reviews.\n\nCloses #717\n"
        code, _, _ = run("verify", "-C", str(root), environ=pull_request_event(body))
        assert code == gate.OK
        (check,) = [c for c in recorder.ran("flywheel.py") if c[2] == "pr"]
        assert check[1] == gate.FLYWHEEL
        assert check[2:5] == ["pr", "check", "--body-file"]
        assert Path(check[5]).read_text(encoding="utf-8") == body

    @pytest.mark.spec("verify-cmd-checks-description-with-flywheel")
    def it_checks_an_empty_description_when_the_pull_request_has_none(
        self, make_repo, recorder, run, pull_request_event
    ):
        root = make_repo()
        run("verify", "-C", str(root), environ=pull_request_event(None))
        (check,) = [c for c in recorder.ran("flywheel.py") if c[2] == "pr"]
        assert Path(check[5]).read_text(encoding="utf-8") == ""

    @pytest.mark.spec("verify-cmd-checks-description-with-flywheel", "script-names-remedy-on-stop")
    def it_stops_and_names_the_variable_when_the_event_cannot_be_read(
        self, make_repo, recorder, run, tmp_path
    ):
        root = make_repo()
        environ = {
            "PATH": os.environ["PATH"],
            gate.EVENT_NAME_ENV: gate.PULL_REQUEST_EVENT,
            gate.EVENT_PATH_ENV: str(tmp_path / "missing.json"),
        }
        code, _, err = run("verify", "-C", str(root), environ=environ)
        assert code == gate.CANNOT_RUN
        assert gate.EVENT_PATH_ENV in err
        assert recorder.calls == []

    @pytest.mark.spec("verify-cmd-runs-check-first")
    def it_prints_its_chain_first(self, make_repo, recorder, run):
        root = make_repo()
        _, _, err = run("verify", "-C", str(root))
        first = err.splitlines()[0]
        assert first.startswith(
            "verify: check (lint, test, checks), then diff, fails-on-base, linked-issues, "
            "description, changes."
        )
        assert "check: lint (format, ruff, shell)" in first

    @pytest.mark.spec("verify-cmd-runs-check-first")
    def it_does_not_reach_the_base_checks_when_check_fails(self, make_repo, recorder, run):
        root = make_repo()
        recorder.answer("pytest", gate.PROBLEMS)
        assert run("verify", "-C", str(root))[0] == gate.PROBLEMS
        assert recorder.ran("diff") == []


class DescribeSkippedChecks:
    @pytest.mark.spec("gate-cmd-names-skipped-checks")
    def it_skips_floors_off_their_python_and_says_why(self, make_repo, recorder, run, monkeypatch):
        monkeypatch.setattr(gate, "floors_python", lambda: ELSEWHERE)
        root = make_repo()
        code, out, _ = run("check", "-C", str(root), "--json")
        body = json.loads(out)
        assert code == gate.OK
        assert "floors" not in steps_of(out)
        assert recorder.ran("floors") == []
        (skipped,) = body["data"]["skipped"]
        assert skipped["name"] == "floors"
        assert "2.7" in skipped["reason"]
        assert body["warnings"] == ["skipped floors: %s" % skipped["reason"]]

    @pytest.mark.spec("gate-cmd-names-skipped-checks")
    def it_names_the_pull_request_checks_it_skips_outside_a_pull_request(
        self, make_repo, recorder, run
    ):
        root = make_repo()
        code, _, err = run("verify", "-C", str(root))
        assert code == gate.OK
        for name in PULL_REQUEST_CHECKS:
            assert "warning: skipped %s: it reads the pull request" % name in err
        for word in ("check-linked-issues.py", "description", "changes"):
            assert recorder.ran(word) == []

    @pytest.mark.spec("gate-cmd-names-skipped-checks")
    def it_reads_the_floors_python_from_check_coverage(self):
        spec = importlib.util.spec_from_file_location("cc", gate.CHECK_COVERAGE)
        cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cc)
        assert gate.floors_python() == cc.FLOORS_PYTHON


class DescribeTools:
    @pytest.mark.spec("gate-cmd-finds-tools-first", "script-names-remedy-on-stop")
    def it_names_a_missing_module_and_its_install_before_any_step(
        self, make_repo, recorder, run, monkeypatch
    ):
        monkeypatch.setattr(gate, "have_module", lambda name: name != "ruff")
        root = make_repo()
        code, out, err = run("check", "-C", str(root))
        assert code == gate.CANNOT_RUN
        assert out == ""
        assert "the Python module ruff" in err
        assert "pip install -r requirements-dev.txt" in err
        assert recorder.calls == []

    @pytest.mark.spec("gate-cmd-finds-tools-first")
    def it_names_a_missing_claude_cli(self, make_repo, recorder, run, monkeypatch):
        monkeypatch.setattr(
            gate, "find_executable", lambda name, path: None if name == "claude" else name
        )
        root = make_repo()
        code, _, err = run("verify", "-C", str(root))
        assert code == gate.CANNOT_RUN
        assert gate.CLAUDE_INSTALL in err
        assert recorder.calls == []

    @pytest.mark.spec("gate-cmd-finds-tools-first")
    def it_looks_for_tools_beside_its_own_python_first(self, make_repo, recorder, run, monkeypatch):
        seen = []
        monkeypatch.setattr(
            gate, "find_executable", lambda name, path: seen.append(path) or "/bin/" + name
        )
        root = make_repo()
        run("check", "-C", str(root), environ={"PATH": os.environ["PATH"]})
        assert seen[0].split(os.pathsep) == [
            str(Path(sys.executable).parent),
            *os.environ["PATH"].split(os.pathsep),
        ]

    @pytest.mark.spec("gate-cmd-finds-tools-first")
    def it_finds_the_real_tools_it_names(self):
        assert gate.have_module("json")
        assert not gate.have_module("no_such_module_anywhere")
        assert gate.find_executable("sh", "/bin:/usr/bin")


class DescribeMain:
    @pytest.mark.parametrize("command", ["build", "test", "check", "verify"])
    @pytest.mark.spec("command-prints-json-envelope")
    def it_prints_the_same_envelope_for_every_command(self, make_repo, recorder, run, command):
        root = make_repo()
        code, out, err = run(command, "-C", str(root), "--json")
        assert code == gate.OK
        body = json.loads(out)
        assert set(body) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert body["command"] == command
        assert body["data"]["chain"].startswith(command + ":")
        assert err == ""

    @pytest.mark.spec("command-prints-json-envelope")
    def it_captures_each_step_s_output_in_the_envelope(self, make_repo, recorder, run):
        root = make_repo()
        recorder.answer("pytest", gate.OK)
        _, out, _ = run("test", "-C", str(root), "--json")
        (step,) = json.loads(out)["data"]["steps"]
        (command,) = step["commands"]
        assert command["stdout"] == "out of pytest\n"
        assert command["stderr"] == "err of pytest\n"

    @pytest.mark.spec("command-splits-output-streams-without-json")
    def it_puts_its_result_on_stdout_and_its_progress_on_stderr(self, make_repo, recorder, run):
        root = make_repo()
        _, out, err = run("test", "-C", str(root))
        assert out == "test passed: suite\n"
        assert err.startswith("test: test (suite)\n")

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_outside_a_clone(self, tmp_path, run):
        code, _, err = run("build", "-C", str(tmp_path))
        assert code == gate.CANNOT_RUN
        assert err.startswith(gate.PROG + ":")

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_on_a_directory_that_does_not_exist(self, tmp_path, run):
        code, out, err = run("build", "-C", str(tmp_path / "nope"))
        assert code == gate.CANNOT_RUN
        assert out == ""
        assert err.startswith("%s: no such directory" % gate.PROG)

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_rejects_an_unknown_command(self, run):
        with pytest.raises(SystemExit) as exc:
            run("nonsense")
        assert exc.value.code == gate.CANNOT_RUN

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_stops_when_it_cannot_load_check_coverage(self, monkeypatch, tmp_path):
        monkeypatch.setattr(gate, "CHECK_COVERAGE", str(tmp_path / "missing.py"))
        with pytest.raises(gate.Fatal, match="cannot load"):
            gate.floors_python()

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_stops_when_a_command_cannot_start(self, tmp_path):
        with pytest.raises(gate.Fatal, match="cannot run"):
            gate.execute([str(tmp_path / "missing")], str(tmp_path), {}, capture=True)

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_stops_when_git_cannot_list_the_files(self, make_repo, recorder, run):
        root = make_repo()
        machine = gate.Machine(str(root), {"PATH": os.environ["PATH"]})
        with pytest.raises(gate.Fatal, match="git ls-files"):
            machine.tracked(":(bad-magic)x")

    @pytest.mark.spec("script-ignores-closed-pipe")
    def it_exits_ok_without_a_traceback_when_its_reader_has_gone(
        self, make_repo, closed_pipe_child
    ):
        root = make_repo()
        assert closed_pipe_child(_PATH, "build", "-C", str(root)) == (gate.OK, "")

    @pytest.mark.spec("script-does-nothing-on-import")
    def it_runs_nothing_on_import(self, recorder):
        spec = importlib.util.spec_from_file_location("gate_again", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert recorder.calls == []

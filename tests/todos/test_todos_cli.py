"""What every todos.py command does at its edges: where it can run, what it
prints, and how it stops."""

import importlib.util

import pytest

import todos

ENVELOPE_KEYS = {"version", "command", "ok", "errors", "warnings", "data"}


@pytest.mark.spec("command-requires-a-repo", "repo:script-exits-2-when-unrunnable")
class DescribeRepoRequired:
    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_stops_outside_a_git_repository(self, tmp_path, capsys):
        assert todos.main(["scan", "-C", str(tmp_path)]) == todos.CANNOT_RUN
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("todos.py: %s is not inside a git working tree" % tmp_path)
        assert "Run from inside a clone, or name one with -C." in captured.err

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_stops_in_a_repository_without_a_commit(self, bare_repo):
        code, env = bare_repo.run("scan")
        assert (code, env) == (todos.CANNOT_RUN, None)
        assert "has no commit yet" in bare_repo.err
        assert "commit the project first" in bare_repo.err

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_stops_when_git_is_not_installed(self, repo, no_git):
        code, _ = repo.run("scan")
        assert code == todos.CANNOT_RUN
        assert repo.err == (
            "todos.py: git is not installed, or not on PATH. Install git, then run again.\n"
        )

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_stops_when_c_names_a_missing_directory(self, tmp_path, capsys):
        missing = tmp_path / "missing"
        assert todos.main(["scan", "-C", str(missing)]) == todos.CANNOT_RUN
        assert capsys.readouterr().err == (
            "todos.py: %s is not a directory. Name a clone with -C.\n" % missing
        )

    def it_rejects_an_unknown_command(self, capsys):
        with pytest.raises(SystemExit) as exc:
            todos.main(["nonsense"])
        assert exc.value.code == todos.CANNOT_RUN

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_names_a_git_command_that_fails(self, repo, monkeypatch):
        real = todos.Repo.run

        def failing(self, *args):
            if args[0] == "ls-files":
                return 128, b"", b"fatal: index file corrupt\n"
            return real(self, *args)

        monkeypatch.setattr(todos.Repo, "run", failing)
        code, _ = repo.run("scan")
        assert code == todos.CANNOT_RUN
        assert "git ls-files -z --others --exclude-standard failed: fatal: index file corrupt" in (
            repo.err
        )
        assert "Run `git status` in" in repo.err


class DescribeOutput:
    @pytest.mark.spec("repo:command-prints-json-envelope", "scan-cmd-warns-on-unread-todos")
    def it_prints_one_envelope_and_nothing_on_stderr(self, repo):
        repo.write("a.py", "# TODO: one\nx = 1  # TODO: two\n")
        code, env = repo.run("scan")
        assert code == todos.OK
        assert set(env) == ENVELOPE_KEYS
        assert (env["version"], env["command"], env["ok"]) == (todos.ENVELOPE_VERSION, "scan", True)
        assert env["errors"] == []
        assert env["warnings"] == [
            "a.py:2: a TODO is read only at the start of its line, after its indent and comment"
            " marker"
        ]
        assert repo.err == ""

    @pytest.mark.spec("repo:script-ignores-closed-pipe")
    def it_exits_ok_when_its_reader_closes_the_pipe(self, repo, capsys, closed_pipe):
        repo.write("a.py", "# TODO: one\n")
        closed_pipe()
        assert todos.main(["scan", "-C", str(repo.root)]) == todos.OK
        assert capsys.readouterr().err == ""


@pytest.mark.spec("repo:script-does-nothing-on-import")
class DescribeImport:
    def it_does_no_work_when_imported(self, script_path, capsys):
        spec = importlib.util.spec_from_file_location("todos_again", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        captured = capsys.readouterr()
        assert (captured.out, captured.err) == ("", "")

    def it_does_not_carry_anything_from_one_run_into_the_next(self, repo):
        repo.write("a.py", "# TODO: one\nx = 1  # TODO: two\n")
        first = repo.run("scan")
        second = repo.run("scan")
        assert first == second
        assert len(first[1]["data"]["todos"]) == 1

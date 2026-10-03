"""How todos.py reaches GitHub through gh, and the labels scan lists.

The tests that put a gh script of their own on PATH drive the script's real
gh(); the rest talk to the fake in conftest.py.
"""

import json

import pytest

import todos

VIEW = '{"nameWithOwner": "owner/project", "url": "https://github.com/owner/project"}'


def gh_script(view=None, labels="[]", auth=0, create=None):
    """A gh that answers repo view, label list, auth status and issue create.

    A value of None makes that call fail, as gh does, on stderr.
    """

    def answer(value):
        if value is None:
            return "echo 'gh: request failed' >&2; exit 1\n"
        return "cat <<'END'\n%s\nEND\n" % value

    return (
        'case "$1 $2" in\n'
        '"repo view")\n%s;;\n'
        '"label list")\n%s;;\n'
        '"auth status") echo "not logged in" >&2; exit %d ;;\n'
        '"issue create") cat > "$0.body"\n%s;;\n'
        "esac\n" % (answer(view), answer(labels), auth, answer(create))
    )


@pytest.mark.spec("command-requires-signed-in-gh", "repo:script-exits-2-when-unrunnable")
class DescribeGhRequired:
    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_stops_when_gh_is_not_installed(self, repo, gh_on_path):
        gh_on_path(None)
        code, env = repo.run("scan")
        assert (code, env) == (todos.CANNOT_RUN, None)
        assert repo.err == "todos.py: %s\n" % todos.GH_MISSING
        assert "run `gh auth login`" in repo.err

    @pytest.mark.spec("repo:script-names-remedy-on-stop")
    def it_stops_when_gh_is_not_signed_in(self, repo, gh_on_path):
        gh_on_path(gh_script(view=None, auth=1))
        code, _ = repo.run("scan")
        assert code == todos.CANNOT_RUN
        assert repo.err == (
            "todos.py: gh is not signed in. `gh auth status` failed: not logged in. Run"
            " `gh auth login`, then run again.\n"
        )

    @pytest.mark.parametrize("command", [("report",), ("file", "--token", "x")])
    def it_stops_report_and_file_too(self, repo, gh_on_path, tmp_path, command):
        gh_on_path(None)
        drafts = tmp_path / "drafts.json"
        drafts.write_text("[]")
        code, _ = repo.run(*command, "--drafts", str(drafts))
        assert code == todos.CANNOT_RUN
        assert todos.GH_MISSING in repo.err


@pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
class DescribeGhFailing:
    def it_names_a_clone_gh_cannot_name_a_repository_for(self, repo, gh_on_path):
        gh_on_path(gh_script(view=None))
        code, _ = repo.run("scan")
        assert code == todos.CANNOT_RUN
        assert repo.err == (
            "todos.py: `gh repo view` failed: gh: request failed. Add a GitHub remote, or"
            " choose one with `gh repo set-default`, then run again.\n"
        )

    def it_names_a_label_list_that_fails(self, repo, gh_on_path):
        gh_on_path(gh_script(view=VIEW, labels=None))
        code, _ = repo.run("scan")
        assert code == todos.CANNOT_RUN
        assert repo.err == (
            "todos.py: `gh label list` failed: gh: request failed. Run it yourself to see"
            " what gh reports.\n"
        )

    def it_names_a_call_that_does_not_print_json(self, repo, gh_on_path):
        gh_on_path(gh_script(view="not json"))
        code, _ = repo.run("scan")
        assert code == todos.CANNOT_RUN
        assert repo.err.startswith("todos.py: `gh repo view` did not print JSON: ")
        assert repo.err.endswith("Run it yourself to see what it prints.\n")

    def it_gives_up_on_a_call_that_does_not_finish(self, repo, gh_on_path, monkeypatch):
        gh_on_path("exec sleep 5\n")
        monkeypatch.setattr(todos, "GH_TIMEOUT", 0.2)
        code, _ = repo.run("scan")
        assert code == todos.CANNOT_RUN
        assert repo.err == (
            "todos.py: `gh repo view` did not finish within 0.2 seconds. Check that GitHub can"
            " be reached, then run again.\n"
        )


@pytest.mark.spec("file-cmd-creates-issues")
class DescribeTheRealGh:
    def it_files_through_gh_with_the_body_on_stdin(self, repo, gh_on_path, tmp_path):
        labels = json.dumps([{"name": "bug", "description": "Broken"}])
        url = "https://github.com/owner/project/issues/42"
        gh_on_path(gh_script(view=VIEW, labels=labels, create="Creating\n\n" + url))
        repo.write("a.py", "x = 1\n")
        repo.commit()
        repo.write("a.py", "# TODO: one\nx = 1\n")
        found, _ = repo.scan()
        drafts = repo.drafts([repo.draft(found[0], body="Body, with 'quotes'.\n", labels=["bug"])])
        code, env = repo.file(drafts)
        assert code == todos.OK, repo.err
        assert [(f["number"], f["url"]) for f in env["data"]["filed"]] == [(42, url)]
        assert (tmp_path / "gh-bin" / "gh.body").read_text() == "Body, with 'quotes'.\n"
        assert repo.read("a.py") == b"x = 1\n"


@pytest.mark.spec("scan-cmd-lists-labels")
class DescribeLabels:
    def it_lists_every_label_with_its_description(self, repo, github):
        code, env = repo.run("scan")
        assert code == todos.OK
        assert env["data"]["labels"] == [
            {"name": "bug", "description": "Something is broken"},
            {"name": "enhancement", "description": "New behavior"},
            {"name": "plugin:todos", "description": ""},
        ]
        assert env["data"]["repository"] == "owner/project"

    def it_asks_gh_for_more_than_its_default_of_thirty(self, repo, github):
        repo.run("scan")
        (call,) = [c for c in github.calls if c[:2] == ("label", "list")]
        assert call == (
            "label",
            "list",
            "--repo",
            "owner/project",
            "--limit",
            str(todos.LABEL_LIMIT),
            "--json",
            "name,description",
        )

    def it_lists_them_in_text(self, repo):
        _, out, _ = repo.human("scan")
        assert out.startswith(
            "Labels in owner/project:\n"
            "  bug  Something is broken\n"
            "  enhancement  New behavior\n"
            "  plugin:todos\n"
        )

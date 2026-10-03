"""The open issues `todos.py scan` lists beside each TODO, and the one query
that finds them."""

import json

import pytest

import todos
from test_todos_github import VIEW, gh_script


def issue(number, title):
    return {
        "number": number,
        "title": title,
        "url": "https://github.com/owner/project/issues/%d" % number,
    }


def searched(title):
    return "repo:owner/project is:issue is:open " + title


def graphql_calls(github):
    return [c for c in github.calls if c[:2] == ("api", "graphql")]


@pytest.fixture
def two(repo):
    """A clone with two pending TODOs in run.py."""
    repo.write("run.py", "def run():\n    pass\n")
    repo.commit()
    repo.write("run.py", "# TODO(bug): run hangs\ndef run():\n    pass\n# TODO: tidy up\n")
    return repo


@pytest.mark.spec("scan-cmd-lists-similar-issues")
class DescribeSimilarIssues:
    def it_lists_the_issues_search_returns_for_each_title(self, two, github):
        github.searches[searched("run hangs")] = [issue(7, "run() hangs"), issue(9, "Hangs")]
        found, _ = two.scan()
        assert [t["similar"] for t in found] == [
            [issue(7, "run() hangs"), issue(9, "Hangs")],
            [],
        ]

    def it_asks_github_for_the_first_five(self, two, github):
        two.scan()
        assert todos.SIMILAR_LIMIT == 5
        (query,) = github.queries
        assert query.count("first: 5)") == 2

    def it_searches_only_the_repositorys_open_issues(self, two, github):
        github.repository = "someone/fork"
        two.scan()
        (query,) = github.queries
        assert json.dumps("repo:someone/fork is:issue is:open run hangs") in query

    @pytest.mark.parametrize(
        ("title", "words"),
        [
            ("is:closed in config", '"is:closed" in config'),
            ('a "quoted phrase', "a quoted phrase"),
            ("repo:other/repo leaks", '"repo:other/repo" leaks'),
        ],
    )
    def it_keeps_a_title_from_acting_as_a_qualifier(self, title, words):
        assert todos.search_query("owner/project", title) == searched(words)

    def it_leaves_out_a_result_github_does_not_return(self, two, github):
        github.searches[searched("run hangs")] = [None, issue(7, "run() hangs")]
        found, _ = two.scan()
        assert found[0]["similar"] == [issue(7, "run() hangs")]

    def it_prints_them_under_their_todo(self, two, github):
        github.searches[searched("run hangs")] = [issue(7, "run() hangs"), issue(9, "Hangs")]
        code, out, _ = two.human("scan")
        assert code == todos.OK
        assert (
            "run.py:1: (bug) run hangs\n"
            "    above line 2 (line 1 at %s): def run():\n"
            "    open issues like it:\n"
            "      #7  run() hangs\n"
            "      #9  Hangs\n"
            "run.py:4: tidy up\n" % two.head()[: todos.ABBREV]
        ) in out

    @pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
    def it_stops_when_the_search_fails(self, two, gh_on_path):
        gh_on_path(gh_script(view=VIEW, graphql=None))
        code, env = two.run("scan")
        assert (code, env) == (todos.CANNOT_RUN, None)
        assert two.err == (
            "todos.py: `gh api graphql` failed: gh: request failed. Run it yourself to see what"
            " gh reports.\n"
        )


@pytest.mark.spec("scan-cmd-searches-in-one-query")
class DescribeOneQuery:
    def it_sends_one_query_for_every_title(self, two, github):
        two.write("other.md", "<!-- TODO: third -->\n")
        found, _ = two.scan()
        assert len(found) == 3
        (call,) = graphql_calls(github)
        assert call == ("api", "graphql", "--input", "-")
        (query,) = github.queries
        assert [a for a in ("s0:", "s1:", "s2:", "s3:") if a in query] == ["s0:", "s1:", "s2:"]

    def it_makes_no_query_when_there_is_no_todo(self, repo, github):
        code, env = repo.run("scan")
        assert code == todos.OK
        assert env["data"]["todos"] == []
        assert graphql_calls(github) == []

    def it_sends_the_query_to_gh_on_stdin(self, repo, gh_on_path, tmp_path):
        gh_on_path(gh_script(view=VIEW))
        repo.write("a.py", "# TODO: one\n")
        code, env = repo.run("scan")
        assert code == todos.OK, repo.err
        assert env["data"]["todos"][0]["similar"] == []
        sent = json.loads((tmp_path / "gh-bin" / "gh.query").read_text())
        assert json.dumps(searched("one")) in sent["query"]

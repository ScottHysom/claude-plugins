"""What check-specs.py promises about the chain from a need to the code.

`trace` fails by absence: a test that cites nothing, or a requirement nothing
cites, is a line that is not there. So each test starts from a throwaway clone
where every link holds and `trace` passes, then removes or breaks one link and
checks that `trace` names it.

`inventory` reads a plugin's script, skills and suite, and a coverage report.
The report here is written by hand, so each test states exactly which test ran
which line.
"""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-specs.py"
_spec = importlib.util.spec_from_file_location("check_specs", _PATH)
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)

REPO_ROOT = Path(__file__).resolve().parents[3]

SCRIPT = "plugins/foo/scripts/foo.py"
SKILL = "plugins/foo/skills/a/SKILL.md"
TEST = "tests/foo/test_foo.py"
REPO_TEST = ".github/scripts/tests/test_tool.py"
WORKFLOW = ".github/workflows/ci.yml"

PYTEST_INI = "[pytest]\ntestpaths = tests .github/scripts/tests\n"

FOO_SPEC = (
    "# foo\n\n"
    "## Out of scope\n\n"
    "- Anything else.\n\n"
    "## need does-things: Do things\n\n"
    "When a user wants things, they want them done.\n\n"
    "- `does-x` (test): When asked, foo does x.\n"
    "- `asks-once` (step): When foo has questions, the skill asks them\n"
    "  in one batch.\n"
)
REPO_SPEC = (
    "# repo\n\n"
    "## need checked: Keep it checked\n\n"
    "When a contributor pushes, the owner wants it checked.\n\n"
    "- `runs-in-ci` (check): When a pull request opens, CI runs the check.\n"
    "- `tool-works` (test): When the tool runs, it works.\n"
)

SOURCE = """import argparse

MODES = ("a", "b")
MIXED = ("a", 1)
NAME = "c"
NAMED = {NAME, "d"}


def build_parser():
    ap = argparse.ArgumentParser(prog="foo")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("go")
    p.add_argument("--mode", choices=MODES)
    p.add_argument("--skip")
    return ap


if __name__ == "__main__":
    build_parser().parse_args()
"""

LOCATE = (
    "## Locate the script\n\n"
    "```sh\n"
    'ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"\n'
    'FOO="$ROOT/scripts/foo.py"\n'
    "```\n\n"
)


def skill(step_one_marker="<!-- spec: asks-once -->\n", step_two_marker="<!-- spec: does-x -->\n"):
    return (
        "---\nname: a\ndescription: the a skill\n---\n\n# a\n\n"
        + LOCATE
        + "## Step 1: go\n"
        + step_one_marker
        + '\n```sh\npython3 "$FOO" go --mode a\n```\n\n'
        + "Pass `go --skip` to leave one out.\n\n"
        + "## Step 2: ask\n"
        + step_two_marker
        + "\nAsk the questions.\n"
    )


def suite_file(class_marker="", method_marker='    @pytest.mark.spec("does-x")\n'):
    return (
        "import pytest\n\n\n"
        + class_marker
        + "class DescribeFoo:\n"
        + method_marker
        + "    def it_does_x(self):\n        pass\n\n"
        + "    def helper(self):\n        pass\n"
    )


REPO_TEST_TEXT = 'import pytest\n\n\n@pytest.mark.spec("tool-works")\ndef it_works():\n    pass\n'

WORKFLOW_TEXT = (
    "jobs:\n  check:\n    steps:\n"
    "      # Runs the check.\n"
    "      # spec: runs-in-ci\n"
    "      - name: Run the check\n"
    "        run: true\n"
)

BASE = {
    "pytest.ini": PYTEST_INI,
    "specs/foo.md": FOO_SPEC,
    "specs/repo.md": REPO_SPEC,
    SCRIPT: SOURCE,
    SKILL: skill(),
    TEST: suite_file(),
    REPO_TEST: REPO_TEST_TEXT,
    WORKFLOW: WORKFLOW_TEXT,
}


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Keep the developer's git config (signing, hooks, default branch) out."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def make_repo(tmp_path):
    """A clone holding BASE, with `changes` applied: a path to text, or to None to leave it out."""

    def make(changes=None, name="repo"):
        root = tmp_path / name
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        files = dict(BASE)
        files.update(changes or {})
        for rel, text in files.items():
            if text is None:
                continue
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return root

    return make


def no_graphql(query, token):
    raise AssertionError("asked GitHub with no token: %s" % query)


@pytest.fixture
def run(capsys):
    """Drive a command through main() so argparse defaults are the real ones.

    The environment is empty unless a test gives one, so a token in the
    developer's shell cannot send a test to GitHub.
    """

    def go(*argv, environ=None, graphql=no_graphql):
        capsys.readouterr()
        code = cp.main(list(argv), environ=environ or {}, graphql=graphql)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


class FakeGitHub:
    """GitHub's GraphQL endpoint, answering for the issues it was given.

    An issue it lacks comes back null, as GitHub answers for one it cannot find.
    """

    def __init__(self, issues):
        self.issues = issues
        self.queries = []

    def __call__(self, query, token):
        self.queries.append(query)
        numbers = re.findall(r"i(\d+): issue\(number: \d+\)", query)
        return {"repository": {"i%s" % n: self.issues.get(int(n)) for n in numbers}}


GITHUB_ENV = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}


def untraced(tests=None, steps=None, surface=None):
    return json.dumps({"tests": tests or {}, "steps": steps or {}, "surface": surface or {}})


TEST_ID = TEST + "::DescribeFoo::it_does_x"
STEP_ID = SKILL + "::1"


class DescribeTrace:
    @pytest.mark.spec("trace-uncited")
    def it_passes_a_clone_where_every_link_holds(self, make_repo, run):
        code, out, err = run("trace", "-C", str(make_repo()))
        assert code == cp.OK, err
        assert "4 requirement(s) verified" in out
        assert err == ""

    @pytest.mark.spec("trace-uncited")
    def it_fails_a_test_that_cites_nothing(self, make_repo, run):
        root = make_repo({TEST: suite_file(method_marker="")})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "%s:5: DescribeFoo::it_does_x cites no requirement" % TEST in err

    @pytest.mark.spec("trace-uncited")
    def it_fails_a_step_that_cites_nothing(self, make_repo, run):
        root = make_repo({SKILL: skill(step_two_marker="")})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert '"Step 2: ask" cites no requirement' in err

    @pytest.mark.spec("trace-uncited")
    def it_reads_a_marker_on_the_class_for_each_test_in_it(self, make_repo, run):
        root = make_repo(
            {TEST: suite_file(class_marker='@pytest.mark.spec("does-x")\n', method_marker="")}
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.OK, err

    @pytest.mark.spec("trace-uncited")
    def it_ignores_a_method_pytest_does_not_collect(self, make_repo, run):
        code, _, err = run("trace", "-C", str(make_repo()))
        assert code == cp.OK
        assert "helper" not in err

    @pytest.mark.spec("trace-uncited")
    def it_fails_a_step_marker_that_shares_its_line(self, make_repo, run):
        root = make_repo({SKILL: skill(step_two_marker="Ask. <!-- spec: does-x -->\n")})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "must be a line of its own" in err

    @pytest.mark.spec("trace-unknown-id")
    def it_fails_a_test_citing_an_id_its_spec_lacks(self, make_repo, run):
        root = make_repo(
            {TEST: suite_file(method_marker='    @pytest.mark.spec("does-x", "does-y")\n')}
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "cites `does-y`, which specs/foo.md does not hold" in err

    @pytest.mark.spec("trace-unknown-id")
    def it_fails_a_step_citing_an_id_its_spec_lacks(self, make_repo, run):
        root = make_repo({SKILL: skill(step_two_marker="<!-- spec: does-x, nope -->\n")})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "%s:" % SKILL in err
        assert "cites `nope`" in err

    @pytest.mark.spec("trace-unknown-id")
    def it_fails_a_workflow_step_citing_an_id_the_repo_spec_lacks(self, make_repo, run):
        root = make_repo({WORKFLOW: WORKFLOW_TEXT.replace("runs-in-ci", "runs-in-ci, gone")})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "%s:5: cites `gone`, which specs/repo.md does not hold" % WORKFLOW in err

    @pytest.mark.spec("trace-unknown-id")
    def it_resolves_a_repo_id_cited_from_a_plugin_test(self, make_repo, run):
        root = make_repo(
            {
                TEST: suite_file(
                    method_marker='    @pytest.mark.spec("does-x", "repo:tool-works")\n'
                ),
                REPO_TEST: REPO_TEST_TEXT.replace('"tool-works"', '"repo:runs-in-ci"'),
            }
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.OK, err

    @pytest.mark.spec("trace-unknown-id")
    def it_fails_a_marker_whose_id_is_not_a_string_literal(self, make_repo, run):
        root = make_repo(
            {TEST: "import pytest\n" + suite_file(method_marker="    @pytest.mark.spec(ID)\n")}
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "as string literals" in err

    @pytest.mark.spec("trace-unverified")
    def it_fails_a_test_requirement_no_test_cites(self, make_repo, run):
        root = make_repo(
            {
                TEST: suite_file(method_marker='    @pytest.mark.spec("asks-once")\n'),
                SKILL: skill(step_two_marker="<!-- spec: asks-once -->\n"),
            }
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "specs/foo.md:11: `does-x` (test) is verified by nothing of its kind" in err

    @pytest.mark.spec("trace-unverified")
    def it_fails_a_step_requirement_only_a_test_cites(self, make_repo, run):
        root = make_repo(
            {
                TEST: suite_file(method_marker='    @pytest.mark.spec("does-x", "asks-once")\n'),
                SKILL: skill(step_one_marker="", step_two_marker="<!-- spec: does-x -->\n"),
            }
        )
        root_skill = root / SKILL
        root_skill.write_text(
            root_skill.read_text().replace(
                "## Step 1: go\n", "## Step 1: go\n<!-- spec: does-x -->\n"
            )
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "`asks-once` (step) is verified by nothing of its kind" in err

    @pytest.mark.spec("trace-unverified")
    def it_fails_a_check_requirement_no_workflow_step_cites(self, make_repo, run):
        root = make_repo({WORKFLOW: WORKFLOW_TEXT.replace("      # spec: runs-in-ci\n", "")})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "`runs-in-ci` (check) is verified by nothing of its kind" in err

    @pytest.mark.spec("trace-unverified")
    def it_fails_a_workflow_comment_that_is_not_above_a_step(self, make_repo, run):
        text = WORKFLOW_TEXT.replace("      # Runs the check.\n", "").replace(
            "      # spec: runs-in-ci\n", "      # spec: runs-in-ci\n\n"
        )
        code, _, err = run("trace", "-C", str(make_repo({WORKFLOW: text})))
        assert code == cp.PROBLEMS
        assert "directly above a step's `- name:`" in err

    @pytest.mark.spec("trace-listed-warns")
    def it_passes_a_listed_test_with_a_warning_naming_its_issue(self, make_repo, run):
        root = make_repo(
            {
                TEST: suite_file(method_marker=""),
                SKILL: skill(
                    step_one_marker="<!-- spec: does-x -->\n",
                    step_two_marker="<!-- spec: asks-once -->\n",
                ),
                "specs/foo.md": FOO_SPEC.replace("(test)", "(step)"),
                cp.UNTRACED_FILE: untraced({TEST_ID: 130}),
            }
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.OK, err
        assert "warning: 1 test(s) cite no requirement yet; #130 will trace them." in err

    @pytest.mark.spec("trace-listed-warns")
    def it_passes_a_listed_step_with_a_warning_naming_its_issue(self, make_repo, run):
        root = make_repo(
            {
                SKILL: skill(step_one_marker="", step_two_marker="<!-- spec: asks-once -->\n"),
                cp.UNTRACED_FILE: untraced(steps={STEP_ID: 131}),
            }
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.OK, err
        assert "1 step(s) cite no requirement yet; #131" in err

    @pytest.mark.spec("trace-list-shrinks")
    def it_fails_a_listed_test_that_now_cites(self, make_repo, run):
        root = make_repo({cp.UNTRACED_FILE: untraced({TEST_ID: 130})})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "now cites a requirement. Remove its entry" in err
        assert "#130" in err

    @pytest.mark.spec("trace-list-shrinks")
    def it_fails_a_listed_item_that_is_gone(self, make_repo, run):
        root = make_repo({cp.UNTRACED_FILE: untraced(steps={SKILL + "::9": 131})})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "lists %s::9 for #131, and there is no such step" % SKILL in err

    @pytest.mark.spec("trace-list-shrinks")
    def it_stops_on_a_list_it_cannot_read(self, make_repo, run):
        root = make_repo({cp.UNTRACED_FILE: json.dumps({"tests": {TEST_ID: "soon"}})})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.CANNOT_RUN
        assert err.startswith("check-specs.py: ")

    @pytest.mark.spec("trace-spec-grammar")
    def it_fails_a_requirement_outside_a_need(self, make_repo, run):
        spec = FOO_SPEC.replace("- Anything else.\n", "- `stray` (test): When lost, it is.\n")
        code, _, err = run("trace", "-C", str(make_repo({"specs/foo.md": spec})))
        assert code == cp.PROBLEMS
        assert "specs/foo.md:5: a requirement sits outside any need" in err

    @pytest.mark.spec("trace-spec-grammar")
    def it_fails_a_bullet_under_a_need_that_is_not_a_requirement(self, make_repo, run):
        spec = FOO_SPEC + "- Just a note.\n"
        code, _, err = run("trace", "-C", str(make_repo({"specs/foo.md": spec})))
        assert code == cp.PROBLEMS
        assert "is not a requirement" in err

    @pytest.mark.spec("trace-spec-grammar")
    def it_fails_a_duplicate_id(self, make_repo, run):
        spec = FOO_SPEC + "- `does-x` (test): When asked again, foo does x.\n"
        code, _, err = run("trace", "-C", str(make_repo({"specs/foo.md": spec})))
        assert code == cp.PROBLEMS
        assert "already the id of the requirement at line 11" in err

    @pytest.mark.spec("trace-spec-grammar")
    @pytest.mark.parametrize("rid", ["Does_Y", "foo-command-can-do-y-and-z"])
    def it_fails_an_id_that_breaks_the_grammar(self, make_repo, run, rid):
        spec = FOO_SPEC + "- `%s` (test): When asked, foo does y.\n" % rid
        code, _, err = run("trace", "-C", str(make_repo({"specs/foo.md": spec})))
        assert code == cp.PROBLEMS
        assert "`%s` is not an id" % rid in err

    @pytest.mark.spec("trace-spec-grammar")
    def it_traces_an_id_of_six_words(self, make_repo, run):
        rid = "steps-command-does-x-when-asked"
        root = make_repo(
            {
                "specs/foo.md": FOO_SPEC + "- `%s` (test): When asked, foo does x.\n" % rid,
                TEST: suite_file(class_marker='@pytest.mark.spec("%s")\n' % rid),
            }
        )
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.OK, err

    @pytest.mark.spec("trace-spec-grammar")
    @pytest.mark.parametrize(
        ("kind", "says"),
        [("eval", "nothing in this repo runs one yet"), ("manual", "names the kind")],
    )
    def it_fails_a_kind_nothing_here_verifies(self, make_repo, run, kind, says):
        spec = FOO_SPEC + "- `does-z` (%s): When asked, foo does z.\n" % kind
        code, _, err = run("trace", "-C", str(make_repo({"specs/foo.md": spec})))
        assert code == cp.PROBLEMS
        assert says in err

    @pytest.mark.spec("trace-scans-something")
    def it_fails_when_there_is_no_spec(self, make_repo, run):
        root = make_repo({"specs/foo.md": None, "specs/repo.md": None, TEST: None, REPO_TEST: None})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "found no spec file" in err

    @pytest.mark.spec("trace-scans-something")
    def it_fails_when_there_is_no_test(self, make_repo, run):
        root = make_repo({TEST: None, REPO_TEST: None})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "found no test;" in err

    @pytest.mark.spec("trace-scans-something")
    def it_fails_when_there_is_no_step(self, make_repo, run):
        root = make_repo({SKILL: None})
        code, _, err = run("trace", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "found no step;" in err

    @pytest.mark.spec("trace-uncited")
    def it_prints_one_envelope_on_stdout_with_json(self, make_repo, run):
        code, out, err = run("trace", "--json", "-C", str(make_repo()))
        assert code == cp.OK
        assert err == ""
        result = json.loads(out)
        assert set(result) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert result["command"] == "trace"
        tests = {t["id"]: t["cites"] for t in result["data"]["tests"]}
        assert tests[TEST_ID] == ["does-x"]

    @pytest.mark.spec("trace-listed-warns")
    def it_accepts_the_repo_as_it_stands(self, run):
        code, _, err = run("trace", "-C", str(REPO_ROOT))
        assert code == cp.OK, err


def coverage_report(contexts=True):
    ran = {
        "3": [""],
        "10": [TEST_ID + "|run"],
        "11": [TEST_ID + "[p1]|run", TEST_ID + "[p2]|setup"],
        "12": [TEST_ID + "|run"],
    }
    entry = {"missing_lines": [4, 5, 6, 14]}
    if contexts:
        entry["contexts"] = ran
    return json.dumps({"meta": {"show_contexts": contexts}, "files": {SCRIPT: entry}})


class DescribeInventory:
    @pytest.fixture
    def listed(self, make_repo, run):
        root = make_repo({cp.DEFAULT_REPORT: coverage_report()})
        code, out, err = run("inventory", "foo", "--json", "-C", str(root))
        assert code == cp.OK, err
        return json.loads(out)["data"]

    @staticmethod
    def surface(data, kind, label):
        for item in data["surface"]:
            if item["kind"] != kind:
                continue
            name = item["command"]
            if kind != "command":
                name += " " + item["option"]
            if kind == "choice":
                name += " " + item["value"]
            if name == label:
                return item
        raise AssertionError("%s %s not listed" % (kind, label))

    @pytest.mark.spec("inventory-surface")
    def it_lists_a_subcommand_with_the_invocation_that_runs_it(self, listed):
        item = self.surface(listed, "command", "go")
        assert [n["path"] for n in item["named_by"]] == [SKILL, SKILL]

    @pytest.mark.spec("inventory-surface")
    def it_lists_an_option_named_only_in_prose(self, listed):
        item = self.surface(listed, "option", "go --skip")
        assert item["named_by"] == [{"path": SKILL, "line": 22, "text": "go --skip"}]

    @pytest.mark.spec("inventory-surface")
    def it_lists_each_choices_value_and_what_names_it(self, listed):
        assert self.surface(listed, "choice", "go --mode a")["named_by"][0]["line"] == 19
        assert self.surface(listed, "choice", "go --mode b")["named_by"] == []

    @pytest.mark.spec("inventory-collections")
    def it_lists_each_collection_of_strings_and_resolves_named_ones(self, listed):
        found = {c["name"]: c["items"] for c in listed["collections"]}
        assert found["MODES"] == ["a", "b"]
        assert sorted(found["NAMED"]) == ["c", "d"]
        assert "MIXED" not in found

    @pytest.mark.spec("inventory-tests")
    def it_lists_each_test_with_the_lines_it_runs(self, listed):
        assert listed["tests"] == [
            {"id": TEST_ID, "line": 6, "cites": ["does-x"], "runs": {SCRIPT: ["10-12"]}}
        ]

    @pytest.mark.spec("inventory-steps")
    def it_lists_each_step_with_the_commands_it_runs(self, listed):
        steps = {s["id"]: s for s in listed["steps"]}
        assert [c["argv"] for c in steps[STEP_ID]["commands"]] == [["go", "--mode", "a"]]
        assert steps[SKILL + "::2"]["commands"] == []

    @pytest.mark.spec("inventory-unrun")
    def it_lists_the_lines_no_test_runs(self, listed):
        assert listed["unrun"] == {SCRIPT: ["4-6", "14"]}

    @pytest.mark.spec("inventory-surface")
    def it_prints_each_section_without_json(self, make_repo, run):
        root = make_repo({cp.DEFAULT_REPORT: coverage_report()})
        code, out, _ = run("inventory", "foo", "-C", str(root))
        assert code == cp.OK
        assert "option go --skip: %s:22" % SKILL in out
        assert "choice go --mode b: named by no skill text" in out
        assert "%s: %s 10-12" % (TEST_ID, SCRIPT) in out

    @pytest.mark.spec("inventory-per-test-report")
    def it_stops_on_a_report_that_does_not_name_each_line_s_tests(self, make_repo, run):
        root = make_repo({cp.DEFAULT_REPORT: coverage_report(contexts=False)})
        code, out, err = run("inventory", "foo", "-C", str(root))
        assert code == cp.CANNOT_RUN
        assert out == ""
        assert "--cov-context=test" in err

    @pytest.mark.spec("inventory-per-test-report")
    def it_stops_when_there_is_no_report(self, make_repo, run):
        code, _, err = run("inventory", "foo", "-C", str(make_repo()))
        assert code == cp.CANNOT_RUN
        assert "no coverage report" in err

    @pytest.mark.spec("inventory-surface")
    def it_stops_on_a_plugin_with_no_script(self, make_repo, run):
        root = make_repo({cp.DEFAULT_REPORT: coverage_report()})
        code, _, err = run("inventory", "bar", "-C", str(root))
        assert code == cp.CANNOT_RUN
        assert "Name a plugin that has one: foo." in err


SEAM_SKILL = "plugins/prose-tuning/skills/adopt-prose/SKILL.md"


def listed_test(issue):
    """A clone where the test waits on `issue`, and nothing else is out of step."""
    return {
        TEST: suite_file(method_marker=""),
        SKILL: skill(
            step_one_marker="<!-- spec: does-x -->\n",
            step_two_marker="<!-- spec: asks-once -->\n",
        ),
        "specs/foo.md": FOO_SPEC.replace("(test)", "(step)"),
        cp.UNTRACED_FILE: untraced({TEST_ID: issue}),
    }


class DescribeTraceOnClosedIssues:
    @pytest.mark.spec("trace-closed-issue")
    def it_fails_a_listed_test_whose_issue_has_closed(self, make_repo, run):
        github = FakeGitHub({130: {"state": "CLOSED"}})
        code, _, err = run(
            "trace", "-C", str(make_repo(listed_test(130))), environ=GITHUB_ENV, graphql=github
        )
        assert code == cp.PROBLEMS
        assert "lists %s for #130, which has closed" % TEST_ID in err

    @pytest.mark.spec("trace-closed-issue")
    def it_fails_a_known_seams_step_whose_issue_has_closed(self, make_repo, run):
        root = make_repo({SEAM_SKILL: "---\nname: adopt-prose\n---\n"})
        github = FakeGitHub({n: {"state": "CLOSED"} for n in range(1000)})
        code, _, err = run("trace", "-C", str(root), environ=GITHUB_ENV, graphql=github)
        assert code == cp.PROBLEMS
        assert "KNOWN_SEAMS lists step 1 of %s for #" % SEAM_SKILL in err

    @pytest.mark.spec("trace-closed-issue", "trace-listed-warns")
    def it_passes_a_listed_test_whose_issue_is_open(self, make_repo, run):
        github = FakeGitHub({130: {"state": "OPEN"}})
        code, _, err = run(
            "trace", "-C", str(make_repo(listed_test(130))), environ=GITHUB_ENV, graphql=github
        )
        assert code == cp.OK, err
        assert "#130 will trace them" in err
        assert len(github.queries) == 1

    @pytest.mark.spec("trace-closed-issue")
    def it_warns_that_it_did_not_look_without_a_token(self, make_repo, run):
        code, _, err = run("trace", "-C", str(make_repo(listed_test(130))))
        assert code == cp.OK, err
        assert "did not check that the issues" in err
        assert "GITHUB_TOKEN" in err

    @pytest.mark.spec("trace-closed-issue")
    def it_stops_on_an_issue_it_cannot_read(self, make_repo, run):
        code, _, err = run(
            "trace",
            "-C",
            str(make_repo(listed_test(130))),
            environ=GITHUB_ENV,
            graphql=FakeGitHub({}),
        )
        assert code == cp.CANNOT_RUN
        assert err.startswith("check-specs.py: cannot read #130")


NAMING_SPEC = FOO_SPEC + (
    "- `goes` (test): When `go --mode a` or `go --mode b` runs, foo goes,\n"
    "  and `go --skip` leaves one out.\n"
)
GO = SCRIPT + "::go"


class DescribeSurface:
    @pytest.mark.spec("surface-unnamed")
    def it_passes_when_a_requirement_names_every_item(self, make_repo, run):
        code, out, err = run("surface", "-C", str(make_repo({"specs/foo.md": NAMING_SPEC})))
        assert code == cp.OK, err
        assert "5 item(s) of 1 parser(s); 5 named" in out

    @pytest.mark.spec("surface-unnamed")
    def it_fails_an_unnamed_subcommand_option_and_choice(self, make_repo, run):
        code, _, err = run("surface", "-C", str(make_repo()))
        assert code == cp.PROBLEMS
        for item in (GO, GO + " --skip", GO + " --mode b"):
            assert "%s is named by no requirement in specs/foo.md or specs/repo.md" % item in err

    @pytest.mark.spec("surface-unnamed")
    def it_ignores_a_name_in_a_skill(self, make_repo, run):
        code, _, err = run("surface", "-C", str(make_repo()))
        assert code == cp.PROBLEMS
        assert "%s --skip is named by no requirement" % GO in err

    @pytest.mark.spec("surface-unnamed")
    def it_counts_a_name_in_the_repo_spec(self, make_repo, run):
        spec = NAMING_SPEC.replace(", foo goes,\n  and `go --skip` leaves one out.", ".")
        repo = REPO_SPEC + "- `skips` (test): When `--skip` is given, a step is left out.\n"
        code, _, err = run(
            "surface", "-C", str(make_repo({"specs/foo.md": spec, "specs/repo.md": repo}))
        )
        assert code == cp.OK, err

    @pytest.mark.spec("surface-unnamed")
    def it_counts_a_script_s_file_name_only_for_that_script(self, make_repo, run):
        other = NAMING_SPEC.replace("`go --skip`", "`bar.py go --skip`")
        code, _, err = run("surface", "-C", str(make_repo({"specs/foo.md": other})))
        assert code == cp.PROBLEMS
        assert "%s --skip is named by no requirement" % GO in err
        own = NAMING_SPEC.replace("`go --skip`", "`foo.py go --skip`")
        code, _, err = run("surface", "-C", str(make_repo({"specs/foo.md": own}, name="own")))
        assert code == cp.OK, err

    @pytest.mark.spec("surface-unnamed")
    def it_reads_a_repo_script_and_skips_one_with_no_parser(self, make_repo, run):
        tool = SOURCE.replace('prog="foo"', 'prog="tool"')
        root = make_repo(
            {
                "specs/foo.md": NAMING_SPEC,
                ".github/scripts/tool.py": tool,
                ".github/scripts/plain.py": "print('no parser')\n",
            }
        )
        code, _, err = run("surface", "-C", str(root))
        assert code == cp.PROBLEMS
        assert ".github/scripts/tool.py::go is named by no requirement in specs/repo.md." in err
        assert "plain.py" not in err

    @pytest.mark.spec("surface-listed-warns")
    def it_passes_a_listed_item_with_a_warning_naming_its_issue(self, make_repo, run):
        spec = NAMING_SPEC.replace("\n  and `go --skip` leaves one out.", "")
        root = make_repo(
            {"specs/foo.md": spec, cp.UNTRACED_FILE: untraced(surface={GO + " --skip": 173})}
        )
        code, _, err = run("surface", "-C", str(root))
        assert code == cp.OK, err
        assert "1 item(s) are named by no requirement yet; #173 will settle them." in err

    @pytest.mark.spec("surface-listed-warns")
    def it_fails_a_listed_item_a_requirement_now_names(self, make_repo, run):
        root = make_repo(
            {"specs/foo.md": NAMING_SPEC, cp.UNTRACED_FILE: untraced(surface={GO: 173})}
        )
        code, _, err = run("surface", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "%s is now named by a requirement. Remove its entry" % GO in err

    @pytest.mark.spec("surface-listed-warns")
    def it_fails_a_listed_item_no_parser_has(self, make_repo, run):
        root = make_repo(
            {"specs/foo.md": NAMING_SPEC, cp.UNTRACED_FILE: untraced(surface={GO + " --gone": 1})}
        )
        code, _, err = run("surface", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "lists %s --gone for #1, and no parser has it" % GO in err

    @pytest.mark.spec("surface-scans-something")
    def it_fails_when_there_is_no_parser(self, make_repo, run):
        code, _, err = run("surface", "-C", str(make_repo({SCRIPT: None})))
        assert code == cp.PROBLEMS
        assert "found no script with a build_parser()" in err

    @pytest.mark.spec("surface-listed-warns")
    def it_accepts_the_repo_as_it_stands(self, run):
        code, _, err = run("surface", "-C", str(REPO_ROOT))
        assert code == cp.OK, err


APPROVED_AT = "2026-09-01T10:00:00Z"
NEW_NEED = (
    "\n## need user-goes-fast: Go fast\n\n"
    "When a user is in a hurry, they want foo to go fast.\n\n"
    "- `foo-goes-fast` (test): When foo goes, it is quick.\n"
)


def approved_issue(body="", edited=None, labeled=(APPROVED_AT,)):
    return {
        "body": body,
        "lastEditedAt": edited,
        "timelineItems": {
            "nodes": [{"createdAt": at, "label": {"name": "approved"}} for at in labeled]
        },
    }


@pytest.fixture
def pull_request(make_repo, tmp_path):
    """A clone whose HEAD is the base, with `changes` in the working tree as the
    pull request, and the event GitHub would write for a pull request with `body`."""

    def make(changes=None, body="", title="t"):
        root = make_repo()
        git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
        subprocess.run([*git, "commit", "-q", "-m", "base"], check=True, capture_output=True)
        for rel, text in (changes or {}).items():
            path = root / rel
            if text is None:
                path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        event = tmp_path / "event.json"
        event.write_text(json.dumps({"pull_request": {"title": title, "body": body}}))
        environ = dict(GITHUB_ENV, GITHUB_EVENT_PATH=str(event))
        return root, environ

    return make


def disclosed(run, root, environ, github=None):
    return run(
        "disclosed",
        "--base",
        "HEAD",
        "-C",
        str(root),
        environ=environ,
        graphql=github or FakeGitHub({}),
    )


class DescribeDisclosed:
    @pytest.mark.spec("disclosed-lists-ids")
    def it_passes_a_pull_request_that_changes_no_spec(self, pull_request, run):
        code, out, err = disclosed(run, *pull_request())
        assert code == cp.OK, err
        assert "0 requirement change(s) and 0 new need(s)" in out

    @pytest.mark.spec("disclosed-lists-ids")
    @pytest.mark.parametrize(
        ("spec", "how"),
        [
            (FOO_SPEC + "- `foo-does-y` (test): When asked, foo does y.\n", "added"),
            (FOO_SPEC.replace("foo does x", "foo does x twice"), "changed"),
            (FOO_SPEC.replace("(test): When asked", "(step): When asked"), "changed"),
            (FOO_SPEC.replace("- `does-x` (test): When asked, foo does x.\n", ""), "removed"),
        ],
    )
    def it_fails_a_requirement_change_the_description_does_not_name(
        self, pull_request, run, spec, how
    ):
        code, _, err = disclosed(run, *pull_request({"specs/foo.md": spec}))
        assert code == cp.PROBLEMS
        assert (
            "in specs/foo.md was %s, and the pull request description does not name it" % how in err
        )

    @pytest.mark.spec("disclosed-lists-ids")
    def it_passes_each_id_the_description_names(self, pull_request, run):
        spec = FOO_SPEC.replace("foo does x", "foo does x twice") + (
            "- `foo-does-y` (test): When asked, foo does y.\n"
        )
        body = "### Requirements\n\n- `does-x`, changed\n- `foo:foo-does-y`, added\n"
        code, out, err = disclosed(run, *pull_request({"specs/foo.md": spec}, body=body))
        assert code == cp.OK, err
        assert "2 requirement change(s)" in out

    @pytest.mark.spec("disclosed-lists-ids")
    def it_does_not_count_rewrapping_as_a_change(self, pull_request, run):
        spec = FOO_SPEC.replace(
            "skill asks them\n  in one batch", "skill\n  asks them in one batch"
        )
        code, _, err = disclosed(run, *pull_request({"specs/foo.md": spec}))
        assert code == cp.OK, err

    @pytest.mark.spec("disclosed-lists-ids")
    def it_reads_every_requirement_of_a_new_spec_file(self, pull_request, run):
        bar = "# bar\n\n## constraint bar-is-slow: Bar is slow\n\nIt is.\n\n- `bar-waits` (test): Bar waits.\n"
        code, _, err = disclosed(run, *pull_request({"specs/bar.md": bar}))
        assert code == cp.PROBLEMS
        assert "`bar-waits` in specs/bar.md was added" in err

    @pytest.mark.spec("disclosed-new-need")
    def it_fails_a_new_need_when_the_pull_request_closes_no_issue(self, pull_request, run):
        code, _, err = disclosed(
            run, *pull_request({"specs/foo.md": FOO_SPEC + NEW_NEED}, body="`foo-goes-fast`")
        )
        assert code == cp.PROBLEMS
        assert "adds the need `user-goes-fast`, and the pull request closes no issue" in err

    @pytest.mark.spec("disclosed-new-need")
    def it_fails_a_new_need_its_issue_does_not_name(self, pull_request, run):
        root, environ = pull_request(
            {"specs/foo.md": FOO_SPEC + NEW_NEED}, body="Closes #7\n`foo-goes-fast`"
        )
        github = FakeGitHub({7: approved_issue("Adds user-goes-faster.")})
        code, _, err = disclosed(run, root, environ, github)
        assert code == cp.PROBLEMS
        assert "adds the need `user-goes-fast`, which #7 does not name" in err

    @pytest.mark.spec("disclosed-new-need")
    def it_passes_a_new_need_its_issue_names(self, pull_request, run):
        root, environ = pull_request(
            {"specs/foo.md": FOO_SPEC + NEW_NEED}, body="Closes #7\n`foo-goes-fast`"
        )
        github = FakeGitHub({7: approved_issue("Adds `need user-goes-fast`.")})
        code, out, err = disclosed(run, root, environ, github)
        assert code == cp.OK, err
        assert "1 new need(s)" in out

    @pytest.mark.spec("disclosed-edited-after-approval")
    def it_fails_an_issue_edited_after_approval(self, pull_request, run):
        root, environ = pull_request(body="Closes #7")
        github = FakeGitHub({7: approved_issue(edited="2026-09-02T10:00:00Z")})
        code, _, err = disclosed(run, root, environ, github)
        assert code == cp.PROBLEMS
        assert "#7 was edited at 2026-09-02T10:00:00Z, after `approved` was added" in err
        assert "removing the label and adding it again" in err

    @pytest.mark.spec("disclosed-edited-after-approval")
    def it_passes_once_the_label_is_added_again(self, pull_request, run):
        root, environ = pull_request(body="Closes #7")
        issue = approved_issue(
            edited="2026-09-02T10:00:00Z", labeled=(APPROVED_AT, "2026-09-03T10:00:00Z")
        )
        code, _, err = disclosed(run, root, environ, FakeGitHub({7: issue}))
        assert code == cp.OK, err

    @pytest.mark.spec("disclosed-edited-after-approval")
    def it_leaves_an_unapproved_issue_to_the_linked_issue_check(self, pull_request, run):
        root, environ = pull_request(body="Closes #7")
        issue = approved_issue(edited="2026-09-02T10:00:00Z", labeled=())
        code, _, err = disclosed(run, root, environ, FakeGitHub({7: issue}))
        assert code == cp.OK, err

    @pytest.mark.spec("disclosed-edited-after-approval")
    def it_stops_on_an_issue_it_cannot_read(self, pull_request, run):
        code, _, err = disclosed(run, *pull_request(body="Closes #7"))
        assert code == cp.CANNOT_RUN
        assert err.startswith("check-specs.py: cannot read #7")

    @pytest.mark.spec("disclosed-lists-ids")
    def it_stops_outside_a_pull_request_event(self, make_repo, run):
        code, _, err = run(
            "disclosed", "--base", "HEAD", "-C", str(make_repo()), environ=GITHUB_ENV
        )
        assert code == cp.CANNOT_RUN
        assert "GITHUB_EVENT_PATH is not set" in err

    @pytest.mark.spec("disclosed-checks-new-ids")
    @pytest.mark.parametrize(
        ("rid", "says"),
        [
            ("foo", "it has 1 word(s), and an id has 2 to 5"),
            ("receipt-late-fee", "`late` is not a verb ending in `s`"),
            ("steps-command", "it has 1 word(s)"),
            ("steps-command-late-x", "`late` is not a verb ending in `s`"),
            ("foo-does-x-and-y-too", "it has 6 word(s)"),
            ("foo-cannot", "`cannot` is followed by no verb"),
            ("foo-never-drop-x", "`never` is followed by `drop`"),
        ],
    )
    def it_fails_a_new_requirement_id_not_in_the_form(self, pull_request, run, rid, says):
        spec = FOO_SPEC + "- `%s` (test): When asked, foo does y.\n" % rid
        code, _, err = disclosed(run, *pull_request({"specs/foo.md": spec}, body="`%s`" % rid))
        assert code == cp.PROBLEMS
        assert "specs/foo.md adds the requirement `%s`, and %s" % (rid, says) in err
        assert 'SPEC-METHODOLOGY.md, under "Ids", has the form' in err

    @pytest.mark.spec("disclosed-checks-new-ids")
    def it_fails_a_new_need_id_that_opens_with_no_role(self, pull_request, run):
        spec = FOO_SPEC + NEW_NEED.replace("user-goes-fast", "foo-goes-fast-need")
        root, environ = pull_request({"specs/foo.md": spec}, body="Closes #7\n`foo-goes-fast`")
        github = FakeGitHub({7: approved_issue("Adds `need foo-goes-fast-need`.")})
        code, _, err = disclosed(run, root, environ, github)
        assert code == cp.PROBLEMS
        assert "adds the need `foo-goes-fast-need`, and a need's id opens with the role" in err

    @pytest.mark.spec("disclosed-checks-new-ids")
    def it_fails_a_new_constraint_id_not_in_the_form(self, pull_request, run):
        bar = "# bar\n\n## constraint slow-bar: Bar is slow\n\nIt is.\n\n- `bar-waits` (test): Bar waits.\n"
        code, _, err = disclosed(run, *pull_request({"specs/bar.md": bar}, body="`bar-waits`"))
        assert code == cp.PROBLEMS
        assert "specs/bar.md adds the constraint `slow-bar`, and `bar` is not a verb" in err

    @pytest.mark.spec("disclosed-checks-new-ids")
    @pytest.mark.parametrize(
        "rid",
        [
            "foo-does-y",
            "foo-cannot-drop-y",
            "foo-only-reads-y",
            "foo-does-y-when-asked",
            "steps-command-counts-step-commands",
            "steps-command-does-y-when-asked",
            "steps-command-never-drops-y",
            "claim-command-adds-y",
        ],
    )
    def it_passes_a_new_id_in_the_form(self, pull_request, run, rid):
        spec = FOO_SPEC + "- `%s` (test): When asked, foo does y.\n" % rid
        code, _, err = disclosed(run, *pull_request({"specs/foo.md": spec}, body="`%s`" % rid))
        assert code == cp.OK, err

    @pytest.mark.spec("disclosed-checks-new-ids")
    def it_leaves_an_id_already_on_the_base_alone(self, pull_request, run):
        spec = FOO_SPEC.replace("## need does-things: Do things", "## need does-things: Do all")
        spec = spec.replace("foo does x", "foo does x twice")
        code, _, err = disclosed(run, *pull_request({"specs/foo.md": spec}, body="`does-x`"))
        assert code == cp.OK, err

    @pytest.mark.spec("disclosed-checks-new-ids")
    def it_checks_a_renamed_id(self, pull_request, run):
        spec = FOO_SPEC.replace("`does-x`", "`foo-x`")
        body = "`does-x` `foo-x`"
        code, _, err = disclosed(run, *pull_request({"specs/foo.md": spec}, body=body))
        assert code == cp.PROBLEMS
        assert "adds the requirement `foo-x`" in err

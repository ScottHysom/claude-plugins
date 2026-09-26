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

    def make(changes=None):
        root = tmp_path / "repo"
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


@pytest.fixture
def run(capsys):
    """Drive a command through main() so argparse defaults are the real ones."""

    def go(*argv):
        capsys.readouterr()
        code = cp.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


def untraced(tests=None, steps=None):
    return json.dumps({"tests": tests or {}, "steps": steps or {}})


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
    def it_fails_an_id_that_breaks_the_grammar(self, make_repo, run):
        spec = FOO_SPEC + "- `Does_Y` (test): When asked, foo does y.\n"
        code, _, err = run("trace", "-C", str(make_repo({"specs/foo.md": spec})))
        assert code == cp.PROBLEMS
        assert "`Does_Y` is not an id" in err

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

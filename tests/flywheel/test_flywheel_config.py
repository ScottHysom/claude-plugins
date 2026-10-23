"""What `flywheel.py config init` writes, and what it leaves to the owner."""

import json

import pytest

import flywheel

ROLES = ".flywheel/roles.json"
REVIEW = ".flywheel/review-policy.md"
MERGE = ".flywheel/merge-policy.md"
GATES = ".flywheel/gates.json"
FILES = [ROLES, REVIEW, MERGE, GATES]
OWNER_FIELDS = [
    "roles.dispatcher.model",
    "roles.dispatcher.effort",
    "roles.implementer.model",
    "roles.implementer.effort",
    "roles.reviewer.model",
    "roles.reviewer.effort",
]
GATE_FIELDS = ["gates.build", "gates.test", "gates.check", "gates.verify"]
UNSET_GATES = {"build": None, "test": None, "check": None, "verify": None}
SET_GATES = {"build": "make", "test": "make test", "check": "make check", "verify": "make verify"}


def written(env):
    return {f["file"]: f["written"] for f in env["data"]["files"]}


def fields(env, rel):
    return next(f["owner_fields"] for f in env["data"]["files"] if f["file"] == rel)


def shipped(name):
    plugin = flywheel.os.path.dirname(flywheel.os.path.dirname(flywheel.SCRIPT_PATH))
    with open(flywheel.os.path.join(plugin, "templates", name), "rb") as fh:
        return fh.read()


def plugin_version():
    path = flywheel.os.path.join(
        flywheel.os.path.dirname(flywheel.os.path.dirname(flywheel.SCRIPT_PATH)),
        ".claude-plugin",
        "plugin.json",
    )
    with open(path) as fh:
        return json.load(fh)["version"]


@pytest.mark.spec("configinit-cmd-writes-roles-file")
class DescribeTheRolesFile:
    def it_writes_one_entry_per_role(self, project):
        code, env = project.run("config", "init")
        assert code == flywheel.OK
        assert written(env)[ROLES] is True
        roles = json.loads(project.read(ROLES))["roles"]
        assert list(roles) == ["dispatcher", "implementer", "reviewer"]

    def it_gives_each_role_its_tier_model_effort_and_version(self, project):
        project.run("config", "init")
        roles = json.loads(project.read(ROLES))["roles"]
        assert roles["implementer"] == {
            "tier": 3,
            "model": None,
            "effort": None,
            "version": plugin_version(),
        }
        assert [roles[r]["tier"] for r in ("dispatcher", "reviewer")] == [2, 2]

    def it_says_what_it_wrote_in_text(self, project):
        code, out, err = project.human("config", "init")
        assert code == flywheel.OK
        assert out.startswith("wrote .flywheel/roles.json\n")
        assert err == ""

    def it_leaves_the_files_for_git_after_setup(self, project):
        project.run("setup")
        project.run("config", "init")
        assert project.git("status", "--porcelain", "--untracked-files=all") == (
            b"?? .flywheel/gates.json\n?? .flywheel/merge-policy.md\n"
            b"?? .flywheel/review-policy.md\n?? .flywheel/roles.json\n"
        )


@pytest.mark.spec("configinit-cmd-writes-policies")
class DescribeThePolicies:
    def it_writes_both_policies_from_the_templates(self, project):
        code, env = project.run("config", "init")
        assert code == flywheel.OK
        assert written(env) == {ROLES: True, REVIEW: True, MERGE: True, GATES: True}
        assert project.read(REVIEW) == shipped("review-policy.md")
        assert project.read(MERGE) == shipped("merge-policy.md")

    def it_writes_the_policies_beside_a_roles_file_that_exists(self, project):
        project.write(ROLES, '{"mine": true}\n')
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert written(env) == {ROLES: False, REVIEW: True, MERGE: True, GATES: True}
        assert project.read(REVIEW) == shipped("review-policy.md")
        assert env["errors"] == [
            "%s already exists, so it was left as it is. Edit it to change it, or delete it and"
            " run config init again to start from the template." % ROLES
        ]

    def it_refuses_to_overwrite_a_policy(self, project):
        project.write(MERGE, "mine\n")
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert written(env) == {ROLES: True, REVIEW: True, MERGE: False, GATES: True}
        assert project.read(MERGE) == b"mine\n"

    @pytest.mark.parametrize(
        "text",
        ["no settings here\n", "```json\n[1]\n```\n", "```json\n{oops\n```\n"],
    )
    def it_writes_nothing_when_a_policy_template_is_broken(self, project, plugin_copy, text):
        (plugin_copy / "templates" / "merge-policy.md").write_text(text)
        code, env = project.run("config", "init")
        assert (code, env) == (flywheel.CANNOT_RUN, None)
        assert "Install the flywheel plugin again" in project.err
        assert not (project.root / ".flywheel").exists()


@pytest.mark.spec("configinit-cmd-writes-roles-file")
class DescribeAnExistingRolesFile:
    def it_refuses_to_overwrite_it(self, project):
        project.write(ROLES, '{"mine": true}\n')
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert env["ok"] is False
        assert written(env)[ROLES] is False
        assert project.read(ROLES) == b'{"mine": true}\n'

    def it_says_how_to_start_again(self, project):
        for rel in FILES:
            project.write(rel, json.dumps({"gates": SET_GATES, "tests": {}}))
        code, out, err = project.human("config", "init")
        assert code == flywheel.PROBLEMS
        assert out == ""
        assert "already exists" in err
        assert "delete it and run config init again" in err

    def it_refuses_a_link_whose_target_is_gone(self, project):
        (project.root / ".flywheel").mkdir()
        (project.root / ROLES).symlink_to(project.root / "gone.json")
        code, _ = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert not (project.root / "gone.json").exists()


@pytest.mark.spec("configinit-cmd-names-owner-fields")
class DescribeTheOwnersFields:
    def it_names_each_field_left_for_the_owner(self, project):
        _, env = project.run("config", "init")
        assert fields(env, ROLES) == OWNER_FIELDS

    def it_names_each_policy_setting_left_for_the_owner(self, project):
        _, env = project.run("config", "init")
        assert fields(env, REVIEW) == ["rules"]
        assert fields(env, MERGE) == []

    def it_lists_them_in_text(self, project):
        _, out, _ = project.human("config", "init")
        named = ["%s: %s" % (ROLES, f) for f in OWNER_FIELDS]
        named += ["%s: rules" % REVIEW]
        named += ["%s: %s" % (GATES, f) for f in GATE_FIELDS]
        named += ["%s: tests.%s" % (GATES, f) for f in ("list", "run", "paths")]
        assert out == "%s\nthe owner fills in each of these:\n%s" % (
            "".join("wrote %s\n" % rel for rel in FILES),
            "".join("  %s\n" % f for f in named),
        )

    def it_names_nothing_when_the_template_fills_every_field(self, project, plugin_copy):
        template = plugin_copy / "templates" / "roles.json"
        template.write_text(json.dumps({"roles": {"implementer": {"tier": 3, "model": "m"}}}))
        for name in ("review-policy.md", "merge-policy.md"):
            (plugin_copy / "templates" / name).write_text('```json\n{"set": 1}\n```\n')
        project.write("pytest.ini", "[pytest]\ntestpaths = tests\n")
        project.write(GATES, json.dumps({"gates": SET_GATES}))
        code, out, _ = project.human("config", "init")
        assert code == flywheel.OK
        assert out == "".join("wrote %s\n" % rel for rel in FILES)


PYTEST_LIST = "python3 -m pytest --collect-only -q -p no:cacheprovider"
PYTEST_RUN = "python3 -m pytest -q -p no:cacheprovider {id}"
PYTEST_REPORT = (
    "python3 -m pytest -q -p no:cacheprovider --continue-on-collection-errors"
    " --junitxml={report} {files}"
)


def tests_object(project):
    return json.loads(project.read(GATES))["tests"]


def owner_test_fields(env):
    return [f for f in fields(env, GATES) if f.startswith("tests.")]


@pytest.mark.spec("configinit-cmd-fills-pytest-test-commands")
class DescribeTheTestCommands:
    @pytest.mark.parametrize(
        ("rel", "text"),
        [
            ("pytest.ini", "[pytest]\ntestpaths = tests extra\n"),
            ("setup.cfg", "[metadata]\nname = x\n\n[tool:pytest]\ntestpaths =\n  tests\n  extra\n"),
            (
                "pyproject.toml",
                '[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                'testpaths = [\n  "tests",\n  "extra",\n]\n\n[tool.ruff]\nline-length = 99\n',
            ),
        ],
    )
    def it_fills_them_in_from_the_pytest_config(self, project, rel, text):
        project.write(rel, text)
        code, env = project.run("config", "init")
        assert code == flywheel.OK
        assert tests_object(project) == {
            "list": PYTEST_LIST,
            "run": PYTEST_RUN,
            "report": PYTEST_REPORT,
            "paths": ["tests", "extra", rel],
        }
        assert owner_test_fields(env) == []

    def it_reads_testpaths_given_as_one_string_in_pyproject(self, project):
        project.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = "tests"\n')
        project.run("config", "init")
        assert tests_object(project)["paths"] == ["tests", "pyproject.toml"]

    def it_leaves_the_paths_to_the_owner_without_testpaths(self, project):
        project.write("pytest.ini", "[pytest]\naddopts = -ra\n")
        _, env = project.run("config", "init")
        assert tests_object(project)["paths"] is None
        assert tests_object(project)["run"] == PYTEST_RUN
        assert owner_test_fields(env) == ["tests.paths"]

    def it_leaves_every_field_to_the_owner_for_another_runner(self, project):
        project.write("pyproject.toml", "[tool.ruff]\nline-length = 99\n")
        _, env = project.run("config", "init")
        assert tests_object(project) == {"list": None, "run": None, "paths": None}
        assert owner_test_fields(env) == ["tests.list", "tests.run", "tests.paths"]

    def it_keeps_the_gates_the_file_names(self, project):
        project.write(GATES, '{"gates": {"check": "make check"}}\n')
        project.write("pytest.ini", "[pytest]\ntestpaths = tests\n")
        code, env = project.run("config", "init")
        assert code == flywheel.OK
        written_gates = json.loads(project.read(GATES))
        assert written_gates["gates"]["check"] == "make check"
        assert written_gates["tests"]["paths"] == ["tests", "pytest.ini"]

    def it_refuses_to_overwrite_test_commands_that_exist(self, project):
        text = json.dumps({"gates": SET_GATES, "tests": {"list": "mine"}})
        project.write(GATES, text)
        project.write("pytest.ini", "[pytest]\ntestpaths = tests\n")
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert written(env)[GATES] is False
        assert project.read(GATES) == text.encode()
        assert '%s already gives "tests"' % GATES in env["errors"][0]

    def it_stops_on_a_pytest_config_it_cannot_read(self, project):
        project.write("pytest.ini", "testpaths = tests\n")
        code, _ = project.run("config", "init")
        assert code == flywheel.CANNOT_RUN
        assert "pytest.ini cannot be read as an ini file" in project.err
        assert not (project.root / GATES).exists()

    def it_takes_a_pyproject_without_testpaths(self, project):
        project.write("pyproject.toml", '[tool.pytest.ini_options]\naddopts = "-ra"\n')
        _, env = project.run("config", "init")
        assert tests_object(project)["list"] == PYTEST_LIST
        assert owner_test_fields(env) == ["tests.paths"]

    def it_passes_over_a_setup_cfg_without_the_pytest_section(self, project):
        project.write("setup.cfg", "[metadata]\nname = x\n")
        _, env = project.run("config", "init")
        assert owner_test_fields(env) == ["tests.list", "tests.run", "tests.paths"]

    def it_stops_on_a_gates_file_that_is_not_an_object(self, project):
        project.write(GATES, "[]\n")
        code, _ = project.run("config", "init")
        assert code == flywheel.CANNOT_RUN
        assert "%s does not hold a JSON object" % GATES in project.err
        assert not (project.root / ROLES).exists()


@pytest.mark.spec("configinit-cmd-fills-pytest-report-command")
class DescribeTheReportCommand:
    def it_fills_in_the_pytest_report_command(self, project):
        project.write("pytest.ini", "[pytest]\ntestpaths = tests\n")
        code, env = project.run("config", "init")
        assert code == flywheel.OK
        assert tests_object(project)["report"] == PYTEST_REPORT
        assert owner_test_fields(env) == []

    def it_leaves_the_report_command_unset_for_another_runner(self, project):
        project.write("pyproject.toml", "[tool.ruff]\nline-length = 99\n")
        _, env = project.run("config", "init")
        assert "report" not in tests_object(project)
        assert "tests.report" not in owner_test_fields(env)


@pytest.mark.spec("configinit-cmd-writes-gate-fields")
class DescribeTheGates:
    def it_writes_each_gate_unset_into_a_new_file(self, project):
        code, env = project.run("config", "init")
        assert code == flywheel.OK
        assert json.loads(project.read(GATES))["gates"] == UNSET_GATES
        assert fields(env, GATES)[: len(GATE_FIELDS)] == GATE_FIELDS

    def it_leaves_each_gate_the_file_gives(self, project):
        project.write(GATES, '{"gates": {"check": "make check"}}\n')
        _, env = project.run("config", "init")
        assert json.loads(project.read(GATES))["gates"] == dict(UNSET_GATES, check="make check")
        assert "gates.check" not in fields(env, GATES)
        assert "gates.build" in fields(env, GATES)

    def it_keeps_a_gate_the_method_does_not_name(self, project):
        project.write(GATES, '{"gates": {"lint": "make lint"}}\n')
        project.run("config", "init")
        assert json.loads(project.read(GATES))["gates"] == dict(UNSET_GATES, lint="make lint")

    def it_writes_the_gates_beside_test_commands_that_exist(self, project):
        project.write(GATES, '{"gates": {"check": "make check"}, "tests": {"list": "mine"}}\n')
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert written(env)[GATES] is True
        found = json.loads(project.read(GATES))
        assert found == {"gates": dict(UNSET_GATES, check="make check"), "tests": {"list": "mine"}}
        assert fields(env, GATES) == ["gates.build", "gates.test", "gates.verify"]
        assert '%s already gives "tests"' % GATES in env["errors"][0]

    def it_stops_on_gates_that_are_not_an_object(self, project):
        project.write(GATES, '{"gates": ["make check"]}\n')
        code, _ = project.run("config", "init")
        assert code == flywheel.CANNOT_RUN
        assert '%s does not hold a "gates" object' % GATES in project.err
        assert not (project.root / ROLES).exists()


@pytest.mark.spec("repo:script-exits-2-when-unrunnable", "repo:script-names-remedy-on-stop")
class DescribeABrokenPlugin:
    @pytest.mark.parametrize(
        "text",
        ["not json", "[]", '{"roles": []}', '{"roles": {"implementer": 3}}'],
    )
    def it_stops_on_a_template_it_cannot_read(self, project, plugin_copy, text):
        (plugin_copy / "templates" / "roles.json").write_text(text)
        code, env = project.run("config", "init")
        assert (code, env) == (flywheel.CANNOT_RUN, None)
        assert project.err.startswith("flywheel.py: ")
        assert "Install the flywheel plugin again" in project.err
        assert not (project.root / ROLES).exists()

    @pytest.mark.parametrize("text", ['{"name": "flywheel"}', '{"version": 1}', "[]"])
    def it_stops_on_a_manifest_without_a_version(self, project, plugin_copy, text):
        (plugin_copy / ".claude-plugin" / "plugin.json").write_text(text)
        code, _ = project.run("config", "init")
        assert code == flywheel.CANNOT_RUN
        assert "does not give a version" in project.err
        assert not (project.root / ROLES).exists()

    def it_stops_when_the_template_is_missing(self, project, plugin_copy):
        (plugin_copy / "templates" / "roles.json").unlink()
        code, _ = project.run("setup")
        assert code == flywheel.CANNOT_RUN
        assert "roles.json is missing" in project.err

    def it_stops_when_a_file_cannot_be_read(self, project, plugin_copy):
        (plugin_copy / "templates" / "roles.json").chmod(0)
        code, _ = project.run("config", "init")
        assert code == flywheel.CANNOT_RUN
        assert "cannot read" in project.err
        assert "Check its permissions" in project.err

    def it_stops_when_the_project_cannot_be_written(self, project):
        (project.root / ".flywheel").write_text("a file where the folder goes\n")
        code, _ = project.run("setup")
        assert code == flywheel.CANNOT_RUN
        assert "cannot write" in project.err

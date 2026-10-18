"""What `flywheel.py assess` reports of the method's levels and the controls
each introduces, and what `flywheel.py record` writes for a later assessment
to compare against."""

import json
import re
from pathlib import Path

import pytest

import flywheel

PLUGIN = Path(flywheel.SCRIPT_PATH).resolve().parents[1]
REPO = PLUGIN.parents[1]
ADOPTION_DOC = PLUGIN / "docs" / "adoption.md"
RULES_TEMPLATE = PLUGIN / "templates" / "agent-rules.md"
SPEC = REPO / "specs" / "flywheel.md"
RECORD = ".flywheel/adoption.json"
GATES = {"build": "make", "test": "make test", "check": "make check", "verify": "make verify"}
WORKFLOW = "on: pull_request\njobs:\n  v:\n    steps:\n      - run: make verify\n"
LEVEL_SPECS = ["assess-cmd-checks-level-%d-controls" % n for n in flywheel.ADOPTION_LEVELS]


def controls():
    """(level, key, text, ids, evidence) for each control, in the method's order."""
    return [
        (level, *control)
        for level, _, introduced in flywheel.METHOD_LEVELS
        for control in introduced
    ]


def template_sections():
    """{level: the rules template's section for that level}."""
    parts = re.split(r"(?m)^(?=### Level )", RULES_TEMPLATE.read_text())
    return {int(p[10]): p for p in parts if p.startswith("### Level ")}


def rules_up_to(level):
    """The rules template with its sections above `level` left out."""
    text = RULES_TEMPLATE.read_text()
    head = text[: text.index("### Level ")]
    return head + "".join(t for n, t in sorted(template_sections().items()) if n <= level)


def cite(ids):
    return "".join("# Source: the method's `%s`.\n" % name for name in ids)


def ci_ids():
    return [i for c in controls() if c[4] is flywheel.ci_evidence for i in c[3]]


def states(env):
    return {c["key"]: c for level in env["data"]["levels"] for c in level["controls"]}


def held(env):
    return {key for key, c in states(env).items() if c["held"]}


def fill_policy(project, rel):
    """Copy the plugin's policy template to rel, with every setting set."""
    text = (PLUGIN / "templates" / rel.split("/")[-1]).read_text()
    project.write(rel, text.replace("null", '["x"]'))


def adopt_everything(project):
    """Give the project the evidence for every control."""
    project.write("CLAUDE.md", rules_up_to(3))
    project.write("specs/app.md", "# app\n\n## Out of scope\n\n- nothing\n")
    project.write(".flywheel/gates.json", json.dumps({"gates": GATES}))
    project.write(".github/workflows/ci.yml", WORKFLOW + cite(ci_ids()))
    project.write(".claude/settings.json", json.dumps({"enabledPlugins": {"flywheel@m": True}}))
    fill_policy(project, ".flywheel/review-policy.md")
    fill_policy(project, ".flywheel/merge-policy.md")
    roles = {"implementer": {"tier": 3, "model": "opus", "effort": "high"}}
    project.write(".flywheel/roles.json", json.dumps({"roles": roles}))


def adoption_tables():
    """(level, control, ids) for each row of adoption.md's level tables."""
    rows, level = [], None
    for line in ADOPTION_DOC.read_text().splitlines():
        m = re.match(r"^### Level (\d)", line)
        if m:
            level = int(m.group(1))
        elif line.startswith("## "):
            level = None
        elif level and line.startswith("| ") and not line.startswith(("| Control", "| ---")):
            control, ids = [c.strip() for c in line.strip("|").split("|")]
            rows.append((level, control, tuple(i.strip() for i in ids.split(","))))
    return rows


def spec_controls(requirement):
    """(key, ids) for each control the spec's requirement lists, in its order."""
    lines = SPEC.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("- `%s`" % requirement))
    items = []
    for line in lines[start + 1 :]:
        if not line.startswith("  "):
            break
        if line.startswith("  - "):
            items.append(line[4:])
        elif items:
            items[-1] += " " + line.strip()
    return [
        (re.match(r"`([^`]+)`", item).group(1), [n for n, _ in flywheel.cited_ids(item)])
        for item in items
    ]


@pytest.mark.spec(
    "assess-cmd-checks-level-1-controls",
    "assess-cmd-checks-level-2-controls",
    "assess-cmd-checks-level-3-controls",
)
class DescribeTheLevels:
    def it_introduces_the_controls_each_level_of_the_spec_names(self):
        for (level, _, introduced), requirement in zip(flywheel.METHOD_LEVELS, LEVEL_SPECS):
            listed = [(key, list(ids)) for key, _, ids, _ in introduced]
            assert listed == spec_controls(requirement), level

    def it_words_each_control_as_adoption_md_does(self, project):
        _, env = project.run("assess")
        reported = [
            (level["level"], c["control"], tuple(c["ids"]))
            for level in env["data"]["levels"]
            for c in level["controls"]
        ]
        assert reported == adoption_tables()
        assert len(states(env)) == len(reported)

    def it_has_a_rule_in_the_template_for_every_id_each_level_names(self):
        sections = template_sections()
        assert sorted(sections) == list(flywheel.ADOPTION_LEVELS)
        for level, _, introduced in flywheel.METHOD_LEVELS:
            named = {i for _, _, ids, _ in introduced for i in ids}
            assert {n for n, _ in flywheel.cited_ids(sections[level])} == named, level

    def it_holds_level_3_when_every_control_has_its_evidence(self, project):
        adopt_everything(project)
        code, env = project.run("assess")
        assert code == flywheel.OK
        assert held(env) == {c[1] for c in controls()}
        assert [lv["held"] for lv in env["data"]["levels"]] == [True, True, True]
        assert env["data"]["level"] == 3

    def it_holds_a_level_only_when_every_lower_level_is_held(self, project):
        adopt_everything(project)
        project.write("specs/app.md", "# app\n")
        _, env = project.run("assess")
        assert [lv["held"] for lv in env["data"]["levels"]] == [False, True, True]
        assert env["data"]["level"] == 0

    @pytest.mark.parametrize("level", flywheel.ADOPTION_LEVELS)
    def it_holds_each_rule_the_template_states_up_to_its_level(self, project, level):
        project.write("CLAUDE.md", rules_up_to(level))
        _, env = project.run("assess")
        ruled = {c[1]: c[0] for c in controls() if c[4] is flywheel.rules_evidence}
        assert {k for k in ruled if k in held(env)} == {k for k, n in ruled.items() if n <= level}


@pytest.mark.spec("assess-cmd-reports-gaps-by-id")
class DescribeAssess:
    def it_reports_every_control_missing_in_a_bare_project_and_exits_0(self, project):
        code, env = project.run("assess")
        assert code == flywheel.OK
        assert held(env) == set()
        assert [lv["name"] for lv in env["data"]["levels"]] == ["Core", "Enforced", "Measured"]
        assert env["data"]["level"] == 0
        assert env["data"]["recorded"] is None
        assert env["data"]["changes"] == []
        assert states(env)["agent-rules"]["evidence"] == (
            "the project has no rules file (CLAUDE.md, AGENTS.md)"
        )

    def it_reads_the_rules_from_agents_md_and_claude_rules(self, project):
        project.write("AGENTS.md", cite(["trace-behavior-to-need"]))
        project.write(".claude/rules/house.md", cite(["humans-decide-agents-record"]))
        project.write(".claude/rules/notes.txt", cite(["write-behavior-tests-first"]))
        _, env = project.run("assess")
        assert "agent-rules" in held(env)
        assert "tests-first" not in held(env)

    def it_names_each_id_the_rules_files_do_not_cite(self, project):
        project.write("CLAUDE.md", cite(["owner-admits-every-need"]))
        _, env = project.run("assess")
        assert states(env)["approved-ticket"]["evidence"] == (
            "the files read (CLAUDE.md) do not cite `one-home-per-artifact` as the method's"
        )

    def it_names_each_spec_that_does_not_open_with_out_of_scope(self, project):
        project.write("specs/a.md", "# a\n\n## Out of scope\n")
        project.write("specs/b.md", "# b\n\n## need x: X\n\n## Out of scope\n")
        project.write("specs/c.md", "# c\n")
        project.write("specs/deeper/d.md", "# d\n")
        _, env = project.run("assess")
        assert states(env)["needs-spec"]["evidence"] == (
            "these specs do not open with ## Out of scope: specs/b.md, specs/c.md"
        )

    def it_reports_a_missing_spec_folder(self, project):
        project.write("specs/notes.txt", "")
        _, env = project.run("assess")
        assert states(env)["needs-spec"]["evidence"] == "specs/ holds no spec"

    def it_names_each_core_gate_the_gates_file_lacks(self, project):
        project.write(".flywheel/gates.json", json.dumps({"gates": {"test": "t", "build": ""}}))
        _, env = project.run("assess")
        assert states(env)["core-gates"]["evidence"] == (
            ".flywheel/gates.json does not name `build`, `check`"
        )

    def it_holds_the_verify_gate_only_where_a_workflow_runs_it(self, project):
        _, env = project.run("assess")
        assert states(env)["verify-gate"]["evidence"] == (
            ".flywheel/gates.json does not name `verify`"
        )
        project.write(".flywheel/gates.json", json.dumps({"gates": GATES}))
        project.write(".github/workflows/README.md", "make verify")
        _, env = project.run("assess")
        assert states(env)["verify-gate"]["evidence"] == (
            "no workflow under .github/workflows/ runs `make verify`"
        )
        project.write(".github/workflows/ci.yaml", WORKFLOW)
        _, env = project.run("assess")
        assert states(env)["verify-gate"]["held"] is True

    def it_holds_a_ci_control_once_a_workflow_cites_its_ids(self, project):
        project.write(".github/workflows/ci.yml", cite(["audit-on-schedule"]))
        _, env = project.run("assess")
        assert "scheduled-audit" in held(env)
        assert "unweakened-checks" not in held(env)

    def it_holds_the_guard_when_settings_enable_the_plugin(self, project):
        plugins = {"other@m": True, "flywheel@m": True}
        project.write(".claude/settings.json", json.dumps({"enabledPlugins": plugins}))
        _, env = project.run("assess")
        assert states(env)["approval-guard"]["evidence"] == (
            ".claude/settings.json enables the flywheel plugin, whose hooks run issue_guard.py"
        )

    def it_holds_the_guard_when_settings_run_it_before_bash(self, project):
        entries = [
            {"matcher": "Write", "hooks": [{"command": "python3 issue_guard.py"}]},
            {"matcher": "Bash", "hooks": [{"command": "python3 other.py"}]},
            {"matcher": "Edit|Bash", "hooks": [{"command": "python3 x/issue_guard.py"}]},
        ]
        settings = {"enabledPlugins": {"flywheel@m": False}, "hooks": {"PreToolUse": entries}}
        project.write(".claude/settings.json", json.dumps(settings))
        _, env = project.run("assess")
        assert states(env)["approval-guard"]["held"] is True

    def it_reports_the_guard_missing_when_nothing_runs_it(self, project):
        entries = [{"matcher": "Bash", "hooks": [{"command": "python3 other.py"}]}]
        project.write(".claude/settings.json", json.dumps({"hooks": {"PreToolUse": entries}}))
        _, env = project.run("assess")
        assert states(env)["approval-guard"]["evidence"] == (
            ".claude/settings.json neither enables the flywheel plugin nor runs issue_guard.py"
            " before Bash"
        )

    def it_names_each_setting_a_policy_leaves_unset(self, project):
        project.run("config", "init")
        _, env = project.run("assess")
        assert states(env)["merge-policy"]["evidence"] == (
            ".flywheel/merge-policy.md leaves `areas` unset"
        )
        assert states(env)["review-policy"]["evidence"] == (
            ".flywheel/review-policy.md leaves `rules` unset"
        )

    def it_names_each_role_field_the_roles_file_leaves_unset(self, project):
        roles = {"implementer": {"model": "opus", "effort": None}, "reviewer": "opus"}
        project.write(".flywheel/roles.json", json.dumps({"roles": roles}))
        _, env = project.run("assess")
        assert states(env)["role-tiers"]["evidence"] == (
            ".flywheel/roles.json leaves `implementer.effort`, `reviewer.model`,"
            " `reviewer.effort` unset"
        )

    def it_prints_each_level_with_its_controls_and_their_evidence(self, project):
        adopt_everything(project)
        code, out, _ = project.human("assess")
        assert code == flywheel.OK
        assert "level 1 (Core): held\n" in out
        assert "  [x] core-gates (one-command-per-gate): .flywheel/gates.json names" in out
        assert "the project holds level 3" in out
        assert "recorded" not in out


@pytest.mark.spec("record-cmd-writes-version-and-controls")
class DescribeRecord:
    def it_writes_the_version_the_level_and_each_controls_state_under_its_level(self, project):
        project.write(".flywheel/gates.json", json.dumps({"gates": GATES}))
        code, env = project.run("record", "--level", "2")
        assert code == flywheel.OK
        record = json.loads(project.read(RECORD))
        assert record["version"] == flywheel.plugin_version() == env["data"]["version"]
        assert record["level"] == 2
        assert sorted(record["levels"]) == ["1", "2", "3"]
        assert record["levels"]["1"]["core-gates"] == {
            "ids": ["one-command-per-gate"],
            "held": True,
        }
        assert record["levels"]["2"]["verify-gate"]["held"] is False
        assert env["data"]["held"] == ["core-gates"]
        assert [(g["level"], [c["key"] for c in g["controls"]]) for g in env["data"]["gaps"]] == [
            (n, [c[1] for c in controls() if c[0] == n and c[1] != "core-gates"]) for n in (1, 2)
        ]

    def it_prints_each_gap_up_to_the_level(self, project):
        code, out, _ = project.human("record", "--level", "1")
        assert code == flywheel.OK
        assert "wrote .flywheel/adoption.json: level 1 under flywheel" in out
        assert "level 1 (Core) control `core-gates` (one-command-per-gate) is missing" in out
        assert "level 2" not in out

    @pytest.mark.parametrize("level", ["0", "4", "two"])
    def it_refuses_a_level_the_method_does_not_have(self, project, level, capsys):
        with pytest.raises(SystemExit) as exc:
            flywheel.main(["record", "--level", level, "-C", str(project.root)])
        assert exc.value.code == flywheel.CANNOT_RUN
        assert "is not a level" in capsys.readouterr().err


@pytest.mark.spec("record-cmd-writes-version-and-controls")
class DescribeAssessAfterRecord:
    def it_names_each_control_whose_state_changed_since(self, project):
        project.run("record", "--level", "1")
        record = json.loads(project.read(RECORD))
        del record["levels"]["3"]["mistakes-to-checks"]
        record["levels"]["1"]["tests-first"] = "held"
        del record["levels"]["2"]
        project.write(RECORD, json.dumps(record))
        project.write(".flywheel/gates.json", json.dumps({"gates": GATES}))
        _, env = project.run("assess")
        assert env["data"]["recorded"] == {"version": flywheel.plugin_version(), "level": 1}
        assert env["data"]["changes"] == [
            {"level": 1, "key": "core-gates", "was": "missing", "now": "held"},
            {"level": 1, "key": "tests-first", "was": "new", "now": "missing"},
        ] + [
            {"level": 2, "key": c[1], "was": "new", "now": "missing"}
            for c in controls()
            if c[0] == 2
        ] + [{"level": 3, "key": "mistakes-to-checks", "was": "new", "now": "missing"}]

    @pytest.mark.spec("assess-cmd-reports-gaps-by-id")
    def it_exits_1_naming_each_control_missing_at_or_below_the_recorded_level(self, project):
        project.write(".flywheel/gates.json", json.dumps({"gates": GATES}))
        project.run("record", "--level", "1")
        code, env = project.run("assess")
        assert code == flywheel.PROBLEMS
        assert len(env["errors"]) == 4
        assert env["errors"][0].startswith(
            "level 1 (Core) control `agent-rules` (trace-behavior-to-need,"
            " humans-decide-agents-record) is missing: "
        )
        assert env["errors"][0].endswith(
            "at or below the recorded level 1. The adopt skill files it as an issue."
        )

    @pytest.mark.spec("assess-cmd-reports-gaps-by-id")
    def it_exits_0_once_every_control_up_to_the_recorded_level_is_held(self, project):
        adopt_everything(project)
        project.run("record", "--level", "3")
        code, env = project.run("assess")
        assert code == flywheel.OK
        assert env["data"]["changes"] == []

    def it_prints_the_record_and_the_changes(self, project):
        project.run("record", "--level", "1")
        project.write(".flywheel/gates.json", json.dumps({"gates": GATES}))
        code, out, _ = project.human("assess")
        assert code == flywheel.PROBLEMS
        assert "recorded: level 1 under flywheel %s, now" % flywheel.plugin_version() in out
        assert "  level 1 core-gates: missing, now held" in out

    @pytest.mark.parametrize(
        "text",
        [
            "not json",
            "[]",
            json.dumps({"version": "1.0.0", "level": 5, "levels": {}}),
            json.dumps({"version": "1.0.0", "level": 1, "levels": []}),
            json.dumps({"version": "1.0.0", "level": 1, "controls": {}}),
            json.dumps({"version": 1, "level": 1, "levels": {}}),
        ],
    )
    def it_stops_on_a_record_that_record_did_not_write(self, project, text):
        project.write(RECORD, text)
        code, env = project.run("assess")
        assert code == flywheel.CANNOT_RUN
        assert env is None
        assert "is not a record that record wrote" in project.err

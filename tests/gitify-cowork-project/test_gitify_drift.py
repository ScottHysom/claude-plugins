"""drift tells a project whose history skill has fallen behind the template
what changed, without calling the project's own names, its rewrapping or its
own additions drift.
"""

import gitify


def rendered_skill(runner, make_answers, skill_rel):
    code, env = runner.render(make_answers())
    assert code == gitify.OK, env["errors"]
    return runner.stage / skill_rel


class DescribeDrift:
    def it_sees_no_drift_in_a_freshly_rendered_skill(self, runner, make_answers, skill_rel):
        skill = rendered_skill(runner, make_answers, skill_rel)
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == gitify.OK, env["errors"]
        assert set(s["status"] for s in env["data"]["sections"]) == {"same"}

    def it_does_not_count_rewrapping_as_drift(self, runner, make_answers, skill_rel):
        skill = rendered_skill(runner, make_answers, skill_rel)
        text = skill.read_text().replace(
            "cannot delete files. Every", "cannot delete files.\nEvery"
        )
        skill.write_text(text)
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == gitify.OK, env["errors"]

    def it_reports_a_changed_rule_with_a_diff(self, runner, make_answers, skill_rel):
        skill = rendered_skill(runner, make_answers, skill_rel)
        skill.write_text(skill.read_text().replace("Never `08/20/26`.", "Any format."))
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == gitify.PROBLEMS
        changed = [s for s in env["data"]["sections"] if s["status"] == "changed"]
        assert [s["heading"] for s in changed] == ["Dates"]
        assert "-Never `08/20/26`." in changed[0]["diff"]

    def it_reports_a_removed_section_as_missing(self, runner, make_answers, skill_rel):
        skill = rendered_skill(runner, make_answers, skill_rel)
        text = skill.read_text()
        start, end = text.index("## Dates"), text.index("## Skill provenance")
        skill.write_text(text[:start] + text[end:])
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == gitify.PROBLEMS
        assert "Dates: section missing from the project's skill" in env["errors"]

    def it_reports_a_project_only_section_without_calling_it_drift(
        self, runner, make_answers, skill_rel
    ):
        skill = rendered_skill(runner, make_answers, skill_rel)
        skill.write_text(skill.read_text() + "\n## Our own rule\n\nTag releases.\n")
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == gitify.OK, env["errors"]
        assert {"heading": "Our own rule", "status": "project-only"} in env["data"]["sections"]

    def it_does_not_split_a_section_at_a_heading_inside_a_code_fence(self):
        text = "## A\n```\n## not a heading\n```\n"
        assert [h for h, _ in gitify.sections(text)] == ["A"]

    def it_writes_human_output_to_stdout_and_problems_to_stderr(
        self, runner, make_answers, skill_rel
    ):
        skill = rendered_skill(runner, make_answers, skill_rel)
        skill.write_text(skill.read_text().replace("Never `08/20/26`.", "Any format."))
        code, _ = runner.run("drift", "--skill", str(skill), json_output=False)
        assert code == gitify.PROBLEMS
        assert "changed" in runner.out
        assert "Dates: differs from the template" in runner.err

    def it_cannot_run_on_an_unreadable_skill(self, runner):
        code, env = runner.run("drift", "--skill", str(runner.tmp / "nope.md"))
        assert code == gitify.CANNOT_RUN
        assert env is None
        assert "cannot read" in runner.err

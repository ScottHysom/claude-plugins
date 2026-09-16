"""drift answers "has this project's skill fallen behind the template?" It has
to ignore everything the interview legitimately changed - placeholders, filled
markers, deleted optional sections, rewrapped lines - and nothing else, or it
either cries wolf on every project or misses the universal rule that changed.
"""

import scaffold


def rendered_skill(runner, make_answers, skill_rel, data=None):
    code, env = runner.render(data or make_answers())
    assert code == scaffold.OK, env["errors"]
    return runner.stage / skill_rel


def statuses(env):
    return dict((s["heading"], s["status"]) for s in env["data"]["sections"])


class DescribeDrift:
    def it_sees_no_drift_in_a_freshly_rendered_skill(self, runner, make_answers, skill_rel):
        skill = rendered_skill(runner, make_answers, skill_rel)
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == scaffold.OK, env["errors"]
        assert set(statuses(env).values()) == {"same"}

    def it_does_not_count_a_deleted_optional_section_as_drift(
        self, runner, make_answers, markers, resolve, skill_rel
    ):
        data = make_answers(markers=resolve(markers, optional="delete"))
        skill = rendered_skill(runner, make_answers, skill_rel, data)
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == scaffold.OK, env["errors"]
        assert statuses(env)["Diagrams"] == "deleted-optional"

    def it_does_not_count_rewrapping_as_drift(self, runner, make_answers, skill_rel):
        skill = rendered_skill(runner, make_answers, skill_rel)
        text = skill.read_text().replace(
            "Subject under ~70 chars, imperative, lowercase after the colon.",
            "Subject under ~70 chars,\n  imperative, lowercase\nafter the colon.",
        )
        skill.write_text(text)
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == scaffold.OK, env["errors"]

    def it_reports_a_changed_universal_rule_with_a_diff(self, runner, make_answers, skill_rel):
        skill = rendered_skill(runner, make_answers, skill_rel)
        skill.write_text(
            skill.read_text().replace("Subject under ~70 chars", "Subject under ~50 chars")
        )
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == scaffold.PROBLEMS
        changed = [s for s in env["data"]["sections"] if s["status"] == "changed"]
        assert [s["heading"] for s in changed] == ["Commit types"]
        assert "+Subject under ~50 chars" in changed[0]["diff"]

    def it_reports_a_removed_universal_section_as_missing(self, runner, make_answers, skill_rel):
        skill = rendered_skill(runner, make_answers, skill_rel)
        text = skill.read_text()
        start = text.index("## Dates\n")
        end = text.index("## Skill provenance\n")
        skill.write_text(text[:start] + text[end:])
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == scaffold.PROBLEMS
        assert statuses(env)["Dates"] == "missing"

    def it_reports_a_project_only_section_without_calling_it_drift(
        self, runner, make_answers, skill_rel
    ):
        skill = rendered_skill(runner, make_answers, skill_rel)
        with open(skill, "a") as fh:
            fh.write("\n## Local rule\n\nOnly here.\n")
        code, env = runner.run("drift", "--skill", str(skill))
        assert code == scaffold.OK, env["errors"]
        assert statuses(env)["Local rule"] == "project-only"

    def it_does_not_split_a_section_at_a_heading_inside_a_code_fence(self):
        text = "## Real\n\n```\n## Not a heading\n```\n"
        assert [h for h, _ in scaffold.sections(text)] == ["Real"]

    def it_writes_human_output_to_stdout_and_problems_to_stderr(
        self, runner, make_answers, skill_rel
    ):
        skill = rendered_skill(runner, make_answers, skill_rel)
        skill.write_text(
            skill.read_text().replace("Subject under ~70 chars", "Subject under ~50 chars")
        )
        code, _ = runner.run("drift", "--skill", str(skill), json_output=False)
        assert code == scaffold.PROBLEMS
        assert "changed           Commit types" in runner.out
        assert "Commit types: differs from the template" in runner.err

    def it_cannot_run_on_an_unreadable_skill(self, runner):
        code, env = runner.run("drift", "--skill", str(runner.tmp / "missing.md"))
        assert code == scaffold.CANNOT_RUN
        assert env is None
        assert runner.err.startswith("scaffold.py: cannot read")

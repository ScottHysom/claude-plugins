"""flywheel.py labels names each label the loop and file-issue need that the
repository lacks, and creates them with --create. gh is faked by a repository
that keeps the labels it is sent, and starts with GitHub's defaults."""

import json

import pytest

import flywheel

# The labels GitHub gives a repository it has just created.
DEFAULTS = (
    "bug",
    "documentation",
    "duplicate",
    "enhancement",
    "good first issue",
    "help wanted",
    "invalid",
    "question",
    "wontfix",
)
BODY = (
    "**Claude:**\n\n## What's wrong\n\nIt breaks.\n\n## Evidence\n\nflywheel.py:1\n\n"
    "## Done when\n\nIt works.\n\n## Requirements\n\nNone.\n"
)


class Labels:
    """gh, as a repository that keeps the labels it is sent."""

    def __init__(self, labels=DEFAULTS):
        self.labels = list(labels)
        self.created = []

    def __call__(self, repo, *args, stdin=None):
        if args[:2] == ("repo", "view"):
            return json.dumps({"nameWithOwner": "o/r", "url": "https://github.com/o/r"})
        if args[:2] == ("label", "list"):
            return json.dumps([{"name": n} for n in self.labels])
        if args[:2] == ("label", "create"):
            self.labels.append(args[2])
            self.created.append(args[2])
            return ""
        raise AssertionError("unexpected gh call: %r" % (args,))


@pytest.fixture
def fake(monkeypatch):
    def install(labels=DEFAULTS):
        hub = Labels(labels)
        monkeypatch.setattr(flywheel, "gh", hub)
        return hub

    return install


def needed():
    return [name for name, _ in flywheel.LOOP_LABELS]


class DescribeLabels:
    @pytest.mark.spec("labels-cmd-names-missing-labels")
    def it_names_each_needed_label_a_new_repository_lacks(self, project, fake):
        hub = fake()
        code, env = project.run("labels")
        assert code == flywheel.PROBLEMS
        missing = env["data"]["missing"]
        assert set(missing) == set(needed()) - set(DEFAULTS)
        assert {"docs", "repo", flywheel.TRACKING, flywheel.APPROVED, flywheel.IN_PROGRESS} <= set(
            missing
        )
        assert env["data"]["created"] == []
        assert hub.created == []
        assert "--create" in env["errors"][0]

    @pytest.mark.spec("labels-cmd-names-missing-labels")
    def it_creates_each_missing_label_with_create(self, project, fake):
        hub = fake()
        code, env = project.run("labels", "--create")
        assert code == flywheel.OK
        assert sorted(hub.created) == sorted(env["data"]["created"])
        assert set(hub.created) == set(needed()) - set(DEFAULTS)
        assert env["data"]["missing"] == []

    @pytest.mark.spec("labels-cmd-names-missing-labels")
    def it_reads_a_label_in_another_case_as_present(self, project, fake):
        hub = fake([n.upper() for n in needed()])
        code, env = project.run("labels", "--create")
        assert code == flywheel.OK
        assert env["data"]["missing"] == []
        assert hub.created == []

    @pytest.mark.spec("labels-cmd-names-missing-labels")
    def it_prints_each_missing_label_without_json(self, project, fake):
        fake()
        code, out, err = project.human("labels")
        assert code == flywheel.PROBLEMS
        for name in set(needed()) - set(DEFAULTS):
            assert name in out
        assert "--create" in err

    @pytest.mark.spec("labels-cmd-names-missing-labels")
    def it_lets_a_plan_of_gaps_pass_report_once_it_creates_them(
        self, project, fake, tmp_path, monkeypatch
    ):
        fake()
        project.run("labels", "--create")
        draft = {"key": "A", "title": "gap", "labels": ["enhancement", "repo"], "body": BODY}
        plan = tmp_path / "plan.json"
        plan.write_text(
            json.dumps(
                {"issues": [draft, dict(draft, key="B")], "tracking": {"title": "t", "plan": "p"}}
            )
        )
        code, env = project.run("plan", "report", "--drafts", str(plan))
        assert code == flywheel.OK, env["errors"]

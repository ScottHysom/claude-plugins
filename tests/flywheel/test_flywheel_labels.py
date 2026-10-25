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
    """gh, as a repository that keeps the labels it is sent, each with its
    description. `labels` gives names, or (name, description) pairs."""

    def __init__(self, labels=DEFAULTS):
        self.labels = [lbl if isinstance(lbl, tuple) else (lbl, "") for lbl in labels]
        self.created = []

    def __call__(self, repo, *args, stdin=None):
        if args[:2] == ("repo", "view"):
            return json.dumps({"nameWithOwner": "o/r", "url": "https://github.com/o/r"})
        if args[:2] == ("label", "list"):
            return json.dumps([{"name": n, "description": d} for n, d in self.labels])
        if args[:2] == ("label", "create"):
            self.labels.append((args[2], args[args.index("--description") + 1]))
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
    return list(flywheel.DEFAULT_KINDS) + list(flywheel.ROLE_LABELS.values())


class DescribeLabels:
    @pytest.mark.spec("labels-cmd-names-missing-labels")
    def it_names_each_needed_label_a_new_repository_lacks(self, project, fake):
        hub = fake()
        code, env = project.run("labels")
        assert code == flywheel.PROBLEMS
        missing = env["data"]["missing"]
        assert set(missing) == set(needed()) - set(DEFAULTS)
        assert {"plan", "approved", "claimed"} <= set(missing)
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
        claim = flywheel.ROLE_LABELS[flywheel.CLAIM]
        hub = fake(
            [n.upper() for n in needed() if n != claim]
            + [(claim.upper(), flywheel.ROLE_TEXTS[flywheel.CLAIM])]
        )
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
    def it_prints_each_label_it_creates_without_json(self, project, fake):
        hub = fake()
        code, out, err = project.human("labels", "--create")
        assert code == flywheel.OK
        assert out.splitlines() == ["created: %s" % name for name in hub.created]
        assert err == ""

    @pytest.mark.spec("labels-cmd-names-missing-labels")
    def it_lets_a_plan_of_gaps_pass_report_once_it_creates_them(
        self, project, fake, tmp_path, monkeypatch
    ):
        fake()
        project.run("labels", "--create")
        draft = {"key": "A", "title": "gap", "labels": ["enhancement"], "body": BODY}
        plan = tmp_path / "plan.json"
        plan.write_text(
            json.dumps(
                {"issues": [draft, dict(draft, key="B")], "tracking": {"title": "t", "plan": "p"}}
            )
        )
        code, env = project.run("plan", "report", "--drafts", str(plan))
        assert code == flywheel.OK, env["errors"]


def labels_file(project):
    return json.loads(project.read(flywheel.LABELS_FILE))


class DescribeLabelsSet:
    @pytest.mark.spec("labels-cmd-sets-role", "labelsfile-maps-roles")
    def it_writes_each_role_and_names_the_labels_it_gives_as_missing(self, project, fake):
        fake()
        code, env = project.run("labels", "--set", "approval=ready", "--set", "plan=epic")
        assert code == flywheel.PROBLEMS
        assert labels_file(project) == {"roles": {"approval": "ready", "plan": "epic"}}
        assert env["data"]["roles"] == dict(
            flywheel.ROLE_LABELS, **{flywheel.APPROVAL: "ready", flywheel.PLAN: "epic"}
        )
        assert {"ready", "epic"} <= set(env["data"]["missing"])
        assert not {"approved", "plan"} & set(env["data"]["missing"])

    @pytest.mark.spec("labels-cmd-sets-role")
    def it_keeps_the_files_other_roles_and_keys(self, project, fake):
        fake()
        project.write(
            flywheel.LABELS_FILE,
            json.dumps({"roles": {"plan": "epic"}, "kinds": {"bug": "Something is broken"}}),
        )
        project.run("labels", "--set", "claim=flywheel-claim")
        assert labels_file(project) == {
            "roles": {"plan": "epic", "claim": "flywheel-claim"},
            "kinds": {"bug": "Something is broken"},
        }

    @pytest.mark.parametrize("value", ["owner=ready", "approval", "approval= "])
    @pytest.mark.spec("labels-cmd-sets-role")
    def it_refuses_a_role_outside_the_four_and_writes_nothing(self, project, fake, value, capsys):
        hub = fake()
        with pytest.raises(SystemExit) as exc:
            flywheel.main(["labels", "--set", value, "-C", str(project.root)])
        assert exc.value.code == flywheel.CANNOT_RUN
        assert "ROLE=NAME" in capsys.readouterr().err
        assert not (project.root / flywheel.LABELS_FILE).exists()
        assert hub.created == []

    @pytest.mark.spec("labels-cmd-sets-role", "labelsfile-refuses-bad-map")
    def it_refuses_to_give_two_roles_one_label_and_writes_nothing(self, project, fake):
        fake()
        project.write(flywheel.LABELS_FILE, json.dumps({"roles": {"plan": "epic"}}))
        code, env = project.run("labels", "--set", "approval=Epic")
        assert code == flywheel.CANNOT_RUN
        assert 'gives the roles "approval" and "plan" one label' in project.err
        assert labels_file(project) == {"roles": {"plan": "epic"}}

    @pytest.mark.parametrize("text", ["[]", '{"roles": []}'])
    @pytest.mark.spec("labels-cmd-sets-role")
    def it_refuses_to_write_into_a_file_without_a_roles_object(self, project, fake, text):
        fake()
        project.write(flywheel.LABELS_FILE, text)
        code, _ = project.run("labels", "--set", "plan=epic")
        assert code == flywheel.CANNOT_RUN
        assert 'does not hold a "roles" object' in project.err
        assert project.read(flywheel.LABELS_FILE).decode() == text


class DescribeLabelsKinds:
    @pytest.mark.spec("labels-cmd-sets-kinds", "labels-cmd-names-missing-labels")
    def it_writes_the_kinds_and_creates_each(self, project, fake):
        hub = fake()
        project.write(
            flywheel.LABELS_FILE,
            json.dumps({"roles": {"plan": "epic"}, "kinds": {"chore": ""}, "notes": 1}),
        )
        code, env = project.run(
            "labels",
            "--kind",
            "bug=Something broke",
            "--kind",
            "docs=Words only",
            "--create",
        )
        assert code == flywheel.OK, env["errors"]
        assert labels_file(project) == {
            "roles": {"plan": "epic"},
            "kinds": {"bug": "Something broke", "docs": "Words only"},
            "notes": 1,
        }
        assert env["data"]["kinds"] == {"bug": "Something broke", "docs": "Words only"}
        assert {"docs", "epic"} <= set(hub.created)
        assert not {"chore", "documentation"} & set(hub.created)
        assert ("docs", "Words only") in hub.labels

    @pytest.mark.spec("labels-cmd-names-missing-labels")
    def it_names_githubs_kinds_without_the_file(self, project, fake):
        fake(["bug", "enhancement"])
        code, env = project.run("labels")
        assert code == flywheel.PROBLEMS
        assert "documentation" in env["data"]["missing"]

    @pytest.mark.parametrize("value", ["docs", "=Words"])
    @pytest.mark.spec("labels-cmd-sets-kinds")
    def it_refuses_an_option_without_a_name(self, project, fake, value, capsys):
        fake()
        with pytest.raises(SystemExit) as exc:
            flywheel.main(["labels", "--kind", value, "-C", str(project.root)])
        assert exc.value.code == flywheel.CANNOT_RUN
        assert "NAME=TEXT" in capsys.readouterr().err
        assert not (project.root / flywheel.LABELS_FILE).exists()


class DescribeLabelsFile:
    @pytest.mark.parametrize(
        ("roles", "says"),
        [
            ({"owner": "ready"}, 'names the role "owner", which is not one of'),
            ({"approval": " "}, 'gives the role "approval" an empty label'),
            ({"approval": 3}, 'gives the role "approval" an empty label'),
            ({"claim": "approved"}, 'gives the roles "approval" and "claim" one label'),
            ([], 'does not hold a "roles" object'),
        ],
        ids=["role", "blank", "not-text", "shared", "not-object"],
    )
    @pytest.mark.spec("labelsfile-refuses-bad-map")
    def it_stops_a_command_and_names_the_fault(self, project, fake, roles, says):
        fake()
        project.write(flywheel.LABELS_FILE, json.dumps({"roles": roles}))
        code, env = project.run("labels")
        assert code == flywheel.CANNOT_RUN
        assert env is None
        assert says in project.err
        assert flywheel.LABELS_FILE in project.err

    @pytest.mark.parametrize(
        ("given", "says"),
        [
            ({"kinds": ["bug"]}, 'does not hold a "kinds" object'),
            ({"kinds": {}}, 'gives no label under "kinds"'),
            ({"kinds": {" ": "x"}}, 'gives an empty label under "kinds"'),
            ({"kinds": {"bug": 3}}, 'gives `bug` under "kinds" a description that is not text'),
        ],
        ids=["kinds-not-object", "no-kinds", "blank", "not-text"],
    )
    @pytest.mark.spec("labelsfile-refuses-bad-map")
    def it_stops_a_command_on_a_bad_kind(self, project, fake, tmp_path, given, says):
        fake()
        project.write(flywheel.LABELS_FILE, json.dumps(given))
        plan = tmp_path / "plan.json"
        plan.write_text(json.dumps({"issues": [{"key": "A"}]}))
        code, env = project.run("plan", "report", "--drafts", str(plan))
        assert code == flywheel.CANNOT_RUN
        assert env is None
        assert says in project.err
        assert flywheel.LABELS_FILE in project.err


class DescribeTakenClaimLabel:
    @pytest.mark.spec("labels-cmd-flags-taken-claim-label")
    def it_names_a_claim_label_the_repository_describes_otherwise(self, project, fake):
        hub = fake([*DEFAULTS, ("claimed", "Someone is on it")])
        code, env = project.run("labels", "--create")
        assert code == flywheel.PROBLEMS
        assert env["data"]["taken"] == "claimed"
        assert "claimed" not in hub.created
        assert len(env["errors"]) == 1
        assert "the claim label `claimed` is taken" in env["errors"][0]
        assert "labels --set claim=NAME" in env["errors"][0]

    @pytest.mark.spec("labels-cmd-flags-taken-claim-label")
    def it_accepts_a_claim_label_carrying_flywheels_description(self, project, fake):
        fake([*DEFAULTS, ("Claimed", flywheel.ROLE_TEXTS[flywheel.CLAIM])])
        code, env = project.run("labels", "--create")
        assert code == flywheel.OK, env["errors"]
        assert env["data"]["taken"] is None

    @pytest.mark.spec("labels-cmd-flags-taken-claim-label", "labels-cmd-sets-role")
    def it_clears_once_the_claim_has_a_label_of_its_own(self, project, fake):
        hub = fake([*DEFAULTS, ("claimed", "Someone is on it")])
        code, env = project.run("labels", "--set", "claim=flywheel-claim", "--create")
        assert code == flywheel.OK, env["errors"]
        assert "flywheel-claim" in hub.created
        assert env["data"]["taken"] is None

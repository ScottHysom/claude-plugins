"""What `flywheel.py config init` writes, and what it leaves to the owner."""

import json

import pytest

import flywheel

ROLES = ".flywheel/roles.json"
OWNER_FIELDS = [
    "roles.dispatcher.model",
    "roles.dispatcher.effort",
    "roles.implementer.model",
    "roles.implementer.effort",
    "roles.reviewer.model",
    "roles.reviewer.effort",
]


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
        assert env["data"]["file"] == ROLES
        assert env["data"]["written"] is True
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

    def it_leaves_the_file_for_git_after_setup(self, project):
        project.run("setup")
        project.run("config", "init")
        assert project.git("status", "--porcelain", "--untracked-files=all") == (
            b"?? .flywheel/roles.json\n"
        )


@pytest.mark.spec("configinit-cmd-writes-roles-file")
class DescribeAnExistingRolesFile:
    def it_refuses_to_overwrite_it(self, project):
        project.write(ROLES, '{"mine": true}\n')
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert env["ok"] is False
        assert env["data"]["written"] is False
        assert project.read(ROLES) == b'{"mine": true}\n'

    def it_says_how_to_start_again(self, project):
        project.write(ROLES, "{}\n")
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
        assert env["data"]["owner_fields"] == OWNER_FIELDS

    def it_lists_them_in_text(self, project):
        _, out, _ = project.human("config", "init")
        assert out == "wrote .flywheel/roles.json\n\nthe owner fills in each of these:\n%s" % (
            "".join("  %s\n" % f for f in OWNER_FIELDS)
        )

    def it_names_nothing_when_the_template_fills_every_field(self, project, plugin_copy):
        template = plugin_copy / "templates" / "roles.json"
        template.write_text(json.dumps({"roles": {"implementer": {"tier": 3, "model": "m"}}}))
        code, out, _ = project.human("config", "init")
        assert code == flywheel.OK
        assert out == "wrote .flywheel/roles.json\n"


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

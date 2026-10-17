"""What `flywheel.py config init` writes, and what it leaves to the owner."""

import json

import pytest

import flywheel

ROLES = ".flywheel/roles.json"
REVIEW = ".flywheel/review-policy.md"
MERGE = ".flywheel/merge-policy.md"
FILES = [ROLES, REVIEW, MERGE]
OWNER_FIELDS = [
    "roles.dispatcher.model",
    "roles.dispatcher.effort",
    "roles.implementer.model",
    "roles.implementer.effort",
    "roles.reviewer.model",
    "roles.reviewer.effort",
]


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
            b"?? .flywheel/merge-policy.md\n?? .flywheel/review-policy.md\n"
            b"?? .flywheel/roles.json\n"
        )


@pytest.mark.spec("configinit-cmd-writes-policies")
class DescribeThePolicies:
    def it_writes_both_policies_from_the_templates(self, project):
        code, env = project.run("config", "init")
        assert code == flywheel.OK
        assert written(env) == {ROLES: True, REVIEW: True, MERGE: True}
        assert project.read(REVIEW) == shipped("review-policy.md")
        assert project.read(MERGE) == shipped("merge-policy.md")

    def it_writes_the_policies_beside_a_roles_file_that_exists(self, project):
        project.write(ROLES, '{"mine": true}\n')
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert written(env) == {ROLES: False, REVIEW: True, MERGE: True}
        assert project.read(REVIEW) == shipped("review-policy.md")
        assert env["errors"] == [
            "%s already exists, so it was left as it is. Edit it to change it, or delete it and"
            " run config init again to start from the template." % ROLES
        ]

    def it_refuses_to_overwrite_a_policy(self, project):
        project.write(MERGE, "mine\n")
        code, env = project.run("config", "init")
        assert code == flywheel.PROBLEMS
        assert written(env) == {ROLES: True, REVIEW: True, MERGE: False}
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
            project.write(rel, "{}\n")
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
        assert fields(env, MERGE) == ["areas"]

    def it_lists_them_in_text(self, project):
        _, out, _ = project.human("config", "init")
        named = ["%s: %s" % (ROLES, f) for f in OWNER_FIELDS]
        named += ["%s: rules" % REVIEW, "%s: areas" % MERGE]
        assert out == "%s\nthe owner fills in each of these:\n%s" % (
            "".join("wrote %s\n" % rel for rel in FILES),
            "".join("  %s\n" % f for f in named),
        )

    def it_names_nothing_when_the_template_fills_every_field(self, project, plugin_copy):
        template = plugin_copy / "templates" / "roles.json"
        template.write_text(json.dumps({"roles": {"implementer": {"tier": 3, "model": "m"}}}))
        for name in ("review-policy.md", "merge-policy.md"):
            (plugin_copy / "templates" / name).write_text('```json\n{"set": 1}\n```\n')
        code, out, _ = project.human("config", "init")
        assert code == flywheel.OK
        assert out == "".join("wrote %s\n" % rel for rel in FILES)


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

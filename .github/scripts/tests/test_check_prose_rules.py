"""The check that keeps the shipped prose rules in step with this repo's.

Every rule it enforces fails by absence: a comparison that sets aside too
much lets a changed rule through, and the gate stays green. So each kind of
drift gets a pair of files that shows it, and each kind of text the check
sets aside gets a pair that differs only there.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-prose-rules.py"
_spec = importlib.util.spec_from_file_location("check_prose_rules", _PATH)
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)

HERE = """---
name: repo prose style
---

# repo: prose style

The house style for this repo.

## Standing instructions

### standing-short-sentences: Prefer short sentences

Two sentences that each carry one claim beat one sentence carrying both.

> **Before.** A long sentence, and another clause.
> **After.** A short sentence. Another one.

### standing-name-the-role: Name the role

The roles in this repo:

- **The owner** merges.

## Sentences

### sentences-own-subject: Every sentence carries its own subject

A sentence that borrows its subject is incomplete.
"""

SHIPPED = """---
---

# {{PROJECT_NAME}}: prose style

The house style for this folder.

## Standing instructions

### standing-short-sentences: Prefer short sentences

Two sentences that each carry one claim beat one sentence carrying both.

<!-- FILL: a real before and after from this project. -->

### standing-name-the-role: Name the role

<!-- FILL: name this project's roles. -->

## Sentences

### sentences-own-subject: Every sentence carries its own subject

A sentence that borrows its subject is incomplete.
"""


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Keep the developer's git config (signing, hooks, default branch) out."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def make_repo(tmp_path, git_init):
    """A throwaway clone holding the two rules files, or None to leave one out."""

    def build(here=HERE, shipped=SHIPPED):
        root = tmp_path / "repo"
        if not root.exists():
            git_init(root)
        for rel, text in ((cp.REPO_RULES, here), (cp.SHIPPED_RULES, shipped)):
            if text is not None:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
        return root

    return build


@pytest.fixture
def run(capsys):
    """Drive a command through main() so argparse defaults are the real ones."""

    def go(*argv):
        capsys.readouterr()
        code = cp.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


class DescribeImport:
    @pytest.mark.spec("script-does-nothing-on-import")
    def it_does_no_work_when_imported(self, capsys):
        spec = importlib.util.spec_from_file_location("again", _PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class DescribeDrift:
    @pytest.mark.spec("drift-cmd-skips-project-text", "command-splits-output-streams-without-json")
    def it_passes_rules_that_differ_only_in_project_text(self, make_repo, run):
        code, out, err = run("drift", "-C", str(make_repo()))
        assert code == cp.OK
        assert "All 3 rule(s) match the shipped rules." in out
        assert err == ""

    @pytest.mark.spec("drift-cmd-skips-project-text")
    def it_passes_a_paragraph_wrapped_differently(self, make_repo, run):
        here = HERE.replace("one claim beat", "one claim\nbeat   ")
        code, _, err = run("drift", "-C", str(make_repo(here=here)))
        assert code == cp.OK, err

    @pytest.mark.spec("drift-cmd-skips-project-text")
    def it_passes_worked_examples_that_differ_outside_a_fill_marker(self, make_repo, run):
        here = HERE.replace(
            "is incomplete.\n",
            "is incomplete.\n\n> **Before.** Able to read.\n> **After.** A reader can read.\n",
        )
        shipped = SHIPPED.replace(
            "is incomplete.\n",
            "is incomplete.\n\n> **Before.** Ran late.\n> **After.** The build ran late.\n",
        )
        code, _, err = run("drift", "-C", str(make_repo(here=here, shipped=shipped)))
        assert code == cp.OK, err

    @pytest.mark.spec("drift-cmd-skips-project-text")
    def it_passes_nothing_in_place_of_a_fill_marker(self, make_repo, run):
        here = HERE.replace("The roles in this repo:\n\n- **The owner** merges.\n", "")
        code, _, err = run("drift", "-C", str(make_repo(here=here)))
        assert code == cp.OK, err

    @pytest.mark.spec("drift-cmd-skips-project-text")
    def it_passes_a_fill_marker_between_two_passages(self, make_repo, run):
        shipped = SHIPPED.replace(
            "<!-- FILL: name this project's roles. -->",
            "Roles differ.\n\n<!-- FILL: name\n     them. -->\n\nName the one meant.",
        )
        here = HERE.replace(
            "The roles in this repo:", "Roles differ.\n\nThe roles in this repo:"
        ).replace("- **The owner** merges.", "- **The owner** merges.\n\nName the one meant.")
        code, _, err = run("drift", "-C", str(make_repo(here=here, shipped=shipped)))
        assert code == cp.OK, err

    @pytest.mark.spec("drift-cmd-fails-changed-rule", "drift-cmd-names-copyprose")
    def it_fails_a_sentence_changed_in_one_copy(self, make_repo, run):
        here = HERE.replace("borrows its subject", "borrows a subject")
        code, _, err = run("drift", "-C", str(make_repo(here=here)))
        assert code == cp.PROBLEMS
        assert "sentences-own-subject: the shipped rules have 'its subject is incomplete.'" in err
        assert "has 'a subject is incomplete.'" in err
        assert "copy-prose" in err

    @pytest.mark.spec("drift-cmd-fails-changed-rule")
    def it_fails_a_changed_heading(self, make_repo, run):
        here = HERE.replace("Prefer short sentences", "Prefer brief sentences")
        code, _, err = run("drift", "-C", str(make_repo(here=here)))
        assert code == cp.PROBLEMS
        assert "standing-short-sentences:" in err

    @pytest.mark.spec("drift-cmd-fails-changed-rule", "drift-cmd-names-copyprose")
    def it_fails_a_sentence_added_where_the_shipped_rule_has_no_fill(self, make_repo, run):
        here = HERE.replace("is incomplete.", "is incomplete. Read it alone.")
        code, _, err = run("drift", "-C", str(make_repo(here=here)))
        assert code == cp.PROBLEMS
        assert "sentences-own-subject: %s adds 'Read it alone.'" % cp.REPO_RULES in err
        assert "copy-prose" in err

    @pytest.mark.spec("drift-cmd-fails-changed-rule")
    def it_fails_a_sentence_added_after_the_text_that_follows_a_fill(self, make_repo, run):
        shipped = SHIPPED.replace(
            "<!-- FILL: name this project's roles. -->",
            "<!-- FILL: name them. -->\n\nName the one meant.",
        )
        here = HERE.replace(
            "- **The owner** merges.", "- **The owner** merges.\n\nName the one meant. Always."
        )
        code, _, err = run("drift", "-C", str(make_repo(here=here, shipped=shipped)))
        assert code == cp.PROBLEMS
        assert "standing-name-the-role: %s adds 'Always.'" % cp.REPO_RULES in err

    @pytest.mark.spec("drift-cmd-fails-changed-rule")
    def it_fails_a_passage_dropped_after_a_fill(self, make_repo, run):
        shipped = SHIPPED.replace(
            "<!-- FILL: name this project's roles. -->",
            "<!-- FILL: name them. -->\n\nName the one meant.",
        )
        code, _, err = run("drift", "-C", str(make_repo(shipped=shipped)))
        assert code == cp.PROBLEMS
        assert "standing-name-the-role: %s lacks 'Name the one meant.'" % cp.REPO_RULES in err

    @pytest.mark.spec("drift-cmd-fails-changed-rule")
    def it_fails_a_passage_dropped_between_two_fills(self, make_repo, run):
        shipped = SHIPPED.replace(
            "<!-- FILL: name this project's roles. -->",
            "<!-- FILL: one. -->\n\nBetween.\n\n<!-- FILL: two. -->",
        )
        code, _, err = run("drift", "-C", str(make_repo(shipped=shipped)))
        assert code == cp.PROBLEMS
        assert "standing-name-the-role: %s lacks 'Between.'" % cp.REPO_RULES in err

    @pytest.mark.spec("drift-cmd-fails-changed-rule")
    def it_reads_a_heading_inside_a_fence_as_rule_text(self, make_repo, run):
        fence = "\n```sh\n# a comment\n```\n"
        here = HERE.replace("is incomplete.\n", "is incomplete.\n" + fence)
        code, _, err = run("drift", "-C", str(make_repo(here=here)))
        assert code == cp.PROBLEMS
        assert "sentences-own-subject: %s adds '```sh # a comment ```'" % cp.REPO_RULES in err

    @pytest.mark.spec("drift-cmd-fails-missing-rule", "drift-cmd-names-copyprose")
    def it_fails_a_rule_the_shipped_rules_lack(self, make_repo, run):
        here = HERE + "\n### sentences-new-rule: A new rule\n\nSay it once.\n"
        code, _, err = run("drift", "-C", str(make_repo(here=here)))
        assert code == cp.PROBLEMS
        assert "sentences-new-rule: in %s and not in %s" % (cp.REPO_RULES, cp.SHIPPED_RULES) in err
        assert "copy-prose" in err

    @pytest.mark.spec("drift-cmd-fails-missing-rule")
    def it_fails_a_rule_this_repo_lacks(self, make_repo, run):
        shipped = SHIPPED + "\n### sentences-old-rule: An old rule\n\nSay it twice.\n"
        code, _, err = run("drift", "-C", str(make_repo(shipped=shipped)))
        assert code == cp.PROBLEMS
        assert "sentences-old-rule: in %s and not in %s" % (cp.SHIPPED_RULES, cp.REPO_RULES) in err

    @pytest.mark.spec("drift-cmd-scans-something")
    @pytest.mark.parametrize("side", ["here", "shipped"])
    def it_fails_a_file_that_holds_no_rules(self, make_repo, run, side):
        root = make_repo(**{side: "# prose style\n\nNo rules yet.\n"})
        code, _, err = run("drift", "-C", str(root))
        assert code == cp.PROBLEMS
        assert "does not hold any rule" in err
        assert "and not in" not in err


class DescribeJson:
    @pytest.mark.spec("command-prints-json-envelope", "drift-cmd-fails-changed-rule")
    def it_prints_one_envelope_and_nothing_on_stderr(self, make_repo, run):
        here = HERE.replace("borrows its subject", "borrows a subject")
        code, out, err = run("drift", "--json", "-C", str(make_repo(here=here)))
        assert code == cp.PROBLEMS
        assert err == ""
        env = json.loads(out)
        assert set(env) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert env["version"] == cp.ENVELOPE_VERSION
        assert env["command"] == "drift"
        assert env["ok"] is False
        assert [e.split(":")[0] for e in env["errors"]] == ["sentences-own-subject"]
        assert env["data"] == {"matching": ["standing-name-the-role", "standing-short-sentences"]}


class DescribeMain:
    @pytest.mark.spec("script-exits-2-when-unrunnable", "script-names-remedy-on-stop")
    def it_exits_cannot_run_for_a_directory_that_does_not_exist(self, tmp_path, run):
        code, out, err = run("drift", "-C", str(tmp_path / "nope"))
        assert code == cp.CANNOT_RUN
        assert out == ""
        assert err.startswith("%s: no such directory" % cp.PROG)
        assert "-C" in err

    @pytest.mark.spec("script-exits-2-when-unrunnable", "script-names-remedy-on-stop")
    def it_exits_cannot_run_for_a_missing_rules_file(self, make_repo, run):
        code, out, err = run("drift", "-C", str(make_repo(shipped=None)))
        assert code == cp.CANNOT_RUN
        assert out == ""
        assert err.startswith("%s: cannot read %s" % (cp.PROG, cp.SHIPPED_RULES))
        assert "Restore it from main" in err

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_cannot_run_outside_a_clone(self, tmp_path, run):
        code, out, err = run("drift", "-C", str(tmp_path))
        assert code == cp.CANNOT_RUN
        assert out == ""
        assert err.startswith(cp.PROG + ":")

    @pytest.mark.spec("script-ignores-closed-pipe")
    def it_exits_ok_when_its_reader_closes_the_pipe(self, make_repo, capsys, closed_pipe):
        root = make_repo()
        closed_pipe()
        assert cp.main(["drift", "-C", str(root)]) == cp.OK
        assert capsys.readouterr().err == ""

    @pytest.mark.spec("script-ignores-closed-pipe")
    @pytest.mark.parametrize("command", [["drift"], ["--help"], ["drift", "--help"]])
    def it_exits_ok_without_a_traceback_when_its_reader_has_gone(
        self, make_repo, closed_pipe_child, command
    ):
        root = make_repo()
        assert closed_pipe_child(_PATH, *command, "-C", str(root)) == (cp.OK, "")

    @pytest.mark.spec("script-exits-2-when-unrunnable")
    def it_requires_a_subcommand(self, run):
        with pytest.raises(SystemExit) as exc:
            run()
        assert exc.value.code == cp.CANNOT_RUN

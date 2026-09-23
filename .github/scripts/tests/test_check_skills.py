"""A step copied between two of a plugin's skills, made loud.

The copy reads fine in either file, so the tests here assert that the check
speaks up, that rewrapping or burying the copy in a list does not hide it, that
its one exception stays narrow - and that it refuses to pass when it has
scanned nothing.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "check-skills.py"
_spec = importlib.util.spec_from_file_location("check_skills", _PATH)
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)

REPO_ROOT = Path(__file__).resolve().parents[3]

A = "plugins/foo/skills/a/SKILL.md"
B = "plugins/foo/skills/b/SKILL.md"

SHARED = "Report first. Change nothing until the author says so, because a silent pass\nis the diff nobody reads.\n"
SHARED_REWRAPPED = "Report first.   Change nothing until the author\nsays so, because a silent pass is the diff nobody reads.\n"

LOCATE = (
    "## Locate the script\n\n"
    "```sh\n"
    'ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"\n'
    'ls "$ROOT/scripts/foo.py"\n'
    "```\n\n"
    "Then follow `$ROOT/reference/setup.md`.\n\n"
)


def skill(name, body):
    return "---\nname: %s\ndescription: the %s skill\n---\n\n# %s\n\n%s" % (name, name, name, body)


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Keep the developer's git config (signing, hooks, default branch) out."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def make_repo(tmp_path):
    """A throwaway clone holding exactly the files a test names."""

    def build(files):
        root = tmp_path / "repo"
        root.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
        return root

    return build


@pytest.fixture
def run(capsys):
    """Drive a command through main() so argparse defaults are the real ones."""

    def go(*argv):
        capsys.readouterr()
        code = cs.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


DISTINCT = {
    A: skill("a", LOCATE + "## Step 1\n\nOnly skill a says this.\n"),
    B: skill("b", LOCATE + "## Step 1\n\nOnly skill b says this.\n"),
}


class DescribeRepeats:
    def it_names_both_files_when_two_skills_share_a_paragraph(self, make_repo, run):
        root = make_repo({A: skill("a", "Intro a.\n\n" + SHARED), B: skill("b", SHARED)})
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS
        assert A + ":" in err
        assert B + ":" in err
        assert "plugins/foo/reference/" in err

    def it_gives_the_line_each_copy_starts_on(self, make_repo, run):
        root = make_repo({A: skill("a", "Intro a.\n\n" + SHARED), B: skill("b", SHARED)})
        _, _, err = run("repeats", "-C", str(root))
        assert A + ":10" in err
        assert B + ":8" in err

    def it_ignores_differences_in_whitespace(self, make_repo, run):
        root = make_repo({A: skill("a", SHARED), B: skill("b", SHARED_REWRAPPED)})
        code, _, _ = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS

    def it_catches_one_list_item_copied_into_different_lists(self, make_repo, run):
        root = make_repo(
            {
                A: skill("a", "- only in a\n- the copied bullet\n  wraps here\n"),
                B: skill("b", "1. only in b\n2. the copied bullet wraps here\n"),
            }
        )
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "the copied bullet" in err

    def it_catches_a_repeated_code_block(self, make_repo, run):
        fence = "```sh\npython3 foo.py lint\n\npython3 foo.py list\n```\n"
        root = make_repo({A: skill("a", fence), B: skill("b", "Intro.\n\n" + fence)})
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS
        assert any("foo.py lint" in e and "foo.py list" in e for e in err.splitlines())

    def it_exempts_the_section_that_locates_the_script(self, make_repo, run):
        root = make_repo(DISTINCT)
        code, out, _ = run("repeats", "-C", str(root))
        assert code == cs.OK
        assert "no block repeated" in out

    def it_checks_the_section_after_the_one_that_locates_the_script(self, make_repo, run):
        body = LOCATE + "## Step 1\n\n" + SHARED
        root = make_repo({A: skill("a", body), B: skill("b", body)})
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "Report first" in err

    def it_checks_a_section_whose_heading_differs_from_the_exception(self, make_repo, run):
        body = "## Locate the scripts\n\n" + SHARED
        root = make_repo(
            {
                A: skill("a", body + "\n## Own\n\nOnly a.\n"),
                B: skill("b", body + "\n## Own\n\nOnly b.\n"),
            }
        )
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "Report first" in err

    def it_allows_a_paragraph_repeated_across_plugins(self, make_repo, run):
        root = make_repo(
            {A: skill("a", SHARED), "plugins/bar/skills/c/SKILL.md": skill("c", SHARED)}
        )
        code, _, _ = run("repeats", "-C", str(root))
        assert code == cs.OK

    def it_allows_a_paragraph_repeated_within_one_skill(self, make_repo, run):
        root = make_repo({A: skill("a", SHARED + "\n" + SHARED), B: skill("b", "Other.\n")})
        code, _, _ = run("repeats", "-C", str(root))
        assert code == cs.OK

    def it_ignores_repeated_headings(self, make_repo, run):
        root = make_repo(
            {
                A: skill("a", "## Step 1: refuse early\n\nOnly a.\n"),
                B: skill("b", "## Step 1: refuse early\n\nOnly b.\n"),
            }
        )
        code, _, _ = run("repeats", "-C", str(root))
        assert code == cs.OK

    def it_ignores_front_matter(self, make_repo, run):
        front = "---\nname: same\ndescription: same\n---\n\n"
        root = make_repo({A: front + "Only a.\n", B: front + "Only b.\n"})
        code, _, _ = run("repeats", "-C", str(root))
        assert code == cs.OK

    def it_sees_a_skill_that_is_not_yet_tracked(self, make_repo, run):
        root = make_repo({A: skill("a", SHARED)})
        (root / "plugins/foo/skills/b").mkdir(parents=True)
        (root / B).write_text(skill("b", SHARED))
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS
        assert B in err

    def it_fails_when_no_skill_file_exists(self, make_repo, run):
        root = make_repo({"README.md": "nothing here\n"})
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "scanning nothing" in err

    def it_fails_when_a_skill_file_yields_no_blocks(self, make_repo, run):
        root = make_repo({A: "---\nname: a\n---\n\n# a\n\n" + LOCATE, B: skill("b", "Only b.\n")})
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.PROBLEMS
        assert A in err
        assert "gone blind" in err

    def it_accepts_the_repo_as_it_stands(self, run):
        code, _, _ = run("repeats", "-C", str(REPO_ROOT))
        assert code == cs.OK


class DescribeMain:
    @pytest.mark.parametrize("command", ["repeats"])
    def it_prints_the_same_envelope_for_every_command(self, make_repo, run, command):
        root = make_repo(DISTINCT)
        code, out, _ = run(command, "-C", str(root), "--json")
        assert code == cs.OK
        body = json.loads(out)
        assert set(body) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert body["command"] == command
        assert body["ok"] is True

    def it_reports_problems_in_the_envelope_rather_than_on_stderr(self, make_repo, run):
        root = make_repo({A: skill("a", SHARED), B: skill("b", SHARED)})
        code, out, err = run("repeats", "-C", str(root), "--json")
        assert code == cs.PROBLEMS
        body = json.loads(out)
        assert body["ok"] is False
        assert body["data"]["repeats"][0]["plugin"] == "foo"
        assert err == ""

    def it_cannot_run_outside_a_clone(self, tmp_path, run):
        code, _, err = run("repeats", "-C", str(tmp_path))
        assert code == cs.CANNOT_RUN
        assert err.startswith(cs.PROG + ":")

    def it_rejects_an_unknown_command(self, run):
        with pytest.raises(SystemExit) as exc:
            run("nonsense")
        assert exc.value.code == cs.CANNOT_RUN

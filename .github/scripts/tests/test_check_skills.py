"""What check-skills.py says about a plugin's skills.

`repeats`: a step copied between two of a plugin's skills, made loud. The copy
reads fine in either file, so the tests here assert that the check speaks up,
that rewrapping or burying the copy in a list does not hide it, that its one
exception stays narrow - and that it refuses to pass when it has scanned
nothing.

`descriptions`: Cowork's .plugin upload rejects a description holding an
XML-like tag, and nothing else in CI notices. The check fails by absence - a
pattern or a file selection that stops matching passes everything - so each
rule gets a repo that breaks it and a test that the check says so.
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


def described(description, body="# A skill\n"):
    return "---\nname: foo\ndescription: %s\n---\n\n%s" % (description, body)


def commit(root):
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], check=True, capture_output=True)


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


SKILL = "plugins/foo/skills/foo/SKILL.md"


class DescribeDescriptions:
    def it_passes_a_description_with_no_tag(self, make_repo, run):
        root = make_repo({SKILL: described("Does foo. Use when asked to foo.")})
        code, out, err = run("descriptions", "-C", str(root))
        assert code == cs.OK
        assert "1 skill description(s) clear" in out
        assert err == ""

    def it_fails_a_skill_whose_description_holds_a_tag(self, make_repo, run):
        root = make_repo({SKILL: described("Reads explicit <ins> markup.")})
        code, out, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "%s:3: description contains an XML-like tag `<ins`" % SKILL in err
        assert out == ""
        assert 'COWORK.md, under "How skills load"' in err

    def it_fails_a_tag_on_a_continuation_line(self, make_repo, run):
        text = "---\nname: foo\ndescription: >\n  Does foo.\n  Reads <del> too.\n---\n"
        root = make_repo({SKILL: text})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "%s:5:" % SKILL in err
        assert "`<del`" in err

    @pytest.mark.parametrize("tag", ["</del>", "<br/>", "<x:y>", "<Repl a='b'>"])
    def it_fails_a_closing_self_closing_or_attributed_tag(self, make_repo, run, tag):
        root = make_repo({SKILL: described("Handles %s markup." % tag)})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "XML-like tag" in err

    @pytest.mark.parametrize("text", ["Runs when a < b.", "Loves prose <3.", "Uses << and <-"])
    def it_passes_a_less_than_sign_not_followed_by_a_name(self, make_repo, run, text):
        root = make_repo({SKILL: described(text)})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.OK, err

    def it_checks_generated_skill_templates(self, make_repo, run):
        path = "plugins/foo/skills/foo/templates/history-skill.md"
        root = make_repo({SKILL: described("Does foo."), path: described("History for <b>it</b>.")})
        code, out, err = run("descriptions", "--json", "-C", str(root))
        assert code == cs.PROBLEMS
        result = json.loads(out)
        assert path in result["data"]["checked"]
        assert any(e.startswith(path + ":3:") for e in result["errors"])

    def it_ignores_front_matter_without_a_description(self, make_repo, run):
        style = "plugins/foo/templates/prose-style.md"
        root = make_repo({SKILL: described("Does foo."), style: "---\nname: <x>\n---\n"})
        code, out, err = run("descriptions", "--json", "-C", str(root))
        assert code == cs.OK, err
        assert json.loads(out)["data"]["checked"] == [SKILL]

    def it_ignores_a_tag_in_the_skill_body(self, make_repo, run):
        text = described("Does foo.", body="Tag with <ins>.\ndescription: <del>\n")
        root = make_repo({SKILL: text})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.OK, err

    def it_stops_reading_at_the_end_of_the_front_matter(self, make_repo, run):
        other = "plugins/foo/notes.md"
        text = "---\nname: notes\n---\n\ndescription: <ins>\n"
        root = make_repo({SKILL: described("Does foo."), other: text})
        code, out, err = run("descriptions", "--json", "-C", str(root))
        assert code == cs.OK, err
        assert json.loads(out)["data"]["checked"] == [SKILL]

    def it_ignores_markdown_outside_plugins(self, make_repo, run):
        root = make_repo({SKILL: described("Does foo."), "docs/SKILL.md": described("<ins>")})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.OK, err

    def it_checks_a_committed_file(self, make_repo, run):
        root = make_repo({SKILL: described("Has <ins>.")})
        commit(root)
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert SKILL in err

    def it_checks_a_file_git_is_not_yet_tracking(self, make_repo, run):
        root = make_repo({SKILL: described("Does foo.")})
        commit(root)
        new = "plugins/foo/skills/bar/SKILL.md"
        (root / new).parent.mkdir(parents=True)
        (root / new).write_text(described("Has <ins>."))
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert new in err

    def it_skips_a_file_git_ignores(self, make_repo, run):
        ignored = "plugins/foo/skills/scratch/SKILL.md"
        root = make_repo(
            {
                SKILL: described("Does foo."),
                ignored: described("Has <ins>."),
                ".gitignore": "scratch/\n",
            }
        )
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.OK, err

    def it_fails_when_it_finds_no_descriptions(self, make_repo, run):
        root = make_repo({"plugins/foo/README.md": "# Foo\n"})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "found no markdown under plugins/" in err

    def it_reports_json_with_the_shared_envelope(self, make_repo, run):
        root = make_repo({SKILL: described("Has <ins>.")})
        code, out, err = run("descriptions", "--json", "-C", str(root))
        assert code == cs.PROBLEMS
        assert err == ""
        result = json.loads(out)
        assert set(result) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert result["version"] == cs.ENVELOPE_VERSION
        assert result["command"] == "descriptions"
        assert result["ok"] is False

    def it_passes_the_repo_as_it_stands(self, run):
        code, out, err = run("descriptions", "--json", "-C", str(REPO_ROOT))
        assert code == cs.OK, err
        checked = json.loads(out)["data"]["checked"]
        assert any(p.endswith("/SKILL.md") for p in checked)
        assert any("/templates/" in p for p in checked)


class DescribeMain:
    @pytest.mark.parametrize("command", ["repeats", "descriptions"])
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

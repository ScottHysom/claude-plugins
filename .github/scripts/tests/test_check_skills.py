"""The check that keeps skill descriptions uploadable to Cowork.

Cowork's .plugin upload rejects a description holding an XML-like tag, and
nothing else in CI notices. The check fails by absence - a pattern or a file
selection that stops matching passes everything - so each rule gets a repo
that breaks it and a test that the check says so.
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

REPO = Path(__file__).resolve().parents[3]


def skill(description, body="# A skill\n"):
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
    """A throwaway clone holding the given files, as {path: text}."""

    def build(files):
        root = tmp_path / "repo"
        root.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        for path, text in files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
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


SKILL = "plugins/foo/skills/foo/SKILL.md"


class DescribeDescriptions:
    def it_passes_a_description_with_no_tag(self, make_repo, run):
        root = make_repo({SKILL: skill("Does foo. Use when asked to foo.")})
        code, out, err = run("descriptions", "-C", str(root))
        assert code == cs.OK
        assert "1 skill description(s) clear" in out
        assert err == ""

    def it_fails_a_skill_whose_description_holds_a_tag(self, make_repo, run):
        root = make_repo({SKILL: skill("Reads explicit <ins> markup.")})
        code, out, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "%s:3: description contains an XML-like tag `<ins`" % SKILL in err
        assert out == ""

    def it_fails_a_tag_on_a_continuation_line(self, make_repo, run):
        text = "---\nname: foo\ndescription: >\n  Does foo.\n  Reads <del> too.\n---\n"
        root = make_repo({SKILL: text})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "%s:5:" % SKILL in err
        assert "`<del`" in err

    @pytest.mark.parametrize("tag", ["</del>", "<br/>", "<x:y>", "<Repl a='b'>"])
    def it_fails_a_closing_self_closing_or_attributed_tag(self, make_repo, run, tag):
        root = make_repo({SKILL: skill("Handles %s markup." % tag)})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "XML-like tag" in err

    @pytest.mark.parametrize("text", ["Runs when a < b.", "Loves prose <3.", "Uses << and <-"])
    def it_passes_a_less_than_sign_not_followed_by_a_name(self, make_repo, run, text):
        root = make_repo({SKILL: skill(text)})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.OK, err

    def it_checks_generated_skill_templates(self, make_repo, run):
        path = "plugins/foo/skills/foo/templates/history-skill.md"
        root = make_repo({SKILL: skill("Does foo."), path: skill("History for <b>it</b>.")})
        code, out, err = run("descriptions", "--json", "-C", str(root))
        assert code == cs.PROBLEMS
        result = json.loads(out)
        assert path in result["data"]["checked"]
        assert any(e.startswith(path + ":3:") for e in result["errors"])

    def it_ignores_front_matter_without_a_description(self, make_repo, run):
        style = "plugins/foo/templates/prose-style.md"
        root = make_repo({SKILL: skill("Does foo."), style: "---\nname: <x>\n---\n"})
        code, out, err = run("descriptions", "--json", "-C", str(root))
        assert code == cs.OK, err
        assert json.loads(out)["data"]["checked"] == [SKILL]

    def it_ignores_a_tag_in_the_skill_body(self, make_repo, run):
        text = skill("Does foo.", body="Tag with <ins>.\ndescription: <del>\n")
        root = make_repo({SKILL: text})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.OK, err

    def it_stops_reading_at_the_end_of_the_front_matter(self, make_repo, run):
        other = "plugins/foo/notes.md"
        text = "---\nname: notes\n---\n\ndescription: <ins>\n"
        root = make_repo({SKILL: skill("Does foo."), other: text})
        code, out, err = run("descriptions", "--json", "-C", str(root))
        assert code == cs.OK, err
        assert json.loads(out)["data"]["checked"] == [SKILL]

    def it_ignores_markdown_outside_plugins(self, make_repo, run):
        root = make_repo({SKILL: skill("Does foo."), "docs/SKILL.md": skill("<ins>")})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.OK, err

    def it_checks_a_committed_file(self, make_repo, run):
        root = make_repo({SKILL: skill("Has <ins>.")})
        commit(root)
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert SKILL in err

    def it_checks_a_file_git_is_not_yet_tracking(self, make_repo, run):
        root = make_repo({SKILL: skill("Does foo.")})
        commit(root)
        new = "plugins/foo/skills/bar/SKILL.md"
        (root / new).parent.mkdir(parents=True)
        (root / new).write_text(skill("Has <ins>."))
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert new in err

    def it_skips_a_file_git_ignores(self, make_repo, run):
        ignored = "plugins/foo/skills/scratch/SKILL.md"
        root = make_repo(
            {SKILL: skill("Does foo."), ignored: skill("Has <ins>."), ".gitignore": "scratch/\n"}
        )
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.OK, err

    def it_fails_when_it_finds_no_descriptions(self, make_repo, run):
        root = make_repo({"plugins/foo/README.md": "# Foo\n"})
        code, _, err = run("descriptions", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "found no markdown under plugins/" in err

    def it_reports_json_with_the_shared_envelope(self, make_repo, run):
        root = make_repo({SKILL: skill("Has <ins>.")})
        code, out, err = run("descriptions", "--json", "-C", str(root))
        assert code == cs.PROBLEMS
        assert err == ""
        result = json.loads(out)
        assert set(result) == {"version", "command", "ok", "errors", "warnings", "data"}
        assert result["version"] == cs.ENVELOPE_VERSION
        assert result["command"] == "descriptions"
        assert result["ok"] is False

    def it_cannot_run_outside_a_clone(self, tmp_path, run):
        code, out, err = run("descriptions", "-C", str(tmp_path / "missing"))
        assert code == cs.CANNOT_RUN
        assert err.startswith("check-skills.py: ")
        assert out == ""

    def it_passes_the_repo_as_it_stands(self, run):
        code, out, err = run("descriptions", "--json", "-C", str(REPO))
        assert code == cs.OK, err
        checked = json.loads(out)["data"]["checked"]
        assert any(p.endswith("/SKILL.md") for p in checked)
        assert any("/templates/" in p for p in checked)

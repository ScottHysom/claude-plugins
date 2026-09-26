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

`commands`: a skill naming a subcommand or flag its script lacks sends the
model into a usage error mid-run. The tests give a throwaway plugin a small
script with a real parser, and check that each form a skill writes a command
in reaches that parser, and that a check which found nothing to resolve fails.

`fences`: a shell fence that runs grep or `python3 -c` has the model compute by
hand what the script should. The tests give each allowed setup line a case
that passes where it belongs and fails where it does not, since an allowlist
entry that holds anywhere is a hole.

`steps`: a step with no command leaves its work to the model unless it says
why, and a step running two commands leaves the work between them to the
model unless it names the seam. The tests build a skill whose steps run a
command, two commands, carry a marker or do neither. They check each rule the
markers, KNOWN_GAPS and KNOWN_SEAMS follow, and that the check fails when it
finds no step. KNOWN_GAPS and KNOWN_SEAMS are emptied for every test, since a
throwaway repo holds none of the real steps they list.
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
    'FOO="$ROOT/scripts/foo.py"\n'
    'ls "$FOO" || echo "foo is not installed"\n'
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


REAL_GAPS = dict(cs.KNOWN_GAPS)
REAL_SEAMS = dict(getattr(cs, "KNOWN_SEAMS", {}))


@pytest.fixture(autouse=True)
def no_known_gaps(monkeypatch):
    """A throwaway repo has none of the real skills, so none of their gaps or seams."""
    monkeypatch.setattr(cs, "KNOWN_GAPS", {})
    monkeypatch.setattr(cs, "KNOWN_SEAMS", {}, raising=False)


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

    @pytest.mark.spec("repeats-skips-markers")
    def it_ignores_a_marker_two_skills_share(self, make_repo, run):
        shared = "<!-- spec: one-question-round -->\n"
        root = make_repo(
            {
                A: skill("a", "## Step 1: ask\n" + shared + "\nOnly a.\n"),
                B: skill("b", "## Step 2: ask\n" + shared + "\nOnly b.\n"),
            }
        )
        code, _, err = run("repeats", "-C", str(root))
        assert code == cs.OK, err

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


FOO_SCRIPT = "plugins/foo/scripts/foo.py"
FOO_REFERENCE = "plugins/foo/reference/setup.md"

# A script with the shape the plugin scripts have: build_parser(), and main()
# only under __main__.
FOO_PY = """import argparse


def build_parser():
    ap = argparse.ArgumentParser(prog="foo.py")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("lint")
    p.add_argument("--file")
    p.add_argument("--json", action="store_true")
    config = sub.add_parser("config").add_subparsers(dest="action", required=True)
    c = config.add_parser("list")
    c.add_argument("--json", action="store_true")
    return ap


if __name__ == "__main__":
    raise SystemExit("main ran on import")
"""

FOO_LOCATE = (
    "## Locate the script\n\n"
    "```sh\n"
    'ROOT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_SKILL_DIR}/../..}"\n'
    'FOO="$ROOT/scripts/foo.py"\n'
    "```\n\n"
)


def uses(fence, script=FOO_PY):
    """A plugin whose one skill sets $FOO and then runs this fence."""
    files = {SKILL: skill("foo", FOO_LOCATE + "## Step 1\n\n" + fence)}
    if script is not None:
        files[FOO_SCRIPT] = script
    return files


def sh(*lines):
    return "```sh\n" + "".join(line + "\n" for line in lines) + "```\n"


class DescribeCommands:
    def it_accepts_commands_the_script_has(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint --json', 'python3 "$FOO" config list')))
        code, out, err = run("commands", "-C", str(root))
        assert code == cs.OK, err
        assert "2 invocation(s) in 1 file(s)" in out

    def it_rejects_an_unknown_subcommand(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" config nope')))
        code, out, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert out == ""
        assert "%s:18:" % SKILL in err
        assert "nope" in err
        assert "invalid choice" in err

    def it_rejects_an_unknown_flag(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint --fix')))
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "unrecognized arguments: --fix" in err

    def it_reads_the_prefix_form(self, make_repo, run):
        root = make_repo(
            {
                SKILL: skill("foo", "No fence here.\n"),
                FOO_SCRIPT: FOO_PY,
                FOO_REFERENCE: sh('cd "<dir>" && FOO=.foo/foo.py && python3 "$FOO" lint --bad'),
            }
        )
        code, out, err = run("commands", "--json", "-C", str(root))
        assert code == cs.PROBLEMS
        body = json.loads(out)
        [found] = body["data"]["invocations"]
        assert found["script"] == FOO_SCRIPT
        assert found["argv"] == ["lint", "--bad"]
        assert any(e.startswith(FOO_REFERENCE + ":2:") for e in body["errors"])

    def it_reads_a_variable_a_sibling_file_sets(self, make_repo, run):
        files = uses(sh('python3 "$FOO" lint'))
        files[FOO_REFERENCE] = sh('python3 "$FOO" config list --json')
        root = make_repo(files)
        code, out, err = run("commands", "--json", "-C", str(root))
        assert code == cs.OK, err
        paths = [i["path"] for i in json.loads(out)["data"]["invocations"]]
        assert FOO_REFERENCE in paths

    def it_accepts_placeholders_and_optional_parts(self, make_repo, run):
        fence = sh(
            'python3 "$FOO" lint --file <two words> \\',
            "  [--json]                # the comment goes",
        )
        root = make_repo(uses(fence))
        code, out, err = run("commands", "--json", "-C", str(root))
        assert code == cs.OK, err
        [found] = json.loads(out)["data"]["invocations"]
        assert found["argv"] == ["lint", "--file", cs.PLACEHOLDER, "--json"]

    def it_checks_the_flag_inside_an_optional_part(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint [--fix]')))
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "--fix" in err

    def it_does_not_read_a_heredoc_body(self, make_repo, run):
        fence = sh(
            "python3 \"$FOO\" lint --file - <<'END'",
            'python3 "$FOO" nope',
            "END",
            'python3 "$FOO" config list',
        )
        root = make_repo(uses(fence))
        code, out, err = run("commands", "--json", "-C", str(root))
        assert code == cs.OK, err
        argvs = [i["argv"] for i in json.loads(out)["data"]["invocations"]]
        assert argvs == [["lint", "--file", "-"], ["config", "list"]]

    def it_skips_a_fence_that_is_not_shell(self, make_repo, run):
        fence = sh('python3 "$FOO" lint') + '\n```\npython3 "$FOO" nope\n```\n'
        fence += '\n```text\npython3 "$FOO" nope\n```\n'
        root = make_repo(uses(fence))
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.OK, err

    def it_reads_a_fence_indented_in_a_list(self, make_repo, run):
        fence = '1. Run it:\n\n   ```sh\n   python3 "$FOO" nope\n   ```\n'
        root = make_repo(uses(fence))
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "nope" in err

    def it_resolves_a_repo_script_by_its_path(self, make_repo, run):
        files = uses(sh("python3 .github/scripts/bar.py lint --fix"))
        files[".github/scripts/bar.py"] = FOO_PY
        root = make_repo(files)
        code, out, err = run("commands", "--json", "-C", str(root))
        assert code == cs.PROBLEMS
        [found] = json.loads(out)["data"]["invocations"]
        assert found["script"] == ".github/scripts/bar.py"
        assert "--fix" in json.loads(out)["errors"][0]

    def it_rejects_a_script_that_does_not_exist(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint'), script=None))
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "%s does not exist" % FOO_SCRIPT in err

    def it_rejects_a_variable_no_assignment_names(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$BAR" lint')))
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "no assignment in plugins/foo/ names a script for $BAR" in err

    def it_rejects_one_variable_naming_two_scripts(self, make_repo, run):
        files = uses(sh('python3 "$FOO" lint'))
        files[FOO_REFERENCE] = sh("FOO=.foo/other.py")
        root = make_repo(files)
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "plugins/foo/scripts/other.py" in err

    def it_fails_when_a_script_has_no_parser(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint'), script="print('no parser')\n"))
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "has no build_parser()" in err

    def it_fails_when_it_finds_no_invocation(self, make_repo, run):
        root = make_repo(uses(sh("ls")))
        code, _, err = run("commands", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "found no script invocation" in err

    def it_accepts_the_repo_as_it_stands(self, run):
        code, out, err = run("commands", "--json", "-C", str(REPO_ROOT))
        assert code == cs.OK, err
        scripts = set(i["script"] for i in json.loads(out)["data"]["invocations"])
        assert "plugins/prose-tuning/scripts/prose.py" in scripts
        assert "plugins/gitify-cowork-project/scripts/gitify.py" in scripts


RUNS = sh('python3 "$FOO" lint')


def steps(*bodies, head=""):
    """A plugin whose one skill sets $FOO, says `head`, then has these steps."""
    text = FOO_LOCATE + head
    for n, body in enumerate(bodies, start=1):
        text += "## Step %d: s%d\n\n%s\n" % (n, n, body)
    return {SKILL: skill("foo", text), FOO_SCRIPT: FOO_PY}


def marker(reason):
    return "<!-- no-command: %s -->\n" % reason


def seam(kind, reason):
    return "<!-- seam: %s: %s -->\n" % (kind, reason)


TWO = sh('python3 "$FOO" lint', 'python3 "$FOO" lint')


class DescribeSteps:
    def it_accepts_steps_that_run_a_command_or_say_why_not(self, make_repo, run):
        root = make_repo(steps(RUNS, marker("the author decides")))
        code, out, err = run("steps", "-C", str(root))
        assert code == cs.OK, err
        assert "2 step(s)" in out

    def it_rejects_a_step_with_neither(self, make_repo, run):
        root = make_repo(steps(RUNS, "Think hard about it.\n"))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert '%s:21: "Step 2: s2" names no command' % SKILL in err

    def it_does_not_count_a_command_its_script_rejects(self, make_repo, run):
        root = make_repo(steps(sh('python3 "$FOO" nope')))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "names no command" in err

    def it_rejects_a_marker_without_a_reason(self, make_repo, run):
        root = make_repo(steps(RUNS, marker("")))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "gives no reason" in err

    def it_rejects_a_marker_inside_a_line(self, make_repo, run):
        root = make_repo(steps(RUNS, "Decide. <!-- no-command: the author decides -->\n"))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "must be a line of its own" in err

    def it_rejects_a_marker_outside_a_step(self, make_repo, run):
        root = make_repo(steps(RUNS, head=marker("stray") + "\n"))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "outside any step" in err

    def it_rejects_a_stale_marker(self, make_repo, run):
        root = make_repo(steps(marker("nothing to run") + "\n" + RUNS))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "marker is stale" in err

    def it_lists_each_marked_step(self, make_repo, run):
        root = make_repo(steps(RUNS, marker("the author decides"), marker("hand off")))
        code, out, _ = run("steps", "-C", str(root))
        assert code == cs.OK
        assert "%s:21 Step 2: s2: the author decides" % SKILL in out
        assert "Step 3: s3: hand off" in out
        code, out, _ = run("steps", "--json", "-C", str(root))
        marked = json.loads(out)["data"]["marked"]
        assert [(m["heading"], m["reason"]) for m in marked] == [
            ("Step 2: s2", "the author decides"),
            ("Step 3: s3", "hand off"),
        ]

    def it_keeps_a_heading_inside_a_fence_in_its_step(self, make_repo, run):
        body = "```markdown\n## Not a heading\n```\n\n" + RUNS
        root = make_repo(steps(body))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.OK, err

    def it_ends_a_step_at_the_next_section(self, make_repo, run):
        files = steps(marker("the author decides"))
        files[SKILL] += "## Abandoning a run\n\n" + RUNS
        root = make_repo(files)
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.OK, err

    def it_warns_for_a_known_gap(self, make_repo, run, monkeypatch):
        monkeypatch.setattr(cs, "KNOWN_GAPS", {(SKILL, 2): 123})
        root = make_repo(steps(RUNS, "Do it by hand for now.\n"))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.OK, err
        assert 'warning: %s:21: "Step 2: s2" runs no command yet; #123' % SKILL in err

    def it_rejects_a_known_gap_that_has_a_command(self, make_repo, run, monkeypatch):
        monkeypatch.setattr(cs, "KNOWN_GAPS", {(SKILL, 1): 123})
        root = make_repo(steps(RUNS))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "Remove its KNOWN_GAPS entry, which points to #123" in err

    def it_rejects_a_known_gap_with_no_step(self, make_repo, run, monkeypatch):
        monkeypatch.setattr(cs, "KNOWN_GAPS", {(SKILL, 7): 123})
        root = make_repo(steps(RUNS))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "there is no such step" in err

    def it_fails_when_it_finds_no_step(self, make_repo, run):
        root = make_repo({SKILL: skill("foo", FOO_LOCATE + "## Usage\n\nRun it.\n")})
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "found no `## Step` heading" in err

    def it_rejects_two_commands_with_no_seam_marker(self, make_repo, run):
        root = make_repo(steps(RUNS, TWO))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert '%s:21: "Step 2: s2" runs 2 commands' % SKILL in err
        assert "<!-- seam: <kind>: <reason> -->" in err

    @pytest.mark.parametrize("kind", ["judgment", "platform"])
    def it_accepts_two_commands_under_a_named_seam(self, make_repo, run, kind):
        root = make_repo(steps(seam(kind, "the author approves the report") + "\n" + TWO))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.OK, err

    def it_rejects_a_seam_of_an_unknown_kind(self, make_repo, run):
        root = make_repo(steps(seam("courier", "passes the list along") + "\n" + TWO))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "kind `courier`" in err
        assert "judgment or platform" in err

    def it_rejects_a_seam_marker_without_a_reason(self, make_repo, run):
        root = make_repo(steps(seam("judgment", "") + "\n" + TWO))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "a seam marker gives no reason" in err

    def it_rejects_a_seam_marker_inside_a_line(self, make_repo, run):
        body = "Decide. <!-- seam: judgment: the author decides -->\n\n" + TWO
        root = make_repo(steps(body))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "a seam marker must be a line of its own" in err

    def it_rejects_a_seam_marker_outside_a_step(self, make_repo, run):
        root = make_repo(steps(RUNS, head=seam("judgment", "stray") + "\n"))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "a seam marker sits outside any step" in err

    def it_rejects_a_stale_seam_marker(self, make_repo, run):
        root = make_repo(steps(seam("judgment", "the author decides") + "\n" + RUNS))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "runs one command or none and carries a seam marker" in err

    def it_lists_each_step_that_runs_more_than_one_command(self, make_repo, run):
        root = make_repo(steps(RUNS, seam("platform", "device_bash") + "\n" + TWO))
        code, out, err = run("steps", "-C", str(root))
        assert code == cs.OK, err
        assert "Steps that run more than one command:" in out
        assert "%s:21 Step 2: s2: 2 commands, platform: device_bash" % SKILL in out
        code, out, _ = run("steps", "--json", "-C", str(root))
        seams = json.loads(out)["data"]["seams"]
        assert [(s["heading"], s["invocations"], s["kind"], s["reason"]) for s in seams] == [
            ("Step 2: s2", 2, "platform", "device_bash"),
        ]

    def it_warns_for_a_known_seam(self, make_repo, run, monkeypatch):
        monkeypatch.setattr(cs, "KNOWN_SEAMS", {(SKILL, 2): 131})
        root = make_repo(steps(RUNS, TWO))
        code, out, err = run("steps", "-C", str(root))
        assert code == cs.OK, err
        assert (
            'warning: %s:21: "Step 2: s2" runs 2 commands with no seam marker yet; #131' % SKILL
            in err
        )
        assert "%s:21 Step 2: s2: 2 commands, unmarked until #131" % SKILL in out

    def it_rejects_a_known_seam_that_runs_one_command(self, make_repo, run, monkeypatch):
        monkeypatch.setattr(cs, "KNOWN_SEAMS", {(SKILL, 1): 131})
        root = make_repo(steps(RUNS))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "Remove its KNOWN_SEAMS entry, which points to #131" in err

    def it_rejects_a_known_seam_with_no_step(self, make_repo, run, monkeypatch):
        monkeypatch.setattr(cs, "KNOWN_SEAMS", {(SKILL, 7): 131})
        root = make_repo(steps(RUNS))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "KNOWN_SEAMS lists step 7" in err

    def it_rejects_a_known_seam_that_also_has_a_marker(self, make_repo, run, monkeypatch):
        monkeypatch.setattr(cs, "KNOWN_SEAMS", {(SKILL, 1): 131})
        root = make_repo(steps(seam("judgment", "the author decides") + "\n" + TWO))
        code, _, err = run("steps", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "a seam marker and a KNOWN_SEAMS entry for #131" in err

    def it_accepts_the_repo_as_it_stands(self, run, monkeypatch):
        monkeypatch.setattr(cs, "KNOWN_GAPS", REAL_GAPS)
        monkeypatch.setattr(cs, "KNOWN_SEAMS", REAL_SEAMS, raising=False)
        code, out, err = run("steps", "--json", "-C", str(REPO_ROOT))
        assert code == cs.OK, err
        data = json.loads(out)["data"]
        assert any(s["invocations"] for s in data["steps"])
        assert data["marked"]


class DescribeFences:
    def it_rejects_python_dash_c(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint', "python3 -c 'print(1)'")))
        code, out, err = run("fences", "-C", str(root))
        assert code == cs.PROBLEMS
        assert out == ""
        assert "%s:19: `python3`" % SKILL in err

    def it_rejects_grep_in_a_pipeline(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint --json | grep -c ok')))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "%s:18: `grep`" % SKILL in err

    def it_rejects_a_fence_without_an_info_string(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint') + "\n```\n<del>x</del>\n```\n"))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "%s:21: fence has no info string" % SKILL in err

    def it_allows_the_findings_heredoc(self, make_repo, run):
        fence = sh(
            "cat > \"${TMPDIR:-/tmp}/foo-findings.json\" <<'END'",
            '{"findings": []}',
            "END",
            'python3 "$FOO" lint --file "${TMPDIR:-/tmp}/foo-findings.json"',
        )
        root = make_repo(uses(fence))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.OK, err

    def it_does_not_scan_a_heredoc_body(self, make_repo, run):
        fence = sh("python3 \"$FOO\" lint --file - <<'END'", "grep -v x | awk '{print}'", "END")
        root = make_repo(uses(fence))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.OK, err

    def it_rejects_a_heredoc_that_is_not_the_findings_file(self, make_repo, run):
        root = make_repo(uses(sh("cat > notes.txt <<'END'", "x", "END")))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "`cat`" in err

    def it_rejects_the_findings_heredoc_sharing_its_line(self, make_repo, run):
        line = 'python3 "$FOO" lint && cat > "${TMPDIR:-/tmp}/foo-findings.json" <<\'END\''
        root = make_repo(uses(sh(line, "{}", "END")))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "`cat`" in err

    def it_allows_a_leading_cd(self, make_repo, run):
        root = make_repo(
            uses(sh('cd "<project folder>" && FOO=.foo/foo.py && python3 "$FOO" lint'))
        )
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.OK, err

    def it_rejects_cd_anywhere_but_the_start(self, make_repo, run):
        root = make_repo(uses(sh('python3 "$FOO" lint && cd ..')))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "`cd`" in err

    def it_rejects_echo_that_does_not_follow_the_installed_check(self, make_repo, run):
        root = make_repo(uses(sh('echo "$FOO" | cut -d/ -f1')))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "`echo`" in err
        assert "`cut`" in err

    def it_allows_the_installed_check_in_locate_the_script(self, make_repo, run):
        root = make_repo(uses(sh('ls "$FOO" || echo "foo is not installed"')))
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.OK, err

    def it_fails_when_it_finds_no_shell_fence(self, make_repo, run):
        root = make_repo({SKILL: skill("foo", "```text\nls\n```\n")})
        code, _, err = run("fences", "-C", str(root))
        assert code == cs.PROBLEMS
        assert "found no shell fence" in err

    def it_accepts_the_repo_as_it_stands(self, run):
        code, out, err = run("fences", "--json", "-C", str(REPO_ROOT))
        assert code == cs.OK, err
        allowed = set(c["allowed"] for c in json.loads(out)["data"]["commands"])
        assert cs.INVOCATION in allowed
        assert "findings heredoc" in allowed

    def it_keeps_each_fences_info_string(self):
        text = "```sh\nls\n```\n\n```\nplain\n```\n\n~~~Text\nx\n~~~\n"
        assert [f.info for f in cs.fences(text)] == ["sh", "", "text"]

    def it_numbers_body_lines_from_the_file(self):
        [fence] = cs.fences("intro\n\n```sh\na\nb\n```\n")
        assert fence.line == 3
        assert fence.body == [(4, "a"), (5, "b")]


class DescribeMain:
    @pytest.mark.parametrize("command", ["repeats", "descriptions", "commands", "steps", "fences"])
    def it_prints_the_same_envelope_for_every_command(self, make_repo, run, command):
        root = make_repo(
            {
                A: skill("a", FOO_LOCATE + "## Step 1\n\n" + sh('python3 "$FOO" lint')),
                B: skill(
                    "b", LOCATE + "## Step 1\n\n" + marker("only skill b says this") + "\nOnly b.\n"
                ),
                FOO_SCRIPT: FOO_PY,
            }
        )
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

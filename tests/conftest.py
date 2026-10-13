"""Fixtures that hand a test a git repository, shared by every suite.

pytest loads this file for the plugin suites under tests/.
.github/scripts/tests/conftest.py loads it by path, since pytest does not
look for a conftest.py in the directories above that suite.
"""

import shutil
import subprocess

import pytest


def init(root):
    root.mkdir(parents=True, exist_ok=True)
    # capture_output so git's default-branch hint stays out of the CI log.
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)


@pytest.fixture(scope="session")
def repo_copy(tmp_path_factory):
    """Copy a repository built once per run to a path a test owns.

    Call it with a function that builds the repository at the path it is
    given, and the path to copy it to, which must not exist yet. The first
    call with a given function builds it; every call copies it, so each test
    still changes a repository of its own. Starting a git process is slow on
    macOS, and copying is several times faster than `git init`, `add` and
    `commit`. With pytest-xdist, each worker builds its own.

    The build runs with the developer's git config shut out, so a repository
    is the same whichever suite built it first. A builder that commits names
    its own author.
    """
    built = {}
    # A template holding only an empty hooks directory keeps `git init` and
    # `git clone` from writing their sample hooks, which never run and would
    # double the copy. A test can still write a hook of its own.
    template = tmp_path_factory.mktemp("git-template")
    (template / "hooks").mkdir()

    def copy(build, dest):
        if build not in built:
            src = tmp_path_factory.mktemp("template") / "repo"
            with pytest.MonkeyPatch.context() as env:
                env.setenv("GIT_TEMPLATE_DIR", str(template))
                env.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
                env.setenv("GIT_CONFIG_NOSYSTEM", "1")
                build(src)
            built[build] = src
        shutil.copytree(str(built[build]), str(dest), symlinks=True)
        return dest

    return copy


@pytest.fixture
def git_init(repo_copy):
    """`git init` at a path that does not exist yet, as a copy."""
    return lambda root: repo_copy(init, root)

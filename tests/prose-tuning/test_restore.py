"""restore: a mangled file goes back to the last commit.

update-prose-config's "Abandoning a run" uses it where `git checkout` would
fail on Cowork's device bridge, which cannot delete a file.
"""

import pytest

import prose


class DescribeRestore:
    @pytest.mark.spec("restore-from-head")
    def it_writes_the_file_as_it_was_at_the_last_commit(self, prose_repo, target):
        prose_repo.commit()
        (prose_repo.root / "target.md").write_text("Mangled.\n")
        code, env = prose_repo.run("restore", "--file", str(prose_repo.root / "target.md"))
        assert code == prose.OK, env["errors"]
        assert prose_repo.read() == target

    @pytest.mark.spec("restore-from-head")
    def it_names_a_file_the_last_commit_does_not_hold(self, prose_repo):
        prose_repo.commit()
        new = prose_repo.root / "new.md"
        new.write_text("Written since.\n")
        code, env = prose_repo.run("restore", "--file", str(new))
        assert (code, env) == (prose.CANNOT_RUN, None)
        assert "new.md is not in HEAD" in prose_repo.err
        assert new.read_text() == "Written since.\n"

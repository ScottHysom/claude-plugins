"""todos.py drafts: the file a run of do-todos writes its drafts to."""

import json
from pathlib import Path

import pytest

import todos


class DescribeDrafts:
    @pytest.fixture(autouse=True)
    def tempdir(self, monkeypatch, tmp_path):
        """The temporary directory drafts makes its file in."""
        monkeypatch.setattr(todos.tempfile, "tempdir", str(tmp_path))
        return tmp_path

    @pytest.mark.spec("drafts-cmd-makes-own-file")
    def it_makes_an_empty_file_in_the_temporary_directory(self, capsys, tempdir):
        code = todos.main(["drafts", "--json"])
        assert code == todos.OK
        path = Path(json.loads(capsys.readouterr().out)["data"]["path"])
        assert path.parent == tempdir
        assert path.name.startswith(todos.DRAFTS_PREFIX)
        assert path.suffix == todos.DRAFTS_SUFFIX
        assert path.read_bytes() == b""

    @pytest.mark.spec("drafts-cmd-makes-own-file")
    def it_gives_each_run_a_file_of_its_own(self, capsys):
        paths = set()
        for _ in range(5):
            assert todos.main(["drafts"]) == todos.OK
            paths.add(capsys.readouterr().out.strip())
        assert len(paths) == 5
        assert all(Path(p).is_absolute() and Path(p).is_file() for p in paths)

    @pytest.mark.spec("drafts-cmd-makes-own-file")
    def it_stops_when_the_temporary_directory_cannot_take_a_file(
        self, capsys, monkeypatch, tempdir
    ):
        monkeypatch.setattr(todos.tempfile, "tempdir", str(tempdir / "missing"))
        code = todos.main(["drafts"])
        assert code == todos.CANNOT_RUN
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Set TMPDIR to a directory you can write" in captured.err

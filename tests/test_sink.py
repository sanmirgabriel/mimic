"""Direct sink contracts: incremental writes, UTF-8 and resource lifetime."""

import io
from pathlib import Path

import pytest

from mimic.core.sink import Sink


def test_stdout_iterator_count_and_no_close(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    def words():
        yield "João"
        assert output.getvalue() == "João\n"
        yield "Árvore"

    assert Sink().drain(words()) == 2
    assert output.getvalue() == "João\nÁrvore\n"
    assert not output.closed


def test_utf8_file_count_and_close(tmp_path, monkeypatch):
    path = tmp_path / "out.txt"
    original_open = Path.open
    handles = []

    def tracked_open(self, *args, **kwargs):
        handle = original_open(self, *args, **kwargs)
        handles.append(handle)
        return handle

    monkeypatch.setattr(Path, "open", tracked_open)
    assert Sink(str(path)).drain(iter(["João", "São Paulo"])) == 2
    assert handles[0].closed
    assert path.read_bytes() == "João\nSão Paulo\n".encode("utf-8")


def test_empty_iterator_creates_empty_file(tmp_path):
    path = tmp_path / "empty.txt"
    assert Sink(str(path)).drain(iter(())) == 0
    assert path.read_bytes() == b""


def test_file_is_closed_on_write_error(monkeypatch):
    class Broken(io.StringIO):
        def write(self, value):
            raise OSError("write failed")

    handle = Broken()
    monkeypatch.setattr(Path, "open", lambda *a, **k: handle)
    with pytest.raises(OSError, match="write failed"):
        Sink("unused").drain(iter(["x"]))
    assert handle.closed


def test_stdout_write_error_propagates_without_closing(monkeypatch):
    class Broken(io.StringIO):
        def write(self, value):
            raise OSError("stdout failed")

    handle = Broken()
    monkeypatch.setattr("sys.stdout", handle)
    with pytest.raises(OSError, match="stdout failed"):
        Sink().drain(iter(["x"]))
    assert not handle.closed

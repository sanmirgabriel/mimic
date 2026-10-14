"""Read-only catalog of validated aggregates; no observation uploads."""

from contextlib import contextmanager
from itertools import islice
import os
from pathlib import Path
import re
import stat

from mimic.application.observations import ObservationError, load_report


def artifact_directory(data_dir: Path) -> Path:
    directory = data_dir / "patterns"
    failed = False
    try:
        failed = directory.is_symlink() or (directory.exists() and not directory.is_dir())
    except OSError:
        failed = True
    if failed:
        raise ObservationError("artifact_directory")
    return directory


def artifact_path(data_dir: Path, artifact_id: str) -> Path:
    _artifact_id(artifact_id)
    return artifact_directory(data_dir) / (artifact_id + ".json")


def _artifact_id(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ObservationError("invalid_report")


@contextmanager
def _directory_handle(data_dir: Path):
    """Pin root and child; filename resolution never follows a swapped parent."""
    if not (hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW") and os.supports_dir_fd):
        raise ObservationError("artifact_directory")  # Unsupported platforms fail closed.
    root_fd = directory_fd = None
    failed = missing = False
    try:
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            root_fd = os.open(data_dir, flags)
            directory_fd = os.open("patterns", flags, dir_fd=root_fd)
        except FileNotFoundError:
            missing = True
        except (OSError, NotImplementedError):
            failed = True
        if failed:
            raise ObservationError("artifact_directory")
        yield None if missing else directory_fd
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        if root_fd is not None:
            os.close(root_fd)


def _read_entry(directory_fd: int, artifact_id: str):
    descriptor = None
    failed = False
    try:
        descriptor = os.open(artifact_id + ".json", os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                             dir_fd=directory_fd)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ObservationError("not_regular_file")
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        with stream:
            return load_report(stream)
    except (OSError, NotImplementedError):
        failed = True
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if failed:
        raise ObservationError("read_failed")


def load_artifact(data_dir: Path, artifact_id: str):
    _artifact_id(artifact_id)
    with _directory_handle(data_dir) as directory_fd:
        if directory_fd is None:
            raise ObservationError("artifact_directory")
        return _read_entry(directory_fd, artifact_id)


def list_artifacts(data_dir: Path) -> tuple[str, ...]:
    with _directory_handle(data_dir) as directory_fd:
        if directory_fd is None:
            return ()
        failed = False
        try:
            with os.scandir(directory_fd) as iterator:
                entries = [entry.name for entry in islice(iterator, 65)]
        except (OSError, NotImplementedError):
            failed = True
        if failed or len(entries) > 64:
            raise ObservationError("artifact_directory")
        valid = []
        for entry in sorted(entries):
            if not entry.endswith(".json"):
                continue
            artifact_id = entry[:-5]
            try:
                _artifact_id(artifact_id)
                _read_entry(directory_fd, artifact_id)
            except ObservationError:
                continue
            valid.append(artifact_id)
        return tuple(valid)

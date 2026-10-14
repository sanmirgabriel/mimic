"""Private aggregate-only registry; descriptor confinement and atomic publication."""
from contextlib import contextmanager
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from mimic.frequencies.models import (FrequencyDataset, FrequencyError, MAX_BYTES,
                                      dataset_bytes, identity_parts)

MAX_REGISTRY_BYTES = MAX_BYTES + 1024
MAX_ENTRIES = 128


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _read_json(stream, limit):
    raw = bytearray()
    failed = False
    try:
        while len(raw) <= limit:
            size = limit + 1 - len(raw)
            piece = stream.read(size)
            if type(piece) is not bytes or len(piece) > size:
                raise ValueError()
            if not piece:
                break
            raw.extend(piece)
        if len(raw) > limit:
            raise ValueError()
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except Exception:
        failed = True
    del raw
    if failed:
        raise FrequencyError('read')
    return data


@contextmanager
def _regular(path, parent=None):
    fd = None
    failed = False
    try:
        try:
            if not (hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_NONBLOCK')):
                raise OSError()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError()
            stream = os.fdopen(fd, 'rb', closefd=False)
        except (OSError, ValueError, TypeError, NotImplementedError):
            failed = True
        if failed:
            raise FrequencyError('read')
        with stream:
            yield stream
    finally:
        if fd is not None:
            os.close(fd)


def load_dataset(stream):
    return FrequencyDataset.from_dict(_read_json(stream, MAX_BYTES))


def load_dataset_file(path):
    with _regular(path) as stream:
        return load_dataset(stream)


class FrequencyRegistry:
    def __init__(self, data_dir=None):
        from mimic.persistence import DataPaths
        failed = False
        try:
            self.paths = data_dir if isinstance(data_dir, DataPaths) else DataPaths(data_dir)
        except (OSError, ValueError, TypeError, RuntimeError):
            failed = True
        if failed:
            raise FrequencyError('registry')
        self.root = self.paths.root / 'frequencies'

    @contextmanager
    def _root(self, create=False):
        root_fd = child_fd = None
        missing = failed = False
        try:
            try:
                if not (hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY') and os.supports_dir_fd):
                    raise OSError()
                if create:
                    self.paths.root.mkdir(parents=True, exist_ok=True)
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                root_fd = os.open(self.paths.root, flags)
                if create:
                    try:
                        os.mkdir('frequencies', mode=0o700, dir_fd=root_fd)
                    except FileExistsError:
                        pass
                child_fd = os.open('frequencies', flags, dir_fd=root_fd)
            except FileNotFoundError:
                missing = True
            except (OSError, NotImplementedError):
                failed = True
            if failed or (create and missing):
                raise FrequencyError('registry')
            yield None if missing else child_fd
        finally:
            if child_fd is not None:
                os.close(child_fd)
            if root_fd is not None:
                os.close(root_fd)

    def _get(self, root, identity, expected_digest=None):
        failed = False
        try:
            with _regular(identity + '.json', root) as stream:
                envelope = _read_json(stream, MAX_REGISTRY_BYTES)
            if type(envelope) is not dict or set(envelope) != {'registry_version', 'sha256', 'dataset'} or envelope['registry_version'] != 'frequency-registry-v1':
                raise ValueError()
            dataset = FrequencyDataset.from_dict(envelope['dataset'])
            if dataset.identity != identity or dataset.sha256 != envelope['sha256'] or (expected_digest is not None and dataset.sha256 != expected_digest):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            failed = True
        if failed:
            raise FrequencyError('integrity')
        return dataset

    def get(self, identity, *, expected_digest=None):
        identity_parts(identity)
        with self._root() as root:
            if root is None:
                raise FrequencyError('integrity')
            return self._get(root, identity, expected_digest)

    verify = get

    def _entries(self, root):
        failed = False
        try:
            with os.scandir(root) as iterator:
                entries = [e.name for e in islice(iterator, MAX_ENTRIES + 1)]
        except (OSError, NotImplementedError, TypeError):
            failed = True
        if failed or len(entries) > MAX_ENTRIES:
            raise FrequencyError('registry')
        return sorted(entries)

    def list(self, query=''):
        if type(query) is not str or len(query) > 200:
            raise FrequencyError('schema')
        with self._root() as root:
            if root is None:
                return ()
            result = []
            for entry in self._entries(root):
                if entry.startswith('.import-'):
                    continue
                if not entry.endswith('.json'):
                    raise FrequencyError('integrity')
                identity = entry[:-5]
                identity_parts(identity)
                dataset = self._get(root, identity)
                if not query or query.casefold() in json.dumps(dataset.to_dict(), ensure_ascii=False).casefold():
                    result.append(dataset)
            return tuple(result)

    def import_file(self, path):
        # Entire source validates before creating a directory or stage.
        return self.import_dataset(load_dataset_file(path))

    def import_dataset(self, dataset):
        dataset = FrequencyDataset.from_dict(dataset.to_dict())
        payload = dataset_bytes(dataset)
        envelope = (b'{"registry_version":"frequency-registry-v1","sha256":"' +
                    hashlib.sha256(payload).hexdigest().encode('ascii') + b'","dataset":' + payload.rstrip() + b'}\n')
        stage = '.import-' + uuid4().hex
        filename = dataset.identity + '.json'
        failed = False
        with self._root(create=True) as root:
            entries = self._entries(root)
            if filename in entries:
                existing = self._get(root, dataset.identity)
                if existing != dataset:
                    raise FrequencyError('conflict')
                return existing
            if len(entries) >= MAX_ENTRIES - 1:
                raise FrequencyError('registry')
            staged = False
            descriptor = None
            try:
                descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
                staged = True
                target = os.fdopen(descriptor, 'wb')
                descriptor = None  # The stream now owns the descriptor.
                with target:
                    if target.write(envelope) != len(envelope):
                        raise OSError()
                    target.flush()
                    os.fsync(target.fileno())
                exists = False
                try:
                    os.link(stage, filename, src_dir_fd=root, dst_dir_fd=root, follow_symlinks=False)
                except FileExistsError:
                    exists = True
                if exists:
                    # Validate after the handler: a foreign filesystem exception
                    # must never attach to a public conflict/integrity error.
                    existing = self._get(root, dataset.identity)
                    if existing != dataset:
                        raise FrequencyError('conflict')
                    return existing
            except (OSError, NotImplementedError):
                failed = True
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                if staged:
                    os.unlink(stage, dir_fd=root)
        if failed:
            raise FrequencyError('write')
        return dataset

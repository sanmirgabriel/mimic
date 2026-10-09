"""Chunked local imports, JSON manifests and descriptor-confined execution."""
import codecs
from contextlib import contextmanager, ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from mimic.core.candidate import Candidate, Origin
from mimic.core.seed import Seed
from mimic.packs.models import PackError, PackMetadata, PackReference, identity_parts

CHUNK_BYTES = 64 * 1024
MAX_IMPORT_BYTES = 1024 * 1024 * 1024
TEXT_SUFFIXES = ('.txt', '.lst', '.wordlist', '.dic')


def inspect_stream(stream, *, destination=None, max_bytes=MAX_IMPORT_BYTES, checkpoint=None):
    """Hash original bytes and count universal physical lines in bounded chunks."""
    digest = hashlib.sha256()
    decoder = io.IncrementalNewlineDecoder(codecs.getincrementaldecoder('utf-8')(), True)
    size = lines = 0
    last = ''
    while True:
        if checkpoint:
            checkpoint()
        chunk = stream.read(CHUNK_BYTES)
        final = not chunk
        size += len(chunk)
        if size > max_bytes:
            raise PackError('size_limit', 'Pack file exceeds the import size limit')
        digest.update(chunk)
        try:
            text = decoder.decode(chunk, final=final)
        except UnicodeError as exc:
            raise PackError('utf8', 'Pack file is not valid UTF-8') from exc
        if '\x00' in text:
            raise PackError('file', 'Pack must contain text, not NUL bytes')
        lines += text.count('\n')
        if text:
            last = text[-1]
        if destination and chunk:
            destination.write(chunk)
        if final:
            break
    return digest.hexdigest(), size, lines + bool(last and last != '\n')


def _directory(name, parent=None):
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)


@contextmanager
def _regular(name, parent=None):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PackError('file', 'Pack source must be a regular file')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            yield stream
    finally:
        os.close(descriptor)


class PackRegistry:
    def __init__(self, data_dir=None):
        from mimic.persistence.database import DataPaths
        self.paths = data_dir if isinstance(data_dir, DataPaths) else DataPaths(data_dir)
        self.root = self.paths.packs

    @contextmanager
    def _root(self, create=False):
        if create:
            self.paths.root.mkdir(parents=True, exist_ok=True)
        root = _directory(self.paths.root)
        try:
            if create:
                try:
                    os.mkdir('packs', mode=0o700, dir_fd=root)
                except FileExistsError:
                    pass
            packs = _directory('packs', root)
            try:
                yield packs
            finally:
                os.close(packs)
        finally:
            os.close(root)

    @contextmanager
    def _version(self, identity):
        pack_id, version = identity_parts(identity)
        try:
            with self._root() as root:
                directory = _directory(pack_id, root)
                try:
                    descriptor = _directory(version, directory)
                    try:
                        yield descriptor
                    finally:
                        os.close(descriptor)
                finally:
                    os.close(directory)
        except OSError as exc:
            raise PackError('unavailable', f'Pack unavailable or unsafe: {identity}') from exc

    def _metadata(self, directory):
        try:
            with _regular('manifest.json', directory) as stream:
                raw = stream.read(CHUNK_BYTES + 1)
                if len(raw) > CHUNK_BYTES:
                    raise PackError('manifest', 'Pack manifest is too large')
                def unique(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise PackError('manifest', 'Duplicate pack manifest key')
                        result[key] = value
                    return result
                return PackMetadata.from_dict(json.loads(raw, object_pairs_hook=unique))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PackError('manifest', 'Pack manifest is unavailable or invalid') from exc

    def get(self, identity):
        with self._version(identity) as directory:
            metadata = self._metadata(directory)
            if metadata.identity != identity:
                raise PackError('manifest', 'Pack manifest identity does not match its directory')
            return metadata

    def list(self):
        try:
            with self._root() as root:
                identities = []
                for pack_id in sorted(os.listdir(root)):
                    if pack_id.startswith('.import-'):
                        continue
                    identity_parts(pack_id + '@1')
                    directory = _directory(pack_id, root)
                    try:
                        identities.extend(pack_id + '@' + version for version in sorted(os.listdir(directory)))
                    finally:
                        os.close(directory)
            return [self.get(identity) for identity in identities]
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise PackError('unavailable', 'Pack registry is unavailable or unsafe') from exc

    def reference(self, identity):
        metadata = self.get(identity)
        return PackReference(metadata.id, metadata.version, metadata.sha256, metadata)

    def resolve(self, reference):
        metadata = self.get(reference.identity)
        if metadata.sha256 != reference.sha256:
            raise PackError('digest', f'Pack digest differs from snapshot: {reference.identity}')
        if reference.metadata is not None and metadata != reference.metadata:
            raise PackError('snapshot', f'Pack metadata differs from snapshot: {reference.identity}')
        return PackReference(metadata.id, metadata.version, metadata.sha256, metadata)

    def import_file(self, path, *, max_bytes=MAX_IMPORT_BYTES, **fields):
        path = Path(path).expanduser()
        if path.suffix.lower() not in TEXT_SUFFIXES:
            raise PackError('file', 'Pack source must be a text file (.txt, .lst, .wordlist or .dic)')
        with _regular(path) as stream:
            return self.import_stream(stream, filename=path.name, max_bytes=max_bytes, **fields)

    def import_stream(self, stream, *, id, version, kind, filename, name=None,
                      language='und', license='NOASSERTION', source_url=None,
                      attribution=None, description='', max_bytes=MAX_IMPORT_BYTES):
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_IMPORT_BYTES:
            raise PackError('size_limit', 'Import limit must be between 1 byte and 1 GiB')
        pack_id = id.strip().lower() if isinstance(id, str) else id
        # Validate everything before creating staging files.
        template = PackMetadata(pack_id, version, name or pack_id, kind, language, license,
            '0' * 64, 0, 0, filename, attribution or 'Local operator import', source_url, description)
        if Path(filename).suffix.lower() not in TEXT_SUFFIXES:
            raise PackError('file', 'Pack source must be a supported text file')
        stage = '.import-' + uuid4().hex
        with self._root(create=True) as root:
            os.mkdir(stage, mode=0o700, dir_fd=root)
            try:
                directory = _directory(stage, root)
            except BaseException:
                os.rmdir(stage, dir_fd=root)
                raise
            published = False
            try:
                descriptor = os.open('corpus.txt', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=directory)
                with os.fdopen(descriptor, 'wb') as target:
                    digest, size, lines = inspect_stream(stream, destination=target, max_bytes=max_bytes)
                    target.flush()
                    os.fsync(target.fileno())
                from dataclasses import replace
                metadata = replace(template, sha256=digest, size_bytes=size, physical_line_count=lines)
                descriptor = os.open('manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=directory)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as target:
                    json.dump(metadata.to_dict(), target, ensure_ascii=False, indent=2)
                    target.write('\n')
                    target.flush()
                    os.fsync(target.fileno())
                os.fsync(directory)
                try:
                    os.mkdir(pack_id, mode=0o700, dir_fd=root)
                except FileExistsError:
                    pass
                parent = _directory(pack_id, root)
                try:
                    # A populated version directory can never be replaced by rename.
                    try:
                        os.stat(version, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        try:
                            os.rename(stage, version, src_dir_fd=root, dst_dir_fd=parent)
                            published = True
                            os.fsync(parent)
                            return metadata
                        except OSError as exc:
                            if exc.errno not in (17, 39):
                                raise
                    existing = self.get(metadata.identity)
                    if existing.sha256 != digest:
                        raise PackError('conflict', f'Pack identity already contains different bytes: {metadata.identity}')
                    if existing.kind != kind:
                        raise PackError('conflict', 'Pack kind cannot change for an existing identity')
                    if existing != metadata:
                        raise PackError('conflict', 'Pack metadata cannot change for an existing identity')
                    self.verify(self.reference(metadata.identity))
                    return existing
                finally:
                    os.close(parent)
            finally:
                try:
                    if not published:
                        for filename in ('corpus.txt', 'manifest.json'):
                            try:
                                os.unlink(filename, dir_fd=directory)
                            except FileNotFoundError:
                                pass
                        os.rmdir(stage, dir_fd=root)
                finally:
                    os.close(directory)

    @contextmanager
    def open_verified(self, references, *, max_lines=None, checkpoint=None):
        """Hold verified descriptors until generation finishes, including cancellation."""
        with ExitStack() as stack:
            streams = {}
            for reference in references:
                resolved = self.resolve(reference)
                directory = stack.enter_context(self._version(resolved.identity))
                try:
                    stream = stack.enter_context(_regular('corpus.txt', directory))
                except OSError as exc:
                    raise PackError('unavailable', f'Pack content is unavailable: {resolved.identity}') from exc
                metadata = resolved.metadata
                digest, size, lines = inspect_stream(stream, checkpoint=checkpoint)
                if digest != reference.sha256:
                    raise PackError('digest', f'Pack SHA-256 mismatch: {resolved.identity}')
                if size != metadata.size_bytes or lines != metadata.line_count:
                    raise PackError('size', f'Pack size/line count mismatch: {resolved.identity}')
                if max_lines is not None and lines > max_lines:
                    raise PackError('line_limit', f'Pack exceeds {max_lines} physical lines: {resolved.identity}')
                stream.seek(0)
                streams[reference.identity] = (metadata, stream, checkpoint)
            yield streams

    def verify(self, reference):
        if isinstance(reference, str):
            reference = self.reference(reference)
        with self.open_verified((reference,)):
            return self.resolve(reference).metadata

    @staticmethod
    def seeds(metadata, stream, checkpoint=None):
        """Existing dataset normalization with stable pack/physical-line provenance."""
        digest = hashlib.sha256()
        text = io.TextIOWrapper(stream, encoding='utf-8', newline='')
        size = lines = 0
        try:
            for index, line in enumerate(text, 1):
                if checkpoint:
                    checkpoint()
                raw = line.encode('utf-8')
                size += len(raw)
                lines = index
                if size > metadata.size_bytes or lines > metadata.line_count:
                    raise PackError('size', f'Pack grew during execution: {metadata.identity}')
                digest.update(raw)
                value = line.strip()
                if value and not value.startswith('#'):
                    yield Seed(Candidate(value, (Origin('ready_candidate' if metadata.kind == 'ready' else 'dataset',
                        f'pack:{metadata.identity}:{index}', value),)),
                        mutable=metadata.kind == 'seed', combinable=False)
            if digest.hexdigest() != metadata.sha256:
                raise PackError('digest', f'Pack changed during execution: {metadata.identity}')
            if size != metadata.size_bytes or lines != metadata.line_count:
                raise PackError('size', f'Pack size/line count changed during execution: {metadata.identity}')
        except UnicodeError as exc:
            raise PackError('utf8', f'Pack UTF-8 changed during execution: {metadata.identity}') from exc
        finally:
            if not text.closed:
                text.detach()

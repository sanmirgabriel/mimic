"""Immutable local pack metadata and digest-pinned request references."""
from dataclasses import asdict, dataclass, fields
import re
from urllib.parse import urlsplit


class PackError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def identity_parts(identity):
    if not isinstance(identity, str) or identity.count('@') != 1:
        raise PackError('identity', 'Pack identity must be id@version')
    pack_id, version = identity.split('@')
    validate_identity(pack_id, version)
    return pack_id, version


def validate_identity(pack_id, version):
    if not isinstance(pack_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', pack_id):
        raise PackError('identity', 'Pack id must be lowercase ASCII letters, digits, hyphens or underscores')
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', version):
        raise PackError('identity', 'Invalid pack version')


@dataclass(frozen=True)
class PackMetadata:
    id: str
    version: str
    name: str
    kind: str
    language: str
    license: str
    sha256: str
    size_bytes: int
    physical_line_count: int
    filename: str
    attribution: str
    source_url: str | None = None
    description: str = ''
    schema_version: int = 1

    def __post_init__(self):
        validate_identity(self.id, self.version)
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise PackError('manifest', 'Unsupported pack manifest schema')
        for field in ('name', 'language', 'license', 'filename', 'attribution', 'description'):
            value = getattr(self, field)
            if (not isinstance(value, str) or len(value) > 2048 or
                    any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value) or
                    (field != 'description' and not value.strip())):
                raise PackError('metadata', f'Invalid pack {field}')
        if self.kind not in ('seed', 'ready'):
            raise PackError('kind', 'Pack kind must be seed or ready')
        if (len(self.filename) > 255 or self.filename in ('.', '..') or
                '/' in self.filename or '\\' in self.filename):
            raise PackError('metadata', 'Pack filename must be a plain filename')
        if not isinstance(self.sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', self.sha256):
            raise PackError('digest', 'Pack SHA-256 must contain 64 lowercase hex characters')
        if any(type(v) is not int or v < 0 for v in (self.size_bytes, self.line_count)):
            raise PackError('metadata', 'Invalid pack size or physical line count')
        if self.source_url is not None:
            if not isinstance(self.source_url, str) or len(self.source_url) > 2048:
                raise PackError('metadata', 'Invalid source URL')
            try:
                url = urlsplit(self.source_url)
                valid = url.scheme in ('https', 'http') and url.hostname and not url.username and not url.password
            except ValueError:
                valid = False
            if not valid or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or
                                0xD800 <= ord(c) <= 0xDFFF for c in self.source_url):
                raise PackError('metadata', 'Source URL must be an HTTP(S) attribution URL')

    @property
    def line_count(self):
        return self.physical_line_count

    @property
    def identity(self):
        return f'{self.id}@{self.version}'

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) != {field.name for field in fields(cls)}:
            raise PackError('manifest', 'Invalid pack manifest fields')
        try:
            return cls(**data)
        except (TypeError, KeyError) as exc:
            raise PackError('manifest', 'Invalid pack manifest fields') from exc


@dataclass(frozen=True)
class PackReference:
    id: str
    version: str
    sha256: str
    metadata: PackMetadata | None = None

    def __post_init__(self):
        validate_identity(self.id, self.version)
        if not isinstance(self.sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', self.sha256):
            raise PackError('digest', 'Pack reference needs a full SHA-256 digest')
        if self.metadata is not None and (not isinstance(self.metadata, PackMetadata) or
                (self.metadata.id, self.metadata.version, self.metadata.sha256) != (self.id, self.version, self.sha256)):
            raise PackError('snapshot', 'Pack metadata does not match its reference')

    @property
    def identity(self):
        return f'{self.id}@{self.version}'

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) - {'id', 'version', 'sha256', 'metadata'}:
            raise PackError('snapshot', 'Invalid pack reference fields')
        try:
            metadata = PackMetadata.from_dict(data['metadata']) if data.get('metadata') is not None else None
            return cls(data['id'], data['version'], data['sha256'], metadata)
        except (KeyError, TypeError) as exc:
            raise PackError('snapshot', 'Invalid pack reference') from exc

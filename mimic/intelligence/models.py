"""Small serializable knowledge configuration; no transport or domain objects."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class IntelligenceOptions:
    enabled: bool = True
    common_numbers: bool = True
    recent_years: bool = True
    corporate_roles: bool = True
    service_profiles: tuple[str, ...] = ()
    reference_year: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.service_profiles, (list, tuple)) or any(
            not isinstance(value, str) for value in self.service_profiles
        ):
            raise TypeError("service_profiles must be a sequence of service IDs")
        object.__setattr__(self, "service_profiles", tuple(dict.fromkeys(self.service_profiles)))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["service_profiles"] = list(self.service_profiles)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "IntelligenceOptions":
        return cls(**data)


@dataclass(frozen=True)
class ServiceProfile:
    id: str
    display_name: str
    tokens: tuple[str, ...]
    roles: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        for field in ("tokens", "roles"):
            values = getattr(self, field)
            if not isinstance(values, (tuple, list)) or any(not isinstance(value, str) for value in values):
                raise TypeError(f"ServiceProfile.{field} must be a sequence of strings")
            object.__setattr__(self, field, tuple(values))


def _text(value: str, field: str) -> None:
    if (not isinstance(value, str) or not value.strip() or len(value) > 4096 or
            any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF
                or c in '\u2028\u2029' for c in value)):
        raise ValueError(f"{field} must be nonempty text of at most 4096 characters without controls or line breaks")


def _identifier(value: str) -> None:
    import re
    if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError("catalog IDs and versions must be lowercase ASCII identifiers of at most 64 characters")


def _url(value: str) -> None:
    import re
    from ipaddress import IPv6Address
    from urllib.parse import urlsplit
    _text(value, "source_url")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.port == 0 or any(c.isspace() for c in value)):
        raise ValueError("source_url must be an absolute HTTPS documentation URL")
    hostname = parsed.hostname.encode('idna').decode('ascii')
    if ':' in hostname:
        IPv6Address(hostname)
    elif not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.?', hostname):
        raise ValueError("source_url must contain a valid documentation hostname")


def _vocabulary(values, field: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise TypeError(f"{field} must be a sequence of strings")
    for value in values:
        _text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {field}")
    return tuple(values)


@dataclass(frozen=True)
class ServiceKnowledge:
    """Read-only technology metadata, independent of generation operands."""

    id: str
    display_name: str
    description: str
    aliases: tuple[str, ...]
    references: tuple[tuple[str, str], ...]
    authentication_notes: str
    catalog_version: str

    def __post_init__(self) -> None:
        _identifier(self.id)
        for name in ("display_name", "description", "authentication_notes", "catalog_version"):
            _text(getattr(self, name), name)
        _identifier(self.catalog_version)
        object.__setattr__(self, "aliases", _vocabulary(self.aliases, "aliases"))
        if not isinstance(self.references, (tuple, list)) or not self.references:
            raise ValueError("service knowledge needs documentation references")
        references = []
        for reference in self.references:
            if not isinstance(reference, (tuple, list)) or len(reference) != 2:
                raise ValueError("references must contain title/URL pairs")
            title, url = reference
            _text(title, "reference title")
            _url(url)
            references.append((title, url))
        object.__setattr__(self, "references", tuple(references))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DefaultCredential:
    """An associated pair with documented applicability; never a Candidate."""

    id: str
    service_id: str
    username: str
    password: str
    source_title: str
    source_url: str
    applicability: str
    restrictions: tuple[str, ...]
    catalog_version: str
    record_version: str = "1"
    version_scope: str | None = None
    type: str = "documented_default"

    def __post_init__(self) -> None:
        _identifier(self.id)
        _identifier(self.service_id)
        for name in ("username", "password", "source_title", "applicability", "catalog_version", "record_version"):
            _text(getattr(self, name), name)
        _identifier(self.catalog_version)
        if not self.record_version.isascii() or not self.record_version.isdecimal() or int(self.record_version) < 1:
            raise ValueError("record_version must be a positive integer string")
        _url(self.source_url)
        if self.type != "documented_default":
            raise ValueError("default credentials require documented_default classification")
        if self.version_scope is not None:
            _text(self.version_scope, "version_scope")
        object.__setattr__(self, "restrictions", _vocabulary(self.restrictions, "restrictions"))
        if not self.restrictions:
            raise ValueError("documented defaults require applicability restrictions")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CommonCredentialVocabulary:
    """Independent value lists, with no implied username/password association."""

    id: str
    version: str
    description: str
    usernames: tuple[str, ...]
    passwords: tuple[str, ...]
    type: str = "common_value"

    def __post_init__(self) -> None:
        _identifier(self.id)
        _identifier(self.version)
        _text(self.description, "description")
        if self.type != "common_value":
            raise ValueError("common vocabulary must be classified as common_value")
        for name in ("usernames", "passwords"):
            object.__setattr__(self, name, _vocabulary(getattr(self, name), name))
            if not getattr(self, name):
                raise ValueError(f"common vocabulary requires nonempty {name}")

    def to_dict(self) -> dict:
        return asdict(self)

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

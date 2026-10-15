"""Resolve opt-in source defaults; never generate or infer organization facts."""
from copy import deepcopy

CORPORATE_BR_VERSION = "corporate-br-v1"


def resolve_preset(data: dict) -> dict:
    """Explicit fields win, including False; resolved snapshots are idempotent.

    Missing fields receive defaults, never mutations, services, policy or caps.
    This boundary is shared by API, CLI and Web before constructing a request.
    """
    preset = data.get("preset")
    if preset is None:
        return data
    if preset not in ("corporate-br", CORPORATE_BR_VERSION):
        raise ValueError("unknown generation preset")
    result = deepcopy(data)
    result["preset"] = CORPORATE_BR_VERSION
    for section, defaults in (
        ("sources", {"include_ptbr": True, "include_common_passwords": True}),
        ("intelligence", {"enabled": True, "common_numbers": True,
                          "recent_years": True, "corporate_roles": True}),
    ):
        supplied = result.get(section, {})
        if not isinstance(supplied, dict):
            raise ValueError(f"{section} must be a mapping")
        result[section] = {**defaults, **supplied}
    result.setdefault("organization_variants", True)
    return result

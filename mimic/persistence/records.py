"""Record operations shared by HTTP JSON and HTML adapters, without HTTP types."""
from __future__ import annotations

from mimic.persistence.repository import Repository


class RecordService:
    _singular = {"engagements": "engagement", "organizations": "organization", "targets": "target"}
    _lists = ("aliases", "locations", "keywords", "relevant_dates", "domains")

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def _operation(self, collection: str, action: str):
        singular = self._singular[collection]
        return getattr(self.repository, f"{action}_{collection if action == 'list' else singular}")

    def list(self, collection: str) -> list[dict]:
        return self._operation(collection, "list")()

    def get(self, collection: str, item_id: str) -> dict:
        result = self._operation(collection, "get")(item_id)
        if result is None:
            raise LookupError("resource not found")
        return result

    def _validated(self, collection: str, data: dict, *, create: bool) -> dict:
        values = dict(data)
        if create or "name" in values:
            name = values.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name must be a non-empty string")
            values["name"] = name.strip()
        if collection == "organizations":
            for field in self._lists:
                if field in values and values[field] is None:
                    raise ValueError(f"{field} must be a list")
        if collection == "targets" and "profile" in values and values["profile"] is None:
            raise ValueError("profile must be an object")
        return values

    def create(self, collection: str, data: dict) -> dict:
        values = self._validated(collection, data, create=True)
        if collection == "engagements":
            return self.repository.create_engagement(values["name"], values.get("description"))
        return self._operation(collection, "create")(values)

    def update(self, collection: str, item_id: str, changes: dict) -> dict:
        values = self._validated(collection, changes, create=False)
        result = self._operation(collection, "update")(item_id, values)
        if result is None:
            raise LookupError("resource not found")
        return result

    def delete(self, collection: str, item_id: str) -> dict:
        if not self._operation(collection, "delete")(item_id):
            raise LookupError("resource not found")
        return {"deleted": True}

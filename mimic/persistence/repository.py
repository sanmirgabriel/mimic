"""Small explicit SQLite repository for local domain objects and jobs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from mimic.domain.models import Organization, Target
from mimic.persistence.database import Database
from mimic.profile.schema import TargetProfile


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StorageConflict(Exception):
    """A referenced row cannot be removed or a foreign key is invalid."""


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _decode(table: str, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        if table == "organizations":
            for field in ("aliases", "locations", "keywords", "relevant_dates", "domains"):
                item[field] = json.loads(item.pop(f"{field}_json"))
        elif table == "targets":
            item["profile"] = json.loads(item.pop("profile_json"))
        elif table == "jobs":
            item["request"] = json.loads(item.pop("request_json"))
            item["cancel_requested"] = bool(item["cancel_requested"])
        elif table == "candidate_preview":
            item["origins"] = json.loads(item.pop("origins_json"))
            item["transformations"] = json.loads(item.pop("transformations_json"))
            item["score_components"] = json.loads(item["score_components"]) if item["score_components"] is not None else None
        return item

    def _get(self, table: str, item_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
        return self._decode(table, row)

    def _list(self, table: str) -> list[dict]:
        order = "created_at DESC, id" if table == "jobs" else "rowid, id"
        with self.database.connection() as connection:
            rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
        return [self._decode(table, row) for row in rows]

    def _insert(self, table: str, values: dict) -> dict:
        item_id = str(uuid4())
        record = {"id": item_id, **values}
        columns = ", ".join(record)
        placeholders = ", ".join("?" for _ in record)
        try:
            with self.database.connection() as connection:
                connection.execute(
                    f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(record.values())
                )
        except sqlite3.IntegrityError as exc:
            raise StorageConflict("invalid reference or duplicate resource") from exc
        return self._get(table, item_id)

    def _update(self, table: str, item_id: str, changes: dict) -> dict | None:
        if not changes:
            return self._get(table, item_id)
        assignments = ", ".join(f"{column} = ?" for column in changes)
        try:
            with self.database.connection() as connection:
                cursor = connection.execute(
                    f"UPDATE {table} SET {assignments} WHERE id = ?",
                    (*changes.values(), item_id),
                )
                found = cursor.rowcount > 0
        except sqlite3.IntegrityError as exc:
            raise StorageConflict("invalid reference or dependent resource") from exc
        return self._get(table, item_id) if found else None

    def _delete(self, table: str, item_id: str) -> bool:
        try:
            with self.database.connection() as connection:
                cursor = connection.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
                return cursor.rowcount > 0
        except sqlite3.IntegrityError as exc:
            raise StorageConflict("resource has dependent records") from exc

    def create_engagement(self, name: str, description: str | None = None) -> dict:
        return self._insert("engagements", {"name": name, "description": description})

    def list_engagements(self) -> list[dict]:
        return self._list("engagements")

    def get_engagement(self, item_id: str) -> dict | None:
        return self._get("engagements", item_id)

    def update_engagement(self, item_id: str, changes: dict) -> dict | None:
        allowed = {key: changes[key] for key in ("name", "description") if key in changes}
        return self._update("engagements", item_id, allowed)

    def delete_engagement(self, item_id: str) -> bool:
        return self._delete("engagements", item_id)

    def create_organization(self, data: dict) -> dict:
        values = {"name": data["name"], "engagement_id": data.get("engagement_id")}
        for field in ("aliases", "locations", "keywords", "relevant_dates", "domains"):
            values[f"{field}_json"] = json.dumps(data.get(field, []), ensure_ascii=False)
        return self._insert("organizations", values)

    def list_organizations(self) -> list[dict]:
        return self._list("organizations")

    def get_organization(self, item_id: str) -> dict | None:
        return self._get("organizations", item_id)

    def update_organization(self, item_id: str, changes: dict) -> dict | None:
        values = {key: changes[key] for key in ("name", "engagement_id") if key in changes}
        for field in ("aliases", "locations", "keywords", "relevant_dates", "domains"):
            if field in changes:
                values[f"{field}_json"] = json.dumps(changes[field], ensure_ascii=False)
        return self._update("organizations", item_id, values)

    def delete_organization(self, item_id: str) -> bool:
        return self._delete("organizations", item_id)

    def create_target(self, data: dict) -> dict:
        profile = TargetProfile.from_dict(data.get("profile", {}))
        return self._insert("targets", {
            "name": data["name"], "profile_json": json.dumps(asdict(profile), ensure_ascii=False),
            "organization_id": data.get("organization_id"),
            "engagement_id": data.get("engagement_id"),
        })

    def list_targets(self) -> list[dict]:
        return self._list("targets")

    def get_target(self, item_id: str) -> dict | None:
        return self._get("targets", item_id)

    def update_target(self, item_id: str, changes: dict) -> dict | None:
        values = {key: changes[key] for key in ("name", "organization_id", "engagement_id")
                  if key in changes}
        if "profile" in changes:
            profile = TargetProfile.from_dict(changes["profile"])
            values["profile_json"] = json.dumps(asdict(profile), ensure_ascii=False)
        return self._update("targets", item_id, values)

    def delete_target(self, item_id: str) -> bool:
        return self._delete("targets", item_id)

    def target_domain(self, item_id: str) -> Target | None:
        record = self.get_target(item_id)
        if record is None:
            return None
        organization = None
        if record["organization_id"]:
            org = self.get_organization(record["organization_id"])
            if org:
                organization = Organization(
                    name=org["name"], aliases=org["aliases"], locations=org["locations"],
                    keywords=org["keywords"], relevant_dates=org["relevant_dates"],
                    domains=org["domains"], id=org["id"],
                )
        return Target(record["name"], TargetProfile.from_dict(record["profile"]),
                      organization, record["id"])

    def create_job(self, request: dict, target_id: str | None, engagement_id: str | None) -> dict:
        return self._insert("jobs", {
            "status": "pending", "request_json": json.dumps(request, ensure_ascii=False),
            "target_id": target_id, "engagement_id": engagement_id,
            "created_at": utc_now(), "started_at": None, "finished_at": None,
            "candidate_count": 0, "evaluated_count": 0, "error": None, "cancel_requested": 0, "output_path": None,
        })

    def list_jobs(self) -> list[dict]:
        return self._list("jobs")

    def get_job(self, item_id: str) -> dict | None:
        return self._get("jobs", item_id)

    def start_job(self, item_id: str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = 'running', started_at = ? "
                "WHERE id = ? AND status = 'pending' AND cancel_requested = 0",
                (utc_now(), item_id),
            )
            return cursor.rowcount > 0

    def set_evaluated_count(self, item_id: str, count: int) -> None:
        with self.database.connection() as connection:
            connection.execute("UPDATE jobs SET evaluated_count = ? WHERE id = ? AND status = 'running'",
                               (count, item_id))

    def set_count(self, item_id: str, count: int) -> None:
        with self.database.connection() as connection:
            connection.execute("UPDATE jobs SET candidate_count = ? WHERE id = ? AND status = 'running'",
                               (count, item_id))

    def finish_job(self, item_id: str, status: str, count: int,
                   error: str | None = None) -> bool:
        """Finish a running job; terminal states are immutable."""
        if status not in ("failed", "cancelled"):
            raise ValueError("finish_job accepts only failed or cancelled")
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = ?, candidate_count = ?, error = ?, output_path = NULL, "
                "finished_at = ? WHERE id = ? AND status = 'running'",
                (status, count, error, utc_now(), item_id),
            )
            return cursor.rowcount > 0

    def complete_job(self, item_id: str, count: int, output_path: str) -> bool:
        """Commit completion only if no concurrent cancellation was requested."""
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = 'completed', candidate_count = ?, output_path = ?, "
                "finished_at = ? WHERE id = ? AND status = 'running' AND cancel_requested = 0",
                (count, output_path, utc_now(), item_id),
            )
            return cursor.rowcount > 0

    def request_cancel(self, item_id: str) -> dict | None:
        with self.database.connection() as connection:
            pending = connection.execute(
                "UPDATE jobs SET status = 'cancelled', cancel_requested = 1, finished_at = ? "
                "WHERE id = ? AND status = 'pending'", (utc_now(), item_id),
            )
            if pending.rowcount == 0:
                connection.execute(
                    "UPDATE jobs SET cancel_requested = 1 "
                    "WHERE id = ? AND status = 'running' AND cancel_requested = 0", (item_id,),
                )
        return self.get_job(item_id)

    def recover_incomplete(self) -> int:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = 'failed', error = 'interrupted by process restart', "
                "finished_at = ?, output_path = NULL WHERE status IN ('pending', 'running')",
                (utc_now(),),
            )
            return cursor.rowcount

    def add_preview(self, item_id: str, candidates: list[dict]) -> None:
        if not candidates:
            return
        with self.database.connection() as connection:
            connection.executemany(
                "INSERT INTO candidate_preview "
                "(job_id, sequence, value, origins_json, transformations_json, rank, score, score_version, score_components) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(item_id, c["sequence"], c["value"],
                  json.dumps(c["origins"], ensure_ascii=False),
                  json.dumps(c["transformations"], ensure_ascii=False), c.get("rank"), c.get("score"),
                  c.get("score_version"), json.dumps(c["score_components"], ensure_ascii=False)
                  if c.get("score_components") is not None else None) for c in candidates],
            )

    def list_preview(self, item_id: str, limit: int = 200, offset: int = 0) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM candidate_preview WHERE job_id = ? "
                "ORDER BY sequence LIMIT ? OFFSET ?", (item_id, limit, offset),
            ).fetchall()
        return [self._decode("candidate_preview", row) for row in rows]

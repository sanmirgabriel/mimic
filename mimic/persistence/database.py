"""Local data paths and one SQLite connection per operation."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import UUID


class DataPaths:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        if data_dir is None:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            data_dir = base / "mimic"
        self.root = Path(data_dir).expanduser().resolve()
        self.database = self.root / "mimic.db"
        self.jobs = self.root / "jobs"
        self.packs = self.root / "packs"

    def job_dir(self, job_id: str) -> Path:
        parsed = UUID(job_id)
        if str(parsed) != job_id:
            raise ValueError("invalid job id")
        return self.jobs / job_id

    def output(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "wordlist.txt"


class Database:
    def __init__(self, paths: DataPaths, path: str | Path | None = None) -> None:
        self.paths = paths
        self.path = Path(path).expanduser().resolve() if path is not None else paths.database

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.jobs.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise RuntimeError(f"unsupported database schema version: {version}")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS engagements (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT
                );
                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY, engagement_id TEXT REFERENCES engagements(id) ON DELETE RESTRICT,
                    name TEXT NOT NULL, aliases_json TEXT NOT NULL, locations_json TEXT NOT NULL,
                    keywords_json TEXT NOT NULL, relevant_dates_json TEXT NOT NULL, domains_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS targets (
                    id TEXT PRIMARY KEY, engagement_id TEXT REFERENCES engagements(id) ON DELETE RESTRICT,
                    organization_id TEXT REFERENCES organizations(id) ON DELETE RESTRICT,
                    name TEXT NOT NULL, profile_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    target_id TEXT REFERENCES targets(id) ON DELETE RESTRICT,
                    engagement_id TEXT REFERENCES engagements(id) ON DELETE RESTRICT,
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    candidate_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
                    output_path TEXT
                );
                CREATE TABLE IF NOT EXISTS candidate_preview (
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL, value TEXT NOT NULL,
                    origins_json TEXT NOT NULL, transformations_json TEXT NOT NULL,
                    PRIMARY KEY (job_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS jobs_created_idx ON jobs(created_at DESC);
            """)
            connection.execute("BEGIN IMMEDIATE")
            # ALTER preserves v1 rows and explanations. NULL marks historical unknowns.
            for table, columns in {"jobs": {"evaluated_count": "INTEGER"},
                    "candidate_preview": {"rank": "INTEGER", "score": "INTEGER",
                        "score_version": "TEXT", "score_components": "TEXT"}}.items():
                existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                for column, sql_type in columns.items():
                    if column not in existing:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
            connection.execute("PRAGMA user_version = 2")

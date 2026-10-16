"""Observed-output export: materialized Python semantics plus exact Affix groups.

One MIMIC pass; disk-backed pairing; no candidate generation by a second engine.
Only explicit verification invokes Hashcat, always --stdout, never hashes.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import ctypes
from dataclasses import asdict, dataclass
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import selectors
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata

from mimic import __version__
from mimic.application import GenerationRequest, GenerationService
from mimic.core.candidate import Candidate
from mimic.intelligence.organization import VERSION as ORGANIZATION_VERSION

FORMAT = "mimic-hashcat-bundle-v1"
MAX_BYTES = 128  # Conservative stdout profile, not every Hashcat kernel's limit.
MAX_OPERATIONS = 31


class BundleError(ValueError):
    """Fixed diagnostic code: do not echo candidate values or private paths."""


@dataclass(frozen=True)
class BundleLimits:
    max_evaluated: int = 1_000_000
    max_segments: int = 64
    max_rules_per_base: int = 1024

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in asdict(self).values()):
            raise BundleError("invalid export limits")


def _line(value: str) -> bytes:
    try:
        data = value.encode("utf-8")
    except UnicodeError as exc:
        raise BundleError("invalid-unicode") from exc
    if not data or any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in "\u2028\u2029" for c in value):
        raise BundleError("empty-or-control-value")
    if len(data) > MAX_BYTES:
        raise BundleError("value-exceeds-128-utf8-bytes")
    return data


def compile_pair(candidate: Candidate) -> tuple[bytes, str, str]:
    """Translate one recorded final Affix, otherwise explicitly materialize.

    All earlier Python transformations are already in the actual Affix input.
    A metadata claim is used only if it reconstructs this exact emitted value.
    No Case/title/global substitution rule is guessed from the final text.
    """
    literal = _line(candidate.value)
    if candidate.transformations and candidate.transformations[-1].kind == "affix":
        p = dict(candidate.transformations[-1].params)
        base, token, sep = p.get("input", ""), p.get("token", ""), p.get("separator", "")
        left = right = None
        if p.get("placement") == "prefix" and p.get("separator_position") == "none":
            left, right = token, ""
        elif p.get("placement") == "suffix":
            position = p.get("separator_position")
            if position == "none": left, right = "", token
            elif position == "between": left, right = "", sep + token
            elif position == "after": left, right = "", token + sep
            elif position == "before": left, right = sep, token
        if left is not None and left + base + right == candidate.value:
            try:
                raw = _line(base)
                before, after = left.encode("utf-8"), right.encode("utf-8")
            except (BundleError, UnicodeError):
                return literal, ":", "literal-fallback"
            if 0 < len(before) + len(after) <= MAX_OPERATIONS:
                rule = "".join(f"^\\x{b:02x}" for b in reversed(before))
                rule += "".join(f"$\\x{b:02x}" for b in after)
                return raw, rule, "compiled-affix"
            return literal, ":", "literal-fallback"
    return literal, ":", "materialized-identity"


def _write(path: Path, lines) -> dict:
    digest = hashlib.sha256(); count = size = 0
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        for line in lines:
            stream.write(line); digest.update(line); count += 1; size += len(line)
        stream.flush(); os.fsync(stream.fileno())
    return {"file": path.name, "sha256": digest.hexdigest(), "bytes": size, "lines": count}


def _parent(path: Path) -> int:
    """Bind an existing parent through directory FDs; reject symlink components."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parent.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def _publish(parent_fd: int, source: str, target: str) -> None:
    # Linux atomic directory publication must not replace even an empty racing
    # destination. Plain os.rename has overwrite semantics and is insufficient.
    try:
        rename = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise BundleError("atomic-no-replace-publication-unavailable") from exc
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent_fd, os.fsencode(source), parent_fd, os.fsencode(target), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _run_hashcat(args, *, env, timeout, max_bytes, stdout=None):
    """Drain bounded pipes under one deadline; kill/reap on every failure.

    stderr is discarded with a 64 KiB ceiling. Never capture unbounded output
    in memory or let an unexpected child fill the filesystem before inspection.
    """
    captured = io.BytesIO() if stdout is None else stdout
    deadline = time.monotonic() + timeout
    totals = {True: 0, False: 0}
    with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env) as process:
        try:
            with selectors.DefaultSelector() as poller:
                poller.register(process.stdout, selectors.EVENT_READ, True)
                poller.register(process.stderr, selectors.EVENT_READ, False)
                while poller.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise BundleError("hashcat-verification-timeout")
                    for key, _ in poller.select(remaining):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            poller.unregister(key.fileobj)
                            continue
                        totals[key.data] += len(chunk)
                        if totals[key.data] > (max_bytes if key.data else 65536):
                            raise BundleError("hashcat-output-limit-exceeded")
                        if key.data:
                            captured.write(chunk)
            process.wait(timeout=max(0, deadline - time.monotonic()))
            if process.returncode:
                raise BundleError("hashcat-stdout-failed")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    return captured.getvalue() if stdout is None else None


def _verify(db, staging: Path, segments: list[dict], runtime: Path) -> dict:
    if not segments:
        raise BundleError("no-exported-candidates-to-verify")
    executable = shutil.which("hashcat")
    if executable is None:
        raise BundleError("hashcat-not-installed")
    runtime.mkdir()
    (runtime / "data/hashcat/sessions").mkdir(parents=True)
    env = {**os.environ, "XDG_DATA_HOME": str(runtime / "data"),
           "XDG_CACHE_HOME": str(runtime / "cache"), "POCL_CACHE_DIR": str(runtime / "pocl")}
    env.setdefault("POCL_MAX_PTHREAD_COUNT", "2")
    try:
        version = _run_hashcat([executable, "--version"], timeout=10, env=env,
                              max_bytes=32).decode("ascii").strip()
        # Fail closed on a different backend profile; newer versions require
        # independent differential validation rather than silently inheriting it.
        if version != "v6.2.6":
            raise BundleError("unvalidated-hashcat-version")
        db.execute("CREATE TABLE observed(value BLOB PRIMARY KEY, n INTEGER NOT NULL)")
        emitted = 0
        for i, segment in enumerate(segments):
            output = runtime / f"stdout-{i}.txt"
            with output.open("wb") as out:
                _run_hashcat([executable, "--stdout", "-r", str(staging / segment["rules"]["file"]),
                              str(staging / segment["bases"]["file"])], stdout=out, env=env, timeout=60,
                             max_bytes=segment["outputs"] * (MAX_BYTES + 1))
            with output.open("rb") as stream:
                segment_emitted = 0
                while line := stream.readline(MAX_BYTES + 2):
                    if not 2 <= len(line) <= MAX_BYTES + 1 or not line.endswith(b"\n"):
                        raise BundleError("invalid-hashcat-output")
                    segment_emitted += 1
                    if segment_emitted > segment["outputs"]:
                        raise BundleError("hashcat-differential-mismatch")
                    value = line[:-1]; emitted += 1
                    db.execute("INSERT INTO observed VALUES(?,1) ON CONFLICT(value) DO UPDATE SET n=n+1", (value,))
        missing = db.execute("SELECT count(*) FROM expected WHERE value NOT IN (SELECT value FROM observed)").fetchone()[0]
        extra = db.execute("SELECT count(*) FROM observed WHERE value NOT IN (SELECT value FROM expected)").fetchone()[0]
        duplicates = db.execute("SELECT coalesce(sum(n-1),0) FROM observed").fetchone()[0]
        if missing or extra or duplicates:
            raise BundleError("hashcat-differential-mismatch")
        return {"status": "passed", "version": version, "missing": missing,
                "extra": extra, "duplicates": duplicates, "emitted": emitted}
    except (subprocess.SubprocessError, UnicodeError) as exc:
        raise BundleError("hashcat-verification-failed") from exc


def export_bundle(request: GenerationRequest, destination: str | Path, *,
                  service: GenerationService | None = None, allow_partial: bool = False,
                  verify: bool = False, limits: BundleLimits = BundleLimits()) -> dict:
    """Publish an immutable new directory or leave no final bundle on failure.

    Exactness is UTF-8 value-set parity for this frozen execution only. Request
    ranking/Policy/caps are consumed by MIMIC, not reimplemented in Hashcat.
    SQLite is a private disk spool, not the application database or a migration.
    """
    if not isinstance(request, GenerationRequest) or not isinstance(limits, BundleLimits):
        raise BundleError("invalid export input")
    if type(allow_partial) is not bool or type(verify) is not bool:
        raise BundleError("invalid export flags")
    if not sys.platform.startswith("linux") or not Path("/proc/self/fd").is_dir():
        raise BundleError("linux-atomic-publication-required")
    path = Path(destination)
    if ".." in path.parts:
        raise BundleError("parent-traversal-destination")
    path = path.absolute()
    parent = _parent(path)
    try:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(errno.EEXIST, "bundle destination exists")
        frozen = GenerationRequest.from_dict(request.to_dict())
        prepared = (service or GenerationService()).prepare(frozen)
        frozen = prepared.request
        summary = prepared.summary()
        anchor = Path(f"/proc/{os.getpid()}/fd/{parent}")
        with tempfile.TemporaryDirectory(prefix=".mimic-hashcat-", dir=anchor) as work_path:
            work = Path(work_path); staging = work / "bundle"; staging.mkdir(mode=0o700)
            with closing(sqlite3.connect(work / "pairs.sqlite")) as db, db:
                db.execute("PRAGMA cache_size=-2048"); db.execute("PRAGMA temp_store=FILE")
                db.executescript("""CREATE TABLE pairs(base BLOB, rule TEXT, PRIMARY KEY(base,rule));
                    CREATE TABLE expected(value BLOB PRIMARY KEY);
                    CREATE TABLE groups(signature TEXT PRIMARY KEY);
                    CREATE TABLE bases(base BLOB PRIMARY KEY, signature TEXT);
                    CREATE INDEX bases_group ON bases(signature,base);""")
                kinds = Counter(); omitted = Counter(); sources = Counter(); steps = Counter()
                provenance = hashlib.sha256(); retained = expanded_bytes = 0
                def checkpoint():
                    if prepared.evaluated_count >= limits.max_evaluated:
                        raise BundleError("accepted-scan-limit-exceeded")
                for result in prepared.iter_results(checkpoint=checkpoint):
                    candidate = result.candidate; retained += 1
                    provenance.update(json.dumps(asdict(candidate), ensure_ascii=True, sort_keys=True).encode() + b"\n")
                    for origin in candidate.origins:
                        sources[origin.source if origin.source in ("organization", "profile", "target", "context_file", "manual", "cli", "dataset", "ready_candidate", "knowledge") else "unknown"] += 1
                    for transformation in candidate.transformations:
                        steps[transformation.kind if transformation.kind in ("case", "leet", "affix", "reverse", "combine", "date", "organization_name", "organization_domain_label", "knowledge_template") else "unknown"] += 1
                    try:
                        base, rule, kind = compile_pair(candidate)
                    except BundleError as exc:
                        if not allow_partial: raise
                        omitted[str(exc)] += 1; continue
                    value = candidate.value.encode("utf-8"); expanded_bytes += len(value) + 1
                    db.execute("INSERT INTO pairs VALUES(?,?)", (base, rule))
                    db.execute("INSERT INTO expected VALUES(?)", (value,)); kinds[kind] += 1
                for (base,) in db.execute("SELECT DISTINCT base FROM pairs ORDER BY base"):
                    rules = [r[0] for r in db.execute("SELECT rule FROM pairs WHERE base=? ORDER BY rule LIMIT ?", (base, limits.max_rules_per_base + 1))]
                    if len(rules) > limits.max_rules_per_base:
                        raise BundleError("rules-per-base-limit-exceeded")
                    signature = json.dumps(rules, separators=(",", ":"))
                    db.execute("INSERT OR IGNORE INTO groups VALUES(?)", (signature,))
                    db.execute("INSERT INTO bases VALUES(?,?)", (base, signature))
                if db.execute("SELECT count(*) FROM groups").fetchone()[0] > limits.max_segments:
                    raise BundleError("segment-limit-exceeded")
                segments = []
                for i, (signature,) in enumerate(db.execute("SELECT signature FROM groups ORDER BY signature"), 1):
                    rules = json.loads(signature)
                    bases = _write(staging / f"segment-{i:03d}.bases.txt", (
                        b"$HEX[" + base.hex().encode("ascii") + b"]\n" for (base,) in db.execute(
                            "SELECT base FROM bases WHERE signature=? ORDER BY base", (signature,))))
                    rule_file = _write(staging / f"segment-{i:03d}.rule", ((rule + "\n").encode("ascii") for rule in rules))
                    segments.append({"bases": bases, "rules": rule_file, "outputs": bases["lines"] * rule_file["lines"]})
                differential = _verify(db, staging, segments, work / "runtime") if verify else {"status": "not-run"}
                count = db.execute("SELECT count(*) FROM expected").fetchone()[0]
                coverage = "partial" if omitted else "complete"
                manifest = {"format": FORMAT, "mimic_version": __version__,
                    "runtime": {"python": sys.version.split()[0], "unicode": unicodedata.unidata_version},
                    "mode": "materialized-frontier-affix" if kinds["compiled-affix"] else "literal-identity-only",
                    "request_sha256": hashlib.sha256(json.dumps(frozen.to_dict(), ensure_ascii=True, sort_keys=True).encode()).hexdigest(),
                    "candidate_provenance_sha256": provenance.hexdigest(),
                    "planning": {"reference_year": frozen.intelligence.reference_year, "preset": frozen.preset,
                        "knowledge_version": summary.knowledge_version,
                        "organization_version": ORGANIZATION_VERSION if frozen.organization_variants else None,
                        "ranking": frozen.ranking.to_dict(), "leet_mode": frozen.mutations.leet_mode,
                        "combine": frozen.mutations.combine, "separator_count": len(frozen.mutations.separators),
                        "policy": asdict(frozen.policy), "limits": asdict(frozen.limits),
                        "organization_variants": frozen.organization_variants,
                        "intelligence": {k: v for k, v in frozen.intelligence.to_dict().items() if k != "service_profiles"},
                        "service_count": len(frozen.intelligence.service_profiles),
                        "dataset_files": len(frozen.sources.dataset_paths), "ready_files": len(frozen.sources.ready_candidate_paths),
                        "ptbr": frozen.sources.include_ptbr, "common_ready_version": frozen.sources.common_passwords_version,
                        "pack_digests": [p.sha256 for p in frozen.sources.packs]},
                    "plan_counts": {"target_seeds": summary.target_seed_count, "organization_seeds": summary.organization_seed_count,
                        "organization_variants": summary.organization_variant_seed_count, "context_facts": summary.context_fact_count,
                        "knowledge_seeds": summary.knowledge_seed_count, "knowledge_numbers": summary.knowledge_number_count,
                        "corporate_roles_active": summary.corporate_roles_enabled},
                    "source_origin_counts": dict(sorted(sources.items())), "transformation_counts": dict(sorted(steps.items())),
                    "export_limits": asdict(limits), "profile": {"base_encoding": "hashcat-autohex-utf8", "max_value_bytes": MAX_BYTES,
                        "max_rule_operations": MAX_OPERATIONS, "hashcat_version": "v6.2.6", "operations": [":", "^", "$"]},
                    "materialization": dict(sorted(kinds.items())), "omitted": dict(sorted(omitted.items())),
                    "counts": {"evaluated": prepared.evaluated_count, "retained": retained, "exported": count,
                        "expanded_exported_bytes": expanded_bytes, "material_bytes": sum(s[k]["bytes"] for s in segments for k in ("bases", "rules"))},
                    "equivalence": {"coverage": coverage, "relation": "utf8-value-set", "scope": "retained-request-output",
                        "status": ("exact-set" if not omitted else "partial-request") if verify else "not-externally-verified",
                        "differential": differential,
                        "not_preserved": ["order", "rank", "score", "encounter_index", "first_cause", "performance"]},
                    "limitations": ["Earlier transformations and independent Reverse/Ready values are materialized, not general rules.",
                        "Policy, frontier caps and global dedup are applied by MIMIC for this frozen execution only.",
                        "Apply each rule file ONLY to its paired base file; do not cross or stack segments.",
                        "Keep default wordlist autohex; no implicit encoding conversion or optimized-kernel flags.",
                        "Identity-only output is literal export, not evidence of convergence or compression.",
                        "Digests are not anonymization; base/rule files contain sensitive input-derived material."],
                    "segments": segments}
                _write(staging / "manifest.json", [json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True).encode() + b"\n"])
            directory = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
            _publish(parent, work.name + "/bundle", path.name)
            return manifest
    finally:
        os.close(parent)

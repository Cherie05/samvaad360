"""Bounded, private analytics projection of the operational relationship outbox.

The operational database owns the leased queue. Snowflake is a read model, not
the transaction database. Run one writer for this sink: ordinary Snowflake
tables do not enforce a unique customer key across concurrent independent jobs.
No payload or connector error text is returned in the worker's public report.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from cloud.config import CloudConfig, CloudError, connect

DATABASE = "SAMVAAD_STAGING"
SCHEMA = "RELATIONSHIP"
ROLE = "SAMVAAD_RELATIONSHIP_SYNC"
TABLE = '"SAMVAAD_STAGING"."RELATIONSHIP"."CUSTOMER_PROJECTIONS"'
MAX_EVENTS = 5
MAX_PAYLOAD_BYTES = 1_048_576
STATEMENT_TIMEOUT_SECONDS = 15
LEASE_SECONDS = 900
MAX_STATEMENTS = 1 + MAX_EVENTS * 5  # identity + BEGIN/MERGE/SELECT/COMMIT/possible ROLLBACK


class SyncError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _safe_code(error: Exception) -> str:
    code = getattr(error, "code", "")
    allowed = {
        "INVALID_EVENT", "INVALID_PAYLOAD", "PAYLOAD_TOO_LARGE", "HASH_MISMATCH",
        "LEASE_EXPIRED", "RUN_DEADLINE", "STATEMENT_BUDGET", "PRIVATE_ROLE_REQUIRED",
        "PRIVATE_DATABASE_REQUIRED", "WAREHOUSE_REQUIRED", "PROJECTION_CONFLICT",
        "DUPLICATE_PROJECTION", "PROJECTION_NOT_VERIFIED", "WORKER_FAILED",
        "OUTBOX_LEASE_EXPIRED", "OUTBOX_LEASE_REQUIRED", "FORBIDDEN",
    }
    return code if code in allowed else "WORKER_FAILED"


def validate_event(event: dict[str, Any]) -> tuple[str, int, str, str]:
    """Validate an immutable complete-customer snapshot before any SQL mutation."""
    if not isinstance(event, dict):
        raise SyncError("INVALID_EVENT")
    customer_id = event.get("customer_id")
    version = event.get("version")
    event_id = event.get("event_id")
    if not isinstance(customer_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", customer_id):
        raise SyncError("INVALID_EVENT")
    if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= 2**53:
        raise SyncError("INVALID_EVENT")
    if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", event_id):
        raise SyncError("INVALID_EVENT")
    payload = event.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("customer"), dict):
        raise SyncError("INVALID_PAYLOAD")
    if payload["customer"].get("customer_id") != customer_id:
        raise SyncError("INVALID_PAYLOAD")
    if not all(isinstance(payload.get(key), list) for key in ("loans", "payments", "interactions")):
        raise SyncError("INVALID_PAYLOAD")
    if not isinstance(payload.get("relationship"), dict):
        raise SyncError("INVALID_PAYLOAD")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        raw = encoded.encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SyncError("INVALID_PAYLOAD") from exc
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise SyncError("PAYLOAD_TOO_LARGE")
    digest = hashlib.sha256(raw).hexdigest()
    if event.get("event_hash") != digest:
        raise SyncError("HASH_MISMATCH")
    return customer_id, version, digest, encoded


def _lease_deadline(event: dict[str, Any]) -> datetime:
    try:
        parsed = datetime.fromisoformat(event["lease_expires_at"].replace("Z", "+00:00"))
        lease_token = event.get("lease_token")
        if parsed.tzinfo is None or not isinstance(lease_token, str) or not 8 <= len(lease_token) <= 200 or not lease_token.isascii():
            raise ValueError("invalid lease")
        return parsed.astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SyncError("INVALID_EVENT") from exc


class PrivateProjectionSink:
    """A fixed-schema, parameterized Snowflake writer with read-after-write checks."""

    def __init__(self, connection, *, max_statements: int = MAX_STATEMENTS,
                 monotonic: Callable[[], float] = time.monotonic, deadline: float | None = None):
        if not 1 <= max_statements <= MAX_STATEMENTS:
            raise ValueError("The relationship statement budget is at most 26.")
        self.connection = connection
        self.max_statements = max_statements
        self.statements = 0
        self.monotonic = monotonic
        self.deadline = deadline
        self.ready = False
        self.broken = False

    def _execute(self, query: str, parameters=None):
        if self.statements >= self.max_statements:
            raise SyncError("STATEMENT_BUDGET")
        if self.deadline is not None and self.monotonic() + STATEMENT_TIMEOUT_SECONDS >= self.deadline:
            raise SyncError("RUN_DEADLINE")
        self.statements += 1
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, parameters, timeout=STATEMENT_TIMEOUT_SECONDS)
            return cursor.fetchall() if query.lstrip().startswith("SELECT") else None
        finally:
            cursor.close()

    def verify_identity(self):
        rows = self._execute("SELECT CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_WAREHOUSE()")
        if not rows or len(rows) != 1 or len(rows[0]) != 3:
            raise SyncError("PRIVATE_ROLE_REQUIRED")
        role, database, warehouse = rows[0]
        if role != ROLE:
            raise SyncError("PRIVATE_ROLE_REQUIRED")
        if database != DATABASE:
            raise SyncError("PRIVATE_DATABASE_REQUIRED")
        if not warehouse:
            raise SyncError("WAREHOUSE_REQUIRED")
        self.ready = True

    def apply(self, event: dict[str, Any]) -> str:
        if not self.ready:
            raise SyncError("PRIVATE_ROLE_REQUIRED")
        if self.broken:
            raise SyncError("WORKER_FAILED")
        customer_id, version, digest, encoded = validate_event(event)
        if _lease_deadline(event) <= datetime.now(timezone.utc):
            raise SyncError("LEASE_EXPIRED")
        begun = False
        try:
            self._execute("BEGIN")
            begun = True
            self._execute(f"""MERGE INTO {TABLE} target
USING (SELECT %s::VARCHAR CUSTOMER_ID, %s::NUMBER VERSION,
              %s::VARCHAR EVENT_HASH, %s::VARCHAR EVENT_ID,
              PARSE_JSON(%s) PAYLOAD) incoming
ON target.CUSTOMER_ID = incoming.CUSTOMER_ID
WHEN MATCHED AND incoming.VERSION > target.VERSION THEN UPDATE SET
 VERSION=incoming.VERSION, EVENT_HASH=incoming.EVENT_HASH,
 EVENT_ID=incoming.EVENT_ID, PAYLOAD=incoming.PAYLOAD, SYNCED_AT=CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (CUSTOMER_ID, VERSION, EVENT_HASH, EVENT_ID, PAYLOAD, SYNCED_AT)
 VALUES (incoming.CUSTOMER_ID, incoming.VERSION, incoming.EVENT_HASH,
         incoming.EVENT_ID, incoming.PAYLOAD, CURRENT_TIMESTAMP())""",
                          (customer_id, version, digest, event["event_id"], encoded))
            rows = self._execute(f"SELECT VERSION, EVENT_HASH FROM {TABLE} WHERE CUSTOMER_ID=%s", (customer_id,))
            if not rows:
                raise SyncError("PROJECTION_NOT_VERIFIED")
            if len(rows) != 1:
                raise SyncError("DUPLICATE_PROJECTION")
            stored_version, stored_hash = rows[0]
            if stored_version == version and stored_hash == digest:
                outcome = "VERIFIED"
            elif isinstance(stored_version, (int, float)) and not isinstance(stored_version, bool) and math.isfinite(stored_version) and stored_version > version:
                outcome = "SUPERSEDED"
            else:
                raise SyncError("PROJECTION_CONFLICT")
            self._execute("COMMIT")
            begun = False
            return outcome
        except Exception:
            if begun:
                try:
                    self._execute("ROLLBACK")
                except Exception:
                    # Closing the connection is the final cleanup if cancellation
                    # or exhausted budget prevents issuing another statement.
                    self.broken = True
            raise

    def close(self):
        self.connection.close()


@dataclass
class SyncReport:
    status: str = "COMPLETED"
    claimed: int = 0
    acknowledged: int = 0
    superseded: int = 0
    retried: int = 0
    unacknowledged: int = 0
    statements: int = 0
    error_code: str | None = None
    target: str = f"{DATABASE}.{SCHEMA}.CUSTOMER_PROJECTIONS"
    public_demo_updated: bool = False

    def as_dict(self):
        return asdict(self)


def sync_once(relationship, actor, sink: PrivateProjectionSink, *, limit: int = MAX_EVENTS,
              monotonic: Callable[[], float] = time.monotonic, max_run_seconds: int = 300) -> SyncReport:
    """Claim once, apply bounded snapshots, acknowledge only a verified active lease.

    A crash between Snowflake MERGE and the local acknowledgement leaves the
    event available for a safe retry after its lease expires. No queue event is
    acknowledged because a provider merely accepted a SQL statement.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_EVENTS:
        raise ValueError("A worker run processes between one and five events.")
    if not 60 <= max_run_seconds <= 600:
        raise ValueError("A worker run deadline must be between 60 and 600 seconds.")
    report = SyncReport()
    sink.deadline = monotonic() + max_run_seconds
    try:
        sink.verify_identity()
        claimed = relationship.claim_outbox(actor, limit=limit, lease_seconds=LEASE_SECONDS)
        if not isinstance(claimed, list) or len(claimed) > limit:
            raise SyncError("INVALID_EVENT")
        report.claimed = len(claimed)
        for event in claimed:
            try:
                outcome = sink.apply(event)
                relationship.complete_outbox(event["event_id"], event["lease_token"], actor)
                report.acknowledged += 1
                report.superseded += outcome == "SUPERSEDED"
            except Exception as exc:
                code = _safe_code(exc)
                report.error_code = code
                report.status = "PARTIAL" if report.acknowledged else "RETRY_REQUIRED"
                try:
                    relationship.complete_outbox(event["event_id"], event["lease_token"], actor, error=code)
                    report.retried += 1
                except Exception:
                    # An expired/stolen lease is never forced into SENT or RETRY.
                    report.unacknowledged += 1
        return report
    except Exception as exc:
        report.status = "FAILED"
        report.error_code = _safe_code(exc)
        return report
    finally:
        report.statements = sink.statements
        try:
            sink.close()
        except Exception:
            report.status = "PARTIAL" if report.acknowledged else "FAILED"
            report.error_code = report.error_code or "WORKER_FAILED"


def connect_private_sink(config: CloudConfig) -> PrivateProjectionSink:
    """Use only privately configured named credentials; never the website reader."""
    config.require_connection()
    config.require_warehouse()
    if config.database.upper() != DATABASE:
        raise CloudError("PRIVATE_DATABASE_REQUIRED", "Relationship sync requires the private SAMVAAD_STAGING database.")
    return PrivateProjectionSink(connect(config))

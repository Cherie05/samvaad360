"""Host-local admission and Snowflake spend guard for the public prototype.

Community Cloud does not provide a verified client-IP contract. Its reported IP
and arbitrary forwarded headers are therefore never used as security identities.
A managed ingress may supply a timestamped HMAC attestation after stripping the
same headers from inbound requests and disabling direct origin access.

SQLite makes reservations atomic across processes sharing this filesystem. This
is not a distributed edge limiter, a dollar/credit meter, or durable protection
across a Community Cloud container replacement. Snowflake resource monitors and
a trusted ingress/shared production store remain the account-level safeguards.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import os
import secrets
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


class GuardUnavailable(RuntimeError):
    """The admission store cannot safely make a reservation."""


class BudgetExceeded(RuntimeError):
    """No public application statements may run until the next budget window."""


@dataclass(frozen=True)
class VisitorIdentity:
    address: str | None = None
    verified: bool = False
    source: str = "shared-unverified"


@dataclass(frozen=True)
class Admission:
    allowed: bool
    retry_after: int = 0
    reason: str = "admitted"


def resolve_visitor(*, context_ip=None, headers: Mapping[str, str] | None = None,
                    edge_secret: str | None = None, now: float | None = None) -> VisitorIdentity:
    """Ignore spoofable context/XFF; accept only a fresh, authenticated edge IP.

    Edge payload: ``v1\n<canonical-IP>\n<UNIX-seconds>``. Headers are
    X-Samvaad-Client-IP, X-Samvaad-Timestamp, X-Samvaad-Signature (hex SHA256).
    A production proxy must overwrite all three and prevent direct origin access.
    Duplicate case-insensitive names, malformed addresses and replay-expired
    timestamps share the anonymous bucket. Raw addresses are never persisted.
    """
    if not isinstance(edge_secret, str) or len(edge_secret) < 32 or not headers:
        return VisitorIdentity()
    # Streamlit's header mapping collapses repeated values for __getitem__;
    # reject duplicates through its explicit get_all API before normalization.
    get_all = getattr(headers, "get_all", None)
    if get_all is not None and any(len(get_all(name)) != 1 for name in
            ("X-Samvaad-Client-IP", "X-Samvaad-Timestamp", "X-Samvaad-Signature")):
        return VisitorIdentity()
    normalized = {}
    for name, value in headers.items():
        key = str(name).lower()
        if key in normalized:
            return VisitorIdentity()
        normalized[key] = value
    address = normalized.get("x-samvaad-client-ip", "")
    stamp = normalized.get("x-samvaad-timestamp", "")
    signature = normalized.get("x-samvaad-signature", "")
    if not all(isinstance(v, str) for v in (address, stamp, signature)):
        return VisitorIdentity()
    if (len(address) > 64 or len(stamp) > 12 or not stamp.isascii() or not stamp.isdecimal()
            or len(signature) != 64 or any(c not in "0123456789abcdef" for c in signature)):
        return VisitorIdentity()
    try:
        parsed = ipaddress.ip_address(address)
        if parsed.version == 6 and parsed.ipv4_mapped:
            parsed = parsed.ipv4_mapped
        address = str(parsed)
        timestamp = int(stamp)
    except ValueError:
        return VisitorIdentity()
    current = time.time() if now is None else now
    if not math.isfinite(current) or abs(current - timestamp) > 60:
        return VisitorIdentity()
    payload = f"v1\n{address}\n{timestamp}".encode()
    expected = hmac.new(edge_secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return VisitorIdentity()
    return VisitorIdentity(address, True, "verified-edge-ip")


class QueryPermit:
    """A pre-charged, non-refundable application-statement reservation."""

    def __init__(self, statements: int):
        self.remaining = statements
        self._lock = threading.Lock()

    def before_execute(self):
        with self._lock:
            if self.remaining <= 0:
                raise BudgetExceeded("This refresh exhausted its public statement reservation.")
            self.remaining -= 1


class PublicGuard:
    """Atomic fixed Snowflake windows plus token buckets on one application host."""

    def __init__(self, path=None, *, hourly_statements=8, daily_statements=64,
                 clock: Callable[[], float] = time.time, max_buckets=4096):
        if any(not isinstance(x, int) or x <= 0 for x in (hourly_statements, daily_statements, max_buckets)):
            raise ValueError("Guard limits must be positive integers.")
        # This is trusted process configuration, never a query parameter or
        # browser header. Managed deployment mounts a persistent /data volume.
        configured_path = path if path is not None else os.getenv("SAMVAAD_PUBLIC_GUARD_PATH")
        self.path = (Path(configured_path) if configured_path
                     else Path(tempfile.gettempdir()) / "samvaad360-public" / "guard.db")
        self.clock = clock
        self.hourly_statements, self.daily_statements = hourly_statements, daily_statements
        self.max_buckets = max_buckets
        # Queue this process's brief writes before taking SQLite's cross-process
        # lock. Contending Streamlit threads must not starve one another until
        # the database timeout; other processes still use BEGIN IMMEDIATE.
        self._transaction_lock = threading.RLock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with closing(sqlite3.connect(self.path, timeout=2)) as connection, connection:
                connection.executescript("""
                    CREATE TABLE IF NOT EXISTS guard_metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS guard_buckets (name TEXT PRIMARY KEY, tokens REAL NOT NULL, updated REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS guard_windows (name TEXT NOT NULL, window INTEGER NOT NULL, used INTEGER NOT NULL,
                        PRIMARY KEY(name,window));
                    CREATE TABLE IF NOT EXISTS guard_counts (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
                """)
                connection.execute("INSERT OR IGNORE INTO guard_metadata VALUES ('hash-key', ?)", (secrets.token_hex(32),))
                connection.execute("INSERT OR IGNORE INTO guard_metadata VALUES ('circuit-failures', '0')")
                connection.execute("INSERT OR IGNORE INTO guard_metadata VALUES ('circuit-until', '0')")
                self._hash_key = connection.execute("SELECT value FROM guard_metadata WHERE name='hash-key'").fetchone()[0].encode()
            if os.name != "nt":
                self.path.chmod(0o600)
        except (OSError, sqlite3.Error, TypeError, IndexError) as error:
            raise GuardUnavailable("Public protection storage is unavailable.") from error

    def visitor(self, *, context_ip=None, headers=None, edge_secret=None):
        return resolve_visitor(context_ip=context_ip, headers=headers, edge_secret=edge_secret, now=self.clock())

    def _transaction(self, operation):
        try:
            with self._transaction_lock, closing(sqlite3.connect(self.path, timeout=2, isolation_level=None)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                result = operation(connection)
                connection.execute("COMMIT")
                return result
        except (OSError, sqlite3.Error, TypeError, ValueError, IndexError) as error:
            raise GuardUnavailable("Public protection storage is unavailable.") from error

    @staticmethod
    def _count(connection, name, amount=1):
        connection.execute("INSERT INTO guard_counts VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=value+excluded.value", (name, amount))

    def _visitor_key(self, identity):
        if not isinstance(identity, VisitorIdentity) or not identity.verified or not identity.address:
            return "shared-unverified"
        # Persist a keyed digest, never a raw visitor address.
        return hmac.new(self._hash_key, identity.address.encode(), hashlib.sha256).hexdigest()

    def admit(self, identity: VisitorIdentity, *, kind="browse") -> Admission:
        if kind not in {"browse", "action"}:
            raise ValueError("Choose browse or action admission.")
        now = self.clock()
        if not math.isfinite(now):
            return Admission(False, 60, "protection-unavailable")
        visitor = self._visitor_key(identity)
        verified = visitor != "shared-unverified"
        # All sessions without verified ingress share this quota; there is no
        # browser-provided session ID that permits creating fresh IP buckets.
        local = (120, 2.0) if kind == "browse" else (30, 0.5)
        if verified:
            local = (60, 1.0) if kind == "browse" else (15, 0.25)
        global_limit = (600, 10.0) if kind == "browse" else (120, 2.0)
        specs = [(f"global:{kind}", *global_limit), (f"visitor:{kind}:{visitor}", *local)]

        def reserve(connection):
            connection.execute("DELETE FROM guard_buckets WHERE updated<?", (now - 86400,))
            rows, wait, new = [], 0, 0
            for key, capacity, refill in specs:
                row = connection.execute("SELECT tokens,updated FROM guard_buckets WHERE name=?", (key,)).fetchone()
                if row:
                    tokens = min(capacity, row[0] + max(0.0, now - row[1]) * refill)
                    updated = max(now, row[1])  # Moving a clock backwards cannot refill a bucket.
                else:
                    tokens, updated, new = float(capacity), now, new + 1
                rows.append((key, tokens, updated))
                if tokens < 1:
                    wait = max(wait, math.ceil((1 - tokens) / refill))
            count = connection.execute("SELECT COUNT(*) FROM guard_buckets").fetchone()[0]
            if count + new > self.max_buckets:
                self._count(connection, "requests-blocked")
                return Admission(False, 60, "identity-capacity")
            if wait:
                self._count(connection, "requests-blocked")
                return Admission(False, wait, "rate-limited")
            for key, tokens, updated in rows:
                connection.execute("INSERT INTO guard_buckets VALUES (?,?,?) ON CONFLICT(name) DO UPDATE SET tokens=excluded.tokens,updated=excluded.updated", (key, tokens - 1, updated))
            self._count(connection, "requests-admitted")
            return Admission(True)
        try:
            return self._transaction(reserve)
        except GuardUnavailable:
            return Admission(False, 60, "protection-unavailable")

    def reserve_queries(self, statements=5) -> QueryPermit:
        if not isinstance(statements, int) or statements <= 0:
            raise ValueError("Reserve a positive number of application statements.")
        now = self.clock()
        if not math.isfinite(now):
            raise GuardUnavailable("The protection clock is unavailable.")
        windows = [("hour", int(now // 3600), self.hourly_statements),
                   ("day", int(now // 86400), self.daily_statements)]

        def reserve(connection):
            until = float(connection.execute("SELECT value FROM guard_metadata WHERE name='circuit-until'").fetchone()[0])
            if now < until:
                return "circuit-open"
            for name, window, maximum in windows:
                row = connection.execute("SELECT used FROM guard_windows WHERE name=? AND window=?", (name, window)).fetchone()
                if (row[0] if row else 0) + statements > maximum:
                    self._count(connection, "refreshes-budget-blocked")
                    return "query-budget-reached"
            for name, window, _ in windows:
                connection.execute("INSERT INTO guard_windows VALUES (?,?,?) ON CONFLICT(name,window) DO UPDATE SET used=used+excluded.used", (name, window, statements))
                connection.execute("DELETE FROM guard_windows WHERE name=? AND window<?", (name, window - 2))
            self._count(connection, "application-statements-reserved", statements)
            return None
        reason = self._transaction(reserve)
        if reason:
            raise BudgetExceeded(reason)
        return QueryPermit(statements)

    def refresh_succeeded(self):
        def update(connection):
            connection.execute("UPDATE guard_metadata SET value='0' WHERE name IN ('circuit-failures','circuit-until')")
            self._count(connection, "refreshes-succeeded")
        self._transaction(update)

    def refresh_failed(self):
        now = self.clock()
        def update(connection):
            failures = int(connection.execute("SELECT value FROM guard_metadata WHERE name='circuit-failures'").fetchone()[0]) + 1
            until = now + min(3600, 60 * (2 ** min(failures - 1, 6)))
            connection.execute("UPDATE guard_metadata SET value=? WHERE name='circuit-failures'", (str(failures),))
            connection.execute("UPDATE guard_metadata SET value=? WHERE name='circuit-until'", (str(until),))
            self._count(connection, "refreshes-failed")
        self._transaction(update)

    def stats(self):
        now = self.clock()
        def read(connection):
            counts = dict(connection.execute("SELECT name,value FROM guard_counts").fetchall())
            used = {}
            for name, seconds in (("hour", 3600), ("day", 86400)):
                row = connection.execute("SELECT used FROM guard_windows WHERE name=? AND window=?", (name, int(now // seconds))).fetchone()
                used[name] = row[0] if row else 0
            until = float(connection.execute("SELECT value FROM guard_metadata WHERE name='circuit-until'").fetchone()[0])
            return {"scope": "shared-application-host", "distributed": False,
                "limiter_scope": "verified-edge-IP-or-shared-unverified-visitors",
                "application_statements_hour": used["hour"], "application_statements_day": used["day"],
                "hourly_statement_limit": self.hourly_statements, "daily_statement_limit": self.daily_statements,
                "circuit_open": now < until, "circuit_retry_seconds": max(0, math.ceil(until - now)),
                "requests_admitted": counts.get("requests-admitted", 0),
                "requests_blocked": counts.get("requests-blocked", 0),
                "refreshes_succeeded": counts.get("refreshes-succeeded", 0),
                "refreshes_failed": counts.get("refreshes-failed", 0),
                "refreshes_budget_blocked": counts.get("refreshes-budget-blocked", 0),
                "credits_metered": False}
        return self._transaction(read)

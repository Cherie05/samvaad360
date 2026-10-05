"""Reproducible synthetic fixture bundles and bound-value cloud loading."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from pathlib import Path

from cloud.config import CloudConfig, CloudError, identifier
from samvaad.fixtures import generate_fixture
from samvaad.signals import extract_signals

TABLES = {"customers": ("CUSTOMERS", "customer_id"), "loans": ("LOANS", "loan_id"), "payments": ("PAYMENTS", "payment_id"), "interactions": ("INTERACTIONS", "interaction_id")}
DEFAULT_REFERENCE = "2026-10-05T00:00:00+00:00"


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def build_bundle(customers: int = 20, reference: str = DEFAULT_REFERENCE) -> dict:
    if isinstance(customers, bool) or not isinstance(customers, int) or not 10 <= customers <= 100:
        raise CloudError("INVALID_COUNT", "Cloud demo fixtures support 10-100 synthetic customers.")
    try:
        stamp = datetime.fromisoformat(reference.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise CloudError("INVALID_REFERENCE", "Choose a valid timezone-aware fixture timestamp.") from exc
    if stamp.tzinfo is None:
        raise CloudError("INVALID_REFERENCE", "Fixture reference must include its timezone.")
    data = generate_fixture(customers, reference=stamp)
    bundle = {"version": 1, "synthetic": True, "reference": stamp.isoformat(), "counts": {key: len(rows) for key, rows in data.items()}, "data": data}
    bundle["sha256"] = digest(bundle)
    return bundle


def validate_bundle(bundle: dict) -> dict:
    if not isinstance(bundle, dict) or set(bundle) != {"version", "synthetic", "reference", "counts", "data", "sha256"}:
        raise CloudError("INVALID_BUNDLE", "Unexpected fixture bundle format.")
    if bundle["version"] != 1 or bundle["synthetic"] is not True or set(bundle["data"]) != set(TABLES):
        raise CloudError("INVALID_BUNDLE", "Only version-1 synthetic fixture bundles are supported.")
    expected = digest({key: value for key, value in bundle.items() if key != "sha256"})
    if bundle["sha256"] != expected:
        raise CloudError("BUNDLE_HASH_MISMATCH", "Fixture content does not match its manifest checksum.")
    for key, (_, id_field) in TABLES.items():
        rows = bundle["data"][key]
        if not isinstance(rows, list) or bundle["counts"].get(key) != len(rows):
            raise CloudError("INVALID_BUNDLE", "Fixture row counts do not match the manifest.")
        identities = [row.get(id_field) for row in rows if isinstance(row, dict)]
        if len(identities) != len(rows) or any(not isinstance(value, str) or not value for value in identities) or len(set(identities)) != len(identities):
            raise CloudError("DUPLICATE_FIXTURE_ID", "Every fixture row must have a distinct, nonempty ID.")
    customers = {row["customer_id"] for row in bundle["data"]["customers"]}
    loans = {row["loan_id"] for row in bundle["data"]["loans"]}
    if not 10 <= len(customers) <= 100:
        raise CloudError("INVALID_COUNT", "Cloud demo bundles must contain 10-100 customers.")
    if any(row.get("email") != row["customer_id"].lower() + "@example.invalid" or row.get("phone") != "******0000" for row in bundle["data"]["customers"]):
        raise CloudError("REAL_CONTACT_REJECTED", "Cloud fixture import accepts only reserved fictional contact details.")
    if any(row.get("customer_id") not in customers for table in ("loans", "interactions") for row in bundle["data"][table]) or any(row.get("loan_id") not in loans for row in bundle["data"]["payments"]):
        raise CloudError("INVALID_RELATION", "Fixture references a missing customer or loan.")
    return bundle


def read_bundle(path: str | Path) -> dict:
    try:
        bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CloudError("BUNDLE_READ_FAILED", "Could not read the specified fixture JSON.") from exc
    return validate_bundle(bundle)


def stage_rows(bundle: dict) -> list[tuple]:
    validate_bundle(bundle)
    records = []
    for dataset, (_, id_field) in TABLES.items():
        for row in bundle["data"][dataset]:
            signals = extract_signals(row["text"]) if dataset == "interactions" else None
            records.append((dataset, row[id_field], row.get("customer_id") if dataset in {"loans", "interactions"} else row.get("loan_id"),
                            row.get("channel"), row.get("ts"), row.get("text"), signals["evidence_text"] if signals else None,
                            canonical(signals) if signals else None, signals["source_hash"] if signals else digest(row), canonical(row), bundle["sha256"]))
    return records


def _state(cursor, config: CloudConfig) -> dict:
    values = {}
    for key, (table, id_field) in TABLES.items():
        cursor.execute(f"SELECT COUNT(*),MIN(FIXTURE_HASH),MAX(FIXTURE_HASH),COUNT(DISTINCT {identifier(id_field)}) FROM {config.object('RAW',table)}")
        count, minimum, maximum, unique = cursor.fetchone()
        values[key] = {"count": count, "min_hash": minimum, "max_hash": maximum, "unique": unique}
    return values


def _is_matching(state: dict, bundle: dict) -> bool:
    return all(row["count"] == bundle["counts"][key] and row["unique"] == row["count"] and row["min_hash"] == row["max_hash"] == bundle["sha256"] for key, row in state.items())


def load_fixture(connection, config: CloudConfig, bundle: dict) -> dict:
    """Single-developer analytics bootstrap, never a workflow state migration."""
    validate_bundle(bundle)
    cursor = connection.cursor()
    stage = config.object("RAW", "SAMVAAD_IMPORT_" + secrets.token_hex(8))
    stage_created = False
    try:
        state = _state(cursor, config)
        if _is_matching(state, bundle):
            return {"status": "ALREADY_LOADED", "counts": bundle["counts"], "sha256": bundle["sha256"]}
        if any(row["count"] for row in state.values()):
            raise CloudError("CLOUD_DATA_EXISTS", "Cloud raw tables contain another or incomplete dataset. No data was overwritten. Choose a new demo database.")
        cursor.execute(f"CREATE TEMPORARY TABLE {stage} (DATASET VARCHAR,ROW_ID VARCHAR,PARENT_ID VARCHAR,CHANNEL VARCHAR,TS VARCHAR,TEXT VARCHAR,EVIDENCE_TEXT VARCHAR,OFFLINE_JSON VARCHAR,SOURCE_HASH VARCHAR,PAYLOAD_JSON VARCHAR,FIXTURE_HASH VARCHAR)")
        stage_created = True
        cursor.execute("BEGIN")
        cursor.executemany(f"INSERT INTO {stage} VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", stage_rows(bundle))
        for dataset, (table, _) in TABLES.items():
            if dataset == "customers":
                selection = "ROW_ID,PARSE_JSON(PAYLOAD_JSON),FIXTURE_HASH,CURRENT_TIMESTAMP()"
            elif dataset in {"loans", "payments"}:
                selection = "ROW_ID,PARENT_ID,PARSE_JSON(PAYLOAD_JSON),FIXTURE_HASH,CURRENT_TIMESTAMP()"
            else:
                selection = "ROW_ID,PARENT_ID,CHANNEL,TO_TIMESTAMP_TZ(TS),TEXT,EVIDENCE_TEXT,PARSE_JSON(OFFLINE_JSON),SOURCE_HASH,FIXTURE_HASH,CURRENT_TIMESTAMP()"
            cursor.execute(f"INSERT INTO {config.object('RAW',table)} SELECT {selection} FROM {stage} WHERE DATASET=%s", (dataset,))
        if not _is_matching(_state(cursor, config), bundle):
            raise CloudError("LOAD_VERIFICATION_FAILED", "Loaded row counts, unique IDs, or manifest checksums differ. Import was rolled back.")
        cursor.execute("COMMIT")
        return {"status": "LOADED", "counts": bundle["counts"], "sha256": bundle["sha256"]}
    except Exception:
        if stage_created:
            cursor.execute("ROLLBACK")
        raise
    finally:
        if stage_created:
            cursor.execute(f"DROP TABLE IF EXISTS {stage}")
        cursor.close()

"""Inspect the private relationship queue, or explicitly apply one bounded batch."""
from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from pathlib import Path

from cloud.config import CloudError, read_config
from cloud.relationship_sync import DATABASE, MAX_EVENTS, MAX_STATEMENTS, SCHEMA, connect_private_sink, sync_once
from samvaad.models import ActionError, DEMO_ACTORS


@contextmanager
def single_writer_lock(path: Path):
    """Host-local locking; distributed deployments must schedule ONE worker."""
    stream = path.open("a+b")
    locked = False
    try:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if __import__("os").name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    except OSError as exc:
        if not locked:
            raise CloudError("WRITER_ALREADY_RUNNING", "Another relationship sync writer is active on this host.") from exc
        raise
    finally:
        if locked:
            stream.seek(0)
            if __import__("os").name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=".local/samvaad.db", help="Existing private operational SQLite database.")
    parser.add_argument("--config", help="Non-secret named Snowflake connection configuration TOML.")
    parser.add_argument("--actor", choices=("demo-admin", "local-runner"), default="demo-admin",
                        help="Local pilot operator; not an enterprise authentication mechanism.")
    parser.add_argument("--max-events", type=int, choices=range(1, MAX_EVENTS + 1), default=MAX_EVENTS)
    parser.add_argument("--apply", action="store_true", help="Connect using private named credentials and write a bounded private batch.")
    options = parser.parse_args(argv)
    db_path = Path(options.db).expanduser().resolve()
    try:
        if not db_path.is_file():
            raise CloudError("OPERATIONAL_DB_REQUIRED", "Start the private local portal and create a customer first. Sync never creates or seeds its source database.")
        from samvaad.service import LocalService
        from samvaad.relationship import RelationshipService
        relationship = RelationshipService(LocalService(db_path, seed=False))
        actor = DEMO_ACTORS[options.actor]
        if not options.apply:
            queue = relationship.outbox_status(actor)
            report = {"status": "NOT_APPLIED", "target": f"{DATABASE}.{SCHEMA}.CUSTOMER_PROJECTIONS",
                      "max_events": options.max_events, "statement_attempt_limit": MAX_STATEMENTS,
                      "queue_totals": queue.get("counts", {}), "public_demo_updated": False,
                      "message": "No connection or Snowflake write attempted. Use --apply after private-role setup."}
            print(json.dumps(report, indent=2))
            return 0
        with single_writer_lock(db_path.parent / "relationship-sync.lock"):
            sink = connect_private_sink(read_config(options.config))
            report = sync_once(relationship, actor, sink, limit=options.max_events).as_dict()
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "COMPLETED" else 1
    except (CloudError, ActionError) as exc:
        # Codes are fixed by our implementation; never print connector exceptions,
        # credentials, customer contacts, event payloads, or lease tokens.
        print(json.dumps({"status": "FAILED", "error_code": exc.code, "public_demo_updated": False}))
        return 1
    except Exception:
        print(json.dumps({"status": "FAILED", "error_code": "WORKER_FAILED", "public_demo_updated": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

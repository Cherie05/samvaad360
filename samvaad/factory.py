"""One boundary for swapping local persistence for the future Snowflake adapter."""
import os
from pathlib import Path
from samvaad.models import ActionError
from samvaad.service import LocalService


def create_service(backend: str | None = None, db_path: str | Path | None = None):
    mode = backend or os.getenv("SAMVAAD_BACKEND", "local")
    if mode != "local":
        raise ActionError("CLOUD_PENDING", "Snowflake migration is pending. Use SAMVAAD_BACKEND=local for the tested local product.")
    return LocalService(db_path=db_path or os.getenv("SAMVAAD_DB_PATH", ".local/samvaad.db"))

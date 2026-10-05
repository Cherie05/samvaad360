"""Render only packaged SQL with conservative, separately validated inputs."""

from pathlib import Path
import re

from cloud.config import CloudConfig, CloudError, identifier

SQL_ROOT = Path(__file__).resolve().parent / "sql"
ASSETS = {"schema": "001_schema.sql", "views": "002_views.sql", "search": "003_search.sql", "enrichment": "004_enrichment.sql"}


def render(asset: str, config: CloudConfig, *, limit: int = 5) -> str:
    if asset not in ASSETS:
        raise CloudError("UNKNOWN_ASSET", "Choose a packaged cloud SQL asset.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise CloudError("INVALID_LIMIT", "Cortex enrichment must be bounded to 1-100 interactions.")
    if asset == "search":
        config.require_warehouse()
    content = (SQL_ROOT / ASSETS[asset]).read_text(encoding="utf-8")
    values = {"DB": identifier(config.database), "WH": identifier(config.warehouse) if config.warehouse else "", "LIMIT": str(limit)}
    def replace(match):
        if match[1] not in values:
            raise CloudError("UNKNOWN_PLACEHOLDER", "SQL contains an unsupported placeholder.")
        return values[match[1]]
    return re.sub(r"\{\{([A-Z]+)\}\}", replace, content)


def statements(content: str) -> list[str]:
    # Packaged statements contain neither semicolons in literals nor SQL scripting.
    return [statement.strip() for statement in content.split(";") if statement.strip()]

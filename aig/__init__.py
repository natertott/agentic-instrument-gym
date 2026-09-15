"""agentic-instrument-gym: benchmark evidence schema and comparison tooling (WP1)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
DATA_DIR = ROOT / "data"
SITE_DATA_DIR = ROOT / "site" / "data"

__all__ = ["ROOT", "SCHEMA_DIR", "DATA_DIR", "SITE_DATA_DIR"]

"""Diagnose and repair only the hosted app environment after private login."""
from cloud.runtime_repair import main

if __name__ == "__main__":
    raise SystemExit(main())

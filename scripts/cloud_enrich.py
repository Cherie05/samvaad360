"""Prepare or explicitly run bounded Cortex signal enrichment."""
import sys
from cloud.cli import main

if __name__ == "__main__":
    sys.exit(main(["enrich", *sys.argv[1:]]))

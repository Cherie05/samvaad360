"""Prepare analytics DDL; --apply is explicit and never creates a warehouse."""
import sys
from cloud.cli import main

if __name__ == "__main__":
    sys.exit(main(["deploy", *sys.argv[1:]]))

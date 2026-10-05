"""Validate/export bootstrap fixture loading; defaults to validation only."""
import sys
from cloud.cli import main

if __name__ == "__main__":
    sys.exit(main(["load", *sys.argv[1:]]))

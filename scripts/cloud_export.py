"""Export reproducible, fictional cloud fixture data."""
import sys
from cloud.cli import main

if __name__ == "__main__":
    sys.exit(main(["export", *sys.argv[1:]]))

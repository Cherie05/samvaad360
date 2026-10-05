"""Run from the workspace root using python -m scripts.cloud_doctor."""
import sys
from cloud.cli import main

if __name__ == "__main__":
    sys.exit(main(["doctor", *sys.argv[1:]]))

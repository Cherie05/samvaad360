"""Check installed CoCo, optionally perform one real account/model smoke."""
import sys
from cloud.cli import main

if __name__ == "__main__":
    sys.exit(main(["coco", *sys.argv[1:]]))

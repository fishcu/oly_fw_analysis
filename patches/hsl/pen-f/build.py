#!/usr/bin/env python3
"""Rebuild the PEN-F HSL release from exact stock and assembly source.

Thin wrapper around the shared patch builder (tools/oly_patch.py) with this
directory's patch.json. The definition records the released package hash, so
the build fails unless the result is byte-identical to the published BIN.
No network or camera access.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'tools'))
from oly_patch import main  # noqa: E402

if __name__ == '__main__':
    main(default_patch=HERE)

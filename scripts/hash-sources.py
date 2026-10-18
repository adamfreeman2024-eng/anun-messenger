#!/usr/bin/env python3
"""Print sha256 of the spike sources. Same tree, same hashes."""

import hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for path in sorted((root / "spike").glob("*.py")):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"{digest}  spike/{path.name}")

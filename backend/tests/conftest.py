"""
Test-wide configuration and shared fixtures.

Ensures the repository root (and Lambda packages) are importable without
duplicated sys.path tweaks inside each test module.
"""
from __future__ import annotations

import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LAMBDA_ROOT = REPO_ROOT / "backend" / "lambdas"

for target in (REPO_ROOT, LAMBDA_ROOT):
    target_str = str(target)
    if target_str not in sys.path:
        sys.path.insert(0, target_str)

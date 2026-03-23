"""Stale flag scanner: find unused flags, always-on/off flags, and flag references in code."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# Patterns that indicate flag usage in source code
FLAG_USAGE_PATTERNS = [
    # Python: is_enabled("flag_name"), flags.is_enabled("flag_name")
    re.compile(r"""is_enabled\(\s*["']([a-zA-Z_][\w.-]*)["']"""),
    # Python: FlagClient; client.evaluate("flag_name")
    re.compile(r"""evaluate\(\s*["']([a-zA-Z_][\w.-]*)["']"""),
    # JavaScript/TypeScript: isEnabled("flag_name"), featureFlag("flag_name")
    re.compile(r"""isEnabled\(\s*["']([a-zA-Z_][\w.-]*)["']"""),
    re.compile(r"""featureFlag\(\s*["']([a-zA-Z_][\w.-]*)["']"""),
    # Generic: feature_flag("name"), flag("name"), FF_NAME
    re.compile(r"""feature_flag\(\s*["']([a-zA-Z_][\w.-]*)["']"""),
    re.compile(r"""flag\(\s*["']([a-zA-Z_][\w.-]*)["']"""),
    # Ruby: feature_enabled?(:flag_name)
    re.compile(r"""feature_enabled\?\(\s*:([a-zA-Z_][\w]*)"""),
    # Go: flags.IsEnabled("flag_name")
    re.compile(r"""IsEnabled\(\s*"([a-zA-Z_][\w.-]*)"\s*"""),
    # ENV-style: FEATURE_FLAG_NAME
    re.compile(r"""FEATURE_([A-Z_]+)"""),
]

# File extensions to scan
SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".rb", ".go",
    ".java", ".kt", ".rs", ".php", ".vue", ".svelte",
}

# Directories to skip
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "vendor", "target",
}


def scan_codebase(
    directory: str,
    extra_patterns: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Scan source code for feature flag references.

    Returns dict mapping flag names to list of usage locations.
    """
    patterns = list(FLAG_USAGE_PATTERNS)
    if extra_patterns:
        for p in extra_patterns:
            patterns.append(re.compile(p))

    flag_refs: dict[str, list[dict[str, Any]]] = {}

    for root, dirs, files in os.walk(directory):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in files:
            ext = Path(filename).suffix
            if ext not in SCAN_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            try:
                with open(filepath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue

            for line_num, line in enumerate(content.splitlines(), 1):
                for pattern in patterns:
                    for match in pattern.finditer(line):
                        flag_name = match.group(1).lower().replace("_", "-")
                        # Normalize: also keep original
                        original_name = match.group(1)
                        ref = {
                            "file": os.path.relpath(filepath, directory),
                            "line": line_num,
                            "match": match.group(0),
                            "original_name": original_name,
                        }
                        flag_refs.setdefault(flag_name, []).append(ref)
                        if original_name != flag_name:
                            flag_refs.setdefault(original_name, []).append(ref)

    return flag_refs


def find_unused_flags(
    defined_flags: list[dict[str, Any]],
    code_refs: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Find flags that are defined but not referenced in code."""
    unused = []
    for flag in defined_flags:
        name = flag["name"]
        # Check both exact match and normalized forms
        normalized = name.lower().replace("-", "_")
        if name not in code_refs and normalized not in code_refs:
            unused.append(flag)
    return unused


def find_undefined_flags(
    defined_flags: list[dict[str, Any]],
    code_refs: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Find flags referenced in code but not defined in YAML."""
    defined_names = set()
    for flag in defined_flags:
        defined_names.add(flag["name"])
        defined_names.add(flag["name"].lower().replace("-", "_"))
        defined_names.add(flag["name"].lower().replace("_", "-"))

    undefined = []
    for ref_name in code_refs:
        normalized = ref_name.lower().replace("-", "_")
        if ref_name not in defined_names and normalized not in defined_names:
            undefined.append(ref_name)
    return sorted(set(undefined))


def find_stale_flags(
    flags: list[dict[str, Any]],
    stale_days: int = 30,
) -> list[dict[str, Any]]:
    """Find flags that have been always-on or always-off for too long.

    A flag is stale if:
    - It was created more than stale_days ago AND is permanently on (100% rollout)
    - It was created more than stale_days ago AND is permanently off
    """
    stale = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

    for flag in flags:
        created = flag.get("created_at", "")
        if not created:
            continue

        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)

        if created_dt > cutoff:
            continue  # Too new to be stale

        enabled = flag.get("enabled", False)
        rollout = flag.get("rollout", 100)
        targeting = flag.get("targeting", [])
        age_days = (datetime.now(timezone.utc) - created_dt).days

        if enabled and rollout == 100 and not targeting:
            stale.append({
                **flag,
                "stale_reason": f"Always ON for {age_days} days - consider removing flag and keeping code",
            })
        elif not enabled:
            stale.append({
                **flag,
                "stale_reason": f"Always OFF for {age_days} days - consider removing flag and dead code",
            })

    return stale

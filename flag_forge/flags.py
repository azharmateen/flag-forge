"""Flag definition and YAML storage management."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_FLAGS_FILE = ".flags.yml"

# Flag schema example:
# flags:
#   new_checkout:
#     enabled: true
#     description: "New checkout flow"
#     rollout: 50
#     targeting:
#       - attribute: country
#         operator: in
#         values: ["US", "CA"]
#       - attribute: plan
#         operator: eq
#         values: ["pro"]
#     environments:
#       - production
#       - staging
#     owner: "team-payments"
#     created_at: "2026-01-15T10:00:00Z"
#     lifecycle: "rollout"


class FlagStore:
    """Manages feature flags stored in a YAML file."""

    def __init__(self, flags_file: str | None = None):
        self.flags_file = flags_file or DEFAULT_FLAGS_FILE
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load flags from YAML file."""
        path = Path(self.flags_file)
        if path.is_file():
            with open(path) as f:
                self._data = yaml.safe_load(f) or {}
        if "flags" not in self._data:
            self._data["flags"] = {}

    def _save(self) -> None:
        """Save flags to YAML file."""
        path = Path(self.flags_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(
                self._data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    def create(
        self,
        name: str,
        description: str = "",
        enabled: bool = False,
        rollout: int = 100,
        environments: list[str] | None = None,
        owner: str = "",
        targeting: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new feature flag."""
        if name in self._data["flags"]:
            raise ValueError(f"Flag '{name}' already exists.")

        flag = {
            "enabled": enabled,
            "description": description,
            "rollout": rollout,
            "targeting": targeting or [],
            "environments": environments or ["development", "staging", "production"],
            "owner": owner,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "lifecycle": "created",
        }

        self._data["flags"][name] = flag
        self._save()
        return flag

    def get(self, name: str) -> dict[str, Any] | None:
        """Get a flag by name."""
        flag = self._data["flags"].get(name)
        if flag:
            return {"name": name, **flag}
        return None

    def update(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """Update a flag's properties."""
        if name not in self._data["flags"]:
            raise ValueError(f"Flag '{name}' not found.")

        for key, value in kwargs.items():
            if value is not None:
                self._data["flags"][name][key] = value

        self._save()
        return self.get(name)  # type: ignore

    def toggle(self, name: str) -> bool:
        """Toggle a flag's enabled state. Returns new state."""
        if name not in self._data["flags"]:
            raise ValueError(f"Flag '{name}' not found.")

        current = self._data["flags"][name].get("enabled", False)
        self._data["flags"][name]["enabled"] = not current
        self._save()
        return not current

    def delete(self, name: str) -> bool:
        """Delete a flag."""
        if name in self._data["flags"]:
            del self._data["flags"][name]
            self._save()
            return True
        return False

    def list_all(self) -> list[dict[str, Any]]:
        """List all flags."""
        flags = []
        for name, config in self._data["flags"].items():
            flags.append({"name": name, **config})
        return flags

    def get_raw(self) -> dict[str, Any]:
        """Get raw flags data for evaluation."""
        return self._data.get("flags", {})

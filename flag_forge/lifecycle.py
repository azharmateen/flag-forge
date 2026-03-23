"""Flag lifecycle management: track stages and suggest actions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# Lifecycle stages:
# created -> enabled -> rollout -> full_rollout -> cleanup
LIFECYCLE_STAGES = [
    "created",       # Flag defined but disabled
    "enabled",       # Flag turned on (limited rollout or targeting)
    "rollout",       # Gradually increasing rollout percentage
    "full_rollout",  # 100% rollout, no targeting restrictions
    "cleanup",       # Flag should be removed, code kept
]


def get_lifecycle_stage(flag: dict[str, Any]) -> str:
    """Determine the current lifecycle stage of a flag."""
    enabled = flag.get("enabled", False)
    rollout = flag.get("rollout", 100)
    targeting = flag.get("targeting", [])

    if not enabled:
        return "created"

    if targeting:
        return "enabled"

    if rollout < 100:
        return "rollout"

    return "full_rollout"


def suggest_action(flag: dict[str, Any]) -> dict[str, str]:
    """Suggest the next action for a flag based on its lifecycle stage."""
    stage = get_lifecycle_stage(flag)
    name = flag.get("name", "unknown")

    suggestions = {
        "created": {
            "stage": "created",
            "action": "Enable the flag for testing",
            "command": f"flag-forge toggle {name}",
            "description": (
                "This flag is defined but not enabled. "
                "Enable it for a subset of users to start testing."
            ),
        },
        "enabled": {
            "stage": "enabled",
            "action": "Start gradual rollout",
            "command": f"flag-forge eval {name} --context user_id=test",
            "description": (
                "The flag is enabled with targeting rules. "
                "Test with targeted users before expanding rollout."
            ),
        },
        "rollout": {
            "stage": "rollout",
            "action": "Increase rollout percentage",
            "command": f"flag-forge create {name}  # (update rollout in .flags.yml)",
            "description": (
                f"Currently at {flag.get('rollout', 0)}% rollout. "
                "Monitor metrics and gradually increase to 100%."
            ),
        },
        "full_rollout": {
            "stage": "full_rollout",
            "action": "Schedule cleanup",
            "command": f"flag-forge cleanup",
            "description": (
                "This flag is at 100% rollout with no targeting. "
                "The feature is fully launched. Remove the flag and keep the code."
            ),
        },
    }

    return suggestions.get(stage, {
        "stage": stage,
        "action": "Unknown stage",
        "command": "",
        "description": "Could not determine next action.",
    })


def generate_rollout_plan(
    flag_name: str,
    steps: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Generate a suggested rollout plan for a flag.

    Default: 1% -> 5% -> 10% -> 25% -> 50% -> 100%
    """
    if steps is None:
        steps = [1, 5, 10, 25, 50, 100]

    plan = []
    for i, pct in enumerate(steps):
        plan.append({
            "step": i + 1,
            "rollout_pct": pct,
            "action": f"Set rollout to {pct}%",
            "validation": (
                f"Monitor error rates and metrics for {pct}% of users"
                if pct < 100
                else "Full rollout - monitor for 48h then schedule cleanup"
            ),
            "yaml_snippet": (
                f"# In .flags.yml\n"
                f"flags:\n"
                f"  {flag_name}:\n"
                f"    enabled: true\n"
                f"    rollout: {pct}\n"
            ),
        })

    return plan


def get_lifecycle_summary(flags: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Summarize all flags by lifecycle stage."""
    summary: dict[str, list[str]] = {stage: [] for stage in LIFECYCLE_STAGES}

    for flag in flags:
        stage = get_lifecycle_stage(flag)
        summary[stage].append(flag.get("name", "unknown"))

    return summary

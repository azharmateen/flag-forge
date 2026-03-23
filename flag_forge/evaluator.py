"""Flag evaluation engine: enabled check, percentage rollout, and targeting rules."""

from __future__ import annotations

import hashlib
from typing import Any


class EvaluationResult:
    """Result of evaluating a feature flag."""

    def __init__(self, enabled: bool, reason: str, flag_name: str = ""):
        self.enabled = enabled
        self.reason = reason
        self.flag_name = flag_name

    def __bool__(self) -> bool:
        return self.enabled

    def __repr__(self) -> str:
        return f"EvaluationResult(enabled={self.enabled}, reason='{self.reason}')"

    def to_dict(self) -> dict[str, Any]:
        return {
            "flag": self.flag_name,
            "enabled": self.enabled,
            "reason": self.reason,
        }


def evaluate_flag(
    flag_name: str,
    flag_config: dict[str, Any],
    context: dict[str, Any] | None = None,
    environment: str | None = None,
) -> EvaluationResult:
    """Evaluate whether a feature flag is enabled for the given context.

    Evaluation order:
    1. Check if flag is globally enabled
    2. Check environment restrictions
    3. Check targeting rules
    4. Check percentage rollout

    Args:
        flag_name: Name of the flag.
        flag_config: Flag configuration dict.
        context: User/request context (e.g. {"user_id": "123", "country": "US"}).
        environment: Current environment name.

    Returns:
        EvaluationResult with enabled status and reason.
    """
    context = context or {}

    # Step 1: Check if globally disabled
    if not flag_config.get("enabled", False):
        return EvaluationResult(False, "flag_disabled", flag_name)

    # Step 2: Check environment
    environments = flag_config.get("environments", [])
    if environments and environment and environment not in environments:
        return EvaluationResult(
            False, f"environment_excluded:{environment}", flag_name
        )

    # Step 3: Check targeting rules
    targeting = flag_config.get("targeting", [])
    if targeting:
        target_result = _evaluate_targeting(targeting, context)
        if target_result is not None:
            if target_result:
                return EvaluationResult(True, "targeting_match", flag_name)
            else:
                return EvaluationResult(False, "targeting_no_match", flag_name)

    # Step 4: Check percentage rollout
    rollout = flag_config.get("rollout", 100)
    if rollout < 100:
        user_id = context.get("user_id", context.get("id", ""))
        if not user_id:
            # No user_id means we can't do deterministic rollout
            return EvaluationResult(False, "no_user_id_for_rollout", flag_name)

        if _in_rollout(flag_name, str(user_id), rollout):
            return EvaluationResult(True, f"rollout_{rollout}pct", flag_name)
        else:
            return EvaluationResult(False, f"rollout_excluded_{rollout}pct", flag_name)

    return EvaluationResult(True, "enabled", flag_name)


def _evaluate_targeting(
    rules: list[dict[str, Any]],
    context: dict[str, Any],
) -> bool | None:
    """Evaluate targeting rules against context.

    Returns True if matched, False if rules exist but no match, None if no applicable rules.
    """
    if not rules:
        return None

    has_applicable = False

    for rule in rules:
        attribute = rule.get("attribute", "")
        operator = rule.get("operator", "eq")
        values = rule.get("values", [])

        if attribute not in context:
            continue

        has_applicable = True
        user_value = context[attribute]

        if _match_rule(user_value, operator, values):
            return True

    if has_applicable:
        return False
    return None


def _match_rule(user_value: Any, operator: str, values: list[Any]) -> bool:
    """Match a single targeting rule."""
    if operator == "eq":
        return user_value in values
    elif operator == "neq":
        return user_value not in values
    elif operator == "in":
        return user_value in values
    elif operator == "not_in":
        return user_value not in values
    elif operator == "gt":
        return any(user_value > v for v in values)
    elif operator == "gte":
        return any(user_value >= v for v in values)
    elif operator == "lt":
        return any(user_value < v for v in values)
    elif operator == "lte":
        return any(user_value <= v for v in values)
    elif operator == "contains":
        return any(v in str(user_value) for v in values)
    elif operator == "starts_with":
        return any(str(user_value).startswith(str(v)) for v in values)
    elif operator == "ends_with":
        return any(str(user_value).endswith(str(v)) for v in values)
    elif operator == "regex":
        import re
        return any(re.search(str(v), str(user_value)) for v in values)
    else:
        return False


def _in_rollout(flag_name: str, user_id: str, percentage: int) -> bool:
    """Deterministic percentage rollout using consistent hashing.

    The same user_id + flag_name always produces the same result.
    """
    hash_input = f"{flag_name}:{user_id}".encode()
    hash_value = int(hashlib.sha256(hash_input).hexdigest()[:8], 16)
    bucket = hash_value % 100
    return bucket < percentage

"""Python SDK for evaluating feature flags in application code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .evaluator import EvaluationResult, evaluate_flag


class FlagClient:
    """Feature flag client for application code.

    Usage:
        from flag_forge import FlagClient

        flags = FlagClient()  # loads .flags.yml from current directory
        flags = FlagClient("/path/to/.flags.yml")
        flags = FlagClient(environment="production")

        if flags.is_enabled("new_checkout", {"user_id": "123"}):
            # new checkout flow
            pass

        # Get detailed result
        result = flags.evaluate("new_checkout", {"user_id": "123"})
        print(result.enabled, result.reason)
    """

    def __init__(
        self,
        flags_file: str = ".flags.yml",
        environment: str | None = None,
        defaults: dict[str, bool] | None = None,
    ):
        """Initialize the flag client.

        Args:
            flags_file: Path to the flags YAML file.
            environment: Current environment (e.g. "production", "staging").
            defaults: Default values for flags if file is missing.
        """
        self.flags_file = flags_file
        self.environment = environment
        self.defaults = defaults or {}
        self._flags: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load flags from YAML file."""
        path = Path(self.flags_file)
        if path.is_file():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            self._flags = data.get("flags", {})
        else:
            self._flags = {}

    def reload(self) -> None:
        """Reload flags from file (useful for long-running processes)."""
        self._load()

    def is_enabled(
        self,
        flag_name: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Check if a feature flag is enabled.

        Args:
            flag_name: Name of the feature flag.
            context: User/request context for targeting and rollout.

        Returns:
            True if the flag is enabled for the given context.
        """
        result = self.evaluate(flag_name, context)
        return result.enabled

    def evaluate(
        self,
        flag_name: str,
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Evaluate a feature flag with detailed result.

        Args:
            flag_name: Name of the feature flag.
            context: User/request context.

        Returns:
            EvaluationResult with enabled status and reason.
        """
        flag_config = self._flags.get(flag_name)

        if flag_config is None:
            # Check defaults
            if flag_name in self.defaults:
                return EvaluationResult(
                    self.defaults[flag_name],
                    "default",
                    flag_name,
                )
            return EvaluationResult(False, "flag_not_found", flag_name)

        return evaluate_flag(
            flag_name,
            flag_config,
            context=context,
            environment=self.environment,
        )

    def get_all_flags(self, context: dict[str, Any] | None = None) -> dict[str, bool]:
        """Evaluate all flags and return a dict of name -> enabled.

        Useful for sending flag state to frontend.
        """
        result = {}
        for flag_name in self._flags:
            result[flag_name] = self.is_enabled(flag_name, context)
        # Include defaults for flags not in file
        for flag_name, default in self.defaults.items():
            if flag_name not in result:
                result[flag_name] = default
        return result

    def get_flag_names(self) -> list[str]:
        """Get all defined flag names."""
        return list(self._flags.keys())

    @property
    def flag_count(self) -> int:
        """Number of defined flags."""
        return len(self._flags)

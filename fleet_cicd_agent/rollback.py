"""Rollback management for fleet deployments."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .deployment import DeploymentResult, DeploymentTarget, DeploymentStatus


@dataclass
class RollbackEvent:
    """Record of a rollback action."""

    deployment_id: str
    reason: str
    targets_affected: int
    rolled_back_at: float = field(default_factory=time.time)
    previous_versions: Dict[str, str] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None


class RollbackManager:
    """Manages automatic and manual rollbacks for fleet deployments.

    Tracks deployment history and can automatically roll back on failure.
    """

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._history: List[RollbackEvent] = []
        self._deployment_records: Dict[str, DeploymentResult] = {}

    def record_deployment(self, result: DeploymentResult) -> None:
        """Record a deployment result for potential rollback."""
        self._deployment_records[result.deployment_id] = result
        # Trim history if needed
        if len(self._deployment_records) > self.max_history:
            oldest_key = next(iter(self._deployment_records))
            del self._deployment_records[oldest_key]

    def should_rollback(self, result: DeploymentResult) -> bool:
        """Determine if a deployment should be rolled back."""
        if result.status == DeploymentStatus.FAILED:
            return True
        if result.status == DeploymentStatus.COMPLETED:
            # Check if any targets are unhealthy post-deployment
            unhealthy = [t for t in result.targets if not t.healthy]
            return len(unhealthy) > 0
        return False

    def rollback(self, result: DeploymentResult, reason: str = "") -> RollbackEvent:
        """Roll back a deployment to previous versions."""
        if result.deployment_id not in self._deployment_records:
            return RollbackEvent(
                deployment_id=result.deployment_id,
                reason=reason or "Unknown deployment",
                targets_affected=0,
                success=False,
                error=f"No record found for deployment '{result.deployment_id}'",
            )

        errors: List[str] = []
        targets_fixed = 0

        for target in result.targets:
            prev_version = result.previous_versions.get(target.id)
            if prev_version is not None:
                target.current_version = prev_version
                targets_fixed += 1
            else:
                errors.append(f"No previous version for target '{target.id}'")

        event = RollbackEvent(
            deployment_id=result.deployment_id,
            reason=reason or "Automatic rollback",
            targets_affected=targets_fixed,
            previous_versions=dict(result.previous_versions),
            success=len(errors) == 0,
            error="; ".join(errors) if errors else None,
        )

        self._history.append(event)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

        return event

    def rollback_all(self, results: List[DeploymentResult], reason: str = "") -> List[RollbackEvent]:
        """Roll back multiple deployments."""
        events: List[RollbackEvent] = []
        for result in results:
            if self.should_rollback(result):
                event = self.rollback(result, reason)
                events.append(event)
        return events

    @property
    def history(self) -> List[RollbackEvent]:
        """Return rollback history (newest first)."""
        return list(reversed(self._history))

    def get_deployment(self, deployment_id: str) -> Optional[DeploymentResult]:
        """Look up a recorded deployment."""
        return self._deployment_records.get(deployment_id)

    @property
    def rollback_count(self) -> int:
        return len(self._history)

    def clear_history(self) -> None:
        """Clear all history and records."""
        self._history.clear()
        self._deployment_records.clear()

"""Deployment strategies and execution for fleet CI/CD."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class DeploymentStrategy(str, Enum):
    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class DeploymentTarget:
    """A single deployment target (e.g., an agent instance)."""

    id: str
    name: str
    environment: str
    current_version: str = ""
    healthy: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeploymentResult:
    """Result of a deployment operation."""

    deployment_id: str
    strategy: DeploymentStrategy
    status: DeploymentStatus
    targets: List[DeploymentTarget] = field(default_factory=list)
    previous_versions: Dict[str, str] = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float = 0.0
    error: Optional[str] = None
    canary_percentage: int = 0

    @property
    def duration_seconds(self) -> float:
        if self.finished_at and self.started_at:
            return self.finished_at - self.started_at
        return 0.0

    @property
    def succeeded(self) -> bool:
        return self.status == DeploymentStatus.COMPLETED


# Health checker callback type
HealthChecker = Callable[[DeploymentTarget], bool]


class Deployment:
    """Manages deployment of a new version across fleet targets.

    Supports three strategies:
    - Rolling: Update targets one batch at a time
    - Blue-Green: Deploy to an inactive set, then switch traffic
    - Canary: Deploy to a small percentage first, then roll out fully
    """

    def __init__(
        self,
        version: str,
        targets: List[DeploymentTarget],
        strategy: DeploymentStrategy = DeploymentStrategy.ROLLING,
        health_checker: Optional[HealthChecker] = None,
        max_unavailable: int = 1,
        canary_percentage: int = 20,
    ) -> None:
        self.deployment_id = str(uuid.uuid4())[:8]
        self.version = version
        self.targets = targets
        self.strategy = strategy
        self.health_checker = health_checker or self._default_health_check
        self.max_unavailable = max_unavailable
        self.canary_percentage = canary_percentage
        self.status = DeploymentStatus.PENDING
        self._previous_versions: Dict[str, str] = {}

    def _default_health_check(self, target: DeploymentTarget) -> bool:
        """Default health check — just returns target.healthy."""
        return target.healthy

    def _save_previous_versions(self) -> None:
        """Snapshot current versions for rollback."""
        for target in self.targets:
            self._previous_versions[target.id] = target.current_version

    def execute(self) -> DeploymentResult:
        """Run the deployment using the configured strategy."""
        self._save_previous_versions()
        started = time.time()

        try:
            if self.strategy == DeploymentStrategy.ROLLING:
                result = self._rolling_deploy()
            elif self.strategy == DeploymentStrategy.BLUE_GREEN:
                result = self._blue_green_deploy()
            elif self.strategy == DeploymentStrategy.CANARY:
                result = self._canary_deploy()
            else:
                raise ValueError(f"Unknown strategy: {self.strategy}")
        except Exception as exc:
            result = DeploymentResult(
                deployment_id=self.deployment_id,
                strategy=self.strategy,
                status=DeploymentStatus.FAILED,
                targets=self.targets,
                previous_versions=self._previous_versions,
                started_at=started,
                finished_at=time.time(),
                error=str(exc),
            )

        return result

    def _rolling_deploy(self) -> DeploymentResult:
        """Rolling update: update targets in batches."""
        started = time.time()
        batch_size = max(1, self.max_unavailable)

        for i in range(0, len(self.targets), batch_size):
            batch = self.targets[i:i + batch_size]
            for target in batch:
                target.current_version = self.version

            # Health check the batch
            for target in batch:
                if not self.health_checker(target):
                    return DeploymentResult(
                        deployment_id=self.deployment_id,
                        strategy=self.strategy,
                        status=DeploymentStatus.FAILED,
                        targets=self.targets,
                        previous_versions=self._previous_versions,
                        started_at=started,
                        finished_at=time.time(),
                        error=f"Health check failed for target '{target.name}'",
                    )

        self.status = DeploymentStatus.COMPLETED
        return DeploymentResult(
            deployment_id=self.deployment_id,
            strategy=self.strategy,
            status=DeploymentStatus.COMPLETED,
            targets=self.targets,
            previous_versions=self._previous_versions,
            started_at=started,
            finished_at=time.time(),
        )

    def _blue_green_deploy(self) -> DeploymentResult:
        """Blue-green: deploy to all targets, verify health, then complete."""
        started = time.time()

        # Update all targets to new version (in a real system, "green" would be new instances)
        for target in self.targets:
            target.current_version = self.version

        # Verify all targets are healthy
        unhealthy = [
            t.name for t in self.targets if not self.health_checker(t)
        ]
        if unhealthy:
            # Roll back
            for target in self.targets:
                if target.id in self._previous_versions:
                    target.current_version = self._previous_versions[target.id]
            self.status = DeploymentStatus.FAILED
            return DeploymentResult(
                deployment_id=self.deployment_id,
                strategy=self.strategy,
                status=DeploymentStatus.FAILED,
                targets=self.targets,
                previous_versions=self._previous_versions,
                started_at=started,
                finished_at=time.time(),
                error=f"Health check failed for: {', '.join(unhealthy)}",
            )

        self.status = DeploymentStatus.COMPLETED
        return DeploymentResult(
            deployment_id=self.deployment_id,
            strategy=self.strategy,
            status=DeploymentStatus.COMPLETED,
            targets=self.targets,
            previous_versions=self._previous_versions,
            started_at=started,
            finished_at=time.time(),
        )

    def _canary_deploy(self) -> DeploymentResult:
        """Canary: deploy to a subset first, then full rollout."""
        started = time.time()
        total = len(self.targets)
        canary_count = max(1, int(total * self.canary_percentage / 100))
        canary_targets = self.targets[:canary_count]

        # Phase 1: Canary deployment
        for target in canary_targets:
            target.current_version = self.version

        for target in canary_targets:
            if not self.health_checker(target):
                # Roll back canary
                for t in canary_targets:
                    if t.id in self._previous_versions:
                        t.current_version = self._previous_versions[t.id]
                self.status = DeploymentStatus.FAILED
                return DeploymentResult(
                    deployment_id=self.deployment_id,
                    strategy=self.strategy,
                    status=DeploymentStatus.FAILED,
                    targets=self.targets,
                    previous_versions=self._previous_versions,
                    started_at=started,
                    finished_at=time.time(),
                    error=f"Canary health check failed for '{target.name}'",
                    canary_percentage=self.canary_percentage,
                )

        # Phase 2: Full rollout
        remaining = self.targets[canary_count:]
        for target in remaining:
            target.current_version = self.version

        for target in remaining:
            if not self.health_checker(target):
                return DeploymentResult(
                    deployment_id=self.deployment_id,
                    strategy=self.strategy,
                    status=DeploymentStatus.FAILED,
                    targets=self.targets,
                    previous_versions=self._previous_versions,
                    started_at=started,
                    finished_at=time.time(),
                    error=f"Full rollout health check failed for '{target.name}'",
                    canary_percentage=100,
                )

        self.status = DeploymentStatus.COMPLETED
        return DeploymentResult(
            deployment_id=self.deployment_id,
            strategy=self.strategy,
            status=DeploymentStatus.COMPLETED,
            targets=self.targets,
            previous_versions=self._previous_versions,
            started_at=started,
            finished_at=time.time(),
            canary_percentage=100,
        )

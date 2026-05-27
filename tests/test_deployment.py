"""Tests for deployment module."""

import pytest
from fleet_cicd_agent.deployment import (
    Deployment,
    DeploymentResult,
    DeploymentStatus,
    DeploymentStrategy,
    DeploymentTarget,
)


def _make_targets(n: int, healthy: bool = True, version: str = "1.0.0") -> list:
    return [
        DeploymentTarget(
            id=f"target-{i}",
            name=f"target-{i}",
            environment="test",
            current_version=version,
            healthy=healthy,
        )
        for i in range(n)
    ]


class TestDeploymentTarget:
    def test_creation(self):
        t = DeploymentTarget(id="t1", name="target-1", environment="prod")
        assert t.current_version == ""
        assert t.healthy is True


class TestRollingDeployment:
    def test_successful_rolling(self):
        targets = _make_targets(5)
        deploy = Deployment(version="2.0.0", targets=targets, strategy=DeploymentStrategy.ROLLING)
        result = deploy.execute()
        assert result.succeeded
        assert all(t.current_version == "2.0.0" for t in targets)

    def test_rolling_with_failure(self):
        targets = _make_targets(5)
        targets[2].healthy = False
        deploy = Deployment(version="2.0.0", targets=targets, strategy=DeploymentStrategy.ROLLING)
        result = deploy.execute()
        assert result.status == DeploymentStatus.FAILED
        assert "Health check failed" in result.error

    def test_rolling_previous_versions_saved(self):
        targets = _make_targets(3, version="1.0.0")
        deploy = Deployment(version="2.0.0", targets=targets, strategy=DeploymentStrategy.ROLLING)
        result = deploy.execute()
        assert result.previous_versions == {
            "target-0": "1.0.0",
            "target-1": "1.0.0",
            "target-2": "1.0.0",
        }

    def test_rolling_batch_size(self):
        targets = _make_targets(6)
        deploy = Deployment(
            version="2.0.0",
            targets=targets,
            strategy=DeploymentStrategy.ROLLING,
            max_unavailable=2,
        )
        result = deploy.execute()
        assert result.succeeded


class TestBlueGreenDeployment:
    def test_successful_blue_green(self):
        targets = _make_targets(4)
        deploy = Deployment(version="3.0.0", targets=targets, strategy=DeploymentStrategy.BLUE_GREEN)
        result = deploy.execute()
        assert result.succeeded
        assert all(t.current_version == "3.0.0" for t in targets)

    def test_blue_green_rollback_on_failure(self):
        targets = _make_targets(3)
        targets[1].healthy = False
        deploy = Deployment(version="3.0.0", targets=targets, strategy=DeploymentStrategy.BLUE_GREEN)
        result = deploy.execute()
        assert result.status == DeploymentStatus.FAILED
        # Should have rolled back
        assert all(t.current_version == "1.0.0" for t in targets)


class TestCanaryDeployment:
    def test_successful_canary(self):
        targets = _make_targets(10)
        deploy = Deployment(
            version="4.0.0",
            targets=targets,
            strategy=DeploymentStrategy.CANARY,
            canary_percentage=20,
        )
        result = deploy.execute()
        assert result.succeeded
        assert all(t.current_version == "4.0.0" for t in targets)

    def test_canary_failure_stops_rollout(self):
        targets = _make_targets(10)
        targets[0].healthy = False  # First target is in canary set
        deploy = Deployment(
            version="4.0.0",
            targets=targets,
            strategy=DeploymentStrategy.CANARY,
            canary_percentage=20,
        )
        result = deploy.execute()
        assert result.status == DeploymentStatus.FAILED
        assert "Canary" in result.error
        # Canary targets should be rolled back
        assert targets[0].current_version == "1.0.0"

    def test_canary_percentage_single_target(self):
        targets = _make_targets(1)
        deploy = Deployment(
            version="4.0.0",
            targets=targets,
            strategy=DeploymentStrategy.CANARY,
            canary_percentage=10,
        )
        result = deploy.execute()
        assert result.succeeded


class TestDeploymentResult:
    def test_duration(self):
        result = DeploymentResult(
            deployment_id="test",
            strategy=DeploymentStrategy.ROLLING,
            status=DeploymentStatus.COMPLETED,
            started_at=100.0,
            finished_at=105.5,
        )
        assert result.duration_seconds == pytest.approx(5.5)

    def test_succeeded_property(self):
        result = DeploymentResult(
            deployment_id="test",
            strategy=DeploymentStrategy.ROLLING,
            status=DeploymentStatus.COMPLETED,
        )
        assert result.succeeded

    def test_not_succeeded_when_failed(self):
        result = DeploymentResult(
            deployment_id="test",
            strategy=DeploymentStrategy.ROLLING,
            status=DeploymentStatus.FAILED,
        )
        assert not result.succeeded

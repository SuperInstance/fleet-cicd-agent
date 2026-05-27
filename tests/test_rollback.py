"""Tests for rollback module."""

import pytest
from fleet_cicd_agent.rollback import RollbackManager, RollbackEvent
from fleet_cicd_agent.deployment import (
    Deployment,
    DeploymentResult,
    DeploymentStatus,
    DeploymentStrategy,
    DeploymentTarget,
)


def _make_deployment_result(
    status: DeploymentStatus = DeploymentStatus.COMPLETED,
    n_targets: int = 3,
    healthy: bool = True,
    version: str = "2.0.0",
) -> DeploymentResult:
    targets = [
        DeploymentTarget(
            id=f"t-{i}",
            name=f"t-{i}",
            environment="test",
            current_version=version if status == DeploymentStatus.COMPLETED else "1.0.0",
            healthy=healthy,
        )
        for i in range(n_targets)
    ]
    return DeploymentResult(
        deployment_id="test-123",
        strategy=DeploymentStrategy.ROLLING,
        status=status,
        targets=targets,
        previous_versions={f"t-{i}": "1.0.0" for i in range(n_targets)},
    )


class TestRollbackManager:
    def test_record_deployment(self):
        mgr = RollbackManager()
        result = _make_deployment_result()
        mgr.record_deployment(result)
        assert mgr.get_deployment("test-123") is result

    def test_should_rollback_on_failure(self):
        mgr = RollbackManager()
        result = _make_deployment_result(status=DeploymentStatus.FAILED)
        assert mgr.should_rollback(result) is True

    def test_should_rollback_on_unhealthy(self):
        mgr = RollbackManager()
        result = _make_deployment_result(healthy=False)
        assert mgr.should_rollback(result) is True

    def test_should_not_rollback_healthy(self):
        mgr = RollbackManager()
        result = _make_deployment_result(healthy=True)
        assert mgr.should_rollback(result) is False

    def test_rollback_restores_versions(self):
        mgr = RollbackManager()
        result = _make_deployment_result()
        mgr.record_deployment(result)
        event = mgr.rollback(result, reason="test rollback")
        assert event.success
        assert event.targets_affected == 3
        assert all(t.current_version == "1.0.0" for t in result.targets)

    def test_rollback_unknown_deployment(self):
        mgr = RollbackManager()
        result = _make_deployment_result()
        event = mgr.rollback(result, reason="unknown")
        assert not event.success
        assert "No record" in event.error

    def test_rollback_history(self):
        mgr = RollbackManager()
        r1 = _make_deployment_result()
        r1.deployment_id = "r1"
        r2 = _make_deployment_result()
        r2.deployment_id = "r2"
        mgr.record_deployment(r1)
        mgr.record_deployment(r2)
        mgr.rollback(r1, reason="first")
        mgr.rollback(r2, reason="second")
        assert mgr.rollback_count == 2
        # Newest first
        assert mgr.history[0].deployment_id == "r2"

    def test_rollback_all(self):
        mgr = RollbackManager()
        good = _make_deployment_result(healthy=True)
        good.deployment_id = "good"
        bad = _make_deployment_result(status=DeploymentStatus.FAILED)
        bad.deployment_id = "bad"
        mgr.record_deployment(good)
        mgr.record_deployment(bad)
        events = mgr.rollback_all([good, bad], reason="batch")
        assert len(events) == 1
        assert events[0].deployment_id == "bad"

    def test_clear_history(self):
        mgr = RollbackManager()
        result = _make_deployment_result()
        mgr.record_deployment(result)
        mgr.rollback(result)
        mgr.clear_history()
        assert mgr.rollback_count == 0
        assert mgr.get_deployment("test-123") is None

    def test_max_history_trim(self):
        mgr = RollbackManager(max_history=2)
        for i in range(5):
            r = _make_deployment_result()
            r.deployment_id = f"r-{i}"
            mgr.record_deployment(r)
        # Only 2 records should remain
        assert len(mgr._deployment_records) <= 2

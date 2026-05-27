"""Tests for CICDAgent orchestrator."""

import pytest
from fleet_cicd_agent.agent import CICDAgent, AgentRunResult
from fleet_cicd_agent.config import FleetConfig, EnvironmentConfig
from fleet_cicd_agent.deployment import DeploymentStrategy, DeploymentTarget
from fleet_cicd_agent.pipeline import Pipeline, PipelineStage, StageResult, StageStatus
from fleet_cicd_agent.rollback import RollbackManager


def _make_agent() -> CICDAgent:
    config = FleetConfig(
        name="test-fleet",
        environments={
            "dev": EnvironmentConfig(name="dev", replicas=1, auto_rollback=False),
            "staging": EnvironmentConfig(name="staging", replicas=3, auto_rollback=True),
            "prod": EnvironmentConfig(
                name="prod", replicas=5, auto_rollback=True, approval_required=True
            ),
        },
    )
    return CICDAgent(config=config)


def _make_targets(n: int = 3, healthy: bool = True) -> list:
    return [
        DeploymentTarget(
            id=f"t-{i}",
            name=f"t-{i}",
            environment="staging",
            current_version="1.0.0",
            healthy=healthy,
        )
        for i in range(n)
    ]


class TestCICDAgent:
    def test_simple_deploy(self):
        agent = _make_agent()
        result = agent.deploy(
            version="2.0.0",
            environment="staging",
            targets=_make_targets(),
            strategy=DeploymentStrategy.ROLLING,
        )
        assert result.succeeded
        assert result.deployment_result is not None
        assert result.deployment_result.succeeded

    def test_deploy_with_pipeline(self):
        agent = _make_agent()
        pipeline = Pipeline("test-pipeline")
        pipeline.add_stage(PipelineStage(
            name="build",
            executor=lambda ctx: StageResult(name="build", status=StageStatus.SUCCESS),
        ))
        pipeline.add_stage(PipelineStage(
            name="deploy-stage",
            executor=lambda ctx: StageResult(name="deploy-stage", status=StageStatus.SUCCESS),
            depends_on=["build"],
        ))

        result = agent.deploy(
            version="2.0.0",
            environment="staging",
            targets=_make_targets(),
            pipeline=pipeline,
        )
        assert result.succeeded
        assert result.pipeline_result.succeeded

    def test_deploy_pipeline_failure_aborts(self):
        agent = _make_agent()
        pipeline = Pipeline("failing-pipeline")
        pipeline.add_stage(PipelineStage(
            name="build",
            executor=lambda ctx: StageResult(
                name="build", status=StageStatus.FAILED, error="build broke"
            ),
        ))
        result = agent.deploy(
            version="2.0.0",
            environment="staging",
            targets=_make_targets(),
            pipeline=pipeline,
        )
        assert not result.succeeded
        assert result.deployment_result is None  # never ran

    def test_deploy_with_auto_rollback(self):
        agent = _make_agent()
        targets = _make_targets(healthy=False)
        result = agent.deploy(
            version="2.0.0",
            environment="staging",  # auto_rollback=True
            targets=targets,
        )
        assert result.rollback_event is not None
        assert result.rollback_event.success

    def test_deploy_without_auto_rollback(self):
        agent = _make_agent()
        targets = _make_targets(healthy=False)
        result = agent.deploy(
            version="2.0.0",
            environment="dev",  # auto_rollback=False
            targets=targets,
        )
        assert result.rollback_event is None

    def test_canary_deploy(self):
        agent = _make_agent()
        result = agent.deploy(
            version="3.0.0",
            environment="staging",
            targets=_make_targets(10),
            strategy=DeploymentStrategy.CANARY,
            canary_percentage=30,
        )
        assert result.succeeded

    def test_get_status(self):
        agent = _make_agent()
        result = agent.deploy(
            version="2.0.0",
            environment="staging",
            targets=_make_targets(),
        )
        status = agent.get_status(result)
        assert "2.0.0" in status
        assert "staging" in status

    def test_default_pipeline(self):
        agent = _make_agent()
        pipeline = agent.create_default_pipeline("2.0.0")
        assert len(pipeline.stage_names) == 3
        result = pipeline.run({"version": "2.0.0", "environment": "dev"})
        assert result.succeeded

    def test_result_duration(self):
        agent = _make_agent()
        result = agent.deploy(
            version="2.0.0",
            environment="staging",
            targets=_make_targets(),
        )
        assert result.duration_seconds >= 0

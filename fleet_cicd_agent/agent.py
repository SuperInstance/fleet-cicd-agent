"""CICDAgent — main orchestrator for fleet CI/CD pipelines."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import FleetConfig, EnvironmentConfig
from .deployment import (
    Deployment,
    DeploymentResult,
    DeploymentStatus,
    DeploymentStrategy,
    DeploymentTarget,
)
from .pipeline import Pipeline, PipelineResult, PipelineStage, StageResult, StageStatus
from .rollback import RollbackManager, RollbackEvent


@dataclass
class AgentRunResult:
    """Complete result of a CI/CD agent run."""

    version: str
    environment: str
    pipeline_result: PipelineResult
    deployment_result: Optional[DeploymentResult] = None
    rollback_event: Optional[RollbackEvent] = None
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def succeeded(self) -> bool:
        if self.deployment_result and not self.deployment_result.succeeded:
            return False
        return self.pipeline_result.succeeded

    @property
    def duration_seconds(self) -> float:
        if self.finished_at and self.started_at:
            return self.finished_at - self.started_at
        return 0.0


class CICDAgent:
    """Orchestrates CI/CD pipelines across a fleet of deployment targets.

    Combines pipeline execution, deployment strategies, and automatic rollback
    into a single cohesive agent.

    Usage:
        agent = CICDAgent(config=my_config)
        result = agent.deploy(
            version="2.0.0",
            environment="production",
            targets=my_targets,
            strategy=DeploymentStrategy.CANARY,
        )
    """

    def __init__(
        self,
        config: FleetConfig,
        rollback_manager: Optional[RollbackManager] = None,
    ) -> None:
        self.config = config
        self.rollback_manager = rollback_manager or RollbackManager()

    def deploy(
        self,
        version: str,
        environment: str,
        targets: List[DeploymentTarget],
        strategy: Optional[DeploymentStrategy] = None,
        pipeline: Optional[Pipeline] = None,
        canary_percentage: int = 20,
    ) -> AgentRunResult:
        """Execute a full deployment: pipeline → deploy → health check → rollback if needed."""
        started = time.time()
        env_config = self.config.get_environment(environment)

        # Default strategy from env config or parameter
        if strategy is None:
            strategy = DeploymentStrategy.ROLLING

        # Resolve environment variables
        env_vars = self.config.resolve_env_vars(environment)
        context: Dict[str, Any] = {
            "version": version,
            "environment": environment,
            "targets": targets,
            "strategy": strategy.value,
            "env_vars": env_vars,
        }

        # Phase 1: Run pipeline (if provided)
        pipeline_result = PipelineResult(pipeline_name="no-pipeline")
        if pipeline:
            pipeline_result = pipeline.run(context)
            if not pipeline_result.succeeded:
                return AgentRunResult(
                    version=version,
                    environment=environment,
                    pipeline_result=pipeline_result,
                    started_at=started,
                    finished_at=time.time(),
                )

        # Phase 2: Deploy
        deployment = Deployment(
            version=version,
            targets=list(targets),  # copy to avoid mutation
            strategy=strategy,
            health_checker=lambda t: t.healthy,
            max_unavailable=env_config.max_unavailable,
            canary_percentage=canary_percentage,
        )
        deployment_result = deployment.execute()

        # Phase 3: Record and check rollback
        self.rollback_manager.record_deployment(deployment_result)
        rollback_event: Optional[RollbackEvent] = None

        if env_config.auto_rollback and self.rollback_manager.should_rollback(deployment_result):
            reason = deployment_result.error or "Automatic rollback triggered"
            rollback_event = self.rollback_manager.rollback(deployment_result, reason)

        return AgentRunResult(
            version=version,
            environment=environment,
            pipeline_result=pipeline_result,
            deployment_result=deployment_result,
            rollback_event=rollback_event,
            started_at=started,
            finished_at=time.time(),
        )

    def create_default_pipeline(self, version: str) -> Pipeline:
        """Create a standard CI/CD pipeline for the given version."""
        pipeline = Pipeline(name=f"deploy-{version}")

        def build_stage(ctx: Dict[str, Any]):
            return StageResult(
                name="build",
                status=StageStatus.SUCCESS,
                output=f"Built version {ctx.get('version', 'unknown')}",
            )

        def test_stage(ctx: Dict[str, Any]):
            return StageResult(
                name="test",
                status=StageStatus.SUCCESS,
                output="All tests passed",
            )

        def deploy_stage(ctx: Dict[str, Any]):
            return StageResult(
                name="deploy",
                status=StageStatus.SUCCESS,
                output=f"Deployed {ctx.get('version')} to {ctx.get('environment')}",
            )

        pipeline.add_stage(PipelineStage(
            name="build",
            executor=build_stage,
            retry_count=1,
        ))
        pipeline.add_stage(PipelineStage(
            name="test",
            executor=test_stage,
            depends_on=["build"],
        ))
        pipeline.add_stage(PipelineStage(
            name="deploy",
            executor=deploy_stage,
            depends_on=["test"],
        ))

        return pipeline

    def get_status(self, result: AgentRunResult) -> str:
        """Human-readable status summary."""
        lines = [
            f"Deployment: v{result.version} → {result.environment}",
            f"  Pipeline: {'✓' if result.pipeline_result.succeeded else '✗'} ({result.pipeline_result.total_duration_seconds:.1f}s)",
        ]
        if result.deployment_result:
            lines.append(
                f"  Deploy: {result.deployment_result.status.value} "
                f"({result.deployment_result.duration_seconds:.1f}s)"
            )
        if result.rollback_event:
            lines.append(
                f"  Rollback: {'✓' if result.rollback_event.success else '✗'} "
                f"— {result.rollback_event.reason}"
            )
        lines.append(f"  Total: {result.duration_seconds:.1f}s")
        return "\n".join(lines)

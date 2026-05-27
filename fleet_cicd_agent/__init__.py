"""Fleet CI/CD Agent — automating deployments across agent fleets."""

__version__ = "0.1.0"

from .agent import CICDAgent
from .pipeline import Pipeline, PipelineStage, StageResult
from .deployment import Deployment, DeploymentStrategy
from .rollback import RollbackManager
from .config import FleetConfig, EnvironmentConfig

__all__ = [
    "CICDAgent",
    "Deployment",
    "DeploymentStrategy",
    "FleetConfig",
    "EnvironmentConfig",
    "Pipeline",
    "PipelineStage",
    "RollbackManager",
    "StageResult",
]

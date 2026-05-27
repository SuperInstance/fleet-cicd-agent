"""Configuration for fleet CI/CD agent."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class EnvironmentConfig:
    """Per-environment configuration."""

    name: str
    replicas: int = 1
    max_unavailable: int = 1
    health_check_url: str = ""
    health_check_timeout_seconds: int = 30
    auto_rollback: bool = True
    approval_required: bool = False
    resource_limits: Dict[str, str] = field(default_factory=dict)
    env_vars: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_unavailable > self.replicas:
            self.max_unavailable = self.replicas


@dataclass
class FleetConfig:
    """Top-level fleet configuration."""

    name: str = "default-fleet"
    environments: Dict[str, EnvironmentConfig] = field(default_factory=dict)
    global_env_vars: Dict[str, str] = field(default_factory=dict)
    max_parallel_deployments: int = 5
    deployment_timeout_seconds: int = 600
    rollback_window_seconds: int = 300
    notification_webhooks: List[str] = field(default_factory=list)

    def get_environment(self, env: str) -> EnvironmentConfig:
        """Get configuration for a specific environment."""
        if env not in self.environments:
            raise KeyError(f"Environment '{env}' not found in fleet config")
        return self.environments[env]

    def add_environment(self, config: EnvironmentConfig) -> None:
        """Add or update an environment configuration."""
        self.environments[config.name] = config

    def resolve_env_vars(self, env_name: str) -> Dict[str, str]:
        """Merge global env vars with environment-specific ones (env overrides global)."""
        merged = copy.deepcopy(self.global_env_vars)
        env_config = self.get_environment(env_name)
        merged.update(env_config.env_vars)
        return merged

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FleetConfig:
        """Create a FleetConfig from a dictionary."""
        envs: Dict[str, EnvironmentConfig] = {}
        for env_data in data.get("environments", []):
            env_config = EnvironmentConfig(**env_data)
            envs[env_config.name] = env_config
        return cls(
            name=data.get("name", "default-fleet"),
            environments=envs,
            global_env_vars=data.get("global_env_vars", {}),
            max_parallel_deployments=data.get("max_parallel_deployments", 5),
            deployment_timeout_seconds=data.get("deployment_timeout_seconds", 600),
            rollback_window_seconds=data.get("rollback_window_seconds", 300),
            notification_webhooks=data.get("notification_webhooks", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "environments": [
                {
                    "name": e.name,
                    "replicas": e.replicas,
                    "max_unavailable": e.max_unavailable,
                    "health_check_url": e.health_check_url,
                    "health_check_timeout_seconds": e.health_check_timeout_seconds,
                    "auto_rollback": e.auto_rollback,
                    "approval_required": e.approval_required,
                    "resource_limits": e.resource_limits,
                    "env_vars": e.env_vars,
                }
                for e in self.environments.values()
            ],
            "global_env_vars": self.global_env_vars,
            "max_parallel_deployments": self.max_parallel_deployments,
            "deployment_timeout_seconds": self.deployment_timeout_seconds,
            "rollback_window_seconds": self.rollback_window_seconds,
            "notification_webhooks": self.notification_webhooks,
        }

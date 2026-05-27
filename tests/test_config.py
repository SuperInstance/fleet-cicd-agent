"""Tests for config module."""

import pytest
from fleet_cicd_agent.config import FleetConfig, EnvironmentConfig, Environment


class TestEnvironmentConfig:
    def test_basic_creation(self):
        env = EnvironmentConfig(name="staging", replicas=3)
        assert env.name == "staging"
        assert env.replicas == 3

    def test_max_unavailable_capped(self):
        env = EnvironmentConfig(name="test", replicas=2, max_unavailable=5)
        assert env.max_unavailable == 2

    def test_defaults(self):
        env = EnvironmentConfig(name="dev")
        assert env.replicas == 1
        assert env.auto_rollback is True
        assert env.approval_required is False


class TestFleetConfig:
    def _make_config(self) -> FleetConfig:
        return FleetConfig(
            name="test-fleet",
            environments={
                "dev": EnvironmentConfig(name="dev", replicas=1),
                "staging": EnvironmentConfig(name="staging", replicas=3),
                "prod": EnvironmentConfig(
                    name="prod", replicas=10, auto_rollback=True, approval_required=True
                ),
            },
            global_env_vars={"LOG_LEVEL": "info"},
        )

    def test_get_environment(self):
        config = self._make_config()
        env = config.get_environment("staging")
        assert env.replicas == 3

    def test_get_missing_environment(self):
        config = self._make_config()
        with pytest.raises(KeyError, match="not found"):
            config.get_environment("nonexistent")

    def test_add_environment(self):
        config = self._make_config()
        config.add_environment(EnvironmentConfig(name="qa", replicas=2))
        assert config.get_environment("qa").replicas == 2

    def test_resolve_env_vars_merge(self):
        config = self._make_config()
        config.environments["staging"].env_vars = {"LOG_LEVEL": "debug", "APP_NAME": "test"}
        resolved = config.resolve_env_vars("staging")
        assert resolved["LOG_LEVEL"] == "debug"  # overridden
        assert resolved["APP_NAME"] == "test"

    def test_from_dict(self):
        data = {
            "name": "dict-fleet",
            "environments": [
                {"name": "dev", "replicas": 2},
                {"name": "prod", "replicas": 10},
            ],
            "global_env_vars": {"KEY": "value"},
        }
        config = FleetConfig.from_dict(data)
        assert config.name == "dict-fleet"
        assert len(config.environments) == 2
        assert config.get_environment("prod").replicas == 10

    def test_to_dict_roundtrip(self):
        config = self._make_config()
        data = config.to_dict()
        config2 = FleetConfig.from_dict(data)
        assert config2.name == config.name
        assert set(config2.environments.keys()) == set(config.environments.keys())

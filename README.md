# Fleet CI/CD Agent

Automating deployments across agent fleets with multiple strategies, pipeline orchestration, and automatic rollback.

## Features

- **Pipeline Orchestration** — Sequential and parallel stage execution with dependency resolution
- **Deployment Strategies** — Rolling, blue-green, and canary deployments
- **Automatic Rollback** — Failure detection and version rollback
- **Environment Config** — Per-environment settings with variable resolution
- **Zero External Dependencies** — Pure Python with dataclasses and type hints

## Quick Start

```python
from fleet_cicd_agent import CICDAgent, FleetConfig, EnvironmentConfig, DeploymentTarget, DeploymentStrategy

config = FleetConfig(
    name="my-fleet",
    environments={
        "staging": EnvironmentConfig(name="staging", replicas=3, auto_rollback=True),
        "production": EnvironmentConfig(name="production", replicas=10, auto_rollback=True, approval_required=True),
    },
)

agent = CICDAgent(config=config)

targets = [
    DeploymentTarget(id="agent-1", name="agent-1", environment="staging", current_version="1.0.0"),
    DeploymentTarget(id="agent-2", name="agent-2", environment="staging", current_version="1.0.0"),
]

result = agent.deploy(
    version="2.0.0",
    environment="staging",
    targets=targets,
    strategy=DeploymentStrategy.CANARY,
    canary_percentage=30,
)

print(agent.get_status(result))
```

## Project Structure

```
fleet_cicd_agent/
├── __init__.py        # Package exports
├── agent.py           # CICDAgent orchestrator
├── pipeline.py        # Pipeline with stages, parallel execution
├── deployment.py      # Deployment strategies (rolling, blue-green, canary)
├── rollback.py        # Rollback manager with automatic failure detection
└── config.py          # Fleet and environment configuration
tests/
├── test_agent.py
├── test_pipeline.py
├── test_deployment.py
├── test_rollback.py
└── test_config.py
```

## Running Tests

```bash
python3 -m pytest tests/ -q
```

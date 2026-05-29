# fleet-cicd-agent

Automated CI/CD for agent fleets — pipeline orchestration, deployment strategies (rolling/blue-green/canary), automatic rollback on failure, and per-environment configuration.

## What This Gives You

- **Pipeline orchestration** — Sequential and parallel stage execution with dependency resolution
- **3 deployment strategies** — Rolling update, blue-green, and canary deployment
- **Automatic rollback** — Detect failure and revert to last-known-good version
- **Per-environment config** — Staging, production, and custom environments with variable resolution
- **Zero external dependencies** — Pure Python with dataclasses and type hints

## Quick Start

```python
from fleet_cicd_agent import (
    CICDAgent, FleetConfig, EnvironmentConfig,
    DeploymentTarget, DeploymentStrategy,
)

config = FleetConfig(
    name="my-fleet",
    environments={
        "staging": EnvironmentConfig(
            name="staging", replicas=3, auto_rollback=True,
        ),
        "production": EnvironmentConfig(
            name="production", replicas=10,
            auto_rollback=True, approval_required=True,
        ),
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

## API Reference

### `CICDAgent`

| Method | Description |
|--------|-------------|
| `CICDAgent(config)` | Create agent with fleet configuration |
| `deploy(version, env, targets, strategy)` | Deploy version to targets |
| `rollback(env, targets)` | Rollback to previous version |
| `get_status(deployment)` | Current deployment status |

### `DeploymentStrategy`

| Value | Description |
|-------|-------------|
| `ROLLING` | Update targets one at a time |
| `BLUE_GREEN` | Deploy to new set, switch traffic |
| `CANARY` | Deploy to percentage, then roll out |

### `EnvironmentConfig`

| Field | Description |
|-------|-------------|
| `name` | Environment name |
| `replicas` | Number of target instances |
| `auto_rollback` | Automatically rollback on failure |
| `approval_required` | Require manual approval before deploy |

## How It Fits
- [OpenConstruct Documentation](https://github.com/SuperInstance/openconstruct-docs) — ecosystem-wide docs and guides

- **[cocapn-health-rs](https://github.com/SuperInstance/cocapn-health-rs)** — Health checks trigger rollback when post-deploy checks fail
- **[co-captain-git-agent](https://github.com/SuperInstance/co-captain-git-agent)** — Human liaison dispatches CI/CD tasks via fleet protocol
- **[commit-predictor](https://github.com/SuperInstance/commit-predictor)** — Schedule deployments around predicted low-activity windows
- **[ccc-os](https://github.com/SuperInstance/ccc-os)** — Fleet monitoring includes deployment status

## Testing

57 tests covering pipeline execution, all three deployment strategies, rollback behavior, environment config, and edge cases.

```bash
pip install -e ".[dev]"
pytest
```

## Installation

```bash
pip install fleet-cicd-agent
```

Or from source:

```bash
git clone https://github.com/SuperInstance/fleet-cicd-agent.git
cd fleet-cicd-agent
pip install -e .
```

Requires Python 3.11+.

## License

MIT

Part of the [SuperInstance OpenConstruct](https://github.com/SuperInstance) ecosystem.

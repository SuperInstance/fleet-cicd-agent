"""Pipeline orchestration for CI/CD stages."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Any


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result of a single pipeline stage execution."""

    name: str
    status: StageStatus
    started_at: float = 0.0
    finished_at: float = 0.0
    output: str = ""
    error: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        if self.finished_at and self.started_at:
            return self.finished_at - self.started_at
        return 0.0

    @property
    def succeeded(self) -> bool:
        return self.status == StageStatus.SUCCESS


# Type for stage execution functions
StageExecutor = Callable[[Dict[str, Any]], StageResult]


@dataclass
class PipelineStage:
    """A single stage in a deployment pipeline."""

    name: str
    executor: Optional[StageExecutor] = None
    depends_on: List[str] = field(default_factory=list)
    retry_count: int = 0
    timeout_seconds: int = 300
    continue_on_failure: bool = False
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute this stage."""
        if self.condition and not self.condition(context):
            return StageResult(
                name=self.name,
                status=StageStatus.SKIPPED,
                started_at=time.time(),
                finished_at=time.time(),
                output="Skipped due to condition",
            )

        if self.executor is None:
            return StageResult(
                name=self.name,
                status=StageStatus.SUCCESS,
                started_at=time.time(),
                finished_at=time.time(),
                output="No executor defined — auto-pass",
            )

        attempts = self.retry_count + 1
        last_error: Optional[str] = None

        for attempt in range(attempts):
            started = time.time()
            try:
                result = self.executor(context)
                result.started_at = started
                result.finished_at = time.time()
                result.name = self.name
                if result.succeeded:
                    return result
                last_error = result.error
            except Exception as exc:
                last_error = str(exc)

        return StageResult(
            name=self.name,
            status=StageStatus.FAILED,
            started_at=started,
            finished_at=time.time(),
            error=last_error,
        )


@dataclass
class PipelineResult:
    """Aggregate result of a pipeline execution."""

    pipeline_name: str
    results: List[StageResult] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def succeeded(self) -> bool:
        return all(
            r.succeeded or r.status == StageStatus.SKIPPED
            for r in self.results
        )

    @property
    def failed_stages(self) -> List[StageResult]:
        return [r for r in self.results if r.status == StageStatus.FAILED]

    @property
    def total_duration_seconds(self) -> float:
        if self.finished_at and self.started_at:
            return self.finished_at - self.started_at
        return 0.0


class Pipeline:
    """Orchestrates execution of deployment pipeline stages.

    Supports:
    - Sequential execution by default
    - Parallel execution of independent stages
    - Dependency resolution between stages
    - Retry logic per stage
    - Conditional stage execution
    """

    def __init__(self, name: str, stages: Optional[List[PipelineStage]] = None) -> None:
        self.name = name
        self.stages: Dict[str, PipelineStage] = {}
        self._execution_order: List[str] = []
        if stages:
            for stage in stages:
                self.add_stage(stage)

    def add_stage(self, stage: PipelineStage) -> Pipeline:
        """Add a stage to the pipeline. Returns self for chaining."""
        self.stages[stage.name] = stage
        return self

    def _resolve_execution_order(self) -> List[str]:
        """Topologically sort stages respecting depends_on."""
        visited: set[str] = set()
        order: List[str] = []
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise ValueError(f"Circular dependency detected involving '{name}'")
            visiting.add(name)
            stage = self.stages[name]
            for dep in stage.depends_on:
                if dep not in self.stages:
                    raise ValueError(
                        f"Stage '{name}' depends on unknown stage '{dep}'"
                    )
                visit(dep)
            visiting.discard(name)
            visited.add(name)
            order.append(name)

        for name in self.stages:
            visit(name)
        return order

    def _find_parallel_groups(self, order: List[str]) -> List[List[str]]:
        """Group stages that can run in parallel based on dependency levels."""
        levels: Dict[str, int] = {}
        for name in order:
            stage = self.stages[name]
            if not stage.depends_on:
                levels[name] = 0
            else:
                levels[name] = max(levels[dep] for dep in stage.depends_on) + 1

        groups: Dict[int, List[str]] = {}
        for name, level in levels.items():
            groups.setdefault(level, []).append(name)

        return [groups[i] for i in sorted(groups)]

    def run(self, context: Optional[Dict[str, Any]] = None) -> PipelineResult:
        """Execute the pipeline sequentially (safe default)."""
        if context is None:
            context = {}

        order = self._resolve_execution_order()
        result = PipelineResult(
            pipeline_name=self.name,
            started_at=time.time(),
        )

        for stage_name in order:
            stage = self.stages[stage_name]
            stage_result = stage.execute(context)
            result.results.append(stage_result)
            context[f"stage_result.{stage_name}"] = stage_result

            if stage_result.status == StageStatus.FAILED and not stage.continue_on_failure:
                # Skip remaining stages
                for remaining_name in order[order.index(stage_name) + 1:]:
                    result.results.append(StageResult(
                        name=remaining_name,
                        status=StageStatus.SKIPPED,
                        output="Skipped due to previous failure",
                    ))
                break

        result.finished_at = time.time()
        return result

    def run_parallel(self, context: Optional[Dict[str, Any]] = None) -> PipelineResult:
        """Execute the pipeline with independent stages running concurrently (simulated)."""
        if context is None:
            context = {}

        order = self._resolve_execution_order()
        groups = self._find_parallel_groups(order)

        result = PipelineResult(
            pipeline_name=self.name,
            started_at=time.time(),
        )

        for group in groups:
            group_results: List[StageResult] = []
            any_failed = False

            for stage_name in group:
                stage = self.stages[stage_name]
                stage_result = stage.execute(context)
                group_results.append(stage_result)
                context[f"stage_result.{stage_name}"] = stage_result

                if stage_result.status == StageStatus.FAILED:
                    any_failed = True

            result.results.extend(group_results)

            if any_failed:
                # Find remaining stages not yet executed
                executed = {r.name for r in result.results}
                for remaining_name in order:
                    if remaining_name not in executed:
                        result.results.append(StageResult(
                            name=remaining_name,
                            status=StageStatus.SKIPPED,
                            output="Skipped due to failure in parallel group",
                        ))
                break

        result.finished_at = time.time()
        return result

    def get_stage(self, name: str) -> PipelineStage:
        """Retrieve a stage by name."""
        if name not in self.stages:
            raise KeyError(f"Stage '{name}' not found")
        return self.stages[name]

    @property
    def stage_names(self) -> List[str]:
        return list(self.stages.keys())

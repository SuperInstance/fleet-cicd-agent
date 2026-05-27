"""Tests for pipeline module."""

import pytest
from fleet_cicd_agent.pipeline import (
    Pipeline,
    PipelineStage,
    PipelineResult,
    StageResult,
    StageStatus,
)


def _success_executor(name: str = "stage") -> object:
    """Create a simple success executor."""
    def executor(ctx):
        return StageResult(name=name, status=StageStatus.SUCCESS, output="ok")
    return executor


def _fail_executor(name: str = "stage", error: str = "boom") -> object:
    def executor(ctx):
        return StageResult(name=name, status=StageStatus.FAILED, error=error)
    return executor


class TestPipelineStage:
    def test_execute_with_executor(self):
        stage = PipelineStage(name="build", executor=_success_executor("build"))
        result = stage.execute({})
        assert result.succeeded
        assert result.name == "build"

    def test_execute_without_executor(self):
        stage = PipelineStage(name="noop")
        result = stage.execute({})
        assert result.succeeded
        assert "auto-pass" in result.output

    def test_conditional_skip(self):
        stage = PipelineStage(
            name="prod-only",
            executor=_success_executor("prod-only"),
            condition=lambda ctx: ctx.get("environment") == "production",
        )
        result = stage.execute({"environment": "staging"})
        assert result.status == StageStatus.SKIPPED

    def test_retry_on_failure(self):
        call_count = {"n": 0}

        def flaky(ctx):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return StageResult(name="flaky", status=StageStatus.FAILED, error="not yet")
            return StageResult(name="flaky", status=StageStatus.SUCCESS)

        stage = PipelineStage(name="flaky", executor=flaky, retry_count=3)
        result = stage.execute({})
        assert result.succeeded
        assert call_count["n"] == 3

    def test_retry_exhausted(self):
        stage = PipelineStage(
            name="always-fail",
            executor=_fail_executor("always-fail"),
            retry_count=2,
        )
        result = stage.execute({})
        assert result.status == StageStatus.FAILED

    def test_exception_in_executor(self):
        def bad(ctx):
            raise RuntimeError("crash")

        stage = PipelineStage(name="bad", executor=bad)
        result = stage.execute({})
        assert result.status == StageStatus.FAILED
        assert "crash" in result.error


class TestPipeline:
    def test_simple_sequential(self):
        pipeline = Pipeline("test")
        pipeline.add_stage(PipelineStage(name="a", executor=_success_executor("a")))
        pipeline.add_stage(PipelineStage(name="b", executor=_success_executor("b")))
        result = pipeline.run()
        assert result.succeeded
        assert len(result.results) == 2

    def test_dependency_ordering(self):
        order = []

        def track(name):
            def executor(ctx):
                order.append(name)
                return StageResult(name=name, status=StageStatus.SUCCESS)
            return executor

        pipeline = Pipeline("dep-test")
        pipeline.add_stage(PipelineStage(name="deploy", executor=track("deploy"), depends_on=["test"]))
        pipeline.add_stage(PipelineStage(name="test", executor=track("test"), depends_on=["build"]))
        pipeline.add_stage(PipelineStage(name="build", executor=track("build")))
        result = pipeline.run()
        assert result.succeeded
        assert order == ["build", "test", "deploy"]

    def test_circular_dependency(self):
        pipeline = Pipeline("circular")
        pipeline.add_stage(PipelineStage(name="a", depends_on=["b"]))
        pipeline.add_stage(PipelineStage(name="b", depends_on=["a"]))
        with pytest.raises(ValueError, match="Circular dependency"):
            pipeline.run()

    def test_missing_dependency(self):
        pipeline = Pipeline("missing-dep")
        pipeline.add_stage(PipelineStage(name="a", depends_on=["nonexistent"]))
        with pytest.raises(ValueError, match="unknown stage"):
            pipeline.run()

    def test_failure_stops_pipeline(self):
        pipeline = Pipeline("fail-stop")
        pipeline.add_stage(PipelineStage(name="build", executor=_success_executor("build")))
        pipeline.add_stage(PipelineStage(name="test", executor=_fail_executor("test")))
        pipeline.add_stage(PipelineStage(name="deploy", executor=_success_executor("deploy")))
        result = pipeline.run()
        assert not result.succeeded
        assert len(result.failed_stages) == 1
        # deploy should be skipped
        statuses = {r.name: r.status for r in result.results}
        assert statuses["deploy"] == StageStatus.SKIPPED

    def test_continue_on_failure(self):
        pipeline = Pipeline("continue")
        pipeline.add_stage(PipelineStage(
            name="maybe-fail",
            executor=_fail_executor("maybe-fail"),
            continue_on_failure=True,
        ))
        pipeline.add_stage(PipelineStage(
            name="still-runs",
            executor=_success_executor("still-runs"),
        ))
        result = pipeline.run()
        assert not result.succeeded  # overall still fails
        statuses = {r.name: r.status for r in result.results}
        assert statuses["still-runs"] == StageStatus.SUCCESS

    def test_parallel_execution(self):
        pipeline = Pipeline("parallel")
        pipeline.add_stage(PipelineStage(name="build", executor=_success_executor("build")))
        pipeline.add_stage(PipelineStage(name="test-a", executor=_success_executor("test-a"), depends_on=["build"]))
        pipeline.add_stage(PipelineStage(name="test-b", executor=_success_executor("test-b"), depends_on=["build"]))
        pipeline.add_stage(PipelineStage(name="deploy", executor=_success_executor("deploy"), depends_on=["test-a", "test-b"]))

        result = pipeline.run_parallel()
        assert result.succeeded
        assert len(result.results) == 4

    def test_stage_names(self):
        pipeline = Pipeline("names")
        pipeline.add_stage(PipelineStage(name="a"))
        pipeline.add_stage(PipelineStage(name="b"))
        assert set(pipeline.stage_names) == {"a", "b"}

    def test_get_stage(self):
        pipeline = Pipeline("get")
        pipeline.add_stage(PipelineStage(name="find-me"))
        stage = pipeline.get_stage("find-me")
        assert stage.name == "find-me"

    def test_get_missing_stage(self):
        pipeline = Pipeline("empty")
        with pytest.raises(KeyError):
            pipeline.get_stage("nope")

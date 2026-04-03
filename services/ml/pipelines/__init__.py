"""Pipeline builder registry.

Maps task names to their pipeline builders. Adding a new task type
means adding a new module here and registering it in _BUILDERS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.ml.pipelines.classification import ClassificationPipelineBuilder
from services.ml.pipelines.inversion import InversionPipelineBuilder
from services.ml.pipelines.regression import RegressionPipelineBuilder

if TYPE_CHECKING:
    from config.ml import MLPipelineConfig

_BUILDERS: dict[str, type] = {
    "regression": RegressionPipelineBuilder,
    "classification": ClassificationPipelineBuilder,
    "inversion": InversionPipelineBuilder,
}


def get_pipeline_builder(task: str) -> object:
    """Return a pipeline builder for the given task.

    Raises:
        KeyError: If the task is not registered.
    """
    builder_cls = _BUILDERS.get(task)
    if builder_cls is None:
        raise KeyError(
            f"Unknown task '{task}'. Available: {list(_BUILDERS.keys())}"
        )
    return builder_cls()


def build_pipelines(
    task: str,
    config: MLPipelineConfig,
) -> list[tuple[str, object]]:
    """Build named sklearn pipelines for the given task.

    Convenience function that instantiates the builder and calls build().
    """
    builder = get_pipeline_builder(task)
    return builder.build(config)

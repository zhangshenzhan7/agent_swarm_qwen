"""Output generation pipeline.

Orchestrates the full output lifecycle: handler lookup → artifact generation →
validation → storage → progress notification.  When validation fails the
artifact is marked ``"invalid"`` and the failure reason is logged, but
processing continues for the remaining artifacts so the task can be reported
as partially completed.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from .artifact_storage import ArtifactStorage
from .interfaces.output_handler import IOutputHandler
from .models.enums import OutputType
from .models.output import OutputArtifact
from .output_registry import OutputTypeRegistry

logger = logging.getLogger(__name__)


class OutputPipeline:
    """End-to-end pipeline that turns an aggregated result into stored artifacts.

    Attributes:
        _registry: Registry used to look up the handler for a given output type.
        _storage: Storage backend for persisting validated artifacts.
    """

    def __init__(
        self,
        registry: OutputTypeRegistry,
        storage: ArtifactStorage,
    ) -> None:
        self._registry = registry
        self._storage = storage

    async def execute(
        self,
        task_id: str,
        aggregated_result: Any,
        output_type: OutputType,
        config: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
    ) -> List[OutputArtifact]:
        """Run the full output pipeline.

        Steps:
        1. Look up the handler from the registry (raises ``KeyError`` if not
           found).
        2. Call ``handler.generate()`` to produce artifacts.
        3. Validate each artifact via ``handler.validate()``.
           - Valid artifacts are stored via ``storage.store()``.
           - Invalid artifacts have their ``validation_status`` set to
             ``"invalid"`` and the failure reasons are logged.
        4. A *progress_callback* (if provided) is invoked at every stage.
        5. All artifacts (valid **and** invalid) are returned.

        Args:
            task_id: Identifier of the owning task.
            aggregated_result: The output from the result aggregator.
            output_type: Desired output type.
            config: Handler-specific configuration.
            progress_callback: Optional ``async def callback(stage, detail)``
                called at each pipeline stage.

        Returns:
            List of all produced ``OutputArtifact`` objects.
        """
        async def _notify(stage: str, detail: str) -> None:
            if progress_callback is not None:
                await progress_callback(stage, detail)

        # 1. Look up handler ------------------------------------------------
        handler: IOutputHandler = self._registry.get_handler(output_type)

        # 2. Generate artifacts ----------------------------------------------
        await _notify("generating", f"Generating {output_type.value} artifacts")
        try:
            artifacts: List[OutputArtifact] = await handler.generate(
                aggregated_result, config
            )
        except Exception as exc:
            logger.error(
                "Artifact generation failed for task %s: %s", task_id, exc
            )
            await _notify("failed", f"Generation failed: {exc}")
            raise

        # 3. Validate each artifact ------------------------------------------
        all_valid = True
        for artifact in artifacts:
            await _notify(
                "validating",
                f"Validating artifact {artifact.artifact_id}",
            )
            try:
                result = await handler.validate(artifact)
            except Exception as exc:
                logger.error(
                    "Validation error for artifact %s: %s",
                    artifact.artifact_id,
                    exc,
                )
                artifact.validation_status = "invalid"
                all_valid = False
                continue

            if result.is_valid:
                artifact.validation_status = "valid"
            else:
                artifact.validation_status = "invalid"
                all_valid = False
                logger.warning(
                    "Artifact %s failed validation: %s",
                    artifact.artifact_id,
                    "; ".join(result.errors),
                )

        # 4. Store valid artifacts -------------------------------------------
        for artifact in artifacts:
            if artifact.validation_status != "valid":
                continue
            await _notify(
                "storing",
                f"Storing artifact {artifact.artifact_id}",
            )
            try:
                path = await self._storage.store(task_id, artifact)
                artifact.file_path = path
            except IOError as exc:
                logger.error(
                    "Storage failed for artifact %s: %s",
                    artifact.artifact_id,
                    exc,
                )
                # Storage failure does not change validation_status;
                # the artifact simply has no file_path.

        # 5. Final progress notification -------------------------------------
        if all_valid:
            await _notify("completed", "All artifacts generated and validated")
        else:
            await _notify(
                "completed",
                "Pipeline finished with some invalid artifacts (partial completion)",
            )

        return artifacts

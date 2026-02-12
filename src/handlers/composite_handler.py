"""Composite output handler.

Implements the IOutputHandler interface for COMPOSITE output type,
managing composite outputs that contain multiple sub-artifacts of
different types. Uses an OutputTypeRegistry to delegate generation
to type-specific handlers and performs topological sorting to
respect inter-artifact dependencies.
"""

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from ..interfaces.output_handler import IOutputHandler, ValidationResult
from ..models.output import OutputArtifact, OutputMetadata
from ..models.enums import OutputType
from ..output_registry import OutputTypeRegistry

logger = logging.getLogger(__name__)


class CompositeHandler(IOutputHandler):
    """Handler for COMPOSITE output type.

    Generates composite outputs containing multiple sub-artifacts of
    different types. Sub-artifacts are generated in dependency order
    (topological sort). If a sub-artifact fails, dependents are skipped
    but independent sub-artifacts continue to be generated.

    Args:
        registry: The OutputTypeRegistry used to look up type-specific handlers.
    """

    def __init__(self, registry: OutputTypeRegistry) -> None:
        self._registry = registry

    async def generate(
        self, aggregated_result: Any, config: Dict[str, Any]
    ) -> List[OutputArtifact]:
        """Generate composite artifacts from *aggregated_result*.

        Config should contain ``"sub_outputs"`` — a list of dicts, each with:
        - ``"output_type"``: str (e.g. ``"report"``, ``"code"``, ``"image"``)
        - ``"config"``: dict (type-specific config passed to the sub-handler)
        - ``"dependencies"``: list of int indices into ``sub_outputs`` that
          this sub-output depends on

        Sub-artifacts are generated in topological (dependency) order.
        If generation of a sub-artifact fails, it is marked as failed and
        any sub-outputs that transitively depend on it are skipped.
        Independent sub-outputs are still generated.

        Returns:
            A list of all successfully generated OutputArtifact instances.
        """
        sub_outputs: List[Dict[str, Any]] = config.get("sub_outputs", [])
        if not sub_outputs:
            return []

        sorted_indices = self._topological_sort(sub_outputs)

        # Track which indices failed (directly or transitively)
        failed_indices: Set[int] = set()
        # Map index -> list of generated artifacts
        artifacts_by_index: Dict[int, List[OutputArtifact]] = {}
        all_artifacts: List[OutputArtifact] = []

        for idx in sorted_indices:
            sub = sub_outputs[idx]
            deps = sub.get("dependencies", [])

            # Skip if any dependency failed
            if any(d in failed_indices for d in deps):
                failed_indices.add(idx)
                logger.warning(
                    "Skipping sub-output %d (%s): dependency failed",
                    idx,
                    sub.get("output_type", "unknown"),
                )
                continue

            output_type_str = sub.get("output_type", "report")
            sub_config = dict(sub.get("config", {}))

            try:
                output_type = OutputType(output_type_str)
                handler = self._registry.get_handler(output_type)

                # Inject dependency artifact IDs into sub_config
                dep_artifact_ids: List[str] = []
                for d in deps:
                    if d in artifacts_by_index:
                        for art in artifacts_by_index[d]:
                            dep_artifact_ids.append(art.artifact_id)
                if dep_artifact_ids:
                    sub_config["dependency_artifact_ids"] = dep_artifact_ids

                generated = await handler.generate(aggregated_result, sub_config)
                artifacts_by_index[idx] = generated

                # Set dependency metadata on generated artifacts
                for art in generated:
                    art.metadata.dependencies = list(dep_artifact_ids)

                all_artifacts.extend(generated)

            except Exception:
                failed_indices.add(idx)
                logger.exception(
                    "Failed to generate sub-output %d (%s)",
                    idx,
                    output_type_str,
                )

        return all_artifacts

    async def validate(self, artifact: OutputArtifact) -> ValidationResult:
        """Validate a composite artifact.

        For composite artifacts, validation is a pass-through — individual
        sub-artifacts are validated by their own type-specific handlers.

        Returns:
            A ValidationResult with ``is_valid=True``.
        """
        return ValidationResult(is_valid=True)

    async def post_process(self, artifact: OutputArtifact) -> OutputArtifact:
        """Return the artifact as-is — no post-processing for composites."""
        return artifact

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _topological_sort(sub_outputs: List[Dict[str, Any]]) -> List[int]:
        """Return indices of *sub_outputs* in dependency-first order.

        Uses Kahn's algorithm (BFS-based topological sort). If the
        dependency graph contains a cycle, the cyclic nodes are appended
        at the end so that as many independent outputs as possible are
        still generated.

        Args:
            sub_outputs: List of sub-output dicts, each optionally
                containing a ``"dependencies"`` key with a list of
                integer indices.

        Returns:
            A list of integer indices in topological order.
        """
        n = len(sub_outputs)
        if n == 0:
            return []

        # Build adjacency and in-degree
        in_degree = [0] * n
        dependents: Dict[int, List[int]] = {i: [] for i in range(n)}

        for i, sub in enumerate(sub_outputs):
            deps = sub.get("dependencies", [])
            for d in deps:
                if 0 <= d < n and d != i:
                    in_degree[i] += 1
                    dependents[d].append(i)

        # Kahn's algorithm
        queue: deque[int] = deque()
        for i in range(n):
            if in_degree[i] == 0:
                queue.append(i)

        order: List[int] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for dep in dependents[node]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        # If there are remaining nodes (cycle), append them
        if len(order) < n:
            remaining = [i for i in range(n) if i not in set(order)]
            order.extend(remaining)

        return order

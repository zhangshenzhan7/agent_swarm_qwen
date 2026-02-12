"""Report output handler.

Encapsulates the existing report generation logic into the IOutputHandler
interface, producing Markdown report artifacts from aggregated results.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..interfaces.output_handler import IOutputHandler, ValidationResult
from ..models.output import OutputArtifact, OutputMetadata
from ..models.enums import OutputType


class ReportHandler(IOutputHandler):
    """Handler for REPORT output type.

    Generates Markdown report artifacts from aggregated results.
    The ``generate`` method extracts the integrated text from the
    aggregation result (either an ``AggregationResult`` object or a plain
    dict with an ``"integrated_result"`` key) and wraps it in an
    ``OutputArtifact``.
    """

    async def generate(
        self, aggregated_result: Any, config: Dict[str, Any]
    ) -> List[OutputArtifact]:
        """Generate a Markdown report artifact from *aggregated_result*.

        The integrated text is resolved in order:
        1. ``aggregated_result.final_output`` (AggregationResult dataclass)
        2. ``aggregated_result["integrated_result"]`` (dict form)
        3. ``aggregated_result["final_output"]`` (dict form, fallback)
        4. ``str(aggregated_result)`` as last resort

        Returns a single-element list containing the report artifact.
        """
        content = self._extract_content(aggregated_result)

        size_bytes = len(content.encode("utf-8")) if isinstance(content, str) else len(content)

        metadata = OutputMetadata(
            format="md",
            size_bytes=size_bytes,
            mime_type="text/markdown",
            dependencies=[],
            generation_time_seconds=config.get("generation_time_seconds", 0.0),
        )

        artifact = OutputArtifact(
            artifact_id=config.get("artifact_id", str(uuid.uuid4())),
            output_type=OutputType.REPORT,
            content=content,
            metadata=metadata,
            validation_status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        return [artifact]

    async def validate(self, artifact: OutputArtifact) -> ValidationResult:
        """Validate a report artifact.

        Checks:
        - Content is a non-empty string.
        - Content contains at least one Markdown indicator (heading, list,
          bold, link, etc.) **or** is at minimum non-empty text (still valid
          with a warning).
        """
        errors: List[str] = []
        warnings: List[str] = []

        # --- non-empty string check ---
        if not isinstance(artifact.content, str):
            errors.append("Report content must be a string")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        if not artifact.content.strip():
            errors.append("Report content is empty")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # --- Markdown indicator check ---
        md_patterns = [
            r"^#{1,6}\s",   # headings
            r"^[-*+]\s",    # unordered lists
            r"^\d+\.\s",    # ordered lists
            r"\*\*.+?\*\*", # bold
            r"\[.+?\]\(",   # links
            r"^>\s",        # blockquotes
            r"```",         # code blocks
            r"\|.+\|",      # tables
        ]
        has_markdown = any(
            re.search(p, artifact.content, re.MULTILINE) for p in md_patterns
        )

        if not has_markdown:
            warnings.append(
                "Report content does not contain recognisable Markdown formatting"
            )

        return ValidationResult(is_valid=True, errors=errors, warnings=warnings)

    async def post_process(self, artifact: OutputArtifact) -> OutputArtifact:
        """Return the artifact unchanged — reports need no post-processing."""
        return artifact

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_content(aggregated_result: Any) -> str:
        """Resolve the text content from various aggregated result shapes."""
        # AggregationResult dataclass (has .final_output)
        if hasattr(aggregated_result, "final_output"):
            raw = aggregated_result.final_output
            return str(raw) if raw is not None else ""

        # Dict forms
        if isinstance(aggregated_result, dict):
            for key in ("integrated_result", "final_output"):
                if key in aggregated_result:
                    val = aggregated_result[key]
                    return str(val) if val is not None else ""

        # Fallback
        return str(aggregated_result)

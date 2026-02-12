"""Website output handler.

Implements the IOutputHandler interface for WEBSITE output type,
producing HTML/CSS/JS file artifacts from aggregated results.
"""

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from ..interfaces.output_handler import IOutputHandler, ValidationResult
from ..models.output import OutputArtifact, OutputMetadata
from ..models.enums import OutputType


# File extension to MIME type mapping for web files
_WEB_EXTENSION_MIME_MAP: Dict[str, str] = {
    ".html": "text/html",
    ".htm": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".xml": "application/xml",
}


def _mime_type_for_path(file_path: str) -> str:
    """Return the MIME type for a file path based on its extension."""
    _, ext = os.path.splitext(file_path)
    return _WEB_EXTENSION_MIME_MAP.get(ext.lower(), "application/octet-stream")


def _format_for_path(file_path: str) -> str:
    """Return the format string (extension without dot) for a file path."""
    _, ext = os.path.splitext(file_path)
    return ext.lstrip(".").lower() if ext else "html"


class WebsiteHandler(IOutputHandler):
    """Handler for WEBSITE output type.

    Generates HTML/CSS/JS file artifacts from aggregated results.
    Supports both single-file HTML and multi-file website outputs.
    """

    async def generate(
        self, aggregated_result: Any, config: Dict[str, Any]
    ) -> List[OutputArtifact]:
        """Generate website artifacts from *aggregated_result*.

        The content is resolved from:
        1. ``aggregated_result.final_output`` (AggregationResult dataclass)
        2. ``aggregated_result["integrated_result"]`` (dict form)
        3. ``aggregated_result["website_files"]`` (dict of file_path -> content)
        4. ``aggregated_result["final_output"]`` (dict form, fallback)
        5. ``str(aggregated_result)`` as last resort

        If the resolved content is a dict mapping file paths to content
        strings, one artifact is created per file. Otherwise a single
        HTML artifact is created.

        Returns a list of OutputArtifact instances.
        """
        raw = self._extract_raw(aggregated_result)

        # Multi-file: dict of file_path -> content
        if isinstance(raw, dict):
            return self._build_multi_file_artifacts(raw, config)

        # Single HTML file
        content = str(raw) if raw is not None else ""
        return [self._build_single_artifact(content, config)]

    async def validate(self, artifact: OutputArtifact) -> ValidationResult:
        """Validate a website artifact.

        Checks:
        - Content is a non-empty string.
        - For HTML files: checks for basic HTML structure (doctype or
          html/body tags).
        - Resource reference check is handled separately via
          ``validate_references`` when a full artifact set is available.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not isinstance(artifact.content, str):
            errors.append("Website content must be a string")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        if not artifact.content.strip():
            errors.append("Website content is empty")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # HTML structure check for .html/.htm files
        fmt = artifact.metadata.format
        if fmt in ("html", "htm"):
            content_lower = artifact.content.lower()
            has_doctype = "<!doctype" in content_lower
            has_html_tag = "<html" in content_lower
            has_body_tag = "<body" in content_lower

            if not (has_doctype or has_html_tag or has_body_tag):
                errors.append(
                    "HTML file missing basic structure: "
                    "no <!DOCTYPE>, <html>, or <body> tag found"
                )
                return ValidationResult(
                    is_valid=False, errors=errors, warnings=warnings
                )

        return ValidationResult(is_valid=True, errors=errors, warnings=warnings)

    def validate_references(
        self, artifact: OutputArtifact, known_files: Set[str]
    ) -> List[str]:
        """Check for broken resource references in an HTML artifact.

        Scans ``src`` and ``href`` attributes for local file references
        and returns a list of warnings for any that are not found in
        *known_files*.

        Args:
            artifact: The HTML artifact to check.
            known_files: Set of file paths available in the artifact set.

        Returns:
            A list of warning strings for broken references.
        """
        warnings: List[str] = []

        if not isinstance(artifact.content, str):
            return warnings

        fmt = artifact.metadata.format
        if fmt not in ("html", "htm"):
            return warnings

        # Extract src="..." and href="..." attribute values
        ref_pattern = re.compile(
            r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE
        )
        refs = ref_pattern.findall(artifact.content)

        for ref in refs:
            # Skip external URLs, data URIs, anchors, and protocol-relative
            if ref.startswith(("http://", "https://", "data:", "#", "//", "mailto:")):
                continue
            # Normalise the reference path
            normalised = ref.split("?")[0].split("#")[0]
            if normalised and normalised not in known_files:
                warnings.append(
                    f"Resource reference '{ref}' not found in artifact set"
                )

        return warnings

    async def post_process(self, artifact: OutputArtifact) -> OutputArtifact:
        """Return the artifact unchanged — websites need no post-processing."""
        return artifact

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_raw(aggregated_result: Any) -> Any:
        """Resolve the raw content from various aggregated result shapes."""
        # AggregationResult dataclass (has .final_output)
        if hasattr(aggregated_result, "final_output"):
            return aggregated_result.final_output

        # Dict forms
        if isinstance(aggregated_result, dict):
            if "integrated_result" in aggregated_result:
                return aggregated_result["integrated_result"]
            if "website_files" in aggregated_result:
                return aggregated_result["website_files"]
            if "final_output" in aggregated_result:
                return aggregated_result["final_output"]

        # Fallback
        return aggregated_result

    def _build_single_artifact(
        self, content: str, config: Dict[str, Any]
    ) -> OutputArtifact:
        """Build a single HTML artifact from a content string."""
        file_path = config.get("file_path", "index.html")
        size_bytes = len(content.encode("utf-8"))

        metadata = OutputMetadata(
            format=_format_for_path(file_path),
            size_bytes=size_bytes,
            mime_type=_mime_type_for_path(file_path),
            dependencies=[],
            generation_time_seconds=config.get("generation_time_seconds", 0.0),
        )

        return OutputArtifact(
            artifact_id=config.get("artifact_id", str(uuid.uuid4())),
            output_type=OutputType.WEBSITE,
            content=content,
            metadata=metadata,
            validation_status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            file_path=file_path,
        )

    def _build_multi_file_artifacts(
        self, files: Dict[str, str], config: Dict[str, Any]
    ) -> List[OutputArtifact]:
        """Build one artifact per file from a file_path -> content mapping."""
        artifacts: List[OutputArtifact] = []
        gen_time = config.get("generation_time_seconds", 0.0)

        for file_path, content in files.items():
            content_str = str(content) if content is not None else ""
            size_bytes = len(content_str.encode("utf-8"))

            metadata = OutputMetadata(
                format=_format_for_path(file_path),
                size_bytes=size_bytes,
                mime_type=_mime_type_for_path(file_path),
                dependencies=[],
                generation_time_seconds=gen_time,
            )

            artifact = OutputArtifact(
                artifact_id=str(uuid.uuid4()),
                output_type=OutputType.WEBSITE,
                content=content_str,
                metadata=metadata,
                validation_status="pending",
                created_at=datetime.now(timezone.utc).isoformat(),
                file_path=file_path,
            )
            artifacts.append(artifact)

        return artifacts

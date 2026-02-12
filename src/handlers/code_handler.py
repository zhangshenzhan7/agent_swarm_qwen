"""Code output handler.

Implements the IOutputHandler interface for CODE output type,
producing source code file artifacts from aggregated results.
"""

import ast
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

from ..interfaces.output_handler import IOutputHandler, ValidationResult
from ..models.output import OutputArtifact, OutputMetadata
from ..models.enums import OutputType


# File extension to MIME type mapping for common languages
_EXTENSION_MIME_MAP: Dict[str, str] = {
    ".py": "text/x-python",
    ".js": "application/javascript",
    ".ts": "application/typescript",
    ".jsx": "text/jsx",
    ".tsx": "text/tsx",
    ".java": "text/x-java-source",
    ".c": "text/x-csrc",
    ".cpp": "text/x-c++src",
    ".h": "text/x-chdr",
    ".hpp": "text/x-c++hdr",
    ".cs": "text/x-csharp",
    ".go": "text/x-go",
    ".rs": "text/x-rustsrc",
    ".rb": "text/x-ruby",
    ".php": "text/x-php",
    ".swift": "text/x-swift",
    ".kt": "text/x-kotlin",
    ".scala": "text/x-scala",
    ".sh": "text/x-shellscript",
    ".bash": "text/x-shellscript",
    ".sql": "text/x-sql",
    ".r": "text/x-r",
    ".html": "text/html",
    ".css": "text/css",
    ".json": "application/json",
    ".xml": "application/xml",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".toml": "application/toml",
    ".md": "text/markdown",
}


def _mime_type_for_path(file_path: str) -> str:
    """Return the MIME type for a file path based on its extension."""
    _, ext = os.path.splitext(file_path)
    return _EXTENSION_MIME_MAP.get(ext.lower(), "text/plain")


def _format_for_path(file_path: str) -> str:
    """Return the format string (extension without dot) for a file path."""
    _, ext = os.path.splitext(file_path)
    return ext.lstrip(".").lower() if ext else "txt"


class CodeHandler(IOutputHandler):
    """Handler for CODE output type.

    Generates source code file artifacts from aggregated results.
    Supports both single-file and multi-file code outputs.
    """

    async def generate(
        self, aggregated_result: Any, config: Dict[str, Any]
    ) -> List[OutputArtifact]:
        """Generate code artifacts from *aggregated_result*.

        The code content is resolved from:
        1. ``aggregated_result.final_output`` (AggregationResult dataclass)
        2. ``aggregated_result["integrated_result"]`` (dict form)
        3. ``aggregated_result["code_files"]`` (dict of file_path -> content)
        4. ``str(aggregated_result)`` as last resort

        If the resolved content is a dict mapping file paths to content
        strings, one artifact is created per file. Otherwise a single
        artifact is created.

        Returns a list of OutputArtifact instances.
        """
        raw = self._extract_raw(aggregated_result)

        # Multi-file: dict of file_path -> content
        if isinstance(raw, dict):
            return self._build_multi_file_artifacts(raw, config)

        # Single file
        content = str(raw) if raw is not None else ""
        return [self._build_single_artifact(content, config)]

    async def validate(self, artifact: OutputArtifact) -> ValidationResult:
        """Validate a code artifact.

        Checks:
        - Content is a non-empty string.
        - For Python files (.py), attempts ``ast.parse`` to verify syntax.
        - For other languages, only checks non-empty content.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not isinstance(artifact.content, str):
            errors.append("Code content must be a string")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        if not artifact.content.strip():
            errors.append("Code content is empty")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # Python syntax check
        fmt = artifact.metadata.format
        if fmt == "py":
            try:
                ast.parse(artifact.content)
            except SyntaxError as exc:
                errors.append(f"Python syntax error: {exc}")
                return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        return ValidationResult(is_valid=True, errors=errors, warnings=warnings)

    async def post_process(self, artifact: OutputArtifact) -> OutputArtifact:
        """Return the artifact unchanged — code needs no post-processing."""
        return artifact

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_raw(aggregated_result: Any) -> Any:
        """Resolve the raw content from various aggregated result shapes."""
        # AggregationResult dataclass
        if hasattr(aggregated_result, "final_output"):
            return aggregated_result.final_output

        # Dict forms
        if isinstance(aggregated_result, dict):
            if "integrated_result" in aggregated_result:
                return aggregated_result["integrated_result"]
            if "code_files" in aggregated_result:
                return aggregated_result["code_files"]
            if "final_output" in aggregated_result:
                return aggregated_result["final_output"]

        # Fallback
        return aggregated_result

    def _build_single_artifact(
        self, content: str, config: Dict[str, Any]
    ) -> OutputArtifact:
        """Build a single code artifact from a content string."""
        file_path = config.get("file_path", "output.py")
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
            output_type=OutputType.CODE,
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
                output_type=OutputType.CODE,
                content=content_str,
                metadata=metadata,
                validation_status="pending",
                created_at=datetime.now(timezone.utc).isoformat(),
                file_path=file_path,
            )
            artifacts.append(artifact)

        return artifacts

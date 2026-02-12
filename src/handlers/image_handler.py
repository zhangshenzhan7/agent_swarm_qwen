"""Image output handler.

Implements the IOutputHandler interface for IMAGE output type,
producing image artifacts from aggregated results.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..interfaces.output_handler import IOutputHandler, ValidationResult
from ..models.output import OutputArtifact, OutputMetadata
from ..models.enums import OutputType


# Image format magic bytes signatures
_IMAGE_SIGNATURES: Dict[str, bytes] = {
    "png": b"\x89PNG",
    "jpeg": b"\xff\xd8\xff",
    "gif87a": b"GIF87a",
    "gif89a": b"GIF89a",
    "bmp": b"BM",
    "webp_riff": b"RIFF",
}

# Minimum bytes needed to identify any supported format
_MIN_MAGIC_BYTES = 12  # RIFF....WEBP needs 12 bytes

# Format to MIME type mapping
_FORMAT_MIME_MAP: Dict[str, str] = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "webp": "image/webp",
}


def _detect_image_format(data: bytes) -> str:
    """Detect image format from magic bytes. Returns format name or 'unknown'."""
    if len(data) < 2:
        return "unknown"

    if data[:4] == b"\x89PNG":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:6] == b"GIF87a" or data[:6] == b"GIF89a":
        return "gif"
    if data[:2] == b"BM":
        return "bmp"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"

    return "unknown"


def _mime_type_for_format(fmt: str) -> str:
    """Return the MIME type for an image format string."""
    return _FORMAT_MIME_MAP.get(fmt, "application/octet-stream")


class ImageHandler(IOutputHandler):
    """Handler for IMAGE output type.

    Generates image artifacts from aggregated results. The ``generate``
    method extracts binary image data from the aggregation result and
    wraps it in an ``OutputArtifact``. The ``validate`` method checks
    for valid image magic bytes to verify format and file integrity.
    """

    async def generate(
        self, aggregated_result: Any, config: Dict[str, Any]
    ) -> List[OutputArtifact]:
        """Generate image artifacts from *aggregated_result*.

        The image content is resolved from:
        1. ``aggregated_result.final_output`` (AggregationResult dataclass)
        2. ``aggregated_result["image_data"]`` (dict form, bytes)
        3. ``aggregated_result["integrated_result"]`` (dict form)
        4. ``aggregated_result["final_output"]`` (dict form, fallback)
        5. Raw bytes if *aggregated_result* is already ``bytes``

        Returns a single-element list containing the image artifact.
        """
        content = self._extract_content(aggregated_result)

        size_bytes = len(content) if isinstance(content, bytes) else len(
            content.encode("utf-8") if isinstance(content, str) else b""
        )

        fmt = _detect_image_format(content) if isinstance(content, bytes) else "unknown"
        mime_type = _mime_type_for_format(fmt)

        metadata = OutputMetadata(
            format=fmt,
            size_bytes=size_bytes,
            mime_type=mime_type,
            dependencies=[],
            generation_time_seconds=config.get("generation_time_seconds", 0.0),
        )

        artifact = OutputArtifact(
            artifact_id=config.get("artifact_id", str(uuid.uuid4())),
            output_type=OutputType.IMAGE,
            content=content,
            metadata=metadata,
            validation_status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        return [artifact]

    async def validate(self, artifact: OutputArtifact) -> ValidationResult:
        """Validate an image artifact.

        Checks:
        - Content is bytes and non-empty.
        - Content starts with valid image magic bytes for a supported
          format: PNG, JPEG, GIF (87a/89a), BMP, or WebP.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not isinstance(artifact.content, bytes):
            errors.append("Image content must be bytes")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        if len(artifact.content) == 0:
            errors.append("Image content is empty")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        fmt = _detect_image_format(artifact.content)
        if fmt == "unknown":
            errors.append(
                "Image content does not match any supported format "
                "(PNG, JPEG, GIF, BMP, WebP)"
            )
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        return ValidationResult(is_valid=True, errors=errors, warnings=warnings)

    async def post_process(self, artifact: OutputArtifact) -> OutputArtifact:
        """Return the artifact unchanged — images need no post-processing."""
        return artifact

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_content(aggregated_result: Any) -> bytes:
        """Resolve the image content from various aggregated result shapes."""
        # AggregationResult dataclass (has .final_output)
        if hasattr(aggregated_result, "final_output"):
            raw = aggregated_result.final_output
            if isinstance(raw, bytes):
                return raw
            return raw if raw is not None else b""

        # Dict forms
        if isinstance(aggregated_result, dict):
            for key in ("image_data", "integrated_result", "final_output"):
                if key in aggregated_result:
                    val = aggregated_result[key]
                    if isinstance(val, bytes):
                        return val
                    return val if val is not None else b""

        # Raw bytes
        if isinstance(aggregated_result, bytes):
            return aggregated_result

        # Fallback — return empty bytes
        return b""

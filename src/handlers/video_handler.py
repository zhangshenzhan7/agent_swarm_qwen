"""Video output handler.

Implements the IOutputHandler interface for VIDEO output type,
producing video artifacts from aggregated results.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..interfaces.output_handler import IOutputHandler, ValidationResult
from ..models.output import OutputArtifact, OutputMetadata
from ..models.enums import OutputType


# Video format magic bytes signatures
# MP4/MOV: "ftyp" at offset 4
# AVI: "RIFF" header + "AVI " at offset 8
# WebM: EBML header starting with \x1a\x45\xdf\xa3
# MOV: "ftyp" at offset 4 or "moov" at offset 4
_MIN_MAGIC_BYTES = 12  # Enough to identify all supported formats

# Format to MIME type mapping
_FORMAT_MIME_MAP: Dict[str, str] = {
    "mp4": "video/mp4",
    "avi": "video/x-msvideo",
    "webm": "video/webm",
    "mov": "video/quicktime",
}


def _detect_video_format(data: bytes) -> str:
    """Detect video format from magic bytes. Returns format name or 'unknown'."""
    if len(data) < 8:
        return "unknown"

    # MP4 / MOV: "ftyp" at offset 4
    if data[4:8] == b"ftyp":
        return "mp4"

    # AVI: "RIFF" header + "AVI " at offset 8
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return "avi"

    # WebM: EBML header
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"

    # MOV: "moov" at offset 4
    if data[4:8] == b"moov":
        return "mov"

    return "unknown"


def _mime_type_for_format(fmt: str) -> str:
    """Return the MIME type for a video format string."""
    return _FORMAT_MIME_MAP.get(fmt, "application/octet-stream")


class VideoHandler(IOutputHandler):
    """Handler for VIDEO output type.

    Generates video artifacts from aggregated results. The ``generate``
    method extracts binary video data from the aggregation result and
    wraps it in an ``OutputArtifact``. The ``validate`` method checks
    for valid video magic bytes to verify format and file integrity.
    """

    async def generate(
        self, aggregated_result: Any, config: Dict[str, Any]
    ) -> List[OutputArtifact]:
        """Generate video artifacts from *aggregated_result*.

        The video content is resolved from:
        1. ``aggregated_result.final_output`` (AggregationResult dataclass)
        2. ``aggregated_result["video_data"]`` (dict form, bytes)
        3. ``aggregated_result["integrated_result"]`` (dict form)
        4. ``aggregated_result["final_output"]`` (dict form, fallback)
        5. Raw bytes if *aggregated_result* is already ``bytes``

        Returns a single-element list containing the video artifact.
        """
        content = self._extract_content(aggregated_result)

        size_bytes = len(content) if isinstance(content, bytes) else len(
            content.encode("utf-8") if isinstance(content, str) else b""
        )

        fmt = _detect_video_format(content) if isinstance(content, bytes) else "unknown"
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
            output_type=OutputType.VIDEO,
            content=content,
            metadata=metadata,
            validation_status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        return [artifact]

    async def validate(self, artifact: OutputArtifact) -> ValidationResult:
        """Validate a video artifact.

        Checks:
        - Content is bytes and non-empty.
        - Content starts with valid video magic bytes for a supported
          format: MP4, AVI, WebM, or MOV.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not isinstance(artifact.content, bytes):
            errors.append("Video content must be bytes")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        if len(artifact.content) == 0:
            errors.append("Video content is empty")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        fmt = _detect_video_format(artifact.content)
        if fmt == "unknown":
            errors.append(
                "Video content does not match any supported format "
                "(MP4, AVI, WebM, MOV)"
            )
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        return ValidationResult(is_valid=True, errors=errors, warnings=warnings)

    async def post_process(self, artifact: OutputArtifact) -> OutputArtifact:
        """Return the artifact unchanged — videos need no post-processing."""
        return artifact

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_content(aggregated_result: Any) -> bytes:
        """Resolve the video content from various aggregated result shapes."""
        # AggregationResult dataclass (has .final_output)
        if hasattr(aggregated_result, "final_output"):
            raw = aggregated_result.final_output
            if isinstance(raw, bytes):
                return raw
            return raw if raw is not None else b""

        # Dict forms
        if isinstance(aggregated_result, dict):
            for key in ("video_data", "integrated_result", "final_output"):
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

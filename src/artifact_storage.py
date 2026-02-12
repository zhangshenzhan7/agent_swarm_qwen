"""Artifact storage service for persisting and retrieving output artifacts.

Stores artifact content and metadata to the filesystem, organized by
task_id and artifact_id. Content is stored as a binary/text file and
metadata as a companion JSON file.

Path format:
    {base_path}/{task_id}/{artifact_id}.{ext}       (content)
    {base_path}/{task_id}/{artifact_id}.meta.json    (metadata)
"""

import json
import os
from pathlib import Path
from typing import List

from .models.enums import OutputType
from .models.output import OutputArtifact, OutputMetadata


class ArtifactStorage:
    """Persist and retrieve OutputArtifact objects on the filesystem.

    Attributes:
        _base_path: Root directory for all stored artifacts.
    """

    def __init__(self, base_path: str = "artifacts"):
        self._base_path = base_path

    async def store(self, task_id: str, artifact: OutputArtifact) -> str:
        """Store artifact content and metadata to the filesystem.

        Creates ``{base_path}/{task_id}/`` if it does not exist, writes the
        content file and a companion ``.meta.json`` sidecar.

        Args:
            task_id: Identifier of the owning task.
            artifact: The artifact to persist.

        Returns:
            The filesystem path where the content was written.

        Raises:
            IOError: If the write operation fails.
        """
        ext = artifact.metadata.format
        task_dir = Path(self._base_path) / task_id
        content_path = task_dir / f"{artifact.artifact_id}.{ext}"
        meta_path = task_dir / f"{artifact.artifact_id}.meta.json"

        try:
            task_dir.mkdir(parents=True, exist_ok=True)

            # Write content
            if isinstance(artifact.content, bytes):
                content_path.write_bytes(artifact.content)
            else:
                # Use newline="" to prevent OS-level newline translation
                with open(content_path, "w", encoding="utf-8", newline="") as f:
                    f.write(artifact.content)

            # Write metadata sidecar
            meta_dict = {
                "artifact_id": artifact.artifact_id,
                "output_type": artifact.output_type.value,
                "metadata": artifact.metadata.to_dict(),
                "validation_status": artifact.validation_status,
                "created_at": artifact.created_at,
                "file_path": str(content_path),
            }
            meta_path.write_text(json.dumps(meta_dict, ensure_ascii=False, indent=2), encoding="utf-8")

            return str(content_path)

        except OSError as exc:
            raise IOError(
                f"Failed to store artifact {artifact.artifact_id} for task {task_id}: {exc}"
            ) from exc

    async def retrieve(self, task_id: str, artifact_id: str) -> OutputArtifact:
        """Retrieve an artifact by task_id and artifact_id.

        Reads the ``.meta.json`` sidecar to reconstruct the full
        ``OutputArtifact``, then loads the content file.

        Args:
            task_id: Identifier of the owning task.
            artifact_id: Identifier of the artifact.

        Returns:
            The reconstructed ``OutputArtifact``.

        Raises:
            FileNotFoundError: If the metadata file does not exist.
        """
        task_dir = Path(self._base_path) / task_id
        meta_pattern = f"{artifact_id}.meta.json"
        meta_path = task_dir / meta_pattern

        if not meta_path.exists():
            raise FileNotFoundError(
                f"Artifact {artifact_id} not found for task {task_id}"
            )

        meta_dict = json.loads(meta_path.read_text(encoding="utf-8"))
        metadata = OutputMetadata.from_dict(meta_dict["metadata"])

        ext = metadata.format
        content_path = task_dir / f"{artifact_id}.{ext}"

        # Determine content type from metadata mime_type
        if self._is_binary_mime(metadata.mime_type):
            content: str | bytes = content_path.read_bytes()
        else:
            # Use newline="" to prevent OS-level newline translation
            with open(content_path, "r", encoding="utf-8", newline="") as f:
                content = f.read()

        return OutputArtifact(
            artifact_id=meta_dict["artifact_id"],
            output_type=OutputType(meta_dict["output_type"]),
            content=content,
            metadata=metadata,
            validation_status=meta_dict.get("validation_status", "pending"),
            created_at=meta_dict["created_at"],
            file_path=meta_dict.get("file_path"),
        )

    async def list_artifacts(self, task_id: str) -> List[OutputArtifact]:
        """List all artifacts stored for a given task.

        Args:
            task_id: Identifier of the owning task.

        Returns:
            A list of ``OutputArtifact`` objects. Returns an empty list if the
            task directory does not exist or contains no artifacts.
        """
        task_dir = Path(self._base_path) / task_id
        if not task_dir.exists():
            return []

        artifacts: List[OutputArtifact] = []
        for meta_file in sorted(task_dir.glob("*.meta.json")):
            artifact_id = meta_file.name.removesuffix(".meta.json")
            try:
                artifact = await self.retrieve(task_id, artifact_id)
                artifacts.append(artifact)
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                # Skip corrupted / incomplete entries
                continue

        return artifacts

    @staticmethod
    def _is_binary_mime(mime_type: str) -> bool:
        """Return True if the MIME type represents binary content."""
        text_prefixes = ("text/", "application/json", "application/xml", "application/javascript")
        return not any(mime_type.startswith(p) for p in text_prefixes)

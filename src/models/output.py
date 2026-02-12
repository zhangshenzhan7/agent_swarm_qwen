"""Output artifact and metadata data models.

Provides OutputMetadata and OutputArtifact dataclasses with full
serialization support (to_dict / from_dict), including base64
encoding for binary content and OutputType enum handling.
"""

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from .enums import OutputType


@dataclass
class OutputMetadata:
    """输出产物元数据。

    Attributes:
        format: 文件格式，如 "md", "py", "html", "png"
        size_bytes: 字节大小
        mime_type: MIME 类型
        dependencies: 依赖的其他 artifact_id 列表
        generation_time_seconds: 生成耗时（秒）
    """

    format: str
    size_bytes: int
    mime_type: str
    dependencies: List[str] = field(default_factory=list)
    generation_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "format": self.format,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "dependencies": list(self.dependencies),
            "generation_time_seconds": self.generation_time_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputMetadata":
        """从字典反序列化。"""
        return cls(
            format=data["format"],
            size_bytes=data["size_bytes"],
            mime_type=data["mime_type"],
            dependencies=list(data.get("dependencies", [])),
            generation_time_seconds=data.get("generation_time_seconds", 0.0),
        )


@dataclass
class OutputArtifact:
    """输出产物。

    Attributes:
        artifact_id: 产物唯一标识
        output_type: 输出类型
        content: 文本内容（str）或二进制内容（bytes）
        metadata: 输出元数据
        validation_status: 验证状态，"pending" | "valid" | "invalid"
        created_at: ISO 格式时间戳
        file_path: 存储后的文件路径（可选）
    """

    artifact_id: str
    output_type: OutputType
    content: Union[str, bytes]
    metadata: OutputMetadata
    validation_status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。

        二进制 content 使用 base64 编码，OutputType 序列化为其字符串值。
        """
        if isinstance(self.content, bytes):
            content_value = base64.b64encode(self.content).decode("ascii")
            content_type = "bytes"
        else:
            content_value = self.content
            content_type = "str"

        return {
            "artifact_id": self.artifact_id,
            "output_type": self.output_type.value,
            "content": content_value,
            "content_type": content_type,
            "metadata": self.metadata.to_dict(),
            "validation_status": self.validation_status,
            "created_at": self.created_at,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputArtifact":
        """从字典反序列化。

        根据 content_type 字段决定是否进行 base64 解码。
        """
        content_type = data.get("content_type", "str")
        if content_type == "bytes":
            content: Union[str, bytes] = base64.b64decode(data["content"])
        else:
            content = data["content"]

        return cls(
            artifact_id=data["artifact_id"],
            output_type=OutputType(data["output_type"]),
            content=content,
            metadata=OutputMetadata.from_dict(data["metadata"]),
            validation_status=data.get("validation_status", "pending"),
            created_at=data["created_at"],
            file_path=data.get("file_path"),
        )

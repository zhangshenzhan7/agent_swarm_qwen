"""Output type handlers for Qwen Agent Swarm.

Exports all handler implementations and provides a convenience function
to register all predefined output types with an OutputTypeRegistry.
"""

from .report_handler import ReportHandler
from .code_handler import CodeHandler
from .website_handler import WebsiteHandler
from .image_handler import ImageHandler
from .video_handler import VideoHandler
from .composite_handler import CompositeHandler

from ..models.enums import OutputType
from ..output_registry import OutputTypeRegistry

__all__ = [
    "ReportHandler",
    "CodeHandler",
    "WebsiteHandler",
    "ImageHandler",
    "VideoHandler",
    "CompositeHandler",
    "register_all_handlers",
]


def register_all_handlers(registry: OutputTypeRegistry) -> None:
    """Register all predefined output types and their handlers.

    Args:
        registry: The OutputTypeRegistry to register handlers with.
    """
    registry.register(
        OutputType.REPORT,
        ReportHandler(),
        "Text Report",
        ["text/markdown"],
    )
    registry.register(
        OutputType.CODE,
        CodeHandler(),
        "Source Code",
        ["text/x-python", "application/javascript", "text/plain"],
    )
    registry.register(
        OutputType.WEBSITE,
        WebsiteHandler(),
        "Website",
        ["text/html", "text/css", "application/javascript"],
    )
    registry.register(
        OutputType.IMAGE,
        ImageHandler(),
        "Image",
        ["image/png", "image/jpeg", "image/gif"],
    )
    registry.register(
        OutputType.VIDEO,
        VideoHandler(),
        "Video",
        ["video/mp4", "video/webm", "video/x-msvideo"],
    )
    registry.register(
        OutputType.COMPOSITE,
        CompositeHandler(registry),
        "Composite Output",
        ["application/octet-stream"],
    )

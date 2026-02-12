"""Output type registry for managing output types and their handlers.

Provides a central registry that maps OutputType enum values to their
corresponding IOutputHandler implementations, display names, and MIME types.
"""

from dataclasses import dataclass
from typing import Dict, List

from .models.enums import OutputType
from .interfaces.output_handler import IOutputHandler


@dataclass
class OutputTypeInfo:
    """Metadata about a registered output type.

    Attributes:
        output_type: The output type enum value.
        display_name: Human-readable name for the output type.
        mime_types: List of MIME types associated with this output type.
        handler: The handler instance for this output type.
    """

    output_type: OutputType
    display_name: str
    mime_types: List[str]
    handler: IOutputHandler


class OutputTypeRegistry:
    """Central registry for output types and their handlers.

    Manages registration, lookup, and enumeration of output types.
    Each output type can only be registered once; duplicate registration
    raises ValueError.
    """

    def __init__(self) -> None:
        self._handlers: Dict[OutputType, IOutputHandler] = {}
        self._type_info: Dict[OutputType, OutputTypeInfo] = {}

    def register(
        self,
        output_type: OutputType,
        handler: IOutputHandler,
        display_name: str,
        mime_types: List[str],
    ) -> None:
        """Register an output type with its handler and metadata.

        Args:
            output_type: A valid OutputType enum member.
            handler: An IOutputHandler instance (must not be None).
            display_name: Non-empty human-readable name.
            mime_types: Non-empty list of MIME type strings.

        Raises:
            ValueError: If any required field is missing/invalid or the
                type is already registered.
            TypeError: If output_type is not an OutputType enum member.
        """
        if not isinstance(output_type, OutputType):
            raise TypeError(
                f"output_type must be an OutputType enum member, got {type(output_type).__name__}"
            )
        if handler is None:
            raise ValueError("handler must not be None")
        if not display_name or not isinstance(display_name, str):
            raise ValueError("display_name must be a non-empty string")
        if not mime_types or not isinstance(mime_types, list):
            raise ValueError("mime_types must be a non-empty list")

        if output_type in self._handlers:
            raise ValueError(
                f"Output type '{output_type.value}' is already registered"
            )

        self._handlers[output_type] = handler
        self._type_info[output_type] = OutputTypeInfo(
            output_type=output_type,
            display_name=display_name,
            mime_types=list(mime_types),
            handler=handler,
        )

    def get_handler(self, output_type: OutputType) -> IOutputHandler:
        """Return the handler for the given output type.

        Args:
            output_type: The output type to look up.

        Returns:
            The registered IOutputHandler instance.

        Raises:
            KeyError: If the output type is not registered.
        """
        try:
            return self._handlers[output_type]
        except KeyError:
            raise KeyError(
                f"No handler registered for output type '{output_type.value}'"
            )

    def list_types(self) -> List[OutputTypeInfo]:
        """Return a list of all registered output type info entries."""
        return list(self._type_info.values())

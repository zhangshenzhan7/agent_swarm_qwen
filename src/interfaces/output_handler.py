"""Output handler interface and validation result model.

Defines the IOutputHandler abstract base class that all output type handlers
must implement, and the ValidationResult dataclass for reporting validation
outcomes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..models.output import OutputArtifact


@dataclass
class ValidationResult:
    """Validation outcome for an output artifact.

    Attributes:
        is_valid: Whether the artifact passed validation.
        errors: List of validation failure reasons.
        warnings: List of non-fatal warnings.
    """

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class IOutputHandler(ABC):
    """Abstract base class for output type handlers.

    Each output type (report, code, website, etc.) must provide a concrete
    implementation with type-specific generation, validation, and
    post-processing logic.
    """

    @abstractmethod
    async def generate(
        self, aggregated_result: Any, config: Dict[str, Any]
    ) -> List[OutputArtifact]:
        """Generate output artifacts from an aggregated result.

        Args:
            aggregated_result: The aggregated result from the result aggregator.
            config: Output configuration dictionary.

        Returns:
            A list of generated OutputArtifact instances.
        """
        ...

    @abstractmethod
    async def validate(self, artifact: OutputArtifact) -> ValidationResult:
        """Validate an output artifact using type-specific rules.

        Args:
            artifact: The artifact to validate.

        Returns:
            A ValidationResult indicating success or failure with details.
        """
        ...

    @abstractmethod
    async def post_process(self, artifact: OutputArtifact) -> OutputArtifact:
        """Post-process an artifact (e.g. compress, format, optimize).

        Args:
            artifact: The artifact to post-process.

        Returns:
            The post-processed OutputArtifact.
        """
        ...

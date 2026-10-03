"""Provider contracts and registry for background generation workers."""

from app.providers.base import (
    GenerationKind,
    GenerationProvider,
    NormalizedProviderResult,
    ProviderArtifact,
    ProviderInputImage,
    ProviderPollResult,
    ProviderReferenceImage,
    ProviderRequest,
    ProviderSubmitResult,
)
from app.providers.fal import FalProvider
from app.providers.openai import OpenAIProvider
from app.providers.registry import ProviderRegistry, configured_registry
from app.providers.runway import RunwayProvider

__all__ = [
    "GenerationKind",
    "GenerationProvider",
    "FalProvider",
    "NormalizedProviderResult",
    "OpenAIProvider",
    "ProviderArtifact",
    "ProviderPollResult",
    "ProviderInputImage",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderReferenceImage",
    "ProviderSubmitResult",
    "RunwayProvider",
    "configured_registry",
]

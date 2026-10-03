from collections.abc import Iterable

from app.config import Settings
from app.errors import ApplicationError
from app.providers.base import GenerationProvider
from app.providers.fal import FalProvider
from app.providers.mock import MockProvider
from app.providers.openai import OpenAIProvider
from app.providers.runway import RunwayProvider


class ProviderRegistry:
    def __init__(self, providers: Iterable[GenerationProvider] = ()) -> None:
        self._providers: dict[str, GenerationProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: GenerationProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider is already registered: {provider.name}")
        self._providers[provider.name] = provider

    def resolve(self, name: str) -> GenerationProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise ApplicationError(
                f"Generation provider is not configured: {name}",
                "provider_not_configured",
                503,
            )
        return provider


def configured_registry(settings: Settings) -> ProviderRegistry:
    providers: list[GenerationProvider] = [OpenAIProvider(settings), FalProvider(settings)]
    if settings.mock_ai and settings.app_env != "production":
        providers.append(MockProvider())
    if settings.runwayml_api_secret or not (settings.mock_ai and settings.app_env != "production"):
        providers.append(RunwayProvider(settings))
    return ProviderRegistry(providers)

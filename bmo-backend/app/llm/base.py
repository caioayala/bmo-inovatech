from typing import Protocol


class ProviderError(Exception):
    """Falha conhecida do provider; nunca contém corpo remoto ou credenciais."""


class ProviderUnavailable(ProviderError):
    """Falha transitória elegível para fallback."""


class LLMProvider(Protocol):
    name: str

    async def generate(self, messages: list[dict[str, str]]) -> str: ...

    async def aclose(self) -> None: ...

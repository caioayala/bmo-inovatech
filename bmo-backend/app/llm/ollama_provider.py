import httpx

from app.config import Settings
from app.llm.base import ProviderError, ProviderUnavailable


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings):
        self.model = settings.ollama_model
        self.max_tokens = settings.llm_max_tokens
        self.client = httpx.AsyncClient(
            base_url=settings.ollama_base_url.rstrip("/") + "/",
            timeout=settings.llm_timeout,
        )

    async def generate(self, messages: list[dict[str, str]]) -> str:
        try:
            result = await self.client.post("api/chat", json={
                "model": self.model, "messages": messages, "stream": False,
                "options": {"num_predict": self.max_tokens},
            })
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailable("Ollama sem conexão ou com timeout") from exc
        if result.status_code in {502, 503, 504}:
            raise ProviderUnavailable("Ollama indisponível")
        if not result.is_success:
            raise ProviderError(f"Ollama retornou HTTP {result.status_code}")
        try:
            text = result.json()["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Resposta vazia")
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Ollama retornou resposta inválida") from exc
        return text.strip()

    async def aclose(self) -> None:
        await self.client.aclose()

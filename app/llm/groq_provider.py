from groq import APIConnectionError, APIStatusError, AsyncGroq

from app.config import Settings
from app.llm.base import ProviderError, ProviderUnavailable


class GroqProvider:
    name = "groq"

    def __init__(self, settings: Settings):
        self.model = settings.groq_model
        self.max_tokens = settings.llm_max_tokens
        self.client = AsyncGroq(
            api_key=settings.groq_api_key.get_secret_value(),
            timeout=settings.llm_timeout,
            max_retries=0,
        )

    async def generate(self, messages: list[dict[str, str]]) -> str:
        try:
            result = await self.client.chat.completions.create(
                model=self.model, messages=messages, max_completion_tokens=self.max_tokens,
                stream=False,
            )
        except APIConnectionError as exc:
            raise ProviderUnavailable("Groq sem conexão ou com timeout") from exc
        except APIStatusError as exc:
            if exc.status_code in {502, 503, 504}:
                raise ProviderUnavailable("Groq indisponível") from exc
            raise ProviderError(f"Groq retornou HTTP {exc.status_code}") from exc
        if not result.choices or not result.choices[0].message.content:
            raise ProviderError("Groq retornou resposta vazia")
        text = result.choices[0].message.content.strip()
        if not text:
            raise ProviderError("Groq retornou resposta vazia")
        return text

    async def aclose(self) -> None:
        await self.client.close()

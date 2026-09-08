from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.groq_provider import GroqProvider
from app.llm.ollama_provider import OllamaProvider


def get_llm_provider(settings: Settings, name: str | None = None) -> LLMProvider:
    selected = settings.llm_provider if name is None else name
    providers = {"groq": GroqProvider, "ollama": OllamaProvider}
    if selected not in providers:
        raise ValueError(f"Provider inválido: {selected}")
    return providers[selected](settings)

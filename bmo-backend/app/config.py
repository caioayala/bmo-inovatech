from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["groq", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True,
    )

    llm_provider: ProviderName = "groq"
    llm_fallback_provider: ProviderName | None = None
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    llm_timeout: float = Field(default=10, gt=0, le=120)
    llm_max_tokens: int = Field(default=160, ge=1, le=1024)

    @model_validator(mode="after")
    def validate_providers(self):
        if self.llm_fallback_provider == self.llm_provider:
            raise ValueError("O fallback deve ser diferente do provider principal")
        selected = {self.llm_provider, self.llm_fallback_provider}
        if "groq" in selected:
            if not self.groq_api_key.get_secret_value().strip() or not self.groq_model.strip():
                raise ValueError("Configure GROQ_API_KEY e GROQ_MODEL")
        if "ollama" in selected:
            if not self.ollama_model.strip():
                raise ValueError("Configure OLLAMA_MODEL")
            if not self.ollama_base_url.startswith(("http://", "https://")):
                raise ValueError("OLLAMA_BASE_URL deve usar HTTP ou HTTPS")
        return self

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.config import Settings
from app.llm.base import ProviderError, ProviderUnavailable
from app.llm.factory import get_llm_provider
from app.llm.service import LLMService

logger = logging.getLogger(__name__)


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Mensagem não pode estar vazia")
        return value.strip()


class ChatOutput(BaseModel):
    response: str
    provider: str
    latency_ms: float


def create_app(settings: Settings | None = None, service: LLMService | None = None):
    @asynccontextmanager
    async def lifespan(api):
        logging.basicConfig(level=logging.INFO)
        config = settings if settings is not None else Settings()
        async with AsyncExitStack() as stack:
            active = service
            if active is None:
                primary = get_llm_provider(config)
                stack.push_async_callback(primary.aclose)
                fallback = None
                if config.llm_fallback_provider:
                    fallback = get_llm_provider(config, config.llm_fallback_provider)
                    stack.push_async_callback(fallback.aclose)
                active = LLMService(primary, fallback, config.llm_timeout)
            root = Path(__file__).parent
            prompt = (root / "prompts/bmo_system.txt").read_text(encoding="utf-8")
            context = "\n\n".join(p.read_text(encoding="utf-8")
                                   for p in sorted((root / "context").glob("*.txt")))
            api.state.system_prompt = prompt + "\n\nContexto do laboratório:\n" + context
            api.state.service, api.state.config = active, config
            yield

    api = FastAPI(title="BMO InovaTech", lifespan=lifespan)

    @api.get("/health")
    async def health(request: Request):
        return {"status": "ok", "llm_provider": request.app.state.config.llm_provider}

    @api.post("/chat", response_model=ChatOutput)
    async def chat(payload: ChatInput, request: Request):
        started = perf_counter()
        try:
            messages = [{"role": "system", "content": request.app.state.system_prompt},
                        {"role": "user", "content": payload.message}]
            llm_started = perf_counter()
            try:
                response, provider = await request.app.state.service.generate(messages)
            finally:
                logger.info("llm_total latency_ms=%.2f", (perf_counter() - llm_started) * 1000)
            return ChatOutput(response=response, provider=provider,
                              latency_ms=round((perf_counter() - started) * 1000, 2))
        except ProviderUnavailable as exc:
            raise HTTPException(503, "LLM indisponível; tente novamente") from exc
        except ProviderError as exc:
            logger.error("llm_error reason=%s", exc)
            raise HTTPException(502, "Falha do provider; verifique a configuração e os logs") from exc
        finally:
            logger.info("chat_total latency_ms=%.2f", (perf_counter() - started) * 1000)

    return api


app = create_app()

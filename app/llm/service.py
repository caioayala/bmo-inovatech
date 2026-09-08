import asyncio
import logging
from time import perf_counter

from app.llm.base import LLMProvider, ProviderUnavailable

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None, timeout: float):
        self.primary, self.fallback, self.timeout = primary, fallback, timeout

    async def _attempt(self, provider, messages):
        started = perf_counter()
        try:
            async with asyncio.timeout(self.timeout):
                return await provider.generate(messages)
        except TimeoutError as exc:
            raise ProviderUnavailable("Tempo limite da LLM excedido") from exc
        finally:
            logger.info("llm_attempt provider=%s latency_ms=%.2f", provider.name,
                        (perf_counter() - started) * 1000)

    async def generate(self, messages):
        try:
            return await self._attempt(self.primary, messages), self.primary.name
        except ProviderUnavailable:
            if self.fallback is None:
                raise
            logger.warning("llm_fallback primary=%s fallback=%s",
                           self.primary.name, self.fallback.name)
            return await self._attempt(self.fallback, messages), self.fallback.name

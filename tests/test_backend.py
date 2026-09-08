import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from groq import APIStatusError
from pydantic import ValidationError

from app.config import Settings
from app.llm.base import ProviderError, ProviderUnavailable
from app.llm.factory import get_llm_provider
from app.llm.groq_provider import GroqProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.service import LLMService
from app.main import create_app


def config(**kwargs):
    values = dict(_env_file=None, llm_provider="groq", llm_fallback_provider=None,
                  groq_api_key="test-only", groq_model="test-model",
                  ollama_model="test-local", ollama_base_url="http://localhost:11434")
    values.update(kwargs)
    return Settings(**values)


def fake(name="groq", error=None):
    return SimpleNamespace(name=name, generate=AsyncMock(
        return_value="Eu sou o BMO do InovaTech!", side_effect=error))


@pytest.mark.parametrize("name,cls", [("groq", GroqProvider), ("ollama", OllamaProvider)])
def test_factory(name, cls):
    provider = get_llm_provider(config(llm_provider=name))
    assert isinstance(provider, cls)
    asyncio.run(provider.aclose())


def test_invalid_provider():
    with pytest.raises(ValueError):
        get_llm_provider(config(), "invalid")
    with pytest.raises(ValidationError):
        config(llm_provider="invalid")


@pytest.mark.parametrize("kwargs", [
    {"groq_api_key": ""}, {"groq_model": ""},
    {"llm_fallback_provider": "groq"},
    {"llm_fallback_provider": "ollama", "ollama_model": ""},
    {"llm_timeout": 0},
])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValidationError):
        config(**kwargs)


def test_fallback():
    primary, fallback = fake(error=ProviderUnavailable()), fake("ollama")
    text, name = asyncio.run(LLMService(primary, fallback, 1).generate([]))
    assert name == "ollama" and text
    fallback.generate.assert_awaited_once_with([])


@pytest.mark.parametrize("error", [ProviderError("unauthorized"), RuntimeError("bug")])
def test_no_fallback_for_other_errors(error):
    fallback = fake("ollama")
    with pytest.raises(type(error)):
        asyncio.run(LLMService(fake(error=error), fallback, 1).generate([]))
    fallback.generate.assert_not_awaited()


def test_success_does_not_call_fallback():
    fallback = fake("ollama")
    assert asyncio.run(LLMService(fake(), fallback, 1).generate([]))[1] == "groq"
    fallback.generate.assert_not_awaited()


def test_timeout_uses_fallback():
    async def slow(messages):
        await asyncio.sleep(10)
    primary = SimpleNamespace(name="groq", generate=slow)
    assert asyncio.run(LLMService(primary, fake("ollama"), 0.01).generate([]))[1] == "ollama"


def test_health_chat_and_prompt(caplog):
    primary = fake()
    with TestClient(create_app(config(), LLMService(primary, None, 1))) as client:
        assert client.get("/health").json() == {"status": "ok", "llm_provider": "groq"}
        primary.generate.assert_not_awaited()
        with caplog.at_level("INFO"):
            response = client.post("/chat", json={"message": "Quem é você?"})
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "groq" and data["latency_ms"] >= 0
        assert "BMO" in data["response"]
        messages = primary.generate.call_args.args[0]
        assert messages[0]["role"] == "system" and "InovaTech" in messages[0]["content"]
        assert messages[1] == {"role": "user", "content": "Quem é você?"}
        assert "llm_total" in caplog.text and "chat_total" in caplog.text


@pytest.mark.parametrize("message", ["", "   ", "x" * 2001, None])
def test_invalid_chat(message):
    primary = fake()
    with TestClient(create_app(config(), LLMService(primary, None, 1))) as client:
        assert client.post("/chat", json={"message": message}).status_code == 422
    primary.generate.assert_not_awaited()


@pytest.mark.parametrize("error,status", [(ProviderError("bad key"), 502),
                                         (ProviderUnavailable(), 503)])
def test_chat_error(error, status):
    with TestClient(create_app(config(), LLMService(fake(error=error), None, 1))) as client:
        response = client.post("/chat", json={"message": "Oi"})
        assert response.status_code == status
        assert "bad key" not in response.text


def test_both_unavailable():
    primary = fake(error=ProviderUnavailable())
    fallback = fake("ollama", ProviderUnavailable())
    with TestClient(create_app(config(), LLMService(primary, fallback, 1))) as client:
        assert client.post("/chat", json={"message": "Oi"}).status_code == 503
    fallback.generate.assert_awaited_once()


def test_chat_reports_actual_fallback():
    service = LLMService(fake(error=ProviderUnavailable()), fake("ollama"), 1)
    with TestClient(create_app(config(), service)) as client:
        assert client.post("/chat", json={"message": "Oi"}).json()["provider"] == "ollama"


@pytest.mark.parametrize("status", [200, 400, 401, 404, 429, 500, 502, 503, 504])
def test_ollama_http_contract(status):
    async def run():
        provider = OllamaProvider(config())
        await provider.aclose()
        def handler(request):
            import json
            payload = json.loads(request.content)
            assert request.url.path == "/api/chat"
            assert payload["stream"] is False
            assert payload["model"] == "test-local"
            assert payload["options"]["num_predict"] == 160
            return httpx.Response(status, json={"message": {"content": "Olá!"}})
        provider.client = httpx.AsyncClient(base_url="http://test/", transport=httpx.MockTransport(handler))
        try:
            if status == 200:
                assert await provider.generate([]) == "Olá!"
            else:
                with pytest.raises(ProviderError) as error:
                    await provider.generate([])
                assert isinstance(error.value, ProviderUnavailable) == (status in {502, 503, 504})
        finally:
            await provider.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("status", [401, 404, 429, 500, 502, 503, 504])
def test_groq_status_classification(status):
    async def run():
        provider = GroqProvider(config())
        try:
            response = httpx.Response(status, request=httpx.Request("POST", "https://test"))
            provider.client.chat.completions.create = AsyncMock(
                side_effect=APIStatusError("remote error", response=response, body=None))
            with pytest.raises(ProviderError) as error:
                await provider.generate([])
            assert isinstance(error.value, ProviderUnavailable) == (status in {502, 503, 504})
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_groq_success():
    async def run():
        provider = GroqProvider(config())
        try:
            mock = AsyncMock(return_value=SimpleNamespace(choices=[
                SimpleNamespace(message=SimpleNamespace(content=" Oi! "))]))
            provider.client.chat.completions.create = mock
            assert await provider.generate([]) == "Oi!"
            assert mock.call_args.kwargs["model"] == "test-model"
            assert mock.call_args.kwargs["max_completion_tokens"] == 160
            assert provider.client.max_retries == 0
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_lifecycle_closes_providers(monkeypatch):
    primary = fake()
    primary.aclose = AsyncMock()
    monkeypatch.setattr("app.main.get_llm_provider", lambda settings: primary)
    with TestClient(create_app(config())) as client:
        assert client.get("/health").status_code == 200
        primary.aclose.assert_not_awaited()
    primary.aclose.assert_awaited_once()


@pytest.mark.parametrize("body", [{}, {"message": {"content": " "}},
                                  {"message": {"content": 42}}])
def test_ollama_invalid_response(body):
    async def run():
        provider = OllamaProvider(config())
        await provider.aclose()
        provider.client = httpx.AsyncClient(base_url="http://test/", transport=
            httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
        try:
            with pytest.raises(ProviderError) as error:
                await provider.generate([])
            assert not isinstance(error.value, ProviderUnavailable)
        finally:
            await provider.aclose()
    asyncio.run(run())


def test_ollama_connection_failure():
    async def run():
        provider = OllamaProvider(config())
        await provider.aclose()
        def fail(request):
            raise httpx.ConnectError("offline", request=request)
        provider.client = httpx.AsyncClient(base_url="http://test/", transport=httpx.MockTransport(fail))
        try:
            with pytest.raises(ProviderUnavailable):
                await provider.generate([])
        finally:
            await provider.aclose()
    asyncio.run(run())

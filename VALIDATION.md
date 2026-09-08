# Validação local

Executado em 08/09/2026, Windows, Python 3.12, com `python -m pytest -q`:
**44 testes passaram**. Providers simulados, sem chamadas reais à Groq/Ollama.

Versões principais utilizadas: FastAPI 0.141.1, Groq 1.7.0, HTTPX 0.28.1,
Pydantic Settings 2.15.0, Uvicorn 0.52.4 e pytest 9.1.1.

Dois avisos de depreciação vieram de Starlette/TestClient (HTTPX e alias de
BlockingPortal do AnyIO); não houve falhas de testes.

Docker não está disponível neste ambiente. A imagem e o Compose foram preparados,
mas não executados. Faltam o teste com credenciais/modelos reais e o benchmark na VM.
Nenhum componente foi instalado no Raspberry ou no Proxmox.

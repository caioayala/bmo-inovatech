# BMO — backend do InovaTech

Primeira iteração: FastAPI, Groq/Ollama, contexto local e latência. Execute na VM Linux
do laboratório ou em um computador de desenvolvimento. O Raspberry não instala este backend.
Whisper, Piper, `/talk`, GPIO, display e áudio ficam para as próximas fases.

## Estrutura

```text
app/
  main.py              # /health, /chat e ciclo de vida dos clientes
  config.py            # configuração e validação na inicialização
  llm/
    base.py            # contrato e erros
    factory.py
    groq_provider.py
    ollama_provider.py
    service.py         # timeout e fallback
  prompts/bmo_system.txt
  context/inovatech.txt
tests/test_backend.py
.env.example
requirements.txt
requirements-dev.txt
Dockerfile
docker-compose.yml
```

## Executar localmente (Python 3.11 ou superior)

Na raiz deste projeto, em Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

No PowerShell, use `py -m venv .venv`, `.\.venv\Scripts\Activate.ps1` e
`Copy-Item .env.example .env` nos passos correspondentes.

Edite `.env`: preencha `GROQ_API_KEY` e `GROQ_MODEL` com uma chave e um modelo
disponível na sua conta. O nome do modelo é obrigatório; não há modelo fixo no código.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

A configuração inválida impede a inicialização com uma mensagem indicando o campo.
Nunca versione `.env`. Para desativar fallback, remova/comente a variável
`LLM_FALLBACK_PROVIDER` (não deixe um valor vazio).

## Testar os endpoints

Em um terminal Linux:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Quem é você?"}'
```

Em PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/health
$body = @{message = 'Quem é você?'} | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/chat -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

`/health` retorna `{"status":"ok","llm_provider":"groq"}` quando a aplicação iniciou.
É uma verificação da API, não da disponibilidade remota da LLM.
`/chat` retorna `response`, `provider` efetivamente usado e `latency_ms` numérico.
Troque localhost pelo IP da VM para acessar a partir do Raspberry.
Não há histórico: cada chamada é independente. Mensagens aceitam de 1 a 2000 caracteres
e não podem conter apenas espaços.

## Ollama e fallback

Com Ollama instalado no servidor, baixe o modelo escolhido por meio de `ollama pull NOME_DO_MODELO`.
Configure `OLLAMA_MODEL` com o mesmo nome e `OLLAMA_BASE_URL=http://localhost:11434`.
Use `LLM_PROVIDER=ollama` e reinicie para operar localmente, sem alterar o cliente.
Escolha um modelo pequeno quantizado e meça a latência na VM; não há garantia de tempo
de resposta em CPU. O primeiro carregamento pode exceder o timeout; faça uma chamada
de aquecimento antes da exposição e ajuste o limite se necessário.

Para fallback, mantenha `LLM_PROVIDER=groq` e defina `LLM_FALLBACK_PROVIDER=ollama`.
Ambos os providers precisam estar configurados. Há uma única tentativa por provider.
Somente conexão, timeout e HTTP 502/503/504 permitem fallback. HTTP 400/401/403/404,
429 e 500 não acionam fallback; isso evita mascarar configuração, quota ou erro interno.
Erros de programação não são capturados como falhas transitórias.

`LLM_TIMEOUT` limita cada tentativa inteira em segundos; com fallback o limite de
espera da LLM pode chegar a aproximadamente duas vezes esse valor. `LLM_MAX_TOKENS`
limita a geração. O SDK Groq está com retentativas desativadas.

## Docker Compose na VM

Use Docker somente dentro da VM, não no host Proxmox. Crie e preencha `.env` antes:

```bash
docker compose up -d --build api
```

Para usar Ollama como principal ou fallback:

```bash
docker compose --profile local up -d ollama
docker compose exec ollama ollama pull NOME_DO_MODELO
docker compose --profile local up -d --build api
```

Preencha `OLLAMA_MODEL` com o nome baixado. O Compose define a URL como
`http://ollama:11434`; para um Ollama externo, ajuste essa entrada em `environment`.
Os modelos persistem em um volume; a porta do Ollama não é publicada.
Depois de editar `.env`, execute novamente `docker compose up -d api` para recriar
o contêiner com as variáveis atualizadas.

Esta API é destinada à rede local do laboratório e não implementa autenticação.
Restrinja a porta 8000 à rede necessária. As dependências têm limites de versões;
a imagem Ollama usa `latest`, portanto registre/fixe versões testadas antes da exposição.

## Contexto, logs e testes

Edite `app/prompts/bmo_system.txt` para a personalidade e os arquivos `.txt` em
`app/context/` para fatos confirmados. Não foram inventados nomes, projetos ou horários.
O contexto pequeno é carregado na inicialização; reinicie após alterações
(no Docker, reconstrua a imagem). Não há RAG nem banco de dados.

Logs incluem `llm_attempt`, `llm_total`, `chat_total` e uso de fallback, com tempos
calculados por `time.perf_counter()`. O tempo total cobre o handler, sem trânsito
de rede/serialização HTTP. STT/TTS não existem nesta etapa e não têm métricas fictícias.
Não são registrados prompts, respostas ou chaves. HTTP 503 indica indisponibilidade;
502 indica falha do provider; 422 indica entrada inválida. Consulte os logs para o
status HTTP remoto, sem expor o corpo remoto ao visitante.

```bash
python -m pytest -q
docker compose logs -f api
```

Os testes usam mocks e transporte HTTP simulado, sem chamadas reais à Groq ou ao Ollama.
Validação com modelos reais, latência na VM e execução Docker precisam ser feitas no ambiente alvo.

Referências utilizadas: [SDK oficial Groq](https://github.com/groq/groq-python) e
[API de chat Ollama](https://docs.ollama.com/api/chat).

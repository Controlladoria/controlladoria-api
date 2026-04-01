# Integracao com IA / AI Integration

> Documentacao da integracao com provedores de IA, configuracao, abstracoes e plano de melhoria para troca de provedores.
>
> Documentation of AI provider integration, configuration, abstractions, and improvement plan for provider switching.

---

## PT-BR: Integracao com IA

### Arquitetura Atual

O sistema usa IA para extrair dados estruturados de documentos financeiros. A classe central e `StructuredDocumentProcessor` em `structured_processor.py`.

#### Provedores Suportados

| Provedor | Modelos | Custo (por 1M tokens) | Uso |
|---|---|---|---|
| **OpenAI** | `gpt-5-mini` (default), `gpt-4o`, `gpt-4o-mini` | $0.25/$2.00 (mini) | Extracao principal |
| **Anthropic** | `claude-haiku-4-5` (default), `claude-sonnet-4-5` | $1.00/$5.00 (haiku) | Alternativa |

#### Configuracao

```bash
# .env
AI_PROVIDER=openai          # ou "anthropic"
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_MODEL=gpt-5-mini
ANTHROPIC_MODEL=claude-haiku-4-5
AI_MAX_RETRIES=3
AI_RETRY_DELAY=1
AI_TIMEOUT=60
ENABLE_AI_CACHE=false       # Requer Redis
AI_CACHE_TTL=86400           # 24 horas
```

#### Fluxo de Chamada AI

```
1. Documento recebido (imagem/texto/PDF)
   |
2. Conteudo preparado:
   - Imagem: base64 encode
   - PDF: base64 (nativo) ou convert -> PNG -> base64
   - Excel: DataFrame -> texto formatado
   - XML: Parse deterministico (sem AI)
   |
3. Prompt construido com instrucoes detalhadas:
   - Schema JSON esperado (FinancialDocument)
   - Regras de classificacao (52 categorias)
   - Contexto do usuario (empresa, CNPJ)
   - Instrucoes para income vs expense
   |
4. Chamada com retry (exponential backoff):
   - Tentativa 1: imediata
   - Tentativa 2: apos 1s
   - Tentativa 3: apos 2s
   - Nao retenta erros de cliente (400, 401, 403)
   |
5. Resposta JSON parseada -> FinancialDocument (Pydantic)
   |
6. Validacao financeira (FinancialValidator)
   |
7. Resultado salvo no banco
```

#### Cache de Respostas AI

Quando `ENABLE_AI_CACHE=true` e Redis esta disponivel:
1. Hash SHA-256 do conteudo do documento e gerado
2. Chave de cache: `ai_extract:{type}:{hash[:16]}`
3. Se cache hit: retorna resposta anterior (sem chamar AI)
4. Se cache miss: chama AI e armazena resultado
5. TTL padrao: 24 horas

Isso e util quando o mesmo documento e re-uploadado.

#### Connection Pooling

O cliente HTTP (httpx) e configurado com connection pooling para alta concorrencia:
```python
httpx.Client(
    limits=httpx.Limits(
        max_connections=100,         # Max conexoes simultaneas
        max_keepalive_connections=20, # Conexoes keep-alive
        keepalive_expiry=30.0,       # 30s de keep-alive
    )
)
```

### Nivel de Abstracao Atual

#### O que esta abstraido

1. **Selecao de provedor**: `AI_PROVIDER` env var seleciona OpenAI ou Anthropic
2. **Modelo configuravel**: `OPENAI_MODEL` / `ANTHROPIC_MODEL` env vars
3. **Retry unificado**: `_call_with_retry()` funciona para ambos provedores
4. **Cache unificado**: Mesma logica de cache para ambos
5. **Connection pooling**: Configurado para ambos

#### O que NAO esta abstraido (problemas)

1. **Acoplamento direto**: `StructuredDocumentProcessor.__init__()` importa e instancia `openai.OpenAI()` ou `anthropic.Anthropic()` diretamente
2. **Chamadas diferentes**: Cada metodo de extracao tem blocos `if self.ai_provider == "openai": ... elif "anthropic":` duplicados
3. **Formatos de mensagem diferentes**: OpenAI usa `messages` com `image_url`; Anthropic usa `messages` com `image` media type
4. **Sem interface comum**: Nao existe uma interface/protocolo que ambos provedores implementam
5. **Adicionar novo provedor**: Requer modificar TODOS os metodos de extracao (6+ metodos) com novos `elif`
6. **Sem fallback entre provedores**: Se OpenAI falha, nao tenta Anthropic automaticamente

#### Avaliacao: E "service agnostic"?

**Parcialmente.** A troca de provedor e possivel via env var sem mudanca de codigo, mas adicionar um NOVO provedor (ex: Google Gemini, Mistral, Cohere) requer mudancas significativas em 6+ metodos. Nao e uma refatoracao gigante, mas tambem nao e trivial.

### Plano de Refatoracao para Provider-Agnostic

A seguir esta um plano detalhado para tornar o sistema verdadeiramente agnoistico de provedor AI.

#### Fase 1: Interface AIProvider (Abstraction Layer)

Criar uma interface abstrata que todos os provedores implementam:

```python
# ai/provider_interface.py
from abc import ABC, abstractmethod
from typing import Optional

class AIProvider(ABC):
    """Interface abstrata para provedores de IA"""

    @abstractmethod
    def extract_from_image(
        self,
        image_base64: str,
        image_type: str,
        prompt: str,
        system_prompt: str,
    ) -> dict:
        """Extrair dados de imagem"""
        pass

    @abstractmethod
    def extract_from_pdf(
        self,
        pdf_base64: str,
        prompt: str,
        system_prompt: str,
    ) -> dict:
        """Extrair dados de PDF nativo"""
        pass

    @abstractmethod
    def extract_from_text(
        self,
        text: str,
        prompt: str,
        system_prompt: str,
    ) -> dict:
        """Extrair dados de texto"""
        pass

    @abstractmethod
    def supports_native_pdf(self) -> bool:
        """Se o provedor suporta PDF nativo (sem conversao)"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome do provedor"""
        pass
```

#### Fase 2: Implementacoes por Provedor

```python
# ai/openai_provider.py
class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str, timeout: int):
        import openai
        self.client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self.model = model

    def extract_from_image(self, image_base64, image_type, prompt, system_prompt):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/{image_type};base64,{image_base64}"
                    }}
                ]}
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    # ... similar para pdf e text

# ai/anthropic_provider.py
class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model: str, timeout: int):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self.model = model

    def extract_from_image(self, image_base64, image_type, prompt, system_prompt):
        response = self.client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": f"image/{image_type}",
                    "data": image_base64
                }},
                {"type": "text", "text": prompt}
            ]}],
        )
        return json.loads(response.content[0].text)
```

#### Fase 3: Factory Pattern + Fallback

```python
# ai/provider_factory.py
class AIProviderFactory:
    _providers = {}

    @classmethod
    def register(cls, name: str, provider_class):
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, name: str, **kwargs) -> AIProvider:
        if name not in cls._providers:
            raise ValueError(f"Unknown provider: {name}")
        return cls._providers[name](**kwargs)

# Registro automatico
AIProviderFactory.register("openai", OpenAIProvider)
AIProviderFactory.register("anthropic", AnthropicProvider)
# Facil adicionar: AIProviderFactory.register("gemini", GeminiProvider)

# ai/fallback_provider.py
class FallbackProvider(AIProvider):
    """Tenta provedores em ordem, fallback automatico"""

    def __init__(self, providers: list[AIProvider]):
        self.providers = providers

    def extract_from_image(self, *args, **kwargs):
        for provider in self.providers:
            try:
                return provider.extract_from_image(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed: {e}")
        raise Exception("All AI providers failed")
```

#### Fase 4: Refatorar StructuredDocumentProcessor

```python
class StructuredDocumentProcessor:
    def __init__(self):
        # Antes: if/elif para cada provedor
        # Depois: factory cria o provedor correto
        self.provider = AIProviderFactory.create(
            name=settings.ai_provider,
            api_key=get_api_key(),
            model=get_model(),
            timeout=settings.ai_timeout,
        )

    def _extract_structured_data(self, image_data, image_type, **kwargs):
        # Antes: if openai ... elif anthropic ...
        # Depois: chamada uniforme
        return self.provider.extract_from_image(
            image_base64=image_data,
            image_type=image_type,
            prompt=self._build_extraction_prompt(),
            system_prompt=self._build_system_prompt(),
        )
```

#### Estimativa de Esforco

| Fase | Esforco | Impacto |
|---|---|---|
| 1. Interface | 2-3 horas | Base da abstracao |
| 2. Implementacoes | 4-6 horas | OpenAI + Anthropic |
| 3. Factory + Fallback | 2-3 horas | Extensibilidade |
| 4. Refatorar Processor | 4-6 horas | Integracao final |
| **Total** | **12-18 horas** | Provider-agnostic completo |

**Risco**: Baixo. A logica de negocios nao muda, apenas a camada de abstrac de AI.

---

## EN-US: AI Integration

### Current Architecture

The system uses AI to extract structured data from financial documents. The central class is `StructuredDocumentProcessor` in `structured_processor.py`.

#### Supported Providers

| Provider | Models | Cost (per 1M tokens) | Usage |
|---|---|---|---|
| **OpenAI** | `gpt-5-mini` (default), `gpt-4o`, `gpt-4o-mini` | $0.25/$2.00 (mini) | Primary extraction |
| **Anthropic** | `claude-haiku-4-5` (default), `claude-sonnet-4-5` | $1.00/$5.00 (haiku) | Alternative |

#### Configuration

```bash
# .env
AI_PROVIDER=openai          # or "anthropic"
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_MODEL=gpt-5-mini
ANTHROPIC_MODEL=claude-haiku-4-5
AI_MAX_RETRIES=3             # Retries with exponential backoff
AI_RETRY_DELAY=1             # Base delay in seconds
AI_TIMEOUT=60                # Request timeout
ENABLE_AI_CACHE=false        # Requires Redis
AI_CACHE_TTL=86400           # 24 hours
```

#### AI Call Flow

1. Document received (image/text/PDF)
2. Content prepared (base64 encode, text conversion, etc.)
3. Prompt constructed with detailed instructions (expected JSON schema, 52 categories, user context)
4. Call with retry (exponential backoff, 3 attempts, no retry on client errors)
5. JSON response parsed into Pydantic `FinancialDocument`
6. Financial validation
7. Result saved to database

#### AI Response Caching

When `ENABLE_AI_CACHE=true` and Redis is available:
- SHA-256 hash of document content used as cache key
- Cache hit: returns previous response (no AI call)
- Cache miss: calls AI and stores result
- Default TTL: 24 hours

#### Connection Pooling

HTTP client (httpx) configured for high concurrency: 100 max connections, 20 keepalive connections.

### Current Abstraction Level

#### What IS abstracted
- Provider selection via `AI_PROVIDER` env var
- Configurable models via env vars
- Unified retry logic
- Unified caching
- Connection pooling for both providers

#### What is NOT abstracted (issues)
1. **Direct coupling**: `__init__()` directly imports and instantiates provider SDKs
2. **Different calls**: Each extraction method has duplicated `if openai ... elif anthropic` blocks
3. **Different message formats**: OpenAI uses `image_url`; Anthropic uses `image` media type
4. **No common interface**: No interface/protocol that both providers implement
5. **Adding new provider**: Requires modifying ALL extraction methods (6+ methods)
6. **No cross-provider fallback**: If OpenAI fails, it doesn't try Anthropic

#### Assessment: Is it "service agnostic"?

**Partially.** Switching between the two existing providers is a simple env var change. But adding a NEW provider (e.g., Google Gemini, Mistral) requires significant changes across 6+ methods. Not a massive undertaking, but not trivial either.

### Refactoring Plan for Provider-Agnostic Architecture

See the PT-BR section above for the detailed 4-phase plan:

1. **Phase 1**: Abstract `AIProvider` interface with `extract_from_image`, `extract_from_pdf`, `extract_from_text`, `supports_native_pdf`
2. **Phase 2**: Concrete implementations (`OpenAIProvider`, `AnthropicProvider`)
3. **Phase 3**: Factory pattern + `FallbackProvider` for automatic failover
4. **Phase 4**: Refactor `StructuredDocumentProcessor` to use provider interface

**Estimated effort**: 12-18 hours of focused development.
**Risk**: Low. Business logic doesn't change, only the AI abstraction layer.
**Benefit**: Adding a new provider becomes a single file with ~50 lines of code + factory registration.

### Cost Optimization Tips

1. **Use mini models by default** - `gpt-5-mini` at $0.25/$2.00 per 1M tokens is 10x cheaper than `gpt-4o`
2. **Enable AI cache** - Same document = same result, no duplicate AI calls
3. **Use native PDF** - Smaller payload than image conversion, less tokens consumed
4. **Batch processing** - Process documents in off-peak hours if possible
5. **Monitor usage** - Track API calls per user for cost attribution

### Adding a New AI Provider (Future Guide)

After the refactoring, to add a new provider (e.g., Google Gemini):

```python
# 1. Create ai/gemini_provider.py
class GeminiProvider(AIProvider):
    def __init__(self, api_key, model, timeout):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
    # ... implement 3 abstract methods

# 2. Register in factory
AIProviderFactory.register("gemini", GeminiProvider)

# 3. Set env var
# AI_PROVIDER=gemini
# GEMINI_API_KEY=...

# Done! No changes to StructuredDocumentProcessor needed.
```

---

### Fase 5: Round-Robin Multi-Provider com Pool de Chaves / Phase 5: Round-Robin Multi-Provider with Key Pool

#### PT-BR

##### Problema

Quando muitos usuarios processam documentos simultaneamente, uma unica chave de API atinge rate limits rapidamente. Isso causa falhas e atrasos. Alem disso, depender de um unico provedor significa que qualquer indisponibilidade para todo o processamento.

##### Solucao: Round-Robin com Pool de Chaves

O sistema aceita **multiplas chaves de API para cada provedor** e distribui as requisicoes entre elas usando round-robin. Isso multiplica efetivamente o throughput por N (numero de chaves).

##### Configuracao

```bash
# .env - Multiplas chaves separadas por virgula
OPENAI_API_KEYS=sk-key1,sk-key2,sk-key3
ANTHROPIC_API_KEYS=sk-ant-key1,sk-ant-key2

# Estrategia de distribuicao
AI_DISTRIBUTION_STRATEGY=round_robin  # round_robin | weighted | least_used | failover

# Peso por provedor (para estrategia weighted)
# Distribui 70% para OpenAI (mais barato) e 30% para Anthropic
AI_PROVIDER_WEIGHTS=openai:70,anthropic:30

# Modelos por provedor
OPENAI_MODELS=gpt-5-mini,gpt-4o-mini          # Pode ter multiplos modelos tambem
ANTHROPIC_MODELS=claude-haiku-4-5
```

##### Estrategias de Distribuicao

| Estrategia | Descricao | Melhor para |
|---|---|---|
| **round_robin** | Alterna entre provedores/chaves sequencialmente | Distribuicao uniforme de carga |
| **weighted** | Distribui por peso (ex: 70% OpenAI, 30% Anthropic) | Otimizacao de custo |
| **least_used** | Envia para o provedor/chave com menos uso recente | Evitar rate limits |
| **failover** | Usa provedor principal, troca se falhar | Maxima confiabilidade |

##### Arquitetura do Key Pool

```python
# ai/key_pool.py
import threading
from collections import deque
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

@dataclass
class APIKeyState:
    """Estado de uma chave de API individual"""
    key: str
    provider: str
    requests_count: int = 0
    errors_count: int = 0
    last_used: Optional[datetime] = None
    rate_limited_until: Optional[datetime] = None  # Backoff automatico
    is_healthy: bool = True

class KeyPool:
    """Pool de chaves de API com round-robin e health tracking"""

    def __init__(self):
        self._lock = threading.Lock()
        self._pools: Dict[str, deque[APIKeyState]] = {}
        self._usage_log: List[dict] = []

    def register_keys(self, provider: str, keys: List[str]):
        """Registra multiplas chaves para um provedor"""
        with self._lock:
            self._pools[provider] = deque(
                APIKeyState(key=k, provider=provider) for k in keys
            )

    def get_next_key(self, provider: str) -> Optional[APIKeyState]:
        """Round-robin: retorna proxima chave disponivel"""
        with self._lock:
            pool = self._pools.get(provider)
            if not pool:
                return None

            # Tenta todas as chaves ate encontrar uma saudavel
            for _ in range(len(pool)):
                key_state = pool[0]
                pool.rotate(-1)  # Move para o fim da fila

                # Pula chaves em rate-limit
                if key_state.rate_limited_until and datetime.utcnow() < key_state.rate_limited_until:
                    continue

                if key_state.is_healthy:
                    key_state.last_used = datetime.utcnow()
                    key_state.requests_count += 1
                    return key_state

            return None  # Todas as chaves indisponiveis

    def report_success(self, key_state: APIKeyState):
        """Reporta sucesso para a chave"""
        key_state.errors_count = 0
        key_state.is_healthy = True

    def report_error(self, key_state: APIKeyState, is_rate_limit: bool = False):
        """Reporta erro para a chave"""
        key_state.errors_count += 1
        if is_rate_limit:
            # Backoff exponencial: 30s, 60s, 120s, 240s
            backoff = min(30 * (2 ** (key_state.errors_count - 1)), 300)
            key_state.rate_limited_until = datetime.utcnow() + timedelta(seconds=backoff)
        elif key_state.errors_count >= 5:
            key_state.is_healthy = False  # Marca como indisponivel apos 5 erros

    def get_stats(self) -> dict:
        """Retorna estatisticas de uso por provedor/chave"""
        stats = {}
        for provider, pool in self._pools.items():
            stats[provider] = {
                "total_keys": len(pool),
                "healthy_keys": sum(1 for k in pool if k.is_healthy),
                "total_requests": sum(k.requests_count for k in pool),
                "keys": [
                    {
                        "key_suffix": k.key[-8:],  # Ultimos 8 chars para identificacao
                        "requests": k.requests_count,
                        "errors": k.errors_count,
                        "healthy": k.is_healthy,
                        "rate_limited": bool(k.rate_limited_until and datetime.utcnow() < k.rate_limited_until),
                    }
                    for k in pool
                ]
            }
        return stats
```

##### Round-Robin Dispatcher

```python
# ai/dispatcher.py
class AIDispatcher:
    """Distribui chamadas AI entre provedores e chaves"""

    def __init__(self, key_pool: KeyPool, strategy: str = "round_robin"):
        self.key_pool = key_pool
        self.strategy = strategy
        self._provider_cycle = deque()  # Para round-robin entre provedores
        self._weights = {}

    def configure_providers(self, providers: List[str], weights: Optional[Dict[str, int]] = None):
        self._provider_cycle = deque(providers)
        self._weights = weights or {}

    def get_next(self) -> tuple[str, APIKeyState]:
        """Retorna (provider_name, key_state) para a proxima chamada"""

        if self.strategy == "round_robin":
            return self._round_robin()
        elif self.strategy == "weighted":
            return self._weighted()
        elif self.strategy == "least_used":
            return self._least_used()
        elif self.strategy == "failover":
            return self._failover()

    def _round_robin(self) -> tuple[str, APIKeyState]:
        """Alterna: OpenAI key1 -> Anthropic key1 -> OpenAI key2 -> ..."""
        for _ in range(len(self._provider_cycle)):
            provider = self._provider_cycle[0]
            self._provider_cycle.rotate(-1)

            key = self.key_pool.get_next_key(provider)
            if key:
                return provider, key

        raise Exception("All AI providers exhausted")

    def _weighted(self) -> tuple[str, APIKeyState]:
        """Distribui por peso configurado"""
        import random
        total_weight = sum(self._weights.values())
        r = random.randint(1, total_weight)
        cumulative = 0
        for provider, weight in self._weights.items():
            cumulative += weight
            if r <= cumulative:
                key = self.key_pool.get_next_key(provider)
                if key:
                    return provider, key
        # Fallback to any available
        return self._round_robin()
```

##### Beneficios

| Cenario | Antes (1 chave) | Depois (3 chaves x 2 provedores) |
|---|---|---|
| Rate limit (RPM) | ~500 req/min | ~3.000 req/min |
| Disponibilidade | ~99.5% | ~99.99% (failover) |
| Custo por documento | Fixo por provedor | Otimizado por peso |
| Tempo de recuperacao | Espera rate limit expirar | Troca para outra chave |
| Usuarios simultaneos | ~50-100 | ~300-600 |

##### Estimativa de Esforco

| Fase | Esforco |
|---|---|
| KeyPool + APIKeyState | 3-4 horas |
| AIDispatcher (4 estrategias) | 4-5 horas |
| Integracao com StructuredDocumentProcessor | 3-4 horas |
| Config (.env, Settings) | 1-2 horas |
| Dashboard de stats (sysadmin) | 3-4 horas |
| Testes | 3-4 horas |
| **Total** | **17-23 horas** |

**Pre-requisito**: Fase 1-4 (provider-agnostic) devem estar implementadas antes.

---

#### EN-US

##### Problem

When many users process documents simultaneously, a single API key hits rate limits quickly, causing failures and delays. Additionally, depending on a single provider means any outage stops all processing.

##### Solution: Round-Robin with Key Pool

The system accepts **multiple API keys per provider** and distributes requests across them using round-robin. This effectively multiplies throughput by N (number of keys).

##### Configuration

```bash
# .env - Multiple keys comma-separated
OPENAI_API_KEYS=sk-key1,sk-key2,sk-key3
ANTHROPIC_API_KEYS=sk-ant-key1,sk-ant-key2

# Distribution strategy
AI_DISTRIBUTION_STRATEGY=round_robin  # round_robin | weighted | least_used | failover

# Provider weights (for weighted strategy)
# Sends 70% to OpenAI (cheaper) and 30% to Anthropic
AI_PROVIDER_WEIGHTS=openai:70,anthropic:30
```

##### Distribution Strategies

| Strategy | Description | Best for |
|---|---|---|
| **round_robin** | Alternates between providers/keys sequentially | Even load distribution |
| **weighted** | Distributes by weight (e.g., 70% OpenAI, 30% Anthropic) | Cost optimization |
| **least_used** | Sends to provider/key with least recent usage | Avoiding rate limits |
| **failover** | Uses primary provider, switches on failure | Maximum reliability |

##### Key Pool Architecture

The `KeyPool` class maintains a pool of API keys per provider with:
- **Round-robin rotation** - Each key gets used in turn via a deque
- **Health tracking** - Keys that fail 5+ times are marked unhealthy
- **Automatic backoff** - Rate-limited keys get exponential cooldown (30s, 60s, 120s...)
- **Thread safety** - Lock-protected for concurrent document processing
- **Stats endpoint** - Monitor key usage, health, and rate limit status via sysadmin dashboard

The `AIDispatcher` sits between `StructuredDocumentProcessor` and the provider implementations, selecting which provider + key combination to use for each extraction call.

##### Benefits

| Scenario | Before (1 key) | After (3 keys x 2 providers) |
|---|---|---|
| Rate limit (RPM) | ~500 req/min | ~3,000 req/min |
| Availability | ~99.5% | ~99.99% (failover) |
| Cost per document | Fixed per provider | Optimized by weight |
| Recovery time | Wait for rate limit | Switches to next key |
| Concurrent users | ~50-100 | ~300-600 |

##### Effort Estimate

| Phase | Effort |
|---|---|
| KeyPool + APIKeyState | 3-4 hours |
| AIDispatcher (4 strategies) | 4-5 hours |
| Integration with StructuredDocumentProcessor | 3-4 hours |
| Config (.env, Settings) | 1-2 hours |
| Stats dashboard (sysadmin) | 3-4 hours |
| Tests | 3-4 hours |
| **Total** | **17-23 hours** |

**Prerequisite**: Phases 1-4 (provider-agnostic) must be implemented first.

##### Claude-Readable Implementation Guide

```
TASK: Implement Round-Robin Multi-Provider AI Key Pool

CONTEXT: The system currently uses a single AI provider (AI_PROVIDER env var)
with a single API key. We need to support multiple keys per provider and
distribute requests across them.

DEPENDENCIES: Requires the AIProvider interface from Phase 1-4 refactoring.

STEPS:
1. Create ai/key_pool.py with KeyPool and APIKeyState classes
2. Create ai/dispatcher.py with AIDispatcher class (4 strategies)
3. Update config.py:
   - Add OPENAI_API_KEYS (comma-separated), ANTHROPIC_API_KEYS
   - Add AI_DISTRIBUTION_STRATEGY (default: round_robin)
   - Add AI_PROVIDER_WEIGHTS (optional, for weighted strategy)
4. Update StructuredDocumentProcessor.__init__() to use AIDispatcher
5. Update _call_with_retry() to use dispatcher.get_next() for each attempt
6. Add /sysadmin/ai-stats endpoint showing key pool statistics
7. Write tests for each distribution strategy
8. Update .env.example with new configuration options

RULES:
- Backward compatible: single key config (OPENAI_API_KEY) still works
- Thread-safe: multiple background tasks process documents concurrently
- Never log full API keys, only last 8 characters
- Rate-limited keys auto-recover after cooldown period
```

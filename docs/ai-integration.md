# Integração com IA / AI Integration

> Status: **Implementado**. Este documento descreve a arquitetura atual de integração com IA, incluindo o pool de chaves e a cascata de failover entre três provedores.

---

## Arquitetura Atual

O sistema usa IA para extrair dados estruturados de documentos financeiros. A classe central é `StructuredDocumentProcessor` em `structured_processor.py`.

### Provedores Suportados (cascata de failover)

| Ordem | Provedor | Modelo | Autenticação |
|-------|----------|--------|-------------|
| 1 — Primário | Google Gemini | `gemini-flash-lite-latest` | `GEMINI_API_KEYS` (pool) |
| 2 — Secundário | Amazon Nova via Bedrock | `us.amazon.nova-2-lite-v1:0` | IAM credentials |
| 3 — Fallback | OpenAI | `gpt-5.4-nano` | `OPENAI_API_KEYS` (pool) |

### Configuração

```bash
AI_PROVIDER=gemini          # ou "nova", "openai", ou lista "gemini,nova,openai"
GEMINI_API_KEYS=key1,key2   # pool de chaves para round-robin
OPENAI_API_KEYS=sk-...
NOVA_MODEL=us.amazon.nova-2-lite-v1:0
NOVA_REGION=us-east-2
AI_FAILOVER_ENABLED=true
AI_KEY_UNHEALTHY_THRESHOLD=3
AI_KEY_RECOVERY_SECONDS=300
ENABLE_AI_CACHE=false        # requer Redis
AI_CACHE_TTL=86400
```

### Pool de Chaves (AIKeyPoolManager)

Implementado em `ai_key_pool.py`. Funcionalidades:

- **Round-robin** por chave dentro de cada provedor
- **Health tracking** — chave marcada como unhealthy após N erros consecutivos
- **Recuperação automática** após tempo configurável
- **Thread-safe** para processamento concorrente
- **Stats endpoint** — `GET /admin/ai-pool-stats`

### Fluxo de Chamada de IA

```
Método call_text_prompt(prompt) ou extração multimodal
       │
       ▼
AIKeyPoolManager.get_next_key(provider=primário)
       │
       ▼
Chamada com retry (3 tentativas, backoff exponencial)
       │
       ├── Sucesso → retorna resultado
       └── Todas as chaves do provedor falharam
             └── AI_FAILOVER_ENABLED=true?
                   └── Tenta próximo provedor na cascata
```

### Método call_text_prompt

Helper unificado adicionado ao `StructuredDocumentProcessor` para chamadas text-only (categorização em lote, auditoria). Respeita o provedor ativo e a cascata de failover:

```python
def call_text_prompt(self, prompt: str, max_tokens: int = 4000, temperature: float = 0.1) -> str:
    """Chamada text-only usando o provedor ativo. Retorna texto bruto."""
    if self.ai_provider == "openai":
        # openai.chat.completions.create(...)
    elif self.ai_provider == "gemini":
        # google.genai.models.generate_content(...)
    elif self.ai_provider == "nova":
        # boto3.converse(modelId=self.nova_model, ...)
```

### Cache de Respostas AI

Quando `ENABLE_AI_CACHE=true` e Redis está disponível:
1. Hash SHA-256 do conteúdo do documento é gerado
2. Chave de cache: `ai_extract:{type}:{hash[:16]}`
3. Cache hit: retorna resposta anterior sem chamar IA
4. TTL padrão: 24 horas

---

## Abstração Atual

### O que está abstraído

1. Seleção de provedor via `AI_PROVIDER` env var
2. Pool de chaves com round-robin e health tracking (`AIKeyPoolManager`)
3. Retry unificado (`_call_with_retry()`)
4. Cache unificado para todos os provedores
5. Failover automático entre provedores (`AI_FAILOVER_ENABLED`)
6. Helper `call_text_prompt()` para chamadas text-only em qualquer provedor

### O que ainda não está abstraído

- Formato das chamadas multimodais (imagem/PDF) ainda tem blocos `if/elif` por provedor dentro dos métodos de extração
- Adicionar um quarto provedor requer modificar os métodos de extração com visão (os métodos text-only já são genéricos via `call_text_prompt`)

---

## Plano de Refatoração (Fase Futura)

Para tornar também as chamadas multimodais completamente agnósticas de provedor, uma refatoração futura pode implementar:

### Interface AIProvider

```python
class AIProvider(ABC):
    @abstractmethod
    def extract_from_image(self, image_base64: str, image_type: str, prompt: str) -> dict: ...
    @abstractmethod
    def extract_from_pdf(self, pdf_base64: str, prompt: str) -> dict: ...
    @abstractmethod
    def extract_from_text(self, text: str, prompt: str) -> dict: ...
    @abstractmethod
    def supports_native_pdf(self) -> bool: ...
```

### Factory Pattern

```python
class AIProviderFactory:
    _providers = {}

    @classmethod
    def register(cls, name: str, provider_class): ...

    @classmethod
    def create(cls, name: str, **kwargs) -> AIProvider: ...

# Uso:
AIProviderFactory.register("gemini", GeminiProvider)
AIProviderFactory.register("nova", NovaProvider)
AIProviderFactory.register("openai", OpenAIProvider)
```

**Esforço estimado**: 12–18 horas. **Risco**: baixo — lógica de negócio não muda.

**Benefício**: adicionar um novo provedor multimodal vira um único arquivo de ~50 linhas + registro no factory.

---

## EN-US: AI Integration

### Current Architecture

Three-provider cascade with automatic failover: **Gemini Flash Lite** (primary, cheapest) → **Nova 2 Lite via Bedrock** (secondary, IAM auth) → **GPT-5.4 Nano** (fallback).

Each provider has a key pool with round-robin rotation, per-key health tracking, and automatic recovery. The `AIKeyPoolManager` class in `ai_key_pool.py` manages all of this.

A unified `call_text_prompt()` method handles text-only AI calls (batch categorization, category audit) across all three providers. Vision/multimodal calls still have per-provider branches inside the extraction methods.

### Cache

SHA-256 hash of document content used as cache key. Same document re-uploaded = no AI call. TTL: 24 hours (requires Redis).

### Cost Optimization

1. **Gemini Flash Lite is ~4x cheaper than GPT-5.4 Nano** — keep it as primary
2. **XML and OFX are parsed deterministically** — zero AI cost for these formats
3. **Enable AI cache** — duplicate document uploads cost nothing
4. **Batch categorization** — groups all uncategorized items in one prompt vs individual calls
5. **Category audit** — one prompt covers all rows, not one per row

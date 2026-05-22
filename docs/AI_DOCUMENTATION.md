# Documentação de IA — ControlladorIA

**Versão**: 2.0
**Última atualização**: 2026-05-22

---

## 1. Visão Geral

A ControlladorIA usa modelos de linguagem (LLMs) para três tarefas principais:

1. **Extração estruturada de documentos financeiros** — converte PDFs, imagens, Excel, OFX e XML em dados JSON estruturados com campos padronizados
2. **Categorização em lote** — classifica itens que não foram categorizados na extração primária usando prompt em batch
3. **Auditoria de categorias** — passa todas as categorias atribuídas por uma segunda revisão de IA antes do usuário ver os dados

A IA **não toma decisões autônomas**. Todo output passa por validação humana antes de ser incorporado aos relatórios financeiros.

---

## 2. Modelos Utilizados — Cascata de 3 Provedores

O sistema usa uma cascata de failover automático entre três provedores. Se todas as chaves do provedor primário falharem, o sistema troca automaticamente para o próximo:

| Ordem | Provedor | Modelo | Custo estimado (1M tokens) | Autenticação |
|-------|----------|--------|---------------------------|--------------|
| **1 — Primário** | Google Gemini | `gemini-flash-lite-latest` | ~$0.075 input / $0.30 output | API Key (`GEMINI_API_KEYS`) |
| **2 — Secundário** | Amazon Nova (Bedrock) | `us.amazon.nova-2-lite-v1:0` | ~$0.06 input / $0.24 output | IAM (AWS credentials) |
| **3 — Fallback** | OpenAI | `gpt-5.4-nano` | ~$0.25 input / $1.00 output | API Key (`OPENAI_API_KEYS`) |

### Configuração de Provedores

```bash
# Provedor ativo (pode ser lista para round-robin: "gemini,nova,openai")
AI_PROVIDER=gemini

# Gemini — múltiplas chaves para pool round-robin
GEMINI_API_KEYS=key1,key2,key3
GEMINI_MODEL=gemini-flash-lite-latest

# Nova — usa credenciais IAM (mesmas do S3), sem API key separada
NOVA_MODEL=us.amazon.nova-2-lite-v1:0
NOVA_REGION=us-east-2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# OpenAI — fallback
OPENAI_API_KEYS=sk-key1,sk-key2
OPENAI_MODEL=gpt-5.4-nano

# Failover automático
AI_FAILOVER_ENABLED=true
AI_KEY_UNHEALTHY_THRESHOLD=3   # erros consecutivos antes de marcar chave como inativa
AI_KEY_RECOVERY_SECONDS=300    # segundos antes de tentar chave inativa novamente

# Cache (requer Redis)
ENABLE_AI_CACHE=false
AI_CACHE_TTL=86400   # 24 horas
```

---

## 3. Pool de Chaves e Failover

### AIKeyPoolManager (`ai_key_pool.py`)

Cada provedor tem um pool de chaves com:

- **Round-robin** — rotação sequencial entre chaves disponíveis
- **Health tracking** — chave marcada como "unhealthy" após N erros consecutivos (padrão: 3)
- **Recuperação automática** — chave unhealthy volta ao pool após 5 minutos
- **Thread-safe** — lock protege o pool para processamento concorrente
- **Stats endpoint** — `GET /admin/ai-pool-stats` exibe uso, saúde e rate limits por chave

### Fluxo de Failover

```
Chamada de IA
   └── Tenta provedor primário (Gemini)
         └── Se todas as chaves falharem:
               └── AI_FAILOVER_ENABLED=true?
                     └── Tenta provedor secundário (Nova)
                           └── Se todas as chaves falharem:
                                 └── Tenta fallback (OpenAI)
                                       └── Se falhar: erro retornado ao usuário
```

---

## 4. Tarefas de IA

### 4.1 Extração Estruturada de Documentos

**Classe**: `StructuredDocumentProcessor` (`structured_processor.py`)

**Input**: Documento financeiro (PDF, imagem, Excel, XML, OFX, DOCX, TXT)
**Output**: JSON estruturado (`FinancialDocument` — modelo Pydantic)

**Campos extraídos**:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `document_type` | string | Tipo (nota_fiscal, recibo, boleto, extrato, etc.) |
| `company_name` | string | Nome da empresa emissora |
| `cnpj` | string | CNPJ do emitente |
| `date` | date | Data do documento |
| `due_date` | date | Data de vencimento (se aplicável) |
| `total_amount` | decimal | Valor total |
| `tax_amount` | decimal | Valor de impostos |
| `items` | array | Itens/transações com descrição, valor, categoria |
| `category` | string | Categoria contábil (1 de 52 categorias) |
| `transaction_type` | string | `receita`, `despesa`, ou `transferencia` |

### 4.2 Detecção de Transferências OFX

Durante o parsing OFX, o sistema detecta automaticamente transferências entre contas do mesmo titular **antes** de chamar a IA:

- `TRNTYPE=XFER` → `transaction_type=transferencia`
- Descrição contendo: `"MESMA TITULARIDADE"`, `"MESMA TIT"`, `"TRANSF PROPRIA"`, `"TRANSFERENCIA PROPRIA"` → `transaction_type=transferencia`

Transferências recebem `category=transferencia_interna` e são excluídas do DRE.

### 4.3 Categorização em Lote

Após a extração primária, itens com `category=nao_categorizado` são agrupados e enviados ao AI em um único prompt (batch). Isso é mais eficiente do que chamadas individuais e usa o mesmo helper `call_text_prompt()` que respeita o provedor ativo.

### 4.4 Auditoria de Categorias (novo em v2.0)

Após a categorização em lote, **todas** as categorias atribuídas passam por uma revisão adicional:

```
Extração → Categorização em lote → Auditoria IA → Validação do usuário
```

A auditoria:
1. Envia todas as linhas (descrição + categoria atual) em um único prompt
2. O AI retorna **apenas** as correções necessárias — `{}` vazio significa tudo correto
3. Correções são aplicadas no banco antes do usuário ver qualquer linha
4. Limita-se a 200 itens por documento para manter o prompt gerenciável
5. Falhas na auditoria são não-bloqueantes — o processamento continua sem ela

---

## 5. Sistema de 52 Categorias

Baseado no Plano de Contas padrão brasileiro, mapeado para linhas do DRE:

| Grupo | Categorias |
|-------|-----------|
| **Receita Operacional** | receita_vendas_produtos, receita_servicos, receita_locacao, receita_comissoes, receita_contratos_recorrentes |
| **Deduções** | impostos_sobre_vendas, devolucoes, descontos_concedidos |
| **Custos** | cmv, csp, materia_prima, insumos, comissoes_sobre_vendas, salarios_producao, encargos_sociais_producao, energia_producao, manutencao_equipamentos_producao |
| **Despesas Administrativas** | salarios_administrativos, pro_labore, encargos_sociais_administrativos, aluguel, condominio, agua_energia, material_escritorio, honorarios_contabeis, sistemas_softwares, telefonia_internet |
| **Despesas Comerciais** | marketing_publicidade, propaganda_digital, comissao_vendas, fretes, representantes_comerciais |
| **Resultado Financeiro** | receita_financeira, juros_ativos, descontos_obtidos, juros_passivos, tarifas_bancarias, iof, multas_encargos |
| **Impostos** | irpj, csll, simples_nacional, iptu, taxas_municipais |
| **Não Operacional** | recuperacao_despesas, venda_imobilizado, indenizacoes_recebidas, outras_receitas_eventuais, perdas, indenizacoes_pagas, doacoes, provisoes, depreciacao, amortizacao, outras_despesas_operacionais |
| **Transferência** | transferencia_interna (excluída do DRE) |
| **Não classificado** | nao_categorizado (último recurso) |

---

## 6. Pipeline de Processamento Completo

```
Documento recebido
       │
       ▼
Tipo detectado (extensão + MIME)
       │
       ├── XML (NF-e, NFSe, CTe): Parse determinístico — sem IA
       ├── OFX/OFC: Parse determinístico + detecção de transferência — sem IA
       ├── Excel: DataFrame → texto formatado → IA
       ├── PDF: base64 → IA (visão multimodal)
       ├── Imagem: base64 → IA (visão multimodal)
       └── DOCX/TXT: texto extraído → IA
              │
              ▼
       Prompt construído:
         - Schema JSON esperado
         - 52 categorias com nomes de exibição
         - Contexto do usuário (empresa, CNPJ)
         - Regras de receita vs despesa vs transferência
              │
              ▼
       Chamada com retry (3 tentativas, backoff exponencial)
       via provedor ativo (Gemini → Nova → GPT)
              │
              ▼
       Resposta JSON parseada → FinancialDocument (Pydantic)
              │
              ▼
       Validação financeira (FinancialValidator)
              │
              ▼
       DocumentValidationRows salvas (status: pending_validation)
              │
              ▼
       Categorização em lote (itens nao_categorizado)
              │
              ▼
       Auditoria de categorias (revisão completa por IA)
              │
              ▼
       Status → PENDING_VALIDATION → fila de validação humana
              │
              ▼
       Usuário aprova/corrige → COMPLETED
              │
              ▼
       Dados incorporados nos relatórios (DRE, Balanço, Fluxo de Caixa)
```

---

## 7. Limiares e Fallback

| Situação | Comportamento |
|----------|---------------|
| IA retorna JSON inválido | Remove code blocks markdown, re-tenta parse. Se falha: documento marcado como erro |
| IA não encontra campos | Retorna valores nulos — aceito com warning |
| CNPJ do documento ≠ CNPJ do usuário | Warning exibido, upload permitido |
| API timeout (60s) | Retry com backoff. Após 3 falhas: próximo provedor |
| API rate limit (429) | Retry com backoff exponencial, chave marcada |
| Todas as chaves e provedores falham | Erro retornado ao usuário com mensagem amigável |
| Auditoria de categorias falha | Non-blocking — processamento continua sem ela |
| Categoria não reconhecida pela IA | Fallback para `nao_categorizado` |

---

## 8. Explicabilidade e Controle Humano

A IA não é uma "caixa-preta" neste sistema:

1. **Output estruturado** — toda saída é JSON com campos predefinidos
2. **Validação humana obrigatória** — nenhum dado entra nos relatórios sem aprovação
3. **Categoria visível** — categoria atribuída pela IA é exibida e pode ser corrigida
4. **Comparação visual** — documento original lado a lado com dados extraídos
5. **Trilha de auditoria** — registra se o dado foi `ai_extracted` ou `manually_entered`
6. **Sem autonomia** — a IA só extrai e sugere; o usuário decide

---

## 9. Privacidade

| Dado | Enviado para IA? | Justificativa |
|------|-----------------|---------------|
| Conteúdo do documento (imagem/texto) | Sim | Necessário para extração |
| CNPJ do usuário | Sim (no prompt) | Contexto para classificação |
| Nome da empresa | Sim (no prompt) | Contexto para classificação |
| Email / senha do usuário | **Não** | Nunca enviados |
| Histórico de documentos anteriores | **Não** | Cada documento é independente |

**Retenção pelos provedores:**
- **Google Gemini**: dados da API não usados para treino (API Terms)
- **Amazon Nova**: dados da API não usados para treino (AWS Terms)
- **OpenAI**: dados da API não usados para treino (API Terms)

**Cache local**: quando `ENABLE_AI_CACHE=true`, hash do documento + resposta ficam em Redis por 24h.

---

## 10. Estimativa de Custos

### Por documento (estimativa com Gemini Flash Lite — primário)

| Tipo de Documento | Tokens input | Tokens output | Custo estimado |
|-------------------|-------------|---------------|----------------|
| Nota Fiscal XML | Parse determinístico | — | **$0.00** |
| Extrato OFX | Parse determinístico | — | **$0.00** |
| Nota Fiscal (imagem) | ~2.000 | ~500 | ~$0.0003 |
| PDF de recibo | ~1.500 | ~500 | ~$0.0002 |
| Extrato bancário (Excel, 50 linhas) | ~3.000 | ~800 | ~$0.0005 |
| + Categorização em lote (50 itens) | ~1.500 | ~400 | ~$0.0002 |
| + Auditoria de categorias (50 itens) | ~2.000 | ~200 | ~$0.0002 |

### Projeção mensal

| Volume | Custo estimado (Gemini) | Custo estimado (GPT fallback) |
|--------|------------------------|-------------------------------|
| 100 docs/mês | ~$0.05 | ~$0.20 |
| 1.000 docs/mês | ~$0.50 | ~$2.00 |
| 10.000 docs/mês | ~$5.00 | ~$20.00 |

---

## 11. Monitoramento

| Métrica | Onde ver |
|---------|----------|
| Pool de chaves (saúde, uso, rate limits) | `GET /admin/ai-pool-stats` + sysadmin UI |
| Logs de erro de extração | Sysadmin UI → Errors + CloudWatch Logs |
| Tempo de processamento por documento | Log de aplicação Railway |
| Cache hit/miss rate | Quando Redis ativo, contagem nos logs |

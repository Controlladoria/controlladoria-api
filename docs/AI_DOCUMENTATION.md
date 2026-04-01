# Documentacao de IA — ControlladorIA

**Versao**: 1.0
**Data**: 2026-03-05

---

## 1. Visao Geral

A ControlladorIA usa modelos de linguagem (LLMs) para duas tarefas principais:

1. **Extracao estruturada de documentos financeiros** — converte PDFs, imagens, Excel e texto em dados JSON estruturados com campos padronizados
2. **Extracao de CNPJ** — identifica CNPJs em cartoes CNPJ, notas fiscais e outros documentos brasileiros

A IA **nao toma decisoes autonomas**. Todo output passa por validacao humana antes de ser incorporado aos relatorios financeiros.

---

## 2. Modelos Utilizados

| Provedor | Modelo | Uso | Custo (1M tokens) | Justificativa |
|----------|--------|-----|--------------------|---------------|
| **OpenAI** | `gpt-5-mini` | Extracao principal (default) | $0.25 input / $2.00 output | Melhor custo-beneficio para extracao estruturada |
| **Anthropic** | `claude-haiku-4-5` | Alternativa | $1.00 input / $5.00 output | Backup, melhor com PDFs nativos |

### Versionamento de Modelos

- Modelos sao configurados via variavel de ambiente (`OPENAI_MODEL`, `ANTHROPIC_MODEL`)
- Mudanca de modelo requer apenas alteracao no `.env` — sem deploy de codigo
- Historico de modelos usados:
  - 2025-Q1: `gpt-4o-mini` (lancamento)
  - 2025-Q3: `gpt-4o-mini` → `gpt-5-mini` (upgrade de qualidade/custo)
  - Anthropic: `claude-haiku-4-5` desde o lancamento

---

## 3. Tarefas de IA

### 3.1 Extracao Estruturada de Documentos

**Classe**: `StructuredDocumentProcessor` (`structured_processor.py`)

**Input**: Documento financeiro (PDF, imagem, Excel, XML, OFX, DOCX)
**Output**: JSON estruturado (`FinancialDocument` — modelo Pydantic)

**Campos extraidos**:

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `document_type` | string | Tipo (nota_fiscal, recibo, boleto, extrato, etc.) |
| `company_name` | string | Nome da empresa emissora |
| `cnpj` | string | CNPJ do emitente |
| `date` | date | Data do documento |
| `due_date` | date | Data de vencimento (se aplicavel) |
| `total_amount` | decimal | Valor total |
| `tax_amount` | decimal | Valor de impostos |
| `items` | array | Itens/produtos com descricao, quantidade, valor |
| `category` | string | Categoria contabil (1 de 52 categorias) |
| `payment_method` | string | Forma de pagamento |
| `is_income` | boolean | Se e receita (true) ou despesa (false) |

**Sistema de 52 categorias**: Definido em `accounting/categories.py`, baseado no Plano de Contas padrao brasileiro:
- Receitas (vendas de mercadorias, servicos, outras receitas)
- Deducoes (impostos sobre vendas: ICMS, PIS, COFINS, ISS)
- Custos variaveis (CMV, materia-prima, frete)
- Despesas fixas administrativas (aluguel, salarios, contabilidade)
- Despesas fixas comerciais (marketing, comissoes)
- Resultado financeiro (juros, tarifas bancarias)
- Resultado nao operacional (venda de ativos, multas)

### 3.2 Extracao de CNPJ

**Modulo**: `cnpj_validator.py`

**Input**: Imagem ou PDF de cartao CNPJ, nota fiscal, ou documento comercial
**Output**: Tupla `(recipient_cnpj, sender_cnpj)`

**Fluxo**:
1. Se PDF + OpenAI: converte primeira pagina para PNG via `pdf2image` (OpenAI nao aceita PDF nativo)
2. Se PDF + Anthropic: envia PDF nativo (Anthropic suporta)
3. Imagem: envia base64 direto para API de visao
4. Resposta JSON parseada com ambos CNPJs

**Uso**: Validacao durante upload (documento pertence ao usuario?) e extracao durante cadastro (cartao CNPJ).

---

## 4. Pipeline de Processamento

```
Documento recebido
       |
       v
Tipo detectado (extensao + MIME)
       |
       +-- XML (NF-e): Parse deterministico (sem IA)
       +-- OFX/OFC: Parse deterministico (sem IA)
       +-- Excel: DataFrame -> texto formatado -> IA
       +-- PDF: base64 -> IA (visao ou nativo)
       +-- Imagem: base64 -> IA (visao)
       +-- DOCX: texto extraido -> IA
       |
       v
Prompt construido:
  - Schema JSON esperado
  - 52 categorias com descricao
  - Contexto do usuario (empresa, CNPJ)
  - Regras de receita vs despesa
       |
       v
Chamada com retry (3 tentativas, backoff exponencial):
  - Tentativa 1: imediata
  - Tentativa 2: apos 1s
  - Tentativa 3: apos 2s
  - Erros 400/401/403: nao retenta (erro do cliente)
       |
       v
Resposta JSON parseada -> FinancialDocument (Pydantic)
       |
       v
Validacao financeira (FinancialValidator):
  - Valores numericos validos?
  - Data no formato correto?
  - Categoria valida (1 de 52)?
  - CNPJ no formato correto?
       |
       v
Salvo no banco com status "pending_validation"
       |
       v
Fila de validacao humana -> usuario aprova/corrige
       |
       v
Dados incorporados nos relatorios (DRE, Balanco, Fluxo de Caixa)
```

---

## 5. Limiares e Fallback

| Situacao | Comportamento |
|----------|---------------|
| IA retorna JSON invalido | Remove code blocks markdown, re-tenta parse. Se falha: documento marcado como "erro de processamento" |
| IA nao encontra CNPJ | Retorna `(None, None)` — documento aceito com warning |
| CNPJ do documento != CNPJ do usuario | Warning exibido, upload permitido (nao bloqueante) |
| API timeout (60s) | Retry com backoff. Apos 3 falhas: erro retornado ao usuario |
| API rate limit (429) | Retry com backoff exponencial |
| API indisponivel (5xx) | Retry. Apos 3 falhas: erro com mensagem amigavel |
| Categoria nao reconhecida pela IA | Fallback para "Outras Despesas" ou "Outras Receitas" |
| Valor extraido = 0 ou negativo | Marcado para revisao na fila de validacao |

---

## 6. Explicabilidade

A IA nao e uma "caixa-preta" neste sistema porque:

1. **Output estruturado**: Toda saida e JSON com campos predefinidos — o usuario ve exatamente o que foi extraido
2. **Validacao humana obrigatoria**: Nenhum dado entra nos relatorios sem aprovacao do usuario
3. **Categoria visivel**: A categoria atribuida pela IA (ex: "Aluguel de Imoveis") e exibida na fila de validacao e pode ser corrigida
4. **Comparacao visual**: O usuario pode ver o documento original lado a lado com os dados extraidos
5. **Trilha de auditoria**: O registro de auditoria inclui se o dado foi "ai_extracted" ou "manually_entered"

### O que NAO fazemos (e por que)

- **Nao usamos confidence scores**: Os modelos atuais (GPT-5-mini, Claude Haiku) nao fornecem scores de confianca nativos para extracao estruturada. Em vez disso, confiamos na validacao humana.
- **Nao fazemos re-treino**: Usamos modelos pre-treinados via API. Nao fazemos fine-tuning nem re-treino. Melhoria de qualidade vem de prompt engineering.
- **Nao usamos embeddings/RAG**: Cada documento e processado independentemente. Nao ha base de conhecimento vetorial.

---

## 7. Dados e Privacidade

### Dados enviados para APIs de IA

| Dado | Enviado? | Justificativa |
|------|----------|---------------|
| Conteudo do documento (imagem/texto) | Sim | Necessario para extracao |
| CNPJ do usuario | Sim (no prompt) | Contexto para classificacao |
| Nome da empresa | Sim (no prompt) | Contexto para classificacao |
| Dados pessoais do usuario (email, senha) | Nao | Nunca enviados |
| Historico de documentos anteriores | Nao | Cada documento e independente |

### Retencao de dados pela IA

- **OpenAI**: Dados enviados via API nao sao usados para treino (API Terms of Use)
- **Anthropic**: Dados enviados via API nao sao usados para treino (API Terms of Use)
- **Cache local**: Quando `ENABLE_AI_CACHE=true`, hash do documento + resposta ficam em Redis por 24h

### Isolamento Multi-Tenant

Documentos de diferentes organizacoes/usuarios nunca sao misturados em uma mesma chamada de IA. Cada documento e processado individualmente com contexto apenas do seu proprietario.

---

## 8. Custos

### Estimativa por documento

| Tipo de Documento | Tokens estimados (input) | Tokens estimados (output) | Custo (gpt-5-mini) |
|-------------------|--------------------------|---------------------------|---------------------|
| Nota Fiscal (imagem) | ~2.000 | ~500 | ~$0.0015 |
| Nota Fiscal (PDF) | ~1.500 | ~500 | ~$0.0014 |
| Extrato bancario (Excel, 50 linhas) | ~3.000 | ~800 | ~$0.0024 |
| Cartao CNPJ (extracao) | ~1.000 | ~100 | ~$0.0005 |

### Projecao mensal

| Volume | Custo estimado (gpt-5-mini) |
|--------|----------------------------|
| 100 docs/mes | ~$0.15 |
| 1.000 docs/mes | ~$1.50 |
| 10.000 docs/mes | ~$15.00 |

---

## 9. Monitoramento em Producao

### Metricas atuais

- **Logs de erro**: Falhas de API logadas com `cnpj_validator - ERROR` e `structured_processor - ERROR`
- **Tempo de processamento**: Logado por documento
- **Cache hit rate**: Quando Redis ativo, contagem de hits/misses

### Metricas recomendadas (roadmap)

- Precisao de classificacao (% de documentos corrigidos na validacao vs aceitos como estao)
- Taxa de erro por tipo de documento
- Custo acumulado por organizacao
- Latencia media por provedor

---

## 10. Registro de Inferencia

Cada documento processado pela IA gera um registro no banco de dados:

| Campo | Tabela | Descricao |
|-------|--------|-----------|
| `ai_provider` | `documents` | Provedor usado ("openai" ou "anthropic") |
| `ai_model` | `documents` | Modelo usado ("gpt-5-mini") |
| `extracted_data_json` | `documents` | Output completo da IA (JSON) |
| `processing_status` | `documents` | Status (processed, error, pending_validation) |
| `created_at` | `documents` | Timestamp do processamento |
| `user_id` | `documents` | Quem enviou |
| `action` | `audit_logs` | "document_created" com source "ai_extracted" |
| `before_value` / `after_value` | `audit_logs` | Mudancas feitas pelo usuario na validacao |

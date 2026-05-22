# ControlladorIA — Documentação Completa

> **Versão**: 2.0 | **Última atualização**: 2026-05-22
> **Stack**: FastAPI + SQLAlchemy 2 + Next.js 16 + TypeScript + AWS Lambda + Gemini/Nova/GPT

---

## Índice / Table of Contents

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Repositórios](#repositórios)
- [Stack de Tecnologia](#stack-de-tecnologia)
- [Estrutura do controlladoria-api](#estrutura-do-controlladoria-api)
- [Entidades do Banco de Dados](#entidades-do-banco-de-dados)
- [API Endpoints](#api-endpoints)
- [Pipeline de Processamento de Documentos](#pipeline-de-processamento-de-documentos)
- [IA — Cascata de 3 Provedores](#ia--cascata-de-3-provedores)
- [Relatórios Financeiros](#relatórios-financeiros)
- [Auth e Autorização](#auth-e-autorização)
- [Setup de Desenvolvimento](#setup-de-desenvolvimento)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Documentação Relacionada](#documentação-relacionada)

---

## Visão Geral

ControlladorIA é uma plataforma SaaS de contabilidade automatizada por inteligência artificial, projetada para PMEs brasileiras e escritórios de contabilidade. O sistema recebe documentos financeiros (notas fiscais, recibos, extratos bancários, planilhas Excel, XML de NFe/NFSe), extrai automaticamente os dados usando IA e gera relatórios contábeis padronizados: **DRE**, **Balanço Patrimonial** e **Fluxo de Caixa**.

### Funcionalidades Principais

1. **Upload inteligente** — PDF, imagem, Excel, XML (NFe/NFSe/CTe), OFX/OFC, DOCX, TXT
2. **Extração por IA** — Gemini Flash Lite (primário) → Nova 2 Lite (secundário) → GPT-5.4 Nano (fallback)
3. **Classificação automática** — 52 categorias baseadas no Plano de Contas brasileiro
4. **Auditoria de categorias** — revisão de IA pós-extração antes da validação humana
5. **Validação de dados** — motor de validação financeira com revisão humana obrigatória
6. **Relatórios contábeis** — DRE, Balanço Patrimonial, Fluxo de Caixa; exportação PDF/Excel/CSV
7. **Multi-tenant** — isolamento completo por organização, múltiplos membros por org
8. **MFA** — TOTP (Google Authenticator) + email OTP + dispositivos confiáveis 30 dias
9. **Assinaturas** — integração Stripe, planos Starter/Equipe/Enterprise em BRL (PIX, boleto, cartão)
10. **Console interno** — sysadmin UI para operações, impersonação e rastreamento de erros

---

## Arquitetura

```
                                +---------------------+
                                | controlladoria-     |
                                | website             |
                                | Next.js 16.2        |
                                | (Site de marketing) |
                                +---------------------+

+---------------------+         +---------------------+         +---------------------+
| controlladoria-ui   |  HTTP   | controlladoria-api  |  HTTP   | controlladoria-     |
| Next.js 16.1        | ------> | FastAPI · Python 3.12| <------ | sysadmin-ui         |
| React 19            |         | Port 8000           |         | Next.js 14.2        |
| Port 3000           |         +----------+----------+         | Port 3001           |
+---------------------+                    |                    +---------------------+
                                           |
                        +------------------+------------------+
                        |                  |                  |
                 +------+------+    +------+------+    +-----+------+
                 | PostgreSQL  |    | Redis       |    | AWS S3     |
                 | 16 (Railway)|    | (Cache +    |    | (Armazena- |
                 |             |    |  Celery)    |    |  mento)    |
                 +-------------+    +------+------+    +------------+
                                           |
                                    +------+------+
                                    | controlladoria-
                                    | jobs         |
                                    | Celery +     |
                                    | Lambda       |
                                    +------+------+
                                           |
                        +------------------+------------------+
                        |                  |                  |
                 +------+------+    +------+------+    +-----+------+
                 | Google      |    | AWS Bedrock |    | OpenAI     |
                 | Gemini Flash|    | Nova 2 Lite |    | GPT-5.4    |
                 | Lite (1º)   |    | (2º)        |    | Nano (3º)  |
                 +-------------+    +-------------+    +------------+
```

---

## Repositórios

| Repo | Propósito | Stack | Porta |
|------|-----------|-------|-------|
| `controlladoria-api` | API REST, lógica de negócio, auth | Python 3.12, FastAPI, SQLAlchemy 2, Alembic | 8000 |
| `controlladoria-jobs` | Processamento assíncrono (docs, cleanup) | Python, Celery + Redis, AWS Lambda | N/A |
| `controlladoria-ui` | App web do cliente | Next.js 16.1, React 19, Tailwind 4, Radix UI | 3000 |
| `controlladoria-sysadmin-ui` | Console admin interno | Next.js 14.2, React 18, Tailwind 3 | 3001 |
| `controlladoria-website` | Landing page de marketing | Next.js 16.2, React 19, Tailwind 4 | 3000 |

### Infraestrutura de Deploy

| Serviço | Plataforma | CI/CD |
|---------|------------|-------|
| API | Railway.app | GitHub Actions → Railway CLI |
| Jobs (Lambda) | AWS Lambda (us-east-2) | GitHub Actions → Docker → ECR → Lambda CLI |
| UI do cliente | AWS Amplify | Amplify built-in (push to main) |
| Sysadmin UI | AWS Amplify | Amplify built-in (push to main) |
| Website | Vercel | N/A (estático) |

---

## Stack de Tecnologia

### Backend (controlladoria-api + controlladoria-jobs)

| Componente | Tecnologia | Versão | Propósito |
|-----------|-----------|--------|-----------|
| Framework | FastAPI | ≥ 0.109 | API REST async |
| ORM | SQLAlchemy | ≥ 2.0 | Mapeamento objeto-relacional |
| Migrações | Alembic | ≥ 1.13 | Versionamento de schema |
| Auth | JWT (python-jose) | ≥ 3.3 | Tokens de autenticação |
| Senhas | bcrypt (passlib 4.0.1) | fixado | Hash de senhas |
| AI — Primário | google-genai | ≥ 0.8 | Gemini Flash Lite |
| AI — Secundário | boto3 | ≥ 1.34 | Nova 2 Lite via Bedrock |
| AI — Fallback | openai | ≥ 1.12 | GPT-5.4 Nano |
| Pagamentos | stripe | ≥ 8.0 | Assinaturas |
| Email | resend | ≥ 0.8 | Emails transacionais |
| Storage | boto3 | ≥ 1.34 | AWS S3 |
| Queue (Celery) | celery + redis | ≥ 5.3 | Processamento assíncrono |
| Rate limit | slowapi | ≥ 0.1.9 | Limitação de requisições |
| Validação | pydantic | ≥ 2.6 | Validação de dados |
| Sanitização | bleach | ≥ 6.1 | Limpeza de input HTML |

### Frontend (controlladoria-ui)

| Componente | Tecnologia | Versão |
|-----------|-----------|--------|
| Framework | Next.js (App Router) | 16.1.6 |
| React | React | 19.2.3 |
| Estilo | Tailwind CSS | 4 |
| Componentes | Radix UI | 1.x–2.x |
| Gráficos | Recharts | 3.6.0 |
| HTTP client | axios | 1.13.2 |
| Pagamentos | @stripe/stripe-js | 8.6.4 |
| Validação | zod | 4.3.6 |

### Sysadmin UI (controlladoria-sysadmin-ui)

| Componente | Tecnologia | Versão |
|-----------|-----------|--------|
| Framework | Next.js (App Router) | 14.2.35 |
| React | React | 18.3.1 |
| Estilo | Tailwind CSS | 3.4.4 |
| Gráficos | Recharts | 2.12.7 |
| Ícones | lucide-react | 0.414.0 |

### Mobile (controlladoria-app)

| Componente | Tecnologia | Versão |
|-----------|-----------|--------|
| Framework | Expo | SDK 54 |
| React Native | react-native | 0.76.6 |
| React | React | 18.3.1 |
| Navigation | expo-router | ~4.0.21 |
| Build | EAS Build (cloud) | — |

---

## Estrutura do controlladoria-api

```
controlladoria-api/
├── api.py                      # FastAPI app principal, middleware, startup
├── config.py                   # Pydantic Settings (todas as configs)
├── database.py                 # Modelos SQLAlchemy (User, Document, etc.)
├── models.py                   # Modelos Pydantic (request/response)
├── structured_processor.py     # StructuredDocumentProcessor — extração AI
├── ai_key_pool.py              # AIKeyPoolManager — pool de chaves round-robin
├── validation.py               # Motor de validação financeira
├── email_service.py            # EmailService (Resend)
├── exception_handlers.py       # Handlers globais de exceções
├── i18n.py                     # Mensagens PT-BR / EN
├── cnpj_validator.py           # BrasilAPI / SERPRO CNPJ lookup
│
├── auth/
│   ├── security.py             # JWT, bcrypt, tokens
│   ├── service.py              # Registro, login, reset
│   ├── dependencies.py         # FastAPI deps (get_current_user)
│   ├── permissions.py          # RBAC com claims granulares
│   ├── mfa_service.py          # MFA (TOTP + email OTP)
│   ├── session_manager.py      # Gerenciamento de sessões (limite 2)
│   └── team_management.py      # Convites e equipe
│
├── routers/
│   ├── auth.py                 # /auth/* — registro, login, MFA, sessions
│   ├── documents.py            # /documents/* — upload, CRUD, validação
│   ├── transactions.py         # /transactions/* — relatórios, DRE, exportação
│   ├── organizations.py        # /organizations/* — multi-org, convites
│   ├── team.py                 # /team/* — membros, convites
│   ├── billing.py              # /stripe/* — Stripe checkout, portal, webhook
│   ├── clients.py              # /clients/* — fornecedores/clientes
│   ├── initial_balance.py      # /initial-balance/* — saldos de abertura
│   ├── sessions.py             # /sessions/* — dispositivos ativos
│   ├── admin.py                # /admin/* — painel, ai-pool-stats
│   ├── sysadmin.py             # /sysadmin/* — impersonação, erros
│   ├── contact.py              # /contact — formulário público
│   └── account.py              # /account/* — perfil
│
├── accounting/
│   ├── categories.py           # 52 categorias + mapeamento para DRE
│   ├── accounting_engine.py    # AccountingEngine
│   ├── dre_calculator.py       # DRECalculator + exportação
│   ├── balance_sheet_calculator.py  # BalanceSheetCalculator
│   └── cash_flow_calculator.py      # CashFlowCalculator
│
├── middleware/
│   └── subscription.py         # require_active_subscription()
│
├── storage/
│   └── s3_service.py           # AWS S3 upload/download/delete
│
├── cache/
│   └── redis_cache.py          # RedisCache (respostas AI, sessões)
│
├── stripe_integration/
│   ├── service.py              # Lógica de assinaturas
│   └── webhooks.py             # Handlers de webhook
│
└── alembic/
    └── versions/               # Arquivos de migração
```

---

## Entidades do Banco de Dados

| Entidade | Propósito |
|---------|-----------|
| `User` | Contas com MFA, theme prefs, org ativa |
| `Organization` | Dados de empresa multi-tenant (CNPJ, endereço, logo) |
| `OrgMembership` | Mapeamento usuário-org com papel (owner/admin/accountant/bookkeeper/viewer/api_user) |
| `OrgInvitation` | Tokens de convite cross-org |
| `Document` | Documentos financeiros com status de extração |
| `DocumentValidationRow` | Linhas de transação extraídas aguardando revisão humana |
| `ChartOfAccountsEntry` | Plano de contas por org |
| `JournalEntry` / `JournalEntryLine` | Lançamentos contábeis (partida dobrada) |
| `Client` | Fornecedores/clientes por org |
| `KnownItem` | Cache de categorização por usuário (aprendizado) |
| `Subscription` / `Plan` | Estado de billing Stripe |
| `OrgBankAccount` | Contas bancárias por org |
| `OrgInitialBalance` | Saldos de abertura por ano fiscal |
| `UserSession` | Rastreamento de sessões ativas (dispositivo, IP, confiança) |
| `UserClaim` | Permissões granulares customizadas |
| `APIKey` | Tokens de acesso programático |
| `AuditLog` | Trilha de auditoria append-only |
| `ContactSubmission` | Dados do formulário de contato |
| `PasswordReset` | Tokens de reset de senha |

---

## API Endpoints

### Auth (`/auth`)

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/auth/register` | Cadastro (rate limit: 5/hora) |
| POST | `/auth/login` | Login → JWT access + refresh |
| POST | `/auth/logout` | Logout |
| POST | `/auth/refresh` | Renovar access token |
| POST | `/auth/forgot-password` | Solicitar reset (rate limit: 3/hora) |
| POST | `/auth/reset-password` | Confirmar reset |
| GET | `/auth/verify-email` | Verificar email |
| POST | `/auth/mfa/setup` | Configurar TOTP |
| POST | `/auth/mfa/enable` | Ativar MFA |
| POST | `/auth/mfa/verify` | Verificar código MFA |
| POST | `/auth/mfa/disable` | Desativar MFA |
| GET | `/auth/cnpj/{cnpj}` | Lookup CNPJ (BrasilAPI/SERPRO) |

### Documentos (`/documents`)

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/documents/upload` | Upload único (rate limit: 60/minuto) |
| POST | `/documents/upload/bulk` | Upload múltiplo |
| POST | `/documents/upload/csv` | Import CSV de transações |
| GET | `/documents/` | Listar documentos da org |
| GET | `/documents/{id}` | Detalhes + linhas de validação |
| PUT | `/documents/{id}` | Atualizar metadados |
| DELETE | `/documents/{id}` | Deletar documento |
| GET | `/documents/{id}/download` | Download do arquivo original |
| GET | `/documents/{id}/preview` | Preview do documento |
| POST | `/documents/{id}/validate` | Validar todas as linhas |
| PUT | `/documents/validation-rows/{row_id}` | Atualizar linha individual |
| GET | `/documents/queue-status` | Status da fila de processamento |
| POST | `/documents/manual-entry` | Entrada manual de transação |

### Transações e Relatórios (`/transactions`)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/transactions/stats` | Estatísticas gerais |
| GET | `/transactions/reports/summary` | Resumo financeiro |
| GET | `/transactions/reports/by-category` | Resumo por categoria |
| GET | `/transactions/reports/monthly` | Resumo mensal |
| GET | `/transactions/reports/dre` | DRE completa |
| GET | `/transactions/reports/balance-sheet` | Balanço Patrimonial |
| GET | `/transactions/reports/cash-flow` | Fluxo de Caixa |
| GET | `/transactions/reports/trial-balance` | Balancete |
| GET | `/transactions/reports/ledger` | Razão Geral |
| GET | `/transactions/reports/chart-of-accounts` | Plano de Contas |
| GET | `/transactions/dashboard-metrics` | Métricas para dashboard |
| POST | `/transactions/journal-entries` | Criar lançamento contábil |
| GET | `/transactions/export/excel` | Exportar Excel |
| GET | `/transactions/export/pdf` | Exportar PDF |
| GET | `/transactions/export/csv` | Exportar CSV |
| GET | `/transactions/initial-balance` | Saldos de abertura |

### Organizações (`/organizations`)

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/organizations/` | Criar organização |
| GET | `/organizations/` | Listar orgs do usuário |
| POST | `/organizations/switch` | Trocar org ativa |
| POST | `/organizations/invite` | Convidar para org |
| POST | `/organizations/accept/{token}` | Aceitar convite |
| DELETE | `/organizations/decline/{token}` | Recusar convite |

### Billing (`/stripe`)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/stripe/plans` | Listar planos disponíveis |
| POST | `/stripe/create-checkout-session` | Criar sessão de checkout |
| POST | `/stripe/create-portal-session` | Portal do cliente Stripe |
| GET | `/stripe/subscription-status` | Status da assinatura |
| POST | `/stripe/cancel` | Cancelar assinatura |
| POST | `/stripe/webhook` | Webhook Stripe (assinado) |

### Admin (`/admin`)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/admin/stats` | Métricas da plataforma |
| GET | `/admin/users` | Listar usuários |
| GET | `/admin/recent-activity` | Atividade recente |
| GET | `/admin/audit-logs` | Trilha de auditoria |
| GET | `/admin/ai-pool-stats` | Saúde do pool de chaves AI |

### Sysadmin (`/sysadmin`)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/sysadmin/dashboard/stats` | Métricas globais (MRR, usuários, erros) |
| GET | `/sysadmin/users/search` | Busca full-text de usuários |
| GET | `/sysadmin/users/{id}` | Detalhes do usuário |
| POST | `/sysadmin/users/{id}/impersonate` | Gerar JWT de impersonação |
| GET | `/sysadmin/errors` | Log de erros com stack traces |

---

## Pipeline de Processamento de Documentos

```
POST /documents/upload
       │
       ▼
Validação (tipo, tamanho ≤ 30MB, CNPJ, assinatura ativa)
       │
       ▼
Arquivo → AWS S3 (ou filesystem local em dev)
       │
       ▼
Document criado (status: PENDING)
       │
       ▼
DocumentQueueManager.enqueue() → máx 3 concorrentes
       │
       ▼
SQS → Lambda (ou Celery worker)
       │
       ▼
StructuredDocumentProcessor:
   ├── XML (NFe/NFSe/CTe): Parse determinístico — sem IA
   ├── OFX/OFC: Parse determinístico + detecção de transferências — sem IA
   ├── Excel: DataFrame → texto formatado → IA
   ├── PDF: base64 → IA (visão multimodal)
   ├── Imagem: base64 → IA (visão multimodal)
   └── DOCX/TXT: texto extraído → IA
       │
       ▼
Chamada AI (3 tentativas, backoff exponencial)
via cascata: Gemini Flash Lite → Nova 2 Lite → GPT-5.4 Nano
       │
       ▼
JSON parseado → FinancialDocument (Pydantic)
       │
       ▼
DocumentValidationRows criadas (status: pending_validation)
       │
       ▼
Categorização em lote (itens nao_categorizado → call_text_prompt())
       │
       ▼
Auditoria de categorias (revisão IA de todas as linhas — non-blocking)
       │
       ▼
Status: PENDING_VALIDATION → fila de revisão humana
       │
       ▼
Usuário aprova/corrige → COMPLETED
       │
       ▼
Dados disponíveis em DRE, Balanço, Fluxo de Caixa
```

---

## IA — Cascata de 3 Provedores

| Ordem | Provedor | Modelo | Auth |
|-------|---------|--------|------|
| 1 — Primário | Google Gemini | `gemini-flash-lite-latest` | `GEMINI_API_KEYS` (pool) |
| 2 — Secundário | Amazon Nova via Bedrock | `us.amazon.nova-2-lite-v1:0` | IAM credentials |
| 3 — Fallback | OpenAI | `gpt-5.4-nano` | `OPENAI_API_KEYS` (pool) |

### AIKeyPoolManager (`ai_key_pool.py`)

- **Round-robin** entre chaves disponíveis por provedor
- **Health tracking** — chave marcada como unhealthy após N erros consecutivos (padrão: 3)
- **Recuperação automática** — chave unhealthy volta ao pool após 5 minutos
- **Thread-safe** — lock protege o pool para processamento concorrente
- **Stats endpoint** — `GET /admin/ai-pool-stats`

### Fases de IA por Documento

1. **Extração** — parse do documento e extração de campos estruturados
2. **Categorização em lote** — itens `nao_categorizado` agrupados em um único prompt
3. **Auditoria de categorias** — revisão de todas as categorias atribuídas; AI retorna apenas correções (`{}` = tudo correto); non-blocking

### Formatos por Provedor

- **XML (NFe/NFSe/CTe)** e **OFX/OFC**: processamento determinístico, zero custo de IA
- **PDF/Imagem**: enviados como base64 para extração multimodal
- **Excel/DOCX/TXT**: convertidos para texto formatado antes do prompt

---

## Relatórios Financeiros

Todos calculados em tempo real a partir dos DocumentValidationRows com status COMPLETED, filtrados por org e período.

### DRE (Demonstração do Resultado do Exercício)

Endpoint: `GET /transactions/reports/dre?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`

Estrutura:
```
Receita Bruta
  (-) Deduções da Receita
= Receita Líquida
  (-) Custos Variáveis (CMV/CSP)
= Margem de Contribuição
  (-) Despesas Administrativas Fixas
  (-) Despesas Comerciais Fixas
  (-) Depreciação e Amortização
= Resultado Operacional (EBITDA ajustado)
  (+/-) Resultado Financeiro
= Resultado Antes dos Impostos
  (-) IRPJ / CSLL / Simples Nacional
= Resultado Líquido do Período
```

### Balanço Patrimonial

Endpoint: `GET /transactions/reports/balance-sheet?date=YYYY-MM-DD`

Baseado no Plano de Contas + JournalEntries com partida dobrada verdadeira. Valores em centavos.

### Fluxo de Caixa

Endpoint: `GET /transactions/reports/cash-flow?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`

Método indireto: Resultado Líquido → ajustes não-caixa → variação do capital de giro → caixa das atividades (operacional, investimento, financiamento).

### Exportação

| Formato | Endpoint |
|---------|---------|
| Excel (.xlsx) | `/transactions/export/excel` |
| PDF | `/transactions/export/pdf` (reportlab) |
| CSV | `/transactions/export/csv` |

### 52 Categorias Contábeis

| Grupo | Exemplos |
|-------|---------|
| Receita Operacional | receita_vendas_produtos, receita_servicos, receita_locacao |
| Deduções | impostos_sobre_vendas, devolucoes, descontos_concedidos |
| Custos | cmv, csp, materia_prima, salarios_producao |
| Despesas Administrativas | salarios_administrativos, aluguel, honorarios_contabeis |
| Despesas Comerciais | marketing_publicidade, fretes, comissao_vendas |
| Resultado Financeiro | juros_passivos, tarifas_bancarias, receita_financeira |
| Impostos | irpj, csll, simples_nacional, iptu |
| Não Operacional | depreciacao, amortizacao, perdas, provisoes |
| Transferência | transferencia_interna (excluída do DRE) |
| Não classificado | nao_categorizado (último recurso) |

---

## Auth e Autorização

### Fluxo de Autenticação

```
Login (email + senha)
  → JWT access (30 min) + refresh (7 dias)
    → MFA (se habilitado):
        → TOTP (Google Authenticator) OU Email OTP
        → Dispositivo confiável (pula por 30 dias)
    → Cookies httponly (UI) / localStorage (sysadmin)
    → Auto-refresh no 401
```

### Papéis e Permissões

| Papel | Permissões |
|-------|-----------|
| owner | Todas — incluindo billing.manage |
| admin | Tudo exceto billing.manage |
| accountant | documents.*, reports.advanced |
| bookkeeper | documents.*, reports.view |
| viewer | Somente leitura |
| api_user | documents.*, reports.view via API key |

22 permissões granulares organizadas por domínio: `documents.*`, `reports.*`, `clients.*`, `team.*`, `billing.*`, `admin.*`, `api.*`, `account.manage`.

### Claims Customizáveis

Tabela `user_claims` — permissões individuais com expiração opcional, registram quem concedeu.

---

## Setup de Desenvolvimento

```bash
# API
cd controlladoria-api
pip install -r requirements.txt
cp .env.example .env          # Configurar variáveis
alembic upgrade head          # Rodar migrações
uvicorn api:app --reload --port 8000

# UI do cliente
cd controlladoria-ui
npm install
cp .env.local.example .env.local
npm run dev                   # Porta 3000

# Sysadmin UI
cd controlladoria-sysadmin-ui
npm install
cp .env.example .env.local
npm run dev                   # Porta 3001

# Jobs (Celery worker)
cd controlladoria-jobs
celery -A celery_app worker -l info -c 4

# Website de marketing
cd controlladoria-website
npm install
npm run dev                   # Porta 3000
```

---

## Variáveis de Ambiente

### controlladoria-api (obrigatórias para produção)

| Variável | Exemplo | Descrição |
|---------|---------|-----------|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` | Conexão PostgreSQL |
| `JWT_SECRET_KEY` | `<hex 64 chars>` | Segredo JWT |
| `ENCRYPTION_KEY` | `<Fernet key>` | Chave para segredos MFA |
| `AI_PROVIDER` | `gemini` | Provedor primário |
| `GEMINI_API_KEYS` | `key1,key2` | Pool de chaves Gemini |
| `OPENAI_API_KEYS` | `sk-...` | Pool de chaves OpenAI (fallback) |
| `NOVA_MODEL` | `us.amazon.nova-2-lite-v1:0` | Modelo Nova via Bedrock |
| `NOVA_REGION` | `us-east-2` | Região AWS |
| `AWS_ACCESS_KEY_ID` | `AKIA...` | Credencial AWS (S3 + Bedrock) |
| `AWS_SECRET_ACCESS_KEY` | `...` | Segredo AWS |
| `S3_BUCKET_NAME` | `controlladoria-prod` | Bucket S3 |
| `USE_S3` | `true` | Habilitar S3 |
| `STRIPE_API_KEY` | `sk_live_...` | Chave Stripe |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | Segredo webhook Stripe |
| `RESEND_API_KEY` | `re_...` | Chave Resend (emails) |
| `REDIS_URL` | `redis://...` | Cache e broker Celery |
| `CORS_ORIGINS` | `https://app.controlladoria.com.br,...` | Origens permitidas |
| `ENVIRONMENT` | `production` | Ambiente |

### Variáveis Opcionais

| Variável | Padrão | Descrição |
|---------|--------|-----------|
| `AI_FAILOVER_ENABLED` | `true` | Failover automático entre provedores |
| `AI_KEY_UNHEALTHY_THRESHOLD` | `3` | Erros antes de marcar chave como inativa |
| `AI_KEY_RECOVERY_SECONDS` | `300` | Segundos antes de reativar chave |
| `ENABLE_AI_CACHE` | `false` | Cache Redis para respostas AI |
| `AI_CACHE_TTL` | `86400` | TTL do cache (24h) |
| `FREE_DEMO_MODE` | `false` | Bypass de todos os paywalls (demo) |
| `FRONTEND_URL` | `http://localhost:3000` | Para links em emails |

---

## Documentação Relacionada

| Documento | Conteúdo |
|-----------|---------|
| [AI_DOCUMENTATION.md](./AI_DOCUMENTATION.md) | Arquitetura completa de IA, pool de chaves, custo, privacidade |
| [ai-integration.md](./ai-integration.md) | Implementação atual, call_text_prompt(), plano de refatoração |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Deploy completo: Railway, Lambda, Amplify, SSM, CI/CD |
| [financial-reports.md](./financial-reports.md) | DRE, Balanço, Fluxo de Caixa — estrutura e cálculos |
| [security.md](./security.md) | Auth, RBAC, MFA, LGPD, auditoria de vulnerabilidades |
| [upload-and-processing.md](./upload-and-processing.md) | Upload, formatos, processamento, validação |
| [ADMIN_GUIDE.md](./ADMIN_GUIDE.md) | Console sysadmin, impersonação, métricas |
| [STRIPE_SETUP.md](./STRIPE_SETUP.md) | Setup de billing, planos, webhooks |
| [DATABASE_SETUP.md](./DATABASE_SETUP.md) | Setup PostgreSQL, migrações Alembic |

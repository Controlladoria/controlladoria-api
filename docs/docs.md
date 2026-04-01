# ControlladorIA (ControlladorIA) - Documentacao Completa

> **Versao**: 0.4.0 | **Ultima atualizacao**: 2026-02-25
> **Stack**: FastAPI + SQLAlchemy + Next.js 16 + TypeScript

---

## Indice / Table of Contents

- [PT-BR: Visao Geral](#pt-br-visao-geral)
- [EN-US: Overview](#en-us-overview)
- [Arquitetura / Architecture](#arquitetura--architecture)
- [Estrutura do Projeto / Project Structure](#estrutura-do-projeto--project-structure)
- [Setup de Desenvolvimento / Development Setup](#setup-de-desenvolvimento--development-setup)
- [Variaveis de Ambiente / Environment Variables](#variaveis-de-ambiente--environment-variables)
- [API Endpoints](#api-endpoints)
- [Modelos de Dados / Data Models](#modelos-de-dados--data-models)
- [Fluxo do Usuario / User Flow](#fluxo-do-usuario--user-flow)

---

# PT-BR: Visao Geral

## O que e o ControlladorIA?

O ControlladorIA e uma plataforma SaaS de contabilidade automatizada por inteligencia artificial, projetada para pequenas e medias empresas brasileiras. O sistema recebe documentos financeiros (notas fiscais, recibos, extratos bancarios, planilhas), extrai automaticamente os dados usando IA, e gera relatorios contabeis padronizados: **DRE** (Demonstracao do Resultado do Exercicio), **Balanco Patrimonial** e **Fluxo de Caixa**.

### Problema que resolve

Contabilidade manual e cara, demorada e propensa a erros. Donos de pequenas empresas gastam horas classificando documentos e gerando relatorios. O ControlladorIA automatiza todo esse processo: o usuario faz upload do documento, a IA extrai e classifica os dados, e os relatorios sao gerados automaticamente.

### Publico-alvo

- Pequenas e medias empresas brasileiras
- Escritorios de contabilidade
- Hospitais e clinicas (departamentalizacao por centro de custo)
- Qualquer empresa que precise de DRE/Balanco/Fluxo automatizados

### Funcionalidades principais

1. **Upload inteligente** - Aceita PDF, imagem, Excel, XML (NFe), OFX/OFC (extratos), Word, TXT
2. **Extracao por IA** - GPT/Claude analisa documentos e extrai dados estruturados
3. **Classificacao automatica** - 52 categorias baseadas no Plano de Contas brasileiro
4. **Validacao de dados** - Motor de validacao financeira com regras de negocio
5. **Relatorios contabeis** - DRE, Balanco Patrimonial, Fluxo de Caixa
6. **Multi-tenant** - Isolamento completo de dados por usuario
7. **Equipe** - Convites, papeis (owner/admin/contador/auxiliar/viewer)
8. **MFA** - Autenticacao em dois fatores (TOTP e email)
9. **Assinaturas** - Integracao Stripe com trial de 15 dias
10. **Dashboard** - 10 graficos interativos com Recharts

---

# EN-US: Overview

## What is ControlladorIA?

ControlladorIA is an AI-powered automated accounting SaaS platform designed for Brazilian small and medium businesses. The system receives financial documents (invoices, receipts, bank statements, spreadsheets), automatically extracts data using AI, and generates standardized accounting reports: **DRE** (Income Statement), **Balance Sheet**, and **Cash Flow Statement**.

### Problem it solves

Manual accounting is expensive, time-consuming, and error-prone. Small business owners spend hours classifying documents and generating reports. ControlladorIA automates the entire process: the user uploads a document, AI extracts and classifies the data, and reports are generated automatically.

### Target audience

- Brazilian small and medium businesses
- Accounting firms
- Hospitals and clinics (departmental cost center tracking)
- Any company needing automated DRE/Balance Sheet/Cash Flow

### Key features

1. **Smart upload** - Accepts PDF, images, Excel, XML (NFe), OFX/OFC (bank statements), Word, TXT
2. **AI extraction** - GPT/Claude analyzes documents and extracts structured data
3. **Automatic classification** - 52 categories based on Brazilian Chart of Accounts
4. **Data validation** - Financial validation engine with business rules
5. **Accounting reports** - Income Statement (DRE), Balance Sheet, Cash Flow
6. **Multi-tenant** - Complete data isolation per user
7. **Teams** - Invitations, roles (owner/admin/accountant/bookkeeper/viewer)
8. **MFA** - Two-factor authentication (TOTP and email)
9. **Subscriptions** - Stripe integration with 15-day trial
10. **Dashboard** - 10 interactive charts with Recharts

---

# Arquitetura / Architecture

## Diagrama de Alto Nivel / High-Level Diagram

```
                    +------------------+
                    |   Next.js 16     |
                    |   (Frontend)     |
                    |   Port: 3000     |
                    +--------+---------+
                             |
                             | HTTPS / JWT Bearer
                             |
                    +--------v---------+
                    |   FastAPI         |
                    |   (Backend API)   |
                    |   Port: 8000      |
                    +---+----+----+----+
                        |    |    |    |
            +-----------+    |    |    +------------+
            |                |    |                 |
    +-------v------+  +-----v----v---+   +----------v--------+
    |  PostgreSQL  |  |   OpenAI /   |   |    AWS S3         |
    |  (Database)  |  |   Anthropic  |   |    (File Storage) |
    |              |  |   (AI APIs)  |   |                   |
    +--------------+  +--------------+   +-------------------+
                            |
                     +------v------+
                     |   Redis     |   (Optional - caching)
                     +-------------+
```

## Stack Tecnologica / Technology Stack

### Backend
| Componente | Tecnologia | Versao | Proposito |
|---|---|---|---|
| Framework | FastAPI | >= 0.109 | API REST async |
| ORM | SQLAlchemy | >= 2.0 | Mapeamento objeto-relacional |
| Migracoes | Alembic | >= 1.13 | Versionamento de schema |
| Auth | JWT (python-jose) | >= 3.3 | Tokens de autenticacao |
| Senhas | bcrypt (passlib) | 4.0.1 | Hash de senhas |
| AI (OpenAI) | openai | >= 1.12 | Extracao de dados |
| AI (Anthropic) | anthropic | >= 0.18 | Extracao de dados (alternativa) |
| Pagamentos | stripe | >= 8.0 | Assinaturas |
| Email | resend | >= 0.8 | Emails transacionais |
| Storage | boto3 | >= 1.34 | AWS S3 |
| Cache | redis | >= 5.0 | Cache de respostas AI |
| Jobs | APScheduler | >= 3.10 | Tarefas agendadas |
| Rate Limit | slowapi | >= 0.1.9 | Limitacao de requisicoes |
| Validacao | pydantic | >= 2.6 | Validacao de dados |
| Sanitizacao | bleach | >= 6.1 | Limpeza de input HTML |

### Frontend
| Componente | Tecnologia | Proposito |
|---|---|---|
| Framework | Next.js 16 | SSR + React |
| Linguagem | TypeScript | Type safety |
| Graficos | Recharts | Dashboard charts |
| Estilo | Tailwind CSS | Utility-first CSS |
| HTTP | Fetch API | Requisicoes ao backend |

### Infraestrutura
| Componente | Tecnologia | Proposito |
|---|---|---|
| DB Producao | PostgreSQL | Banco relacional |
| DB Dev | SQLite | Desenvolvimento local |
| Storage | AWS S3 | Armazenamento de arquivos |
| Deploy Backend | Railway | Hosting do backend |
| Deploy Frontend | Vercel | Hosting do frontend |

---

# Estrutura do Projeto / Project Structure

```
ControlladorIA/
|-- api.py                      # FastAPI app principal, middleware, startup
|-- config.py                   # Pydantic Settings (todas as configs)
|-- database.py                 # Modelos SQLAlchemy (User, Document, etc.)
|-- models.py                   # Modelos Pydantic (request/response)
|-- structured_processor.py     # Processador de documentos (AI extraction)
|-- validation.py               # Motor de validacao financeira
|-- email_service.py            # Servico de email (Resend)
|-- exception_handlers.py       # Handlers globais de excecoes
|-- exceptions.py               # Custom exceptions
|-- i18n.py                     # Mensagens PT-BR / EN
|-- i18n_errors.py              # Traducao de erros de AI
|-- validators.py               # Validador de dados financeiros
|-- create_database.py          # Auto-criacao de banco PostgreSQL
|--
|-- auth/                       # Modulo de autenticacao
|   |-- __init__.py
|   |-- security.py             # JWT, bcrypt, tokens
|   |-- service.py              # Logica de registro/login/reset
|   |-- dependencies.py         # FastAPI deps (get_current_user)
|   |-- permissions.py          # RBAC com claims granulares
|   |-- models.py               # Schemas Pydantic de auth
|   |-- mfa_service.py          # MFA (TOTP + email)
|   |-- session_manager.py      # Gerenciamento de sessoes
|   |-- team_management.py      # Convites e equipe
|
|-- routers/                    # Routers modulares (SoC/SOLID)
|   |-- auth.py                 # /auth/* - registro, login, MFA
|   |-- documents.py            # /documents/* - upload, CRUD
|   |-- transactions.py         # /stats, /reports/* - relatorios
|   |-- billing.py              # /billing/* - Stripe
|   |-- team.py                 # /team/* - membros, convites
|   |-- sessions.py             # /sessions/* - dispositivos
|   |-- admin.py                # /admin/* - painel admin
|   |-- contact.py              # /contact - formulario
|   |-- account.py              # /account/* - perfil
|
|-- accounting/                 # Logica contabil
|   |-- categories.py           # 52 categorias DRE (Plano de Contas)
|
|-- middleware/
|   |-- subscription.py         # Middleware de assinatura ativa
|
|-- storage/
|   |-- s3_service.py           # AWS S3 upload/download/delete
|
|-- stripe_integration/         # Integracao Stripe
|   |-- client.py               # Cliente Stripe
|   |-- service.py              # Logica de assinaturas
|   |-- webhooks.py             # Handlers de webhook
|
|-- tasks/
|   |-- queue_manager.py        # Fila de processamento de documentos
|
|-- alembic/                    # Migracoes de banco de dados
|   |-- versions/               # Arquivos de migracao
|
|-- frontend/                   # Aplicacao Next.js
|   |-- src/
|   |   |-- app/                # App Router (paginas)
|   |   |-- components/         # Componentes React
|   |   |-- lib/                # Utilitarios, API client
|
|-- tests/                      # Testes unitarios e integracao
|-- docs/                       # Documentacao (voce esta aqui)
```

---

# Setup de Desenvolvimento / Development Setup

## Pre-requisitos / Prerequisites

- Python 3.10+
- Node.js 18+ (para frontend)
- PostgreSQL 14+ (producao) ou SQLite (dev)
- Poppler (para processar PDFs) - [Download Windows](https://github.com/oschwartz10612/poppler-windows/releases/)

## Backend Setup

```bash
# 1. Clone o repositorio
git clone <repo-url>
cd ControlladorIA

# 2. Crie o ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Instale as dependencias
pip install -r requirements.txt

# 4. Configure o .env
cp .env.example .env
# Edite o .env com suas chaves (API keys, JWT secret, etc.)

# 5. Rode as migracoes
alembic upgrade head

# 6. Inicie o servidor
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Setup

```bash
cd frontend

# 1. Instale dependencias
npm install

# 2. Configure variaveis
# Crie .env.local com NEXT_PUBLIC_API_URL=http://localhost:8000

# 3. Inicie o dev server
npm run dev
```

## Testes / Running Tests

```bash
# Testes unitarios (CI-safe)
pytest tests/ --ignore=tests/integration --ignore=tests/test_api_integration.py --ignore=tests/test_multi_user_system.py -q

# Todos os testes (requer servidor rodando)
pytest tests/ -v
```

---

# Variaveis de Ambiente / Environment Variables

## Obrigatorias para producao / Required for production

| Variavel | Exemplo | Descricao |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` | Conexao PostgreSQL |
| `JWT_SECRET_KEY` | `<hex 64 chars>` | Segredo JWT (gere com `openssl rand -hex 32`) |
| `OPENAI_API_KEY` | `sk-...` | Chave API OpenAI |
| `STRIPE_API_KEY` | `sk_live_...` | Chave Stripe |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | Segredo webhook Stripe |
| `RESEND_API_KEY` | `re_...` | Chave API Resend (emails) |
| `USE_S3` | `true` | Habilitar S3 |
| `AWS_ACCESS_KEY_ID` | `AKIA...` | Credencial AWS |
| `AWS_SECRET_ACCESS_KEY` | `...` | Segredo AWS |
| `S3_BUCKET_NAME` | `controlladoria-prod` | Nome do bucket S3 |

## Opcionais / Optional

| Variavel | Default | Descricao |
|---|---|---|
| `AI_PROVIDER` | `openai` | Provedor AI: `openai` ou `anthropic` |
| `OPENAI_MODEL` | `gpt-5-mini` | Modelo OpenAI |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | Modelo Anthropic |
| `ENABLE_AI_CACHE` | `false` | Cache Redis para respostas AI |
| `RATE_LIMIT_ENABLED` | `true` | Rate limiting |
| `ENVIRONMENT` | `development` | Ambiente (habilita HSTS em producao) |
| `CORS_ORIGINS` | `*` | Origens permitidas (restringir em producao) |

---

# API Endpoints

## Autenticacao / Authentication (`/auth`)

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| POST | `/auth/register` | Cadastro de usuario | Nao |
| POST | `/auth/login` | Login (retorna JWT) | Nao |
| POST | `/auth/refresh` | Renovar token | Refresh token |
| POST | `/auth/forgot-password` | Solicitar reset de senha | Nao |
| POST | `/auth/reset-password` | Confirmar reset de senha | Token |
| GET | `/auth/verify-email` | Verificar email | Token |
| POST | `/auth/mfa/setup` | Configurar MFA | JWT |
| POST | `/auth/mfa/enable` | Ativar MFA | JWT |
| POST | `/auth/mfa/verify` | Verificar codigo MFA | Temp token |

## Documentos / Documents (`/documents`)

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| POST | `/documents/upload` | Upload de documento | JWT |
| POST | `/documents/upload/bulk` | Upload multiplo | JWT |
| GET | `/documents/` | Listar documentos | JWT |
| GET | `/documents/{id}` | Detalhes do documento | JWT |
| PUT | `/documents/{id}` | Atualizar documento | JWT |
| DELETE | `/documents/{id}` | Deletar documento | JWT |
| GET | `/documents/{id}/download` | Download do arquivo | JWT |
| POST | `/documents/{id}/validate` | Validar transacoes | JWT |

## Relatorios / Reports

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| GET | `/stats` | Estatisticas gerais | JWT |
| GET | `/reports/summary` | Resumo financeiro | JWT |
| GET | `/reports/by-category` | Resumo por categoria | JWT |
| GET | `/reports/monthly` | Resumo mensal | JWT |
| GET | `/reports/dre` | DRE (Income Statement) | JWT |
| GET | `/reports/balance-sheet` | Balanco Patrimonial | JWT |
| GET | `/reports/cash-flow` | Fluxo de Caixa | JWT |
| GET | `/reports/export/excel` | Exportar Excel | JWT |
| GET | `/reports/export/pdf` | Exportar PDF | JWT |

## Equipe / Team (`/team`)

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| GET | `/team/members` | Listar membros | JWT + permission |
| POST | `/team/invite` | Convidar membro | JWT + team.invite |
| DELETE | `/team/members/{id}` | Remover membro | JWT + team.remove |
| POST | `/team/invitations/{token}/accept` | Aceitar convite | Token |
| DELETE | `/team/invitations/{id}` | Cancelar convite | JWT |

## Assinaturas / Billing (`/billing`)

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| GET | `/billing/subscription` | Status da assinatura | JWT |
| POST | `/billing/create-checkout` | Criar sessao Stripe | JWT |
| POST | `/billing/create-portal` | Portal do cliente | JWT |
| POST | `/billing/webhook` | Webhook Stripe | Webhook secret |

## Outros / Other

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| GET | `/health` | Health check completo | Nao |
| GET | `/health/ready` | Readiness probe (K8s) | Nao |
| GET | `/health/live` | Liveness probe (K8s) | Nao |
| POST | `/contact` | Formulario de contato | Nao (rate limited) |
| GET | `/sessions/active` | Sessoes ativas | JWT |

---

# Modelos de Dados / Data Models

## Banco de Dados / Database Schema

### Tabela `users`
- Autenticacao: email, password_hash, JWT
- Perfil: full_name, company_name, cnpj
- MFA: mfa_enabled, mfa_method, mfa_secret
- Equipe: role, parent_user_id, invited_by
- Compliance: agreed_to_terms, agreed_to_privacy (LGPD)

### Tabela `documents`
- Arquivo: file_name, file_type, file_path, file_size, file_hash
- Status: pending -> processing -> completed/failed/cancelled
- Dados: extracted_data_json (JSON com toda extracao)
- Isolamento: user_id (multi-tenant)
- NFe: is_cancellation, cancels_document_id

### Tabela `subscriptions`
- Stripe: stripe_customer_id, stripe_subscription_id
- Status: trialing, active, past_due, canceled
- Equipe: max_users (plano de membros)

### Tabela `chart_of_accounts`
- Plano de Contas customizavel por usuario
- Codigos padrao brasileiro (X.Y.ZZ)
- Natureza: debito ou credito

### Tabela `journal_entries` + `journal_entry_lines`
- Lancamentos contabeis (partida dobrada)
- Valores em centavos (evita decimais)
- Link com documento fonte

### Tabela `audit_logs`
- Trilha de auditoria completa
- Before/after values (JSON)
- IP, user agent, timestamp

### Outras tabelas
- `user_sessions` - Controle de dispositivos (limite 2)
- `user_claims` - Permissoes granulares
- `api_keys` - Chaves API programaticas
- `team_invitations` - Convites de equipe
- `password_resets` - Tokens de reset
- `contact_submissions` - Formulario de contato
- `document_validation_rows` - Linhas para validacao manual
- `clients` - Clientes/fornecedores

---

# Fluxo do Usuario / User Flow

## Fluxo de Upload / Upload Flow

```
1. Usuario seleciona arquivo(s)
   |
2. Frontend envia POST /documents/upload
   |
3. Backend valida:
   - Tamanho (max 30MB)
   - Extensao permitida
   - MIME type (se python-magic disponivel)
   - Assinatura ativa
   - Rate limit (10/minuto)
   |
4. Arquivo salvo (S3 ou local) com UUID unico
   |
5. Registro criado no DB (status: pending)
   |
6. Background task iniciada:
   a. Detecta tipo do arquivo
   b. Converte se necessario (PDF -> imagem via Poppler)
   c. Envia para AI (OpenAI ou Anthropic)
   d. Recebe JSON estruturado
   e. Valida dados extraidos
   f. Atualiza DB (status: completed)
   g. Auto-cria cliente se identificado
   |
7. Frontend polling verifica status
```

## Fluxo de Relatorios / Report Flow

```
1. Usuario acessa DRE/Balanco/Fluxo
   |
2. Frontend chama GET /reports/dre?date_from=...&date_to=...
   |
3. Backend:
   a. Carrega documentos completed do usuario
   b. Extrai dados financeiros de cada documento
   c. Classifica por categoria (52 categorias DRE V2)
   d. Calcula totais e subtotais
   e. Retorna estrutura completa do relatorio
   |
4. Frontend renderiza com formatacao brasileira (R$, separadores)
```

---

## Documentacao Relacionada / Related Docs

- [Upload e Processamento de Arquivos](./upload-and-processing.md)
- [Relatorios Financeiros (DRE/Balanco/Fluxo)](./financial-reports.md)
- [Integracao com IA (AI APIs)](./ai-integration.md)
- [Seguranca](./security.md)
- [Plano de Microservicos](./microservices-plan.md)
- [Setup do Banco de Dados](./DATABASE_SETUP.md)
- [Guia de Deploy](./DEPLOYMENT.md)
- [Setup do Stripe](./STRIPE_SETUP.md)

# Guia de Administracao — ControlladorIA

**Versao**: 1.0
**Data**: 2026-03-05

---

## 1. Painel Administrativo

Acesso: `/admin` (requer papel `owner` ou `admin` com claim `admin.dashboard`)

### Dashboard Admin

- Total de usuarios cadastrados
- Total de documentos processados
- Documentos por status (processado, erro, pendente)
- Submissoes de contato
- Logs de auditoria

---

## 2. Gestao de Usuarios

### Visualizar Usuarios

**Painel**: `/admin/users`
**API**: `GET /admin/users`

Lista todos os usuarios com:
- Nome, email, CNPJ
- Papel (role)
- Status da assinatura (trial, active, canceled)
- Data de criacao
- Ultimo login

### Papeis Disponiveis (RBAC)

| Papel | Pode ver dados | Pode editar | Pode excluir | Pode gerenciar equipe | Pode acessar billing |
|-------|---------------|-------------|-------------|----------------------|---------------------|
| **owner** | Tudo | Tudo | Tudo | Sim | Sim |
| **admin** | Tudo | Tudo | Tudo | Sim | Nao |
| **accountant** | Docs + relatorios | Docs + relatorios | Nao | Nao | Nao |
| **bookkeeper** | Docs + relatorios basicos | Docs | Nao | Nao | Nao |
| **viewer** | Somente leitura | Nao | Nao | Nao | Nao |
| **api_user** | Docs + relatorios via API | Docs via API | Nao | Nao | Nao |

### Convidar Membro para Organizacao

**UI**: Pagina da equipe (`/account/team`)
**API**: `POST /organizations/{org_id}/invite`

```json
{
  "email": "contador@email.com",
  "role": "accountant"
}
```

O convidado recebe email com link de convite. Se ja tem conta, aceita na pagina `/organizations/invitations`. Se nao tem, precisa se registrar primeiro.

### Claims Customizadas

Alem do papel, permissoes individuais podem ser concedidas:

**API**: `POST /admin/users/{user_id}/claims`

```json
{
  "claim": "reports.advanced",
  "granted_by": "owner_user_id",
  "expires_at": "2026-12-31T23:59:59"
}
```

---

## 3. Gestao de Organizacoes

### Criar Nova Organizacao (como owner)

**UI**: Sidebar -> Dropdown de organizacao -> "Criar Nova Empresa"
**API**: `POST /organizations/create`

Fluxo:
1. Informar CNPJ
2. Sistema busca dados via BrasilAPI/SERPRO/ReceitaWS
3. Preview dos dados da empresa
4. Confirmar criacao
5. Nova organizacao criada com:
   - Membership (owner)
   - Subscription (trial de 14 dias)
   - Contexto trocado automaticamente

### Trocar de Organizacao

**UI**: Sidebar -> Dropdown -> Selecionar organizacao
**API**: `POST /organizations/switch`

Troca o contexto ativo sem precisar fazer logout/login.

### Limite

- Maximo 20 organizacoes por usuario
- Cada organizacao tem sua propria assinatura Stripe

---

## 4. Assinaturas e Pagamentos

### Planos

Configurados no Stripe Dashboard. A aplicacao busca planos via `get_default_plan()`.

### Status de Assinatura

| Status | Descricao | Acesso |
|--------|-----------|--------|
| `trialing` | Periodo de teste (14 dias) | Completo |
| `active` | Pagamento em dia | Completo |
| `past_due` | Pagamento atrasado | Completo (Stripe retenta) |
| `canceled` | Cancelada pelo usuario | Limitado (somente leitura) |
| `unpaid` | Todas as tentativas falharam | Bloqueado |

### Portal do Cliente Stripe

**UI**: `/account/subscription` -> "Gerenciar Assinatura"
**API**: `POST /stripe/create-portal-session`

Redireciona para o portal Stripe onde o usuario pode:
- Atualizar metodo de pagamento
- Trocar de plano
- Cancelar assinatura
- Ver historico de faturas

### Webhooks Stripe

URL configurada no Stripe Dashboard: `https://API_URL/stripe/webhook`

Eventos tratados:
- `checkout.session.completed` — ativa assinatura
- `customer.subscription.updated` — atualiza status
- `customer.subscription.deleted` — marca como cancelada
- `invoice.payment_failed` — marca como past_due

---

## 5. Logs de Auditoria

### Visualizar

**UI**: `/admin/audit`
**API**: `GET /admin/audit-logs`

### O que e Registrado

Toda acao sobre documentos:
- Criacao (upload + processamento)
- Edicao (correcao de valores na validacao)
- Exclusao
- Exportacao

Cada registro contem:
- **Quem**: user_id, email
- **O que**: acao (created, updated, deleted)
- **Quando**: timestamp UTC
- **De onde**: IP, User-Agent
- **Antes/Depois**: JSON com valores antes e depois da mudanca

### Filtros

- Por usuario
- Por documento
- Por tipo de acao
- Por periodo

---

## 6. Variaveis de Ambiente

### Criticas (obrigatorias em producao)

| Variavel | Descricao |
|----------|-----------|
| `DATABASE_URL` | Connection string PostgreSQL |
| `JWT_SECRET_KEY` | Chave para assinar tokens JWT (NUNCA mudar em producao sem avisar) |
| `OPENAI_API_KEY` | Chave da API OpenAI |
| `STRIPE_SECRET_KEY` | Chave secreta do Stripe |
| `STRIPE_WEBHOOK_SECRET` | Secret do webhook Stripe |
| `FRONTEND_URL` | URL do frontend (para CORS e links de email) |
| `AWS_ACCESS_KEY_ID` | Chave AWS para S3 |
| `AWS_SECRET_ACCESS_KEY` | Secret AWS para S3 |
| `S3_BUCKET_NAME` | Nome do bucket S3 |

### Opcionais

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `AI_PROVIDER` | `openai` | Provedor de IA (`openai` ou `anthropic`) |
| `OPENAI_MODEL` | `gpt-5-mini` | Modelo OpenAI |
| `ENABLE_AI_CACHE` | `false` | Cache de respostas IA (requer Redis) |
| `ENVIRONMENT` | `development` | `development` ou `production` |
| `DEBUG` | `true` | Modo debug |
| `USE_S3` | `false` | Usar S3 para armazenamento |

### Trocar Provedor de IA

```
Railway Dashboard -> Servico -> Variables
AI_PROVIDER = anthropic
-> Salvar (redeploy automatico)
```

Tempo: ~2 minutos. Sem mudanca de codigo necessaria.

---

## 7. Reprocessamento de Documentos

### Documento com Erro

Se um documento falhou no processamento (status `error`):

1. Verificar o erro nos logs (Railway -> Logs)
2. Se foi erro temporario (timeout, rate limit): usuario pode re-enviar o mesmo arquivo
3. Hash SHA-256 detecta duplicata e permite reprocessamento

### Reprocessamento em Massa

Atualmente nao ha endpoint de reprocessamento em massa. Para reprocessar:
1. Identificar documentos com `processing_status = 'error'`
2. Notificar usuarios para re-upload
3. (Futuro) Endpoint admin para reprocessar batch

---

## 8. Saude do Sistema

### Endpoint de Saude

```bash
curl https://API_URL/health
```

Retorna:
```json
{
  "status": "healthy",
  "version": "0.4.0",
  "database": "connected"
}
```

### Verificacoes Manuais

| Verificacao | Como |
|------------|------|
| API respondendo | `curl /health` |
| Banco conectado | Health check inclui teste de conexao |
| S3 acessivel | Upload de teste |
| Stripe funcionando | Verificar dashboard Stripe |
| IA respondendo | Upload de documento de teste |
| Frontend carregando | Acessar URL do frontend |
| Migracoes em dia | `alembic current` == `alembic heads` |

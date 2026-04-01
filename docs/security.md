# Seguranca / Security

> Documentacao das funcionalidades de seguranca, auditoria de vulnerabilidades e plano de melhorias.
>
> Documentation of security features, vulnerability audit, and improvement plan.

---

## Indice / Table of Contents

- [PT-BR: Funcionalidades de Seguranca](#pt-br-funcionalidades-de-seguranca)
- [PT-BR: Auditoria de Seguranca](#pt-br-auditoria-de-seguranca)
- [PT-BR: Plano de Melhorias](#pt-br-plano-de-melhorias)
- [EN-US: Security Features](#en-us-security-features)
- [EN-US: Security Audit](#en-us-security-audit)
- [EN-US: Improvement Plan](#en-us-improvement-plan)

---

# PT-BR: Funcionalidades de Seguranca

## 1. Autenticacao

### JWT (JSON Web Tokens)
- **Algoritmo**: HS256 com chave secreta configuravel (`JWT_SECRET_KEY`)
- **Access token**: Expira em 30 minutos (configuravel via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Refresh token**: Expira em 7 dias (configuravel via `REFRESH_TOKEN_EXPIRE_DAYS`)
- **Payload**: Contem `sub` (user_id), `email`, `role`, `claims` (permissoes), `type` (access/refresh), `exp`, `iat`
- **Implementacao**: `auth/security.py` - `create_access_token()`, `verify_token()`

### Hash de Senhas
- **Algoritmo**: bcrypt via passlib
- **Versao fixa**: `bcrypt==4.0.1` (fixada para compatibilidade com passlib)
- **Salt**: Gerado automaticamente pelo bcrypt
- **Implementacao**: `auth/security.py` - `hash_password()`, `verify_password()`

### MFA (Autenticacao Multi-Fator)
- **Metodos suportados**: TOTP (Google Authenticator) e Email
- **TOTP**: Segredo gerado e criptografado com Fernet antes de salvar no banco
- **Email MFA**: Codigo temporario enviado via Resend
- **Dispositivo confiavel**: Apos verificacao MFA, dispositivo pode ser marcado como confiavel por 30 dias
- **Fingerprint**: Hash SHA-256 de User-Agent + IP para identificacao de dispositivo
- **Backup codes**: 10 codigos de uso unico, criptografados no banco
- **Implementacao**: `auth/mfa_service.py`

### Gerenciamento de Sessoes
- **Limite de dispositivos**: Maximo 2 sessoes simultaneas por usuario
- **Kick automatico**: Sessao mais antiga e invalidada quando limite e atingido
- **Tracking**: IP, User-Agent, tipo de dispositivo, navegador, SO
- **Expiracao**: Sessoes expiram automaticamente
- **Implementacao**: `auth/session_manager.py`

## 2. Autorizacao (RBAC)

### Sistema de Papeis
O sistema usa RBAC (Role-Based Access Control) com claims granulares:

| Papel | Descricao | Permissoes |
|---|---|---|
| **owner** | Dono da organizacao | TODAS as permissoes |
| **admin** | Administrador | Tudo exceto billing.manage |
| **accountant** | Contador | Documentos + relatorios avancados |
| **bookkeeper** | Auxiliar contabil | Documentos + relatorios basicos |
| **viewer** | Visualizador | Somente leitura |
| **api_user** | Acesso API | Documentos + relatorios via API |

### Permissoes Granulares (Claims)
22 permissoes individuais organizadas por dominio:
- `documents.*` (read, write, delete, export)
- `reports.*` (view, export, advanced)
- `clients.*` (read, write, delete)
- `team.*` (view, invite, remove, manage_roles)
- `billing.*` (view, manage)
- `admin.*` (dashboard, view_users, audit_logs, contact_submissions)
- `api.*` (access, keys.manage)
- `account.manage`

### Claims Customizaveis
Alem das permissoes do papel, cada usuario pode ter claims individuais:
- Armazenados na tabela `user_claims`
- Podem adicionar ou revogar permissoes especificas
- Tem data de expiracao opcional
- Registram quem concedeu a permissao
- **Implementacao**: `auth/permissions.py`

## 3. Isolamento Multi-Tenant

### Dados
- **Todas** as queries de documentos, relatorios e clientes filtram por `user_id`
- Funcao central: `get_accessible_user_ids(user, db)` retorna IDs acessiveis
- Owner ve dados de toda a equipe
- Membros veem dados do owner + proprios + colegas

### Arquivos
- S3: `users/{user_id}/{uuid}.ext` - isolamento por diretorio
- Local: UUID unico previne colisoes de nome

### Indices de Banco
- Indice composto `idx_user_status` para queries eficientes por tenant
- Indice composto `idx_user_client` para filtragem de clientes

## 4. Protecao de Headers HTTP

Middleware de seguranca em `api.py` adiciona headers a todas as respostas:

| Header | Valor | Proposito |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Previne MIME type sniffing |
| `X-Frame-Options` | `DENY` | Previne clickjacking |
| `X-XSS-Protection` | `1; mode=block` | Protecao XSS (legacy) |
| `Content-Security-Policy` | `default-src 'self'; ...` | Controle de recursos |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Forca HTTPS (somente producao) |

## 5. Validacao de Input

### Pydantic Models
- Todos os inputs validados via modelos Pydantic com restricoes:
  - `min_length`, `max_length` em campos de texto
  - `EmailStr` para emails
  - Regex para telefone brasileiro
- **Sanitizacao HTML**: `bleach.clean()` em campos de texto (remove tags HTML)
- **Formato brasileiro**: Validacao de CNPJ, CPF, telefone

### Upload de Arquivos
- Whitelist de extensoes (11 tipos permitidos)
- Validacao de MIME type (via `python-magic` quando disponivel)
- Limite de tamanho: 30MB
- Hash SHA-256 para deteccao de duplicatas

## 6. Rate Limiting

| Endpoint | Limite | Implementacao |
|---|---|---|
| Upload de documentos | 10/minuto | slowapi |
| Registro | 5/hora | slowapi |
| Formulario de contato | 5/hora | slowapi |
| Login | Sem limite explicito | A melhorar |

## 7. Trilha de Auditoria

### O que e registrado
- Toda criacao, atualizacao e exclusao de documentos
- Quem fez a acao (user_id)
- Quando (timestamp UTC)
- De onde (IP, User-Agent)
- Valores antes e depois da mudanca (JSON)
- Resumo da mudanca em texto legivel

### Tabela `audit_logs`
- `document_id`: Sem FK (preserva historico mesmo apos exclusao)
- `before_value` / `after_value`: JSON dos estados
- `changes_summary`: Texto legivel
- Indice composto `idx_audit_user_document`

## 8. Compliance (LGPD/GDPR)

### Consentimento
- `agreed_to_terms` + `agreed_to_terms_at`: Aceite dos Termos de Uso
- `agreed_to_privacy` + `agreed_to_privacy_at`: Aceite da Politica de Privacidade
- Registrados com timestamp no momento do registro

### Dados Pessoais
- Senhas hasheadas (bcrypt, irreversivel)
- Segredos MFA criptografados (Fernet)
- Backup codes MFA criptografados

### Classificacao de Dados (LGPD)

| Categoria | Dados | Base Legal | Retencao |
|-----------|-------|-----------|----------|
| **Dados Pessoais** | Nome, email, telefone | Execucao de contrato (Art. 7, V) | Enquanto conta ativa + 5 anos |
| **Dados de Empresa** | Razao social, CNPJ, endereco, regime tributario | Execucao de contrato | Enquanto conta ativa + 5 anos |
| **Documentos Financeiros** | Notas fiscais, recibos, extratos | Execucao de contrato + Obrigacao legal | Enquanto conta ativa + 5 anos (obrigacao fiscal) |
| **Dados de Autenticacao** | Hash de senha, segredos MFA, tokens | Execucao de contrato | Enquanto conta ativa |
| **Dados de Auditoria** | Logs de acao (IP, User-Agent, timestamps) | Interesse legitimo (Art. 7, IX) | 2 anos |
| **Dados de Pagamento** | Nenhum armazenado localmente (Stripe) | N/A | N/A |

### Principios LGPD Aplicados

| Principio | Implementacao |
|-----------|--------------|
| **Finalidade** | Dados coletados apenas para processamento financeiro e autenticacao |
| **Adequacao** | Apenas dados necessarios para o servico |
| **Necessidade** | Nao coletamos dados desnecessarios. Pagamento delegado ao Stripe |
| **Transparencia** | Politica de privacidade e termos aceitos no registro com timestamp |
| **Seguranca** | Criptografia em transito (HTTPS/HSTS) e repouso (Fernet/bcrypt) |

### Direitos do Titular (LGPD Art. 18)

| Direito | Como Atender |
|---------|-------------|
| **Acesso** | Usuario ve todos seus dados no perfil e documentos |
| **Correcao** | Usuario edita perfil e corrige dados de documentos |
| **Eliminacao** | Usuario exclui documentos. Exclusao de conta: via suporte |
| **Portabilidade** | Exportacao de relatorios em PDF/Excel |
| **Revogacao** | Cancelamento de conta remove consentimento |

### Dados Enviados para APIs de IA

- Conteudo de documentos e enviado para OpenAI/Anthropic para extracao
- Provedores nao usam dados de API para treino (conforme termos de uso)
- Dados pessoais do usuario (email, senha) nunca sao enviados
- Cada documento processado individualmente (sem contexto cruzado)

## 9. Pagamentos Seguros

### Stripe
- Processamento de pagamento delegado ao Stripe (PCI-DSS)
- Validacao de assinatura em webhooks (`stripe.Webhook.construct_event`)
- Nenhum dado de cartao armazenado localmente
- Webhook secret separado da API key

## 10. Criptografia

### Em Transito
- HSTS em producao (`max-age=31536000; includeSubDomains`)
- HTTPS obrigatorio (via infraestrutura de deploy)

### Em Repouso
- Segredos MFA: Criptografia Fernet (AES-128-CBC)
- Chave de criptografia derivada do `JWT_SECRET_KEY` se `ENCRYPTION_KEY` nao definida
- Senhas: bcrypt (hash unidirecional)

---

# PT-BR: Auditoria de Seguranca

## Problemas Encontrados (Fevereiro 2026)

### CRITICO

#### 1. Token de Reset de Senha Vazando na Resposta da API
**Arquivo**: `routers/auth.py`
**Problema**: O token de reset de senha e retornado no JSON da resposta, com um `TODO` para remover em producao. Qualquer pessoa que faca a requisicao recebe o token imediatamente, sem precisar acessar o email.
**Impacto**: Bypass completo da verificacao por email no fluxo de reset de senha.
**Correcao**: Remover o campo `token` da resposta. Enviar apenas por email.

#### 2. Spoofing de IP via X-Forwarded-For
**Arquivo**: `api.py` (linhas 318-335), `routers/documents.py` (linhas 98-115)
**Problema**: O IP do cliente e extraido do header `X-Forwarded-For` sem validacao. Este header pode ser facilmente falsificado por qualquer cliente.
**Impacto**: Bypass de rate limiting, falsificacao de trilha de auditoria, ataques de lockout.
**Correcao**: Usar `request.client.host` quando nao ha proxy confiavel, ou validar que o proxy esta configurado corretamente.

### ALTO

#### 3. CORS Wildcard com Credenciais
**Arquivo**: `api.py` (linhas 169-193)
**Problema**: Ambiente de desenvolvimento usa `"*"` como origem CORS junto com `allow_credentials=True`. Isso permite que qualquer site faca requisicoes autenticadas.
**Impacto**: Ataques CSRF, roubo de credenciais.
**Correcao**: Remover `"*"` e usar apenas URLs especificas de localhost.

#### 4. Sem Revogacao de Tokens (Logout Nao Funcional)
**Arquivo**: `routers/auth.py`
**Problema**: O endpoint de logout apenas retorna uma mensagem pedindo que o cliente descarte os tokens. Nao ha blacklist de tokens.
**Impacto**: Tokens roubados permanecem validos mesmo apos logout.
**Correcao**: Implementar blacklist de tokens usando Redis (armazenar JTI do token, expirar junto com o token).

#### 5. Path Traversal Potencial no Download
**Arquivo**: `routers/documents.py`
**Problema**: O download usa `Path(doc.file_path)` sem validar que o caminho esta dentro do diretorio esperado.
**Impacto**: Se o `file_path` no banco for manipulado, pode permitir download de arquivos arbitrarios.
**Correcao**: Validar que `file_path.resolve()` comeca com o diretorio de uploads.

#### 6. Validacao de Chave S3 Ausente
**Arquivo**: `routers/documents.py`
**Problema**: O download de S3 nao valida que a chave segue o padrao `users/{user_id}/...`.
**Impacto**: Se um usuario obtem a chave S3 de outro usuario, pode baixar o arquivo.
**Correcao**: Validar que a chave S3 comeca com `users/{current_user.id}/`.

#### 7. Sem Protecao CSRF
**Arquivo**: `api.py`
**Problema**: Nao ha tokens CSRF para operacoes que alteram estado (POST, PUT, DELETE).
**Impacto**: Ataques CSRF via formularios cross-site.
**Correcao**: Implementar double-submit cookie ou tokens sincronizadores.

### MEDIO

#### 8. Token de Verificacao de Email Sem Expiracao
**Problema**: Tokens de verificacao de email nao tem prazo de validade.
**Correcao**: Adicionar campo `email_verification_token_expires_at` com expiracao de 24-48 horas.

#### 9. Rate Limiting Bypassavel via IP Spoofing
**Problema**: Rate limiting usa o mesmo mecanismo de extracao de IP vulneravel.
**Correcao**: Usar IP real da conexao TCP.

#### 10. Login Sem Rate Limiting Explicito
**Problema**: Endpoint de login nao tem limite explicito de tentativas.
**Correcao**: Adicionar rate limiting (ex: 10 tentativas por minuto por IP + 5 por conta).

---

# PT-BR: Plano de Melhorias

## Prioridade 1 (Implementar Imediatamente)

### 1.1 Remover Token de Reset da Resposta
```python
# ANTES (VULNERAVEL):
return {"message": "...", "token": token}

# DEPOIS (SEGURO):
return {"message": "Se o email existir, enviaremos instrucoes de reset."}
```
**Esforco**: 5 minutos. **Risco**: Zero.

### 1.2 Corrigir Extracao de IP
```python
# ANTES (VULNERAVEL):
def get_client_ip(request):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

# DEPOIS (SEGURO):
def get_client_ip(request):
    # Em producao atras de proxy confiavel (Railway, Render):
    # O proxy define X-Forwarded-For corretamente
    # Mas em dev sem proxy, usar IP real
    if settings.environment == "production":
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
```
**Esforco**: 30 minutos. **Risco**: Baixo.

### 1.3 Corrigir CORS
```python
# ANTES (VULNERAVEL):
cors_origins = ["http://localhost:3000", "http://localhost:3001", "*"]

# DEPOIS (SEGURO):
cors_origins = ["http://localhost:3000", "http://localhost:3001"]
```
**Esforco**: 5 minutos. **Risco**: Zero.

## Prioridade 2 (Implementar em 1-2 Semanas)

### 2.1 Token Blacklist (Redis)
```python
# Em auth/token_blacklist.py
import redis

blacklist = redis.from_url(settings.redis_url)

def blacklist_token(jti: str, exp_seconds: int):
    blacklist.setex(f"blacklist:{jti}", exp_seconds, "1")

def is_blacklisted(jti: str) -> bool:
    return blacklist.exists(f"blacklist:{jti}")
```
**Esforco**: 2-3 horas. **Risco**: Baixo.

### 2.2 Rate Limiting no Login
```python
@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, ...):
```
**Esforco**: 15 minutos. **Risco**: Zero.

### 2.3 Path Traversal Protection
```python
# Em downloads
file_path = Path(doc.file_path).resolve()
allowed_base = Path("uploads").resolve()
if not str(file_path).startswith(str(allowed_base)):
    raise HTTPException(403, "Acesso negado")
```
**Esforco**: 30 minutos. **Risco**: Zero.

### 2.4 Expiracao de Token de Verificacao de Email
Adicionar campo `email_verification_token_expires_at` ao modelo `User` e validar na verificacao.
**Esforco**: 1 hora (inclui migracao Alembic). **Risco**: Baixo.

## Prioridade 3 (Implementar em 1-2 Meses)

### 3.1 CSRF Tokens
Implementar double-submit cookie pattern:
1. Gerar token CSRF no login e retornar como cookie `SameSite=Strict`
2. Frontend envia token no header `X-CSRF-Token`
3. Backend valida que cookie == header

### 3.2 Monitoramento de Seguranca
- Alertas para login de novos dispositivos
- Notificacao por email para mudancas de senha
- Dashboard de sessoes ativas para o usuario
- Deteccao de brute force (bloqueio temporario de conta)

### 3.3 Hardening de Dependencias
- Fixar versoes exatas em `requirements.txt`
- Rodar `pip audit` no CI para detectar CVEs
- Atualizar dependencias mensalmente

### 3.4 Security.txt
```
# /.well-known/security.txt
Contact: mailto:security@controllad oria.com.br
Expires: 2027-01-01T00:00:00.000Z
Preferred-Languages: pt-BR, en
Canonical: https://controllad oria.com.br/.well-known/security.txt
```

---

# EN-US: Security Features

## 1. Authentication

### JWT (JSON Web Tokens)
- **Algorithm**: HS256 with configurable secret key (`JWT_SECRET_KEY`)
- **Access token**: Expires in 30 minutes (configurable)
- **Refresh token**: Expires in 7 days (configurable)
- **Payload**: Contains `sub` (user_id), `email`, `role`, `claims` (permissions), `type`, `exp`, `iat`
- **Implementation**: `auth/security.py`

### Password Hashing
- **Algorithm**: bcrypt via passlib
- **Pinned version**: `bcrypt==4.0.1` for passlib compatibility
- **Salt**: Auto-generated by bcrypt

### MFA (Multi-Factor Authentication)
- **Supported methods**: TOTP (Google Authenticator) and Email
- **TOTP**: Secret generated and encrypted with Fernet before database storage
- **Email MFA**: Temporary code sent via Resend
- **Trusted device**: After MFA verification, device can be trusted for 30 days
- **Fingerprint**: SHA-256 hash of User-Agent + IP for device identification
- **Backup codes**: 10 single-use codes, encrypted in database

### Session Management
- **Device limit**: Maximum 2 simultaneous sessions per user
- **Auto-kick**: Oldest session invalidated when limit reached
- **Tracking**: IP, User-Agent, device type, browser, OS
- **Expiration**: Sessions expire automatically

## 2. Authorization (RBAC)

### Role System
6 predefined roles with 22 granular permissions:

| Role | Description | Key Permissions |
|---|---|---|
| **owner** | Organization owner | ALL permissions |
| **admin** | Administrator | Everything except billing.manage |
| **accountant** | Accountant | Documents + advanced reports |
| **bookkeeper** | Bookkeeper | Documents + basic reports |
| **viewer** | Viewer | Read-only access |
| **api_user** | API access | Documents + reports via API |

### Custom Claims
Beyond role-based permissions, each user can have individual claims:
- Stored in `user_claims` table
- Can add or revoke specific permissions
- Optional expiration date
- Records who granted the permission

## 3. Multi-Tenant Isolation

### Data
- **ALL** document, report, and client queries filter by `user_id`
- Central function: `get_accessible_user_ids(user, db)` returns accessible IDs
- Owner sees all team data; members see owner + own + siblings

### Files
- S3: `users/{user_id}/{uuid}.ext` - directory isolation
- Local: UUID prevents name collisions

## 4. HTTP Security Headers

All responses include:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Content-Security-Policy` (restrictive)
- `Strict-Transport-Security` (production only, 1 year)

## 5. Input Validation

- All inputs validated via Pydantic models with constraints
- HTML sanitization via `bleach.clean()` (strips all HTML tags)
- Brazilian format validation (CNPJ, CPF, phone)
- File upload: extension whitelist, MIME type validation, 30MB size limit

## 6. Rate Limiting

| Endpoint | Limit | Library |
|---|---|---|
| Document upload | 10/minute | slowapi |
| Registration | 5/hour | slowapi |
| Contact form | 5/hour | slowapi |
| Login | No explicit limit | To improve |

## 7. Audit Trail

- All document CRUD operations logged
- Records: who, what, when, from where (IP, User-Agent)
- Before/after values preserved as JSON
- Document ID preserved after deletion (no FK cascade)

## 8. Compliance (LGPD/GDPR)

- Terms of Service and Privacy Policy consent with timestamps
- Passwords hashed (bcrypt, irreversible)
- MFA secrets encrypted (Fernet/AES)
- Backup codes encrypted

### Data Classification (LGPD)

| Category | Data | Legal Basis | Retention |
|----------|------|------------|-----------|
| **Personal Data** | Name, email, phone | Contract execution (Art. 7, V) | Active account + 5 years |
| **Company Data** | Legal name, CNPJ, address, tax regime | Contract execution | Active account + 5 years |
| **Financial Documents** | Invoices, receipts, statements | Contract + Legal obligation | Active account + 5 years |
| **Auth Data** | Password hash, MFA secrets, tokens | Contract execution | While account active |
| **Audit Data** | Action logs (IP, UA, timestamps) | Legitimate interest (Art. 7, IX) | 2 years |
| **Payment Data** | None stored locally (Stripe handles) | N/A | N/A |

### Data Subject Rights (LGPD Art. 18)

| Right | Implementation |
|-------|---------------|
| **Access** | User can view all data in profile and documents |
| **Correction** | User can edit profile and correct document data |
| **Deletion** | User can delete documents. Account deletion via support |
| **Portability** | Export reports as PDF/Excel |
| **Revocation** | Account cancellation removes consent |

### Data Sent to AI APIs

- Document content sent to OpenAI/Anthropic for extraction
- Providers do not use API data for training (per their terms)
- User personal data (email, password) never sent to AI APIs
- Each document processed individually (no cross-user context)

## 9. Payment Security

- Payment processing delegated to Stripe (PCI-DSS compliant)
- Webhook signature validation
- No card data stored locally

## 10. Encryption

- **In transit**: HSTS in production, HTTPS enforced
- **At rest**: MFA secrets encrypted with Fernet (AES-128-CBC), passwords hashed with bcrypt

---

# EN-US: Security Audit

## Findings (February 2026)

### CRITICAL

| # | Finding | File | Impact | Fix |
|---|---|---|---|---|
| 1 | Password reset token leaked in API response | `routers/auth.py` | Complete bypass of email verification | Remove `token` field from response |
| 2 | X-Forwarded-For spoofing | `api.py`, `routers/documents.py` | Rate limit bypass, audit trail forgery | Use `request.client.host` or validate proxy |

### HIGH

| # | Finding | File | Impact | Fix |
|---|---|---|---|---|
| 3 | CORS wildcard with credentials | `api.py` | CSRF attacks, credential theft | Remove `"*"` from origins |
| 4 | No token revocation (logout broken) | `routers/auth.py` | Stolen tokens remain valid | Implement Redis token blacklist |
| 5 | Path traversal in file download | `routers/documents.py` | Arbitrary file download | Validate path within uploads dir |
| 6 | S3 key validation missing | `routers/documents.py` | Cross-tenant file download | Validate S3 key prefix |
| 7 | No CSRF protection | `api.py` | Cross-site state changes | Implement double-submit cookie |

### MEDIUM

| # | Finding | File | Impact | Fix |
|---|---|---|---|---|
| 8 | Email verification token no expiration | `auth/service.py` | Old tokens valid forever | Add expiration field |
| 9 | Rate limiting bypassable via IP spoofing | `routers/auth.py` | Rate limit bypass | Use real TCP IP |
| 10 | Login has no rate limiting | `routers/auth.py` | Brute force attacks | Add `@limiter.limit("10/minute")` |

### LOW

| # | Finding | Impact | Fix |
|---|---|---|---|
| 11 | No `security.txt` | No responsible disclosure channel | Create `/.well-known/security.txt` |
| 12 | Temp file cleanup not guaranteed | Disk space leak | Use `finally` blocks |
| 13 | Dependencies not pinned exactly | Breaking changes possible | Use `~=` constraints |

---

# EN-US: Improvement Plan

## Priority 1: Immediate (Before Production)

### 1.1 Remove Reset Token from Response
```python
# BEFORE (VULNERABLE):
return {"message": "...", "token": token}

# AFTER (SECURE):
return {"message": "If the email exists, we will send reset instructions."}
```
**Effort**: 5 minutes.

### 1.2 Fix IP Extraction
Only trust `X-Forwarded-For` in production behind a trusted proxy:
```python
def get_client_ip(request):
    if settings.environment == "production":
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
```
**Effort**: 30 minutes.

### 1.3 Fix CORS
Remove wildcard from dev origins. Use only specific localhost URLs.
**Effort**: 5 minutes.

## Priority 2: Within 1-2 Weeks

### 2.1 Token Blacklist
Redis-based token blacklist for logout revocation.
**Effort**: 2-3 hours.

### 2.2 Login Rate Limiting
Add `@limiter.limit("10/minute")` to login endpoint.
**Effort**: 15 minutes.

### 2.3 Path Traversal Protection
Validate file paths are within expected directories.
**Effort**: 30 minutes.

### 2.4 Email Verification Token Expiration
Add expiration timestamp and validate on verification.
**Effort**: 1 hour (includes Alembic migration).

## Priority 3: Within 1-2 Months

### 3.1 CSRF Tokens
Double-submit cookie pattern for state-changing operations.

### 3.2 Security Monitoring
- Login alerts for new devices
- Email notifications for password changes
- Active sessions dashboard
- Brute force detection with temporary account lockout

### 3.3 Dependency Hardening
- Pin exact versions in `requirements.txt`
- Run `pip audit` in CI
- Monthly dependency updates

### 3.4 Security.txt
Create `/.well-known/security.txt` with responsible disclosure information.

---

## What We're Already Good At

These are areas where the codebase passes security review and an auditor would approve:

1. **Multi-tenant data isolation** - Consistent `user_id` filtering everywhere
2. **Password hashing** - bcrypt with proper salt
3. **Input validation** - Pydantic + bleach sanitization
4. **File upload security** - Extension whitelist + MIME type + size limits
5. **Security headers** - Comprehensive header middleware
6. **Audit trail** - Full before/after logging with IP/UA
7. **MFA** - TOTP + email with encrypted secrets
8. **RBAC** - 6 roles with 22 granular permissions + custom claims
9. **Payment security** - Stripe handles PCI-DSS
10. **Error handling** - Exception handlers don't leak internals
11. **SQL injection** - SQLAlchemy ORM prevents injection (no raw SQL)
12. **XSS** - bleach.clean() on all text inputs
13. **HSTS** - Enabled in production
14. **Session management** - Device limit, auto-kick, fingerprinting
15. **LGPD compliance** - Consent timestamps, encrypted sensitive data

These 15 security features demonstrate a security-conscious development approach. The issues found are common in fast-moving startups and are straightforward to fix.

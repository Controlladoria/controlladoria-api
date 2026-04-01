# Runbooks de Incidente — ControlladorIA

**Versao**: 1.0
**Data**: 2026-03-05

---

## Runbook 1: API Backend Fora do Ar / Lenta

### Sintomas
- Frontend mostra "Erro de conexao" ou loading infinito
- Better Stack alerta indisponibilidade
- Railway mostra deploy failed ou crash loop

### Diagnostico

1. **Verificar status do Railway**
   ```
   Railway Dashboard -> Servico -> Deployments
   ```
   - Deploy falhou? Ver logs de build
   - Crash loop? Ver logs de runtime

2. **Verificar logs**
   ```
   Railway Dashboard -> Servico -> Logs
   ```
   Procurar por:
   - `alembic` errors (migracao falhou)
   - `ModuleNotFoundError` (dependencia faltando)
   - `OperationalError` (banco de dados)
   - `SIGKILL` / `OOM` (memoria)

3. **Testar endpoint de saude**
   ```bash
   curl https://API_URL/health
   ```
   - 200: API esta rodando, problema pode ser em rota especifica
   - Timeout: API esta down

### Acoes

| Causa | Acao |
|-------|------|
| Migracao Alembic falhou | Corrigir migracao, push para main, Railway redeploy automatico |
| Dependencia faltando | Adicionar em `requirements.txt`, push |
| Erro de banco (connection refused) | Verificar PostgreSQL no Railway, pode estar em manutencao |
| OOM (Out of Memory) | Verificar se processamento de documento grande causou spike. Considerar upgrade de plano Railway |
| Deploy travado | Railway Dashboard -> Redeploy manual |

### Validacao
- `curl https://API_URL/health` retorna 200
- Frontend carrega dashboard normalmente
- Better Stack volta a reportar "up"

---

## Runbook 2: Processamento de Documento Falha

### Sintomas
- Usuario faz upload e recebe "Erro ao processar documento"
- Log: `structured_processor - ERROR`
- Documento fica com status `error`

### Diagnostico

1. **Verificar logs do processador**
   Procurar por:
   - `Error code: 400` — parametro invalido na API de IA
   - `Error code: 401` — API key invalida ou expirada
   - `Error code: 429` — rate limit atingido
   - `Error code: 500` — erro do provedor de IA
   - `Invalid MIME type` — PDF enviado como imagem para OpenAI
   - `max_tokens` / `max_completion_tokens` — parametro errado para o modelo

2. **Verificar tipo de documento**
   - XML/OFX: processados sem IA (problema e de parsing, nao de IA)
   - PDF/Imagem/Excel/DOCX: processados com IA

3. **Testar manualmente**
   ```bash
   curl -X POST https://API_URL/documents/upload \
     -H "Authorization: Bearer TOKEN" \
     -F "file=@documento.pdf"
   ```

### Acoes

| Causa | Acao |
|-------|------|
| API key expirada | Renovar key no painel OpenAI/Anthropic, atualizar env var no Railway |
| Rate limit (429) | Aguardar (retry automatico com backoff). Se persistente: verificar volume de requests |
| Parametro invalido (400) | Verificar se modelo mudou parametros (ex: `max_tokens` -> `max_completion_tokens`). Atualizar codigo |
| PDF nao aceito pelo OpenAI | Verificar se `pdf2image` esta convertendo para PNG. Poppler instalado? |
| Documento corrompido | Informar usuario para re-enviar arquivo |
| JSON invalido na resposta | IA retornou texto em vez de JSON. Prompt pode precisar de ajuste |

### Validacao
- Re-upload do mesmo documento processa com sucesso
- Log mostra `Extracted CNPJs` ou `Processing complete`

---

## Runbook 3: Erro de Migracao Alembic

### Sintomas
- Deploy falha no Railway com erro de Alembic
- Log: `sqlalchemy.exc.OperationalError` ou `psycopg2.errors`
- App nao inicia (startup command falha)

### Diagnostico

1. **Verificar log de erro exato**
   Erros comuns:
   - `constraint "X" does not exist` — nome de constraint hardcoded errado
   - `column "X" already exists` — migracao executada parcialmente
   - `relation "X" does not exist` — tabela nao existe ainda
   - `Multiple heads` — branch de migracao divergente

2. **Verificar historico de migracoes**
   ```bash
   alembic history --verbose
   alembic heads
   ```

### Acoes

| Causa | Acao |
|-------|------|
| Constraint name errado | Usar SQL dinamico para descobrir nome real (ver `pg_constraint`). Corrigir migracao |
| Coluna ja existe | Adicionar `IF NOT EXISTS` ou check antes de adicionar |
| Branch divergente (multiple heads) | `alembic merge heads` para criar merge migration |
| Migracao parcial | Pode ser necessario ajustar `alembic_version` manualmente no banco. **CUIDADO**: fazer backup antes |
| Enum PostgreSQL | Usar `ALTER TYPE ... ADD VALUE IF NOT EXISTS` (enums nao suportam transacao) |

### Validacao
- `alembic upgrade head` completa sem erro
- `alembic current` mostra head correto
- App inicia normalmente

### Prevencao
- Sempre verificar `alembic heads` antes de criar nova migracao
- Usar nomes de constraint dinamicos (introspeccao do catalog) em vez de hardcoded
- Testar migracoes localmente com PostgreSQL antes de push

---

## Runbook 4: Provedor de IA Indisponivel

### Sintomas
- Uploads falham com `Error code: 500` ou timeout
- Log: `openai.APIConnectionError` ou `anthropic.APIConnectionError`
- Status page do provedor mostra incidente

### Diagnostico

1. **Verificar status do provedor**
   - OpenAI: https://status.openai.com
   - Anthropic: https://status.anthropic.com

2. **Verificar nos logs**
   - Todos os documentos falhando? Provedor indisponivel
   - Apenas alguns? Pode ser rate limit ou documento especifico

### Acoes

| Causa | Acao |
|-------|------|
| OpenAI fora do ar | Trocar `AI_PROVIDER=anthropic` no Railway env vars. Reiniciar servico |
| Anthropic fora do ar | Trocar `AI_PROVIDER=openai` no Railway env vars. Reiniciar servico |
| Ambos fora do ar | Informar usuarios. XML e OFX continuam funcionando (sem IA). Outros documentos ficam em fila para reprocessamento |
| Rate limit persistente | Verificar se consumo esta normal. Considerar upgrade de tier na OpenAI/Anthropic |

### Validacao
- Upload de documento de teste processa com sucesso
- Logs mostram chamadas bem-sucedidas ao novo provedor

### Troca Rapida de Provedor
```
Railway Dashboard -> Servico -> Variables
AI_PROVIDER = anthropic  (ou openai)
Salvar -> Redeploy automatico
```
Tempo estimado: 2-3 minutos.

---

## Runbook 5: Problemas de Autenticacao / Login

### Sintomas
- Usuarios nao conseguem fazer login
- Token expirado e refresh nao funciona
- MFA nao aceita codigo

### Diagnostico

1. **Login falha com credenciais corretas**
   - Verificar se `JWT_SECRET_KEY` mudou (invalida todos os tokens)
   - Verificar se banco de dados esta acessivel
   - Verificar rate limiting (se implementado)

2. **Token refresh falha**
   - Refresh token expirado (> 7 dias sem login)?
   - `JWT_SECRET_KEY` foi alterada?

3. **MFA nao aceita codigo**
   - Relogio do dispositivo do usuario esta sincronizado? (TOTP depende de hora)
   - TOTP window: aceita +/- 1 intervalo (30s)
   - Backup codes usados? (10 codigos unicos)

### Acoes

| Causa | Acao |
|-------|------|
| JWT_SECRET_KEY mudou | Todos os tokens invalidados. Usuarios precisam re-logar. Normal em mudanca de env var |
| Banco inacessivel | Ver Runbook 1 (API down) |
| MFA clock skew | Orientar usuario a sincronizar relogio. Android: Settings -> Date -> Auto. iOS: Settings -> General -> Date |
| Usuario bloqueado (muitas tentativas) | Verificar se ha lock de conta. Atualmente nao ha — pode ser rate limit de IP |
| Email MFA nao chega | Verificar credenciais do Resend no env. Verificar spam/junk folder |
| ENCRYPTION_KEY mudou | Segredos MFA ficam illegiveis. Usuarios precisam re-configurar MFA |

### Validacao
- Login com credenciais validas retorna tokens
- MFA aceita codigo correto
- Dashboard carrega apos login

---

## Escalonamento

Se o problema nao e resolvido com os runbooks acima:

1. **Infraestrutura** (Railway, Vercel): Verificar status pages, abrir ticket de suporte
2. **Banco de dados**: Conectar via psql para diagnostico manual (Railway fornece connection string)
3. **Provedor de IA**: Verificar status page, considerar trocar provedor temporariamente
4. **Stripe**: Verificar dashboard do Stripe, logs de webhook

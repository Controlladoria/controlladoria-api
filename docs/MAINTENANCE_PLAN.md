# Plano de Manutencao e Politica de Versoes — ControlladorIA

**Versao**: 1.0
**Data**: 2026-03-05

---

## 1. Ciclo de Releases

| Tipo | Frequencia | Descricao | Exemplo |
|------|-----------|-----------|---------|
| **Hotfix** | Quando necessario | Correcao critica em producao | Bug de login, migracao quebrada |
| **Patch** | Semanal | Bug fixes, ajustes de UI, melhorias menores | Correcao de label, ajuste de prompt |
| **Minor** | Quinzenal/Mensal | Novas funcionalidades, melhorias significativas | Novo tipo de relatorio, nova integracao |
| **Major** | Trimestral | Mudancas arquiteturais, breaking changes | Refatoracao de IA, novo modelo de dados |

### Fluxo de Deploy

```
Feature branch -> Pull Request -> CI (testes) -> Merge to main -> Railway auto-deploy
```

- Railway faz deploy automatico a cada push para `main`
- Vercel faz deploy automatico a cada push para `main` (frontend)
- Rollback: Railway permite reverter para deploy anterior via dashboard
- Nao ha janela de manutencao — deploys sao zero-downtime (Railway reinicia graciosamente)

---

## 2. Versionamento

### Aplicacao (API)

- Versao atual: `0.4.0` (configurada em `config.py` -> `api_version`)
- Formato: Semantic Versioning (`MAJOR.MINOR.PATCH`)
- Versionamento de API: sem prefixo de versao na URL atualmente (`/documents`, nao `/v1/documents`)
- **Politica**: Breaking changes na API requerem aviso previo aos consumidores e periodo de depreciacao

### Banco de Dados (Migracoes)

- Gerenciado via Alembic
- Cada migracao tem um revision ID unico (hash)
- Cadeia atual: ~10 migracoes desde o inicio
- Head atual: `a1b2c3d4e5f6` (multi-org subscriptions)
- **Politica**: Nunca apagar migracoes. Sempre criar nova migracao para desfazer mudancas.
- **Politica**: Testar migracoes localmente com PostgreSQL antes de push

### Modelos de IA

- Nao fazemos fine-tuning — usamos modelos via API
- Versao do modelo e registrada por documento (`ai_model` field)
- Mudanca de modelo: alterar env var `OPENAI_MODEL` ou `ANTHROPIC_MODEL`
- **Politica**: Testar novo modelo com 20-50 documentos reais antes de promover para producao

### Frontend

- Versao vinculada ao deploy (commit hash)
- Nao tem versionamento separado
- Deploys no Vercel sao imutaveis (cada deploy tem URL unica)

---

## 3. Patching de Seguranca

### Dependencias Python

```bash
# Verificar vulnerabilidades
pip audit

# Atualizar dependencias
pip install --upgrade PACOTE
```

- **Frequencia**: Mensal (ou imediatamente para CVEs criticas)
- **Responsavel**: Tech Lead
- **Processo**: Atualizar `requirements.txt` -> rodar testes -> merge -> deploy

### Dependencias Frontend (npm)

```bash
# Verificar vulnerabilidades
npm audit

# Atualizar
npm update
```

- **Frequencia**: Mensal
- **Cuidado**: Atualizacoes de Next.js podem ter breaking changes — testar build antes de merge

### Sistema Operacional (Railway)

- Railway gerencia o SO base (Nixpacks)
- Atualizacoes de seguranca do SO sao automaticas
- Aptfile (`poppler-utils`, `libmagic1`) reinstalados a cada deploy

---

## 4. Backup e Recuperacao

### Banco de Dados

| Item | Configuracao |
|------|-------------|
| Provedor | Railway PostgreSQL (managed) |
| Backup automatico | Sim (diario, gerenciado pelo Railway) |
| Retencao | 7 dias (Railway free/pro) |
| Backup manual | `pg_dump` via connection string |
| Restore | `pg_restore` ou Railway dashboard |

### Arquivos (S3)

| Item | Configuracao |
|------|-------------|
| Provedor | AWS S3 |
| Redundancia | S3 Standard (99.999999999% durabilidade) |
| Versionamento | Nao habilitado (considerar para producao) |
| Retencao | Indefinida (ate exclusao) |

### RTO / RPO

| Metrica | Meta | Atual |
|---------|------|-------|
| **RTO** (Recovery Time Objective) | < 1 hora | ~30 min (redeploy Railway + restore banco) |
| **RPO** (Recovery Point Objective) | < 24 horas | 24h (backup diario Railway) |

---

## 5. Monitoramento Continuo

| Ferramenta | O que monitora | Alertas |
|-----------|---------------|---------|
| **Railway** | CPU, memoria, rede, deploy status | Dashboard |
| **Better Stack** | Uptime do endpoint `/health` | Email/SMS quando down |
| **Sentry** | Excecoes e erros nao tratados | Email por erro novo |
| **Logs (Railway)** | Stdout/stderr da aplicacao | Manual (busca no dashboard) |

### Metricas a Acompanhar

- Uptime mensal (meta: 99.5%)
- Tempo medio de processamento de documento
- Taxa de erro de IA (% de documentos com status "error")
- Numero de documentos processados por dia
- Custo de API de IA por mes

---

## 6. Processo de Rollback

### Backend (Railway)

1. Railway Dashboard -> Servico -> Deployments
2. Encontrar ultimo deploy funcional
3. Clicar "Redeploy"
4. Tempo: ~2 minutos

**Cuidado com migracoes**: Se o deploy incluiu migracao Alembic, o rollback do codigo nao reverte o banco. Pode ser necessario criar migracao de downgrade.

### Frontend (Vercel)

1. Vercel Dashboard -> Projeto -> Deployments
2. Encontrar ultimo deploy funcional
3. Clicar "..." -> "Promote to Production"
4. Tempo: ~1 minuto

### Banco de Dados

1. Railway Dashboard -> PostgreSQL -> Backups
2. Selecionar backup anterior ao problema
3. Restaurar
4. Tempo: ~15-30 minutos dependendo do tamanho

**IMPORTANTE**: Restaurar banco perde dados inseridos apos o backup. Usar apenas como ultimo recurso.

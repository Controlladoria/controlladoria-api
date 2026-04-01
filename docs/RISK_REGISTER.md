# Registro de Riscos — ControlladorIA

**Versao**: 1.0
**Data**: 2026-03-05

---

| # | Risco | Probabilidade | Impacto | Severidade | Mitigacao | Status |
|---|-------|--------------|---------|------------|-----------|--------|
| R01 | **Indisponibilidade do provedor de IA** (OpenAI/Anthropic fora do ar) | Media | Alto | Alto | Dois provedores configurados (OpenAI + Anthropic). Troca via env var. Plano: fallback automatico (AIDispatcher). XML e OFX processados sem IA. | Mitigado parcialmente |
| R02 | **Aumento de custo de API de IA** (reajuste de precos dos modelos) | Media | Medio | Medio | Modelo default e `gpt-5-mini` (mais barato). Cache de respostas via Redis. Possibilidade de trocar para modelos mais baratos sem mudanca de codigo. | Mitigado |
| R03 | **Classificacao incorreta pela IA** (categoria contabil errada) | Alta | Medio | Alto | Fila de validacao humana obrigatoria. Usuario revisa e corrige antes de incorporar nos relatorios. 52 categorias com descricoes detalhadas no prompt. | Mitigado |
| R04 | **Vazamento de dados entre tenants** (usuario ve dados de outra organizacao) | Baixa | Critico | Alto | Todas as queries filtram por `user_id` via `get_accessible_user_ids()`. S3 usa path `users/{user_id}/`. Testes de isolamento em CI. | Mitigado |
| R05 | **Indisponibilidade da API CNPJ** (BrasilAPI, SERPRO, ReceitaWS) | Media | Baixo | Baixo | 3 provedores em cascata (BrasilAPI -> SERPRO -> ReceitaWS). Cadastro funciona com dados manuais se todas falharem. | Mitigado |
| R06 | **Perda de dados** (falha no banco de dados ou storage) | Baixa | Critico | Alto | PostgreSQL gerenciado (Railway/Render) com backups automaticos. S3 para arquivos com redundancia. Alembic migrations versionadas. | Mitigado parcialmente |
| R07 | **Ataque de forca bruta** (tentativas de login) | Media | Medio | Medio | MFA (TOTP + Email) implementado. Limite de 2 sessoes simultaneas. Rate limiting em registro e upload. **Gap**: login sem rate limiting explicito. | Mitigado parcialmente |
| R08 | **Token JWT roubado** (sessao comprometida) | Baixa | Alto | Medio | Access token expira em 30min. Refresh token em 7 dias. Limite de sessoes com auto-kick. **Gap**: sem blacklist de tokens (logout nao revoga). | Mitigado parcialmente |
| R09 | **Custo de infraestrutura escala alem do faturamento** | Media | Alto | Alto | Modelo SaaS com planos (trial/pro). AI cache reduz chamadas duplicadas. Modelo gpt-5-mini 10x mais barato que gpt-4o. Monitoramento de custos. | Monitorado |
| R10 | **Mudanca de API dos provedores de IA** (breaking change na OpenAI/Anthropic SDK) | Baixa | Medio | Baixo | SDKs versionados em requirements.txt. Alteracoes de parametro (ex: max_tokens -> max_completion_tokens) detectadas rapidamente em producao. | Aceito |
| R11 | **Poppler/libmagic indisponivel no deploy** (dependencias de sistema) | Baixa | Alto | Medio | `Aptfile` com `poppler-utils` e `libmagic1`. Testado em Railway (Nixpacks). Fallback: PDF enviado como texto (pypdf) se poppler falhar. | Mitigado |
| R12 | **Falha de migracao Alembic em producao** | Media | Alto | Alto | Migracoes executam no startup (`alembic upgrade head`). Timeout de 30s. Nomes de constraints descobertos dinamicamente (vs hardcoded). Railway restart on failure. | Mitigado |

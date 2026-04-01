# Termo de Abertura do Projeto (TAP) — ControlladorIA

**Versao**: 1.0
**Data**: 2026-03-05
**Status**: Em execucao (MVP em producao)

---

## 1. Objetivo do Projeto

Desenvolver uma plataforma SaaS de controladoria financeira com inteligencia artificial que automatiza a ingestao, classificacao e consolidacao de documentos financeiros (Notas Fiscais, recibos, boletos, extratos bancarios) para micro, pequenas e medias empresas brasileiras, eliminando o trabalho manual de digitacao e organizacao contabil.

## 2. Problema

Empresas de pequeno e medio porte no Brasil dependem de processos manuais para organizar documentos financeiros. Contadores e controllers gastam horas classificando notas fiscais, digitando valores e montando demonstrativos (DRE, Balanco Patrimonial, Fluxo de Caixa). Esse processo e lento, sujeito a erros e caro.

## 3. Proposta de Valor

- **Automatizacao por IA**: Upload de documento -> classificacao automatica em 52 categorias contabeis -> relatorios prontos
- **Reducao de tempo**: De horas para minutos no fechamento mensal
- **Precisao**: Validacao automatica com CNPJ, valores e categorias
- **Acessibilidade**: Interface web responsiva, preco acessivel para PMEs
- **Conformidade**: Padroes contabeis brasileiros (CPC/IFRS), trilha de auditoria completa

## 4. Escopo

### Dentro do Escopo (In)

| Modulo | Descricao | Status |
|--------|-----------|--------|
| Autenticacao | Registro, login, MFA (TOTP + Email), RBAC com 6 papeis | Implementado |
| Upload de Documentos | PDF, imagens, Excel, XML, OFX/OFC, DOCX | Implementado |
| Processamento por IA | Extracao estruturada com OpenAI/Anthropic, 52 categorias | Implementado |
| Validacao | Fila de validacao humana, CNPJ cruzado, alertas | Implementado |
| DRE Gerencial | Demonstrativo de Resultado por periodo com 52 linhas | Implementado |
| Balanco Patrimonial | Ativo, Passivo, Patrimonio Liquido | Implementado |
| Fluxo de Caixa | Metodo direto, por periodo | Implementado |
| Dashboard | 10 graficos interativos (Recharts) | Implementado |
| Multi-Organizacao | Multiplas empresas por usuario, troca sem logout | Implementado |
| Pagamentos | Stripe (planos, trial, portal do cliente) | Implementado |
| Exportacao | PDF e Excel para DRE, Balanco, Fluxo de Caixa | Implementado |
| Auditoria | Trilha completa (quem/o que/quando/de onde) | Implementado |
| Admin | Painel admin com metricas, usuarios, logs | Implementado |

### Fora do Escopo (Out) — Para releases futuros

- Integracao direta com ERPs (SAP, TOTVS, Omie)
- Integracao WhatsApp Business
- Conciliacao bancaria automatica
- Previsao de fluxo de caixa (ML preditivo)
- App mobile nativo (iOS/Android) — PWA planejado
- Emissao de Nota Fiscal

## 5. Stakeholders

| Papel | Responsabilidade |
|-------|------------------|
| Product Owner | Visao do produto, priorizacao, decisoes de negocio |
| Tech Lead / Dev | Arquitetura, desenvolvimento, deploy, manutencao |
| Contadores-piloto | Validacao de regras contabeis, feedback de usabilidade |
| Usuarios finais (PMEs) | Uso diario, feedback, validacao de documentos |

## 6. Premissas

1. Usuarios possuem CNPJ ativo e documentos financeiros digitalizados
2. Conexao com internet disponivel para uso da plataforma
3. OpenAI e/ou Anthropic manterao APIs estaveis e precos competitivos
4. Stripe disponivel para processamento de pagamentos no Brasil
5. Poppler e dependencias de sistema disponivies no ambiente de deploy

## 7. Restricoes

1. **Orcamento**: Custos de infraestrutura devem ser compativeis com modelo SaaS para PMEs
2. **Regulatorio**: Conformidade com LGPD para dados financeiros
3. **Tecnico**: Dependencia de APIs de IA externas (OpenAI, Anthropic)
4. **Performance**: Processamento de documento deve completar em ate 60 segundos

## 8. Stack Tecnologica

| Camada | Tecnologia |
|--------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Recharts |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic |
| Banco de Dados | PostgreSQL (producao), SQLite (desenvolvimento) |
| IA | OpenAI (gpt-5-mini), Anthropic (claude-haiku-4-5) |
| Armazenamento | AWS S3 (producao), filesystem local (desenvolvimento) |
| Pagamentos | Stripe |
| Email | Resend |
| Deploy | Railway (backend), Vercel (frontend) |
| Monitoramento | Railway metrics, Better Stack (uptime), Sentry (erros) |

## 9. Roadmap

| Release | Conteudo | Status |
|---------|----------|--------|
| **MVP (R1)** | Upload + IA + DRE + Balanco + Fluxo + Dashboard + Auth + Stripe | Em producao |
| **R2** | PWA, conciliacao bancaria, integracao ERP basica, relatorios avancados | Planejado |
| **R3** | WhatsApp Business, ML preditivo, app mobile, marketplace de conectores | Futuro |

## 10. KPIs de Sucesso

| Metrica | Meta MVP | Meta R2 |
|---------|----------|---------|
| Tempo de processamento por documento | < 60s | < 30s |
| Precisao de classificacao da IA | > 85% | > 92% |
| Uptime da plataforma | 99.5% | 99.9% |
| NPS (usuarios-piloto) | > 40 | > 60 |
| Documentos processados/mes | 1.000 | 10.000 |
| Usuarios ativos | 10 | 100 |

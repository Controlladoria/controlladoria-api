# Relatorios Financeiros / Financial Reports

> DRE (Income Statement), Balanco Patrimonial (Balance Sheet), Fluxo de Caixa (Cash Flow)
>
> Documentacao do sistema de geracao de relatorios contabeis automatizados.

---

## PT-BR: Relatorios Financeiros

### Visao Geral

O sistema gera tres relatorios contabeis principais, todos seguindo normas contabeis brasileiras (CPC/IFRS):

1. **DRE** - Demonstracao do Resultado do Exercicio (Income Statement)
2. **Balanco Patrimonial** - Balance Sheet
3. **Fluxo de Caixa** - Cash Flow Statement

Todos os relatorios sao calculados em tempo real a partir dos documentos processados, com filtros de data. Nao ha cache de relatorios - cada chamada recalcula com base nos dados atuais.

### DRE (Demonstracao do Resultado do Exercicio)

#### Endpoint
```
GET /reports/dre?date_from=2026-01-01&date_to=2026-12-31
```

#### Estrutura do Relatorio

A DRE segue a estrutura padrao brasileira com 52 categorias organizadas em secoes:

```
1. RECEITA BRUTA
   1.1.01 Receita de Vendas de Produtos
   1.1.02 Receita de Prestacao de Servicos
   1.1.03 Receita de Locacao
   1.1.04 Receita de Comissoes
   1.1.05 Receita de Contratos Recorrentes
   1.1.06 Outras Receitas Operacionais

2. (-) DEDUCOES DA RECEITA
   1.2.01 Impostos sobre Vendas (ICMS, ISS, PIS, COFINS)
   1.2.02 Devolucoes e Abatimentos
   1.2.03 Descontos Incondicionais Concedidos

   = RECEITA LIQUIDA (1 - 2)

3. (-) CUSTOS VARIAVEIS (CMV/CPV/CSP)
   2.1.01 Custo das Mercadorias Vendidas (CMV)
   2.1.02 Custo dos Produtos Vendidos (CPV)
   2.1.03 Custo dos Servicos Prestados (CSP)
   2.1.04 Materiais Diretos / Materia-Prima
   2.1.05 Mao de Obra Direta
   2.1.06 Custos de Producao
   2.1.07 Frete sobre Vendas
   2.1.08 Comissoes sobre Vendas
   2.1.09 Embalagens

   = MARGEM DE CONTRIBUICAO (Receita Liquida - Custos Variaveis)

4. (-) DESPESAS FIXAS ADMINISTRATIVAS
   3.1.01 Salarios e Encargos Administrativos
   3.1.02 Pro-labore / Retirada dos Socios
   3.1.03 Aluguel e Condominio
   3.1.04 Energia Eletrica, Agua, Telefone
   3.1.05 Material de Escritorio e Limpeza
   3.1.06 Servicos de Contabilidade
   3.1.07 Honorarios Advocaticios e Consultoria
   3.1.08 Seguros
   3.1.09 Manutencao e Reparos
   3.1.10 Sistemas e Softwares (TI)
   3.1.11 Despesas com Veiculos
   3.1.12 Viagens e Hospedagens
   3.1.13 Alimentacao e Refeicoes
   3.1.14 Despesas Diversas Administrativas

5. (-) DESPESAS FIXAS COMERCIAIS
   3.2.01 Marketing e Publicidade
   3.2.02 Salarios e Encargos Comerciais
   3.2.03 Eventos e Feiras

6. (-) DEPRECIACAO E AMORTIZACAO
   4.1.01 Depreciacao de Maquinas e Equipamentos
   4.1.02 Depreciacao de Veiculos
   4.1.03 Amortizacao de Intangiveis

   = RESULTADO OPERACIONAL (EBITDA ajustado)

7. (+/-) RESULTADO FINANCEIRO
   5.1.01 Receitas Financeiras (Juros, Rendimentos)
   5.1.02 Despesas Financeiras (Juros, Tarifas)
   5.1.03 Variacao Cambial

   = RESULTADO ANTES DOS IMPOSTOS

8. (-) IMPOSTOS SOBRE O LUCRO
   6.1.01 IRPJ (Imposto de Renda Pessoa Juridica)
   6.1.02 CSLL (Contribuicao Social sobre o Lucro)
   6.1.03 Outros Tributos sobre o Lucro

   = RESULTADO LIQUIDO DO PERIODO
```

#### Categorias V2 (`accounting/categories.py`)

O sistema usa 52 categorias mapeadas do Plano de Contas padrao brasileiro. Cada categoria possui:

- `account_code`: Codigo contabil (ex: "1.1.01")
- `dre_line`: Identificador unico da linha
- `line_type`: Tipo DRE (REVENUE, DEDUCTION, VARIABLE_COST, etc.)
- `dre_group`: Grupo na DRE (ex: "Receita Bruta")
- `nature`: Receita ou Despesa
- `cost_behavior`: Variavel ou Fixo (para analise de margem)
- `sign`: +1 (soma) ou -1 (subtrai)
- `order`: Ordem de exibicao no relatorio

#### Classificacao Automatica

Quando a AI extrai um documento, ela classifica a transacao em uma das 52 categorias. O mapeamento e feito pela funcao `get_dre_category()` que resolve alias e categorias legadas para o formato V2.

#### Calculo da DRE

```python
# Pseudo-codigo do calculo
receita_bruta = sum(docs where line_type == REVENUE)
deducoes = sum(docs where line_type == DEDUCTION)
receita_liquida = receita_bruta - deducoes

custos_variaveis = sum(docs where line_type == VARIABLE_COST)
margem_contribuicao = receita_liquida - custos_variaveis

despesas_admin = sum(docs where line_type == FIXED_EXPENSE_ADMIN)
despesas_comerciais = sum(docs where line_type == FIXED_EXPENSE_COMMERCIAL)
depreciacao = sum(docs where line_type == DEPRECIATION)
resultado_operacional = margem_contribuicao - despesas_admin - despesas_comerciais - depreciacao

resultado_financeiro = sum(FINANCIAL_REVENUE) - sum(FINANCIAL_EXPENSE)
resultado_antes_impostos = resultado_operacional + resultado_financeiro

impostos = sum(docs where line_type == TAX_ON_PROFIT)
resultado_liquido = resultado_antes_impostos - impostos
```

### Balanco Patrimonial (Balance Sheet)

#### Endpoint
```
GET /reports/balance-sheet?date=2026-12-31
```

#### Estrutura

Baseado no Plano de Contas (`chart_of_accounts`) e lancamentos contabeis (`journal_entries`):

```
ATIVO (Assets)
  Ativo Circulante (Current Assets)
    - Caixa e Equivalentes
    - Contas a Receber
    - Estoques
    - Impostos a Recuperar
  Ativo Nao Circulante (Non-Current Assets)
    - Imobilizado
    - Intangivel
    - Investimentos

PASSIVO (Liabilities)
  Passivo Circulante (Current Liabilities)
    - Fornecedores
    - Salarios a Pagar
    - Impostos a Pagar
    - Emprestimos CP
  Passivo Nao Circulante (Non-Current Liabilities)
    - Emprestimos LP
    - Provisoes

PATRIMONIO LIQUIDO (Equity)
  - Capital Social
  - Reservas
  - Lucros/Prejuizos Acumulados
```

#### Partida Dobrada (Double-Entry)

O sistema usa partida dobrada verdadeira:
- Cada `JournalEntry` tem 2+ `JournalEntryLine` (debito e credito)
- Valores armazenados em **centavos** (evita problemas com decimais)
- `debit_amount` e `credit_amount` em cada linha
- Soma de debitos DEVE igualar soma de creditos

### Fluxo de Caixa (Cash Flow)

#### Endpoint
```
GET /reports/cash-flow?date_from=2026-01-01&date_to=2026-12-31
```

#### Estrutura (Metodo Indireto)

```
ATIVIDADES OPERACIONAIS
  Resultado Liquido do Periodo
  (+) Depreciacao e Amortizacao
  (+/-) Variacao de Contas a Receber
  (+/-) Variacao de Estoques
  (+/-) Variacao de Fornecedores
  = Caixa Gerado pelas Operacoes

ATIVIDADES DE INVESTIMENTO
  (-) Aquisicao de Imobilizado
  (-) Aquisicao de Intangiveis
  (+) Venda de Ativos
  = Caixa das Atividades de Investimento

ATIVIDADES DE FINANCIAMENTO
  (+) Emprestimos Obtidos
  (-) Pagamento de Emprestimos
  (-) Distribuicao de Lucros
  = Caixa das Atividades de Financiamento

= VARIACAO LIQUIDA DE CAIXA
+ Saldo Inicial de Caixa
= SALDO FINAL DE CAIXA
```

### Exportacao de Relatorios

#### Excel
```
GET /reports/export/excel?date_from=...&date_to=...
```
Gera arquivo `.xlsx` com:
- Aba "Resumo" com totais
- Aba "Transacoes" com todas as transacoes detalhadas
- Formatacao brasileira (R$, datas dd/mm/yyyy)

#### PDF
```
GET /reports/export/pdf?date_from=...&date_to=...
```
Gera PDF formatado usando `reportlab` com:
- Logo e cabecalho
- Tabelas formatadas
- Totais e subtotais

#### CSV
```
GET /reports/export/csv?date_from=...&date_to=...
```
CSV simples para importacao em outros sistemas.

### Dashboard (10 Graficos)

O frontend renderiza 10 graficos interativos com Recharts:

1. **Receita vs Despesa** (mensal) - BarChart
2. **Evolucao do Saldo** - AreaChart
3. **Distribuicao por Categoria** - PieChart
4. **Top 5 Despesas** - HorizontalBarChart
5. **Fluxo de Caixa Mensal** - ComposedChart
6. **Margem de Lucro** - LineChart
7. **Comparativo Ano a Ano** - GroupedBarChart
8. **Status dos Documentos** - DonutChart
9. **Tendencia de Receita** - LineChart com previsao
10. **Sazonalidade** - RadarChart

Todos usam `dynamic import` com `ssr: false` para renderizacao client-side (Recharts nao suporta SSR).

---

## EN-US: Financial Reports

### Overview

The system generates three main accounting reports, all following Brazilian accounting standards (CPC/IFRS):

1. **DRE** - Income Statement (Demonstracao do Resultado do Exercicio)
2. **Balance Sheet** (Balanco Patrimonial)
3. **Cash Flow Statement** (Fluxo de Caixa)

All reports are calculated in real-time from processed documents, with date filters. There is no report caching - each call recalculates based on current data.

### DRE (Income Statement)

#### Endpoint
```
GET /reports/dre?date_from=2026-01-01&date_to=2026-12-31
```

#### Report Structure

The DRE follows the standard Brazilian structure with 52 categories organized in sections:

```
1. GROSS REVENUE
   Product Sales, Service Revenue, Rental, Commissions, Recurring Contracts, Other

2. (-) REVENUE DEDUCTIONS
   Sales Taxes, Returns, Unconditional Discounts

   = NET REVENUE

3. (-) VARIABLE COSTS (COGS)
   Cost of Goods Sold, Cost of Products, Cost of Services,
   Direct Materials, Direct Labor, Production Costs, Freight, Commissions, Packaging

   = CONTRIBUTION MARGIN

4. (-) FIXED ADMINISTRATIVE EXPENSES
   Salaries, Pro-labore, Rent, Utilities, Office Supplies, Accounting,
   Legal, Insurance, Maintenance, IT, Vehicles, Travel, Meals, Misc

5. (-) FIXED COMMERCIAL EXPENSES
   Marketing, Sales Salaries, Events

6. (-) DEPRECIATION & AMORTIZATION

   = OPERATING RESULT (adjusted EBITDA)

7. (+/-) FINANCIAL RESULT
   Financial Revenue - Financial Expenses +/- Foreign Exchange

   = RESULT BEFORE TAXES

8. (-) INCOME TAXES (IRPJ, CSLL)

   = NET INCOME
```

#### V2 Categories (`accounting/categories.py`)

The system uses 52 categories mapped from the standard Brazilian Chart of Accounts. Each category includes:

- `account_code`: Accounting code (e.g., "1.1.01")
- `dre_line`: Unique line identifier
- `line_type`: DRE type enum (REVENUE, DEDUCTION, VARIABLE_COST, etc.)
- `dre_group`: Group in the DRE (e.g., "Receita Bruta")
- `nature`: Revenue or Expense
- `cost_behavior`: Variable or Fixed (for margin analysis)
- `sign`: +1 (add) or -1 (subtract)
- `order`: Display order in the report

#### Automatic Classification

When AI extracts a document, it classifies the transaction into one of 52 categories. The mapping is done by `get_dre_category()` which resolves aliases and legacy categories to V2 format.

### Balance Sheet

#### Endpoint
```
GET /reports/balance-sheet?date=2026-12-31
```

Uses the Chart of Accounts (`chart_of_accounts`) and journal entries (`journal_entries`) with true double-entry bookkeeping:
- Each `JournalEntry` has 2+ `JournalEntryLine` entries (debit and credit)
- Values stored in **cents** (avoids decimal issues)
- Sum of debits MUST equal sum of credits

### Cash Flow Statement

#### Endpoint
```
GET /reports/cash-flow?date_from=2026-01-01&date_to=2026-12-31
```

Uses the indirect method, starting from Net Income and adjusting for non-cash items and working capital changes.

### Report Export

- **Excel** (`/reports/export/excel`): Multi-sheet XLSX with summary and transaction details
- **PDF** (`/reports/export/pdf`): Formatted PDF using reportlab
- **CSV** (`/reports/export/csv`): Simple CSV for import into other systems

### Dashboard Charts

10 interactive charts rendered with Recharts in the Next.js frontend, using dynamic imports with `ssr: false` for client-side rendering. Charts include revenue vs expense, balance evolution, category distribution, top expenses, cash flow, profit margin, year-over-year comparison, document status, revenue trend, and seasonality.

### Multi-Tenant Data Isolation

All report queries filter by `user_id` using `get_accessible_user_ids()`:
- **Owner/Admin**: Sees their data + all team members' data
- **Team members**: See owner's data + their own + siblings' data
- Data is NEVER leaked between organizations

```python
# Every report query follows this pattern
documents = db.query(Document).filter(
    Document.user_id.in_(get_accessible_user_ids(current_user, db)),
    Document.status == DocumentStatus.COMPLETED,
)
```

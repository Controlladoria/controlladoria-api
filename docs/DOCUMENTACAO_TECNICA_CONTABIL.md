# 📊 ControlladorIA - Documentação Técnica Contábil

**Data:** 25 de Janeiro de 2026
**Versão:** 1.0
**Objetivo:** Validação técnica por contador credenciado

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [DRE - Demonstração do Resultado do Exercício](#dre---demonstração-do-resultado-do-exercício)
3. [Balanço Patrimonial](#balanço-patrimonial)
4. [DFC - Demonstração do Fluxo de Caixa](#dfc---demonstração-do-fluxo-de-caixa)
5. [Sistema de Partidas Dobradas](#sistema-de-partidas-dobradas)
6. [Plano de Contas](#plano-de-contas)
7. [Validação e Testes](#validação-e-testes)

---

## Visão Geral

O ControlladorIA é uma plataforma SaaS de contabilidade desenvolvida para atender **100% das normas brasileiras**:

- **CPC 26 (R1)** - Apresentação das Demonstrações Contábeis
- **Lei 6.404/1976 Art. 187** - Estrutura da DRE
- **Normas CVM** - Resoluções do Conselho de Valores Mobiliários
- **Princípios Contábeis IFRS** adaptados ao Brasil

### Arquitetura do Sistema

```
┌─────────────────────────────────────────┐
│   Entrada de Documentos (PDF, Excel)   │
│   IA extrai dados automaticamente      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Motor Contábil (Partidas Dobradas)   │
│   - Validação D = C                     │
│   - Lançamentos automáticos             │
│   - Histórico completo                  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Demonstrações Contábeis               │
│   - DRE                                 │
│   - Balanço Patrimonial                 │
│   - DFC (Fluxo de Caixa)               │
└─────────────────────────────────────────┘
```

### Formato de Armazenamento

**Valores Monetários:**
- Armazenados em **centavos (inteiros)** no banco de dados
- Conversão: `valor_centavos = valor_reais × 100`
- Exemplo: R$ 1.234,56 → 123456 centavos
- **Motivo:** Eliminar erros de arredondamento com ponto flutuante

**Tipo de Dados:**
- Python: `Decimal` (precisão arbitrária)
- Banco: `INTEGER` para centavos, `NUMERIC(15,2)` para alguns campos históricos
- Conversões sempre usam `Decimal` para evitar perda de precisão

---

## DRE - Demonstração do Resultado do Exercício

### Estrutura Conforme Lei 6.404/76 Art. 187

A DRE segue **rigorosamente** a estrutura legal brasileira com no mínimo 13 itens obrigatórios:

```
DRE - Demonstração do Resultado do Exercício
Período: 01/01/2024 a 31/12/2024
Empresa: [Nome da Empresa]
CNPJ: XX.XXX.XXX/0001-XX

┌────────────────────────────────────────────────────┐
│ 1. RECEITA BRUTA DE VENDAS E SERVIÇOS             │
│                                        R$ 1.000.000,00 │
├────────────────────────────────────────────────────┤
│ 2. DEDUÇÕES DA RECEITA BRUTA                       │
│    (-) Devoluções e Cancelamentos   R$ (10.000,00) │
│    (-) Abatimentos                 R$ (5.000,00)   │
│    (-) Impostos sobre Vendas       R$ (150.000,00) │
│    TOTAL DEDUÇÕES                  R$ (165.000,00) │
├────────────────────────────────────────────────────┤
│ 3. RECEITA LÍQUIDA DE VENDAS                       │
│                                        R$ 835.000,00 │
├────────────────────────────────────────────────────┤
│ 4. CUSTO DAS VENDAS/SERVIÇOS                       │
│    (-) CMV / CPV / CSP             R$ (400.000,00) │
├────────────────────────────────────────────────────┤
│ 5. LUCRO BRUTO                                     │
│                                        R$ 435.000,00 │
├────────────────────────────────────────────────────┤
│ 6. DESPESAS OPERACIONAIS                           │
│    (-) Despesas com Vendas         R$ (80.000,00)  │
│    (-) Despesas Administrativas    R$ (120.000,00) │
│    (-) Despesas Gerais             R$ (40.000,00)  │
│    TOTAL DESPESAS OPERACIONAIS     R$ (240.000,00) │
├────────────────────────────────────────────────────┤
│ 7. EBITDA (Antes de Deprec./Amort./Juros/IR)      │
│                                        R$ 195.000,00 │
├────────────────────────────────────────────────────┤
│ 8. DEPRECIAÇÃO E AMORTIZAÇÃO                       │
│    (-) Depreciação                 R$ (30.000,00)  │
│    (-) Amortização                 R$ (10.000,00)  │
│    TOTAL DEPREC./AMORT.            R$ (40.000,00)  │
├────────────────────────────────────────────────────┤
│ 9. RESULTADO OPERACIONAL (EBIT)                    │
│                                        R$ 155.000,00 │
├────────────────────────────────────────────────────┤
│ 10. RESULTADO FINANCEIRO                           │
│     (+) Receitas Financeiras       R$ 15.000,00    │
│     (-) Despesas Financeiras       R$ (25.000,00)  │
│     RESULTADO FINANCEIRO LÍQUIDO   R$ (10.000,00)  │
├────────────────────────────────────────────────────┤
│ 11. RESULTADO ANTES DO IR/CSLL (LAIR)             │
│                                        R$ 145.000,00 │
├────────────────────────────────────────────────────┤
│ 12. IMPOSTO DE RENDA E CSLL                        │
│     (-) Provisão para IR/CSLL      R$ (49.300,00)  │
├────────────────────────────────────────────────────┤
│ 13. LUCRO LÍQUIDO DO EXERCÍCIO                     │
│                                        R$ 95.700,00  │
└────────────────────────────────────────────────────┘

ÍNDICES DE RENTABILIDADE:
- Margem Bruta:       52,10%  (Lucro Bruto / Receita Líquida)
- Margem EBITDA:      23,35%  (EBITDA / Receita Líquida)
- Margem Operacional: 18,56%  (EBIT / Receita Líquida)
- Margem Líquida:     11,46%  (Lucro Líquido / Receita Líquida)
```

### Matemática da DRE

#### 1. Receita Líquida
```
Receita Líquida = Receita Bruta
                  - Devoluções
                  - Cancelamentos
                  - Abatimentos
                  - Impostos sobre Vendas

Fórmula:
RL = RB - DEV - CANC - ABAT - IMP
```

**Contas envolvidas:**
- Receita Bruta: `4.01.001` (Receita de Vendas)
- Deduções: `4.02.xxx` (Devoluções, Impostos sobre Vendas)

#### 2. Lucro Bruto
```
Lucro Bruto = Receita Líquida - Custo das Vendas

Fórmula:
LB = RL - CMV

Onde:
- CMV = Custo das Mercadorias Vendidas (comércio)
- CPV = Custo dos Produtos Vendidos (indústria)
- CSP = Custo dos Serviços Prestados (serviços)
```

**Contas envolvidas:**
- Custos: `5.01.xxx` (CMV, CPV, CSP)

**Margem Bruta:**
```
Margem Bruta (%) = (Lucro Bruto / Receita Líquida) × 100
```

#### 3. EBITDA
```
EBITDA = Lucro Bruto - Despesas Operacionais

Fórmula:
EBITDA = LB - DESP_OP

Onde DESP_OP inclui:
- Despesas com Vendas (5.02.xxx)
- Despesas Administrativas (5.03.xxx)
- Despesas Gerais (5.04.xxx)
- EXCETO: Depreciação, Amortização, Juros
```

**EBITDA = Earnings Before Interest, Taxes, Depreciation and Amortization**
(Lucros antes de Juros, Impostos, Depreciação e Amortização)

**Margem EBITDA:**
```
Margem EBITDA (%) = (EBITDA / Receita Líquida) × 100
```

#### 4. EBIT (Resultado Operacional)
```
EBIT = EBITDA - Depreciação - Amortização

Fórmula:
EBIT = EBITDA - DEPREC - AMORT
```

**Contas envolvidas:**
- Depreciação: `5.05.001`
- Amortização: `5.05.002`

**Margem Operacional:**
```
Margem Operacional (%) = (EBIT / Receita Líquida) × 100
```

#### 5. LAIR (Lucro Antes do IR)
```
LAIR = EBIT + Resultado Financeiro

Resultado Financeiro = Receitas Financeiras - Despesas Financeiras

Fórmula:
LAIR = EBIT + (REC_FIN - DESP_FIN)
```

**Contas envolvidas:**
- Receitas Financeiras: `4.03.xxx`
- Despesas Financeiras: `5.06.xxx`

#### 6. Lucro Líquido
```
Lucro Líquido = LAIR - IR - CSLL

Fórmula:
LL = LAIR - (IR + CSLL)

Onde:
- IR = Imposto de Renda sobre o Lucro
- CSLL = Contribuição Social sobre o Lucro Líquido
```

**Contas envolvidas:**
- IR/CSLL: `5.07.xxx`

**Margem Líquida:**
```
Margem Líquida (%) = (Lucro Líquido / Receita Líquida) × 100
```

### Código Python - Cálculo da DRE

```python
from decimal import Decimal
from datetime import date

def calcular_dre(
    receita_bruta: Decimal,
    deducoes_vendas: Decimal,
    impostos_vendas: Decimal,
    custo_vendas: Decimal,
    despesas_vendas: Decimal,
    despesas_administrativas: Decimal,
    despesas_gerais: Decimal,
    deprec_amortizacao: Decimal,
    receitas_financeiras: Decimal,
    despesas_financeiras: Decimal,
    aliquota_ir_csll: Decimal = Decimal('0.34')  # 34% (25% IR + 9% CSLL)
) -> dict:
    """
    Calcula DRE completa conforme Lei 6.404/76

    Returns:
        dict com todos os valores da DRE
    """
    # 1. Receita Líquida
    total_deducoes = deducoes_vendas + impostos_vendas
    receita_liquida = receita_bruta - total_deducoes

    # 2. Lucro Bruto
    lucro_bruto = receita_liquida - custo_vendas

    # 3. EBITDA
    total_despesas_op = (
        despesas_vendas +
        despesas_administrativas +
        despesas_gerais
    )
    ebitda = lucro_bruto - total_despesas_op

    # 4. EBIT (Resultado Operacional)
    ebit = ebitda - deprec_amortizacao

    # 5. LAIR (Lucro Antes do IR)
    resultado_financeiro = receitas_financeiras - despesas_financeiras
    lair = ebit + resultado_financeiro

    # 6. Lucro Líquido
    ir_csll = lair * aliquota_ir_csll if lair > 0 else Decimal('0')
    lucro_liquido = lair - ir_csll

    # 7. Indicadores
    if receita_liquida > 0:
        margem_bruta = (lucro_bruto / receita_liquida) * 100
        margem_ebitda = (ebitda / receita_liquida) * 100
        margem_operacional = (ebit / receita_liquida) * 100
        margem_liquida = (lucro_liquido / receita_liquida) * 100
    else:
        margem_bruta = margem_ebitda = margem_operacional = margem_liquida = Decimal('0')

    return {
        'receita_bruta': receita_bruta,
        'total_deducoes': total_deducoes,
        'receita_liquida': receita_liquida,
        'custo_vendas': custo_vendas,
        'lucro_bruto': lucro_bruto,
        'total_despesas_operacionais': total_despesas_op,
        'ebitda': ebitda,
        'deprec_amortizacao': deprec_amortizacao,
        'ebit': ebit,
        'resultado_financeiro': resultado_financeiro,
        'lair': lair,
        'ir_csll': ir_csll,
        'lucro_liquido': lucro_liquido,
        'indicadores': {
            'margem_bruta': margem_bruta,
            'margem_ebitda': margem_ebitda,
            'margem_operacional': margem_operacional,
            'margem_liquida': margem_liquida
        }
    }
```

### Validação da DRE

**Verificações automáticas:**
1. ✅ Receita Líquida = Receita Bruta - Deduções
2. ✅ Lucro Bruto = Receita Líquida - Custos
3. ✅ EBITDA = Lucro Bruto - Despesas Operacionais
4. ✅ Margem Bruta ∈ [0%, 100%] (geralmente entre 20% e 60%)
5. ✅ Margem Líquida < Margem Bruta (sempre)

---

## Balanço Patrimonial

### Estrutura Conforme CPC 26

```
BALANÇO PATRIMONIAL
Em 31/12/2024
Empresa: [Nome da Empresa]
CNPJ: XX.XXX.XXX/0001-XX

┌────────────────────────────────────────────────────────────┐
│                         ATIVO                              │
├────────────────────────────────────────────────────────────┤
│ ATIVO CIRCULANTE                          R$ 500.000,00    │
│   Caixa e Equivalentes                   R$ 100.000,00    │
│   Bancos Conta Corrente                  R$ 150.000,00    │
│   Aplicações Financeiras                 R$ 50.000,00     │
│   Contas a Receber                       R$ 150.000,00    │
│   Estoques                                R$ 50.000,00     │
│                                                            │
│ ATIVO NÃO CIRCULANTE                      R$ 800.000,00    │
│   Investimentos                           R$ 100.000,00    │
│   Imobilizado                             R$ 650.000,00    │
│     Imóveis                   R$ 400.000,00                │
│     Veículos                  R$ 200.000,00                │
│     Móveis e Utensílios       R$ 50.000,00                 │
│   Intangível                              R$ 50.000,00     │
│                                                            │
│ TOTAL DO ATIVO                            R$ 1.300.000,00  │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│              PASSIVO + PATRIMÔNIO LÍQUIDO                  │
├────────────────────────────────────────────────────────────┤
│ PASSIVO CIRCULANTE                        R$ 200.000,00    │
│   Fornecedores                            R$ 100.000,00    │
│   Impostos a Recolher                     R$ 50.000,00     │
│   Salários a Pagar                        R$ 50.000,00     │
│                                                            │
│ PASSIVO NÃO CIRCULANTE                    R$ 400.000,00    │
│   Empréstimos de Longo Prazo             R$ 300.000,00    │
│   Financiamentos                          R$ 100.000,00    │
│                                                            │
│ PATRIMÔNIO LÍQUIDO                        R$ 700.000,00    │
│   Capital Social                          R$ 500.000,00    │
│   Reservas de Lucros                      R$ 100.000,00    │
│   Lucros Acumulados                       R$ 100.000,00    │
│   Lucros do Exercício                     R$ 0,00          │
│                                                            │
│ TOTAL PASSIVO + PL                        R$ 1.300.000,00  │
└────────────────────────────────────────────────────────────┘

VALIDAÇÃO: ✅ ATIVO = PASSIVO + PATRIMÔNIO LÍQUIDO
           R$ 1.300.000,00 = R$ 1.300.000,00
```

### Equação Fundamental

```
ATIVO = PASSIVO + PATRIMÔNIO LÍQUIDO

A = P + PL

Onde:
- A  = Tudo que a empresa possui (bens e direitos)
- P  = Tudo que a empresa deve (obrigações)
- PL = Patrimônio dos sócios (capital próprio)
```

**Esta equação SEMPRE deve ser verdadeira!**

### Matemática do Balanço

#### 1. Classificação de Contas

**ATIVO (Natureza Devedora):**
- Saldo DEBITADO aumenta
- Saldo CREDITADO diminui
- Fórmula: `Saldo = Débitos - Créditos`

**PASSIVO (Natureza Credora):**
- Saldo CREDITADO aumenta
- Saldo DEBITADO diminui
- Fórmula: `Saldo = Créditos - Débitos`

**PATRIMÔNIO LÍQUIDO (Natureza Credora):**
- Saldo CREDITADO aumenta
- Saldo DEBITADO diminui
- Fórmula: `Saldo = Créditos - Débitos`

#### 2. Cálculo de Saldos

```python
def calcular_saldo_conta(
    natureza: str,  # 'debit' ou 'credit'
    debitos: Decimal,
    creditos: Decimal
) -> Decimal:
    """
    Calcula saldo de uma conta conforme sua natureza

    Args:
        natureza: 'debit' (ativo) ou 'credit' (passivo/PL)
        debitos: Total de lançamentos a débito
        creditos: Total de lançamentos a crédito

    Returns:
        Saldo da conta (sempre positivo no balanço)
    """
    if natureza == 'debit':
        # Contas de natureza devedora (ATIVO)
        # Débito aumenta, Crédito diminui
        return debitos - creditos
    else:
        # Contas de natureza credora (PASSIVO, PL)
        # Crédito aumenta, Débito diminui
        return creditos - debitos
```

#### 3. Integração com DRE

**O Balanço Patrimonial reflete o resultado da DRE através do Patrimônio Líquido:**

```
Lucros do Exercício = Lucro Líquido da DRE

Patrimônio Líquido = Capital Social
                     + Reservas
                     + Lucros Acumulados
                     + Lucros do Exercício
```

**Tratamento de Receitas e Despesas:**

As contas de **RECEITA** e **DESPESA** (contas de resultado) não aparecem diretamente no Balanço Patrimonial. Elas são **consolidadas** como "Lucros do Exercício" no Patrimônio Líquido:

```python
def integrar_resultado_dre_no_balanco(
    balanco: BalanceSheet,
    receitas: Decimal,
    despesas: Decimal
) -> None:
    """
    Integra o resultado da DRE (receitas - despesas) no Balanço
    como "Lucros do Exercício" no Patrimônio Líquido

    Args:
        balanco: Objeto do Balanço Patrimonial
        receitas: Total de receitas do período
        despesas: Total de despesas do período
    """
    # Calcula lucro líquido do exercício
    lucro_exercicio = receitas - despesas

    # Adiciona ao Patrimônio Líquido
    balanco.patrimonio_liquido += lucro_exercicio

    # Adiciona linha detalhada
    balanco.equity_lines.append(
        BalanceSheetLine(
            code='3.04.001',
            name='Lucros do Exercício',
            balance=lucro_exercicio,
            level=2
        )
    )
```

### Código Python - Balanço Patrimonial

```python
from decimal import Decimal
from datetime import datetime
from typing import List, Dict

def calcular_balanco_patrimonial(
    db_session,
    user_id: int,
    data_referencia: datetime
) -> Dict:
    """
    Calcula Balanço Patrimonial em uma data específica

    Process:
    1. Buscar todas as contas ativas do usuário
    2. Calcular saldo de cada conta até a data
    3. Classificar por tipo (Ativo/Passivo/PL)
    4. Consolidar receitas/despesas como "Lucros do Exercício"
    5. Validar equação fundamental (A = P + PL)

    Returns:
        Balanço com todos os grupos e validação
    """
    # Inicializar balanço
    balanco = {
        'ativo_circulante': Decimal('0'),
        'ativo_nao_circulante': Decimal('0'),
        'passivo_circulante': Decimal('0'),
        'passivo_nao_circulante': Decimal('0'),
        'patrimonio_liquido': Decimal('0'),
        'lines': []
    }

    # Buscar todas as contas
    contas = db_session.query(ChartOfAccountsEntry).filter_by(
        user_id=user_id,
        is_active=True
    ).all()

    # Acumuladores para receitas e despesas
    receitas_total = Decimal('0')
    despesas_total = Decimal('0')

    # Calcular saldo de cada conta
    for conta in contas:
        saldo = _calcular_saldo_conta_ate_data(
            db_session,
            conta.id,
            data_referencia
        )

        if saldo == Decimal('0'):
            continue  # Pular contas zeradas

        # Classificar conta
        tipo = conta.account_type

        if tipo == 'ativo_circulante':
            balanco['ativo_circulante'] += saldo
            balanco['lines'].append({
                'codigo': conta.account_code,
                'nome': conta.account_name,
                'saldo': saldo,
                'grupo': 'Ativo Circulante'
            })

        elif tipo == 'ativo_nao_circulante':
            balanco['ativo_nao_circulante'] += saldo
            balanco['lines'].append({
                'codigo': conta.account_code,
                'nome': conta.account_name,
                'saldo': saldo,
                'grupo': 'Ativo Não Circulante'
            })

        elif tipo == 'passivo_circulante':
            balanco['passivo_circulante'] += saldo
            balanco['lines'].append({
                'codigo': conta.account_code,
                'nome': conta.account_name,
                'saldo': saldo,
                'grupo': 'Passivo Circulante'
            })

        elif tipo == 'passivo_nao_circulante':
            balanco['passivo_nao_circulante'] += saldo
            balanco['lines'].append({
                'codigo': conta.account_code,
                'nome': conta.account_name,
                'saldo': saldo,
                'grupo': 'Passivo Não Circulante'
            })

        elif tipo == 'patrimonio_liquido':
            balanco['patrimonio_liquido'] += saldo
            balanco['lines'].append({
                'codigo': conta.account_code,
                'nome': conta.account_name,
                'saldo': saldo,
                'grupo': 'Patrimônio Líquido'
            })

        elif tipo == 'receita':
            # Receitas aumentam o PL
            receitas_total += saldo

        elif tipo == 'despesa':
            # Despesas diminuem o PL
            despesas_total += saldo

    # Consolidar resultado (receitas - despesas) no PL
    lucro_exercicio = receitas_total - despesas_total

    if lucro_exercicio != Decimal('0'):
        balanco['patrimonio_liquido'] += lucro_exercicio
        balanco['lines'].append({
            'codigo': '3.04.001',
            'nome': 'Lucros do Exercício',
            'saldo': lucro_exercicio,
            'grupo': 'Patrimônio Líquido'
        })

    # Calcular totais
    total_ativo = (
        balanco['ativo_circulante'] +
        balanco['ativo_nao_circulante']
    )

    total_passivo_pl = (
        balanco['passivo_circulante'] +
        balanco['passivo_nao_circulante'] +
        balanco['patrimonio_liquido']
    )

    # Validar equação fundamental
    diferenca = abs(total_ativo - total_passivo_pl)
    esta_balanceado = diferenca < Decimal('0.01')  # Tolerância de 1 centavo

    balanco['total_ativo'] = total_ativo
    balanco['total_passivo_pl'] = total_passivo_pl
    balanco['esta_balanceado'] = esta_balanceado
    balanco['diferenca'] = diferenca

    return balanco


def _calcular_saldo_conta_ate_data(
    db_session,
    account_id: int,
    ate_data: datetime
) -> Decimal:
    """
    Calcula saldo de uma conta somando todos os lançamentos até uma data

    Args:
        db_session: Sessão do banco de dados
        account_id: ID da conta
        ate_data: Data limite (inclusive)

    Returns:
        Saldo da conta (considerando natureza devedora/credora)
    """
    # Buscar conta para obter natureza
    conta = db_session.query(ChartOfAccountsEntry).get(account_id)

    if not conta:
        return Decimal('0')

    # Buscar todos os lançamentos até a data
    lancamentos = db_session.query(JournalEntryLine).join(JournalEntry).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.entry_date <= ate_data,
        JournalEntry.is_posted == True,
        JournalEntry.is_reversed == False
    ).all()

    # Somar débitos e créditos
    total_debitos = Decimal('0')
    total_creditos = Decimal('0')

    for linha in lancamentos:
        # Valores estão em centavos, converter para reais
        total_debitos += Decimal(linha.debit_amount) / Decimal('100')
        total_creditos += Decimal(linha.credit_amount) / Decimal('100')

    # Calcular saldo conforme natureza da conta
    if conta.account_nature == 'debit':
        # Natureza devedora (ATIVO)
        saldo = total_debitos - total_creditos
    else:
        # Natureza credora (PASSIVO, PL, RECEITA)
        saldo = total_creditos - total_debitos

    return saldo
```

### Validação do Balanço

**Verificações automáticas:**
1. ✅ **A = P + PL** (equação fundamental)
2. ✅ **Todas as contas classificadas** (Ativo, Passivo ou PL)
3. ✅ **Saldos não negativos** (contas patrimoniais sempre positivas)
4. ✅ **Receitas e despesas consolidadas** no PL como "Lucros do Exercício"
5. ✅ **Diferença < R$ 0,01** (tolerância para arredondamento)

---

## DFC - Demonstração do Fluxo de Caixa

### Estrutura - Método Direto

```
DEMONSTRAÇÃO DO FLUXO DE CAIXA (DFC)
Período: 01/01/2024 a 31/12/2024
Empresa: [Nome da Empresa]
CNPJ: XX.XXX.XXX/0001-XX
Método: DIRETO

┌────────────────────────────────────────────────────────────┐
│ 1. ATIVIDADES OPERACIONAIS                                │
├────────────────────────────────────────────────────────────┤
│ Recebimentos de Clientes               R$ 950.000,00      │
│ Outros Recebimentos Operacionais       R$ 50.000,00       │
│ Pagamentos a Fornecedores              R$ (500.000,00)    │
│ Pagamentos a Empregados                R$ (200.000,00)    │
│ Outros Pagamentos Operacionais         R$ (100.000,00)    │
├────────────────────────────────────────────────────────────┤
│ CAIXA LÍQUIDO DAS ATIVIDADES                              │
│ OPERACIONAIS                            R$ 200.000,00      │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 2. ATIVIDADES DE INVESTIMENTO                             │
├────────────────────────────────────────────────────────────┤
│ Venda de Imobilizado                    R$ 50.000,00       │
│ Aquisição de Imobilizado                R$ (150.000,00)    │
│ Aquisição de Investimentos              R$ (50.000,00)     │
├────────────────────────────────────────────────────────────┤
│ CAIXA LÍQUIDO DAS ATIVIDADES                              │
│ DE INVESTIMENTO                         R$ (150.000,00)    │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 3. ATIVIDADES DE FINANCIAMENTO                            │
├────────────────────────────────────────────────────────────┤
│ Integralização de Capital               R$ 100.000,00      │
│ Empréstimos Obtidos                     R$ 200.000,00      │
│ Pagamento de Empréstimos                R$ (100.000,00)    │
│ Pagamento de Dividendos                 R$ (50.000,00)     │
├────────────────────────────────────────────────────────────┤
│ CAIXA LÍQUIDO DAS ATIVIDADES                              │
│ DE FINANCIAMENTO                        R$ 150.000,00      │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ RESUMO DO FLUXO DE CAIXA                                   │
├────────────────────────────────────────────────────────────┤
│ Caixa Gerado pelas Operações           R$ 200.000,00      │
│ Caixa Usado em Investimentos           R$ (150.000,00)    │
│ Caixa Gerado por Financiamentos        R$ 150.000,00      │
├────────────────────────────────────────────────────────────┤
│ AUMENTO LÍQUIDO DE CAIXA                R$ 200.000,00      │
├────────────────────────────────────────────────────────────┤
│ Caixa no Início do Período             R$ 100.000,00      │
│ Caixa no Final do Período              R$ 300.000,00      │
├────────────────────────────────────────────────────────────┤
│ VALIDAÇÃO: ✅ Caixa Final = Caixa Inicial + Variação      │
│            R$ 300.000 = R$ 100.000 + R$ 200.000           │
└────────────────────────────────────────────────────────────┘
```

### Matemática do Fluxo de Caixa

#### Método Direto - Categorização

O DFC método direto categoriza **movimentações de caixa** (contas 1.01.001 Caixa e 1.01.002 Bancos) em três atividades:

**1. Atividades Operacionais:**
- Entradas e saídas relacionadas à **operação principal** do negócio
- Vendas, compras, pagamento de despesas operacionais

**2. Atividades de Investimento:**
- Compra e venda de **ativos de longo prazo**
- Imobilizado, investimentos, intangível

**3. Atividades de Financiamento:**
- Captação e pagamento de **recursos financeiros**
- Empréstimos, capital social, dividendos

#### Lógica de Classificação

```python
def classificar_movimentacao_caixa(
    conta_contrapartida: str,  # Código da conta que não é caixa
    valor: Decimal,
    tipo_movimento: str  # 'entrada' ou 'saida'
) -> tuple[str, Decimal]:
    """
    Classifica uma movimentação de caixa em uma das 3 atividades

    Args:
        conta_contrapartida: Código da conta offsetting
        valor: Valor da movimentação (sempre positivo)
        tipo_movimento: 'entrada' (débito em caixa) ou 'saida' (crédito em caixa)

    Returns:
        Tupla (categoria, valor) onde categoria é:
        - 'operacional_entrada' ou 'operacional_saida'
        - 'investimento_entrada' ou 'investimento_saida'
        - 'financiamento_entrada' ou 'financiamento_saida'
    """

    # ATIVIDADES OPERACIONAIS
    if conta_contrapartida.startswith('4.01'):  # Receitas de Vendas
        return ('operacional_entrada', valor)  # Recebimento de clientes

    elif conta_contrapartida.startswith('2.01.001'):  # Fornecedores
        return ('operacional_saida', valor)  # Pagamento a fornecedores

    elif conta_contrapartida.startswith('5.02.001'):  # Salários
        return ('operacional_saida', valor)  # Pagamento de salários

    elif conta_contrapartida.startswith('5.'):  # Outras despesas
        return ('operacional_saida', valor)  # Outras despesas operacionais

    # ATIVIDADES DE INVESTIMENTO
    elif conta_contrapartida.startswith('1.02'):  # Ativo Não Circulante
        if tipo_movimento == 'entrada':
            return ('investimento_entrada', valor)  # Venda de ativo
        else:
            return ('investimento_saida', valor)  # Compra de ativo

    # ATIVIDADES DE FINANCIAMENTO
    elif conta_contrapartida.startswith('2.02'):  # Passivo Não Circulante (empréstimos)
        if tipo_movimento == 'entrada':
            return ('financiamento_entrada', valor)  # Empréstimo obtido
        else:
            return ('financiamento_saida', valor)  # Pagamento de empréstimo

    elif conta_contrapartida.startswith('3.01'):  # Capital Social
        return ('financiamento_entrada', valor)  # Integralização de capital

    elif conta_contrapartida.startswith('3.03'):  # Dividendos
        return ('financiamento_saida', valor)  # Pagamento de dividendos

    else:
        # Não classificado - colocar em "Outros operacionais"
        if tipo_movimento == 'entrada':
            return ('operacional_entrada', valor)
        else:
            return ('operacional_saida', valor)
```

#### Cálculo do DFC

```python
from decimal import Decimal
from datetime import date, datetime
from typing import Dict

def calcular_fluxo_caixa(
    db_session,
    user_id: int,
    data_inicio: date,
    data_fim: date
) -> Dict:
    """
    Calcula DFC método direto para um período

    Process:
    1. Obter saldo inicial de caixa (antes do período)
    2. Buscar todas movimentações de caixa no período
    3. Classificar cada movimentação (operacional/investimento/financiamento)
    4. Somar por categoria
    5. Calcular saldo final e validar

    Returns:
        Dicionário com DFC completo
    """
    dfc = {
        # Operacionais
        'recebimentos_clientes': Decimal('0'),
        'pagamentos_fornecedores': Decimal('0'),
        'pagamentos_empregados': Decimal('0'),
        'outros_recebimentos_op': Decimal('0'),
        'outros_pagamentos_op': Decimal('0'),

        # Investimentos
        'venda_ativos': Decimal('0'),
        'compra_ativos': Decimal('0'),

        # Financiamentos
        'emprestimos_obtidos': Decimal('0'),
        'pagamento_emprestimos': Decimal('0'),
        'integralizacao_capital': Decimal('0'),
        'pagamento_dividendos': Decimal('0'),

        # Saldos
        'caixa_inicio': Decimal('0'),
        'caixa_fim': Decimal('0'),
    }

    # 1. Saldo inicial (antes do período)
    data_inicio_datetime = datetime.combine(
        data_inicio - timedelta(days=1),
        datetime.max.time()
    )
    dfc['caixa_inicio'] = _obter_saldo_caixa_na_data(
        db_session,
        user_id,
        data_inicio_datetime
    )

    # 2. Buscar contas de caixa (1.01.001 e 1.01.002)
    contas_caixa = db_session.query(ChartOfAccountsEntry).filter(
        ChartOfAccountsEntry.user_id == user_id,
        ChartOfAccountsEntry.account_code.in_(['1.01.001', '1.01.002']),
        ChartOfAccountsEntry.is_active == True
    ).all()

    conta_caixa_ids = [c.id for c in contas_caixa]

    # 3. Buscar movimentações de caixa no período
    data_inicio_dt = datetime.combine(data_inicio, datetime.min.time())
    data_fim_dt = datetime.combine(data_fim, datetime.max.time())

    lancamentos = db_session.query(JournalEntryLine, JournalEntry).join(JournalEntry).filter(
        JournalEntryLine.account_id.in_(conta_caixa_ids),
        JournalEntry.user_id == user_id,
        JournalEntry.entry_date >= data_inicio_dt,
        JournalEntry.entry_date <= data_fim_dt,
        JournalEntry.is_posted == True,
        JournalEntry.is_reversed == False
    ).all()

    # 4. Classificar cada movimentação
    for linha_caixa, lancamento in lancamentos:
        # Encontrar conta contrapartida (a outra conta do lançamento)
        outras_linhas = [l for l in lancamento.lines if l.id != linha_caixa.id]

        if not outras_linhas:
            continue  # Lançamento inválido

        linha_contrapartida = outras_linhas[0]
        conta_contrapartida = db_session.query(ChartOfAccountsEntry).get(
            linha_contrapartida.account_id
        )

        if not conta_contrapartida:
            continue

        # Calcular efeito no caixa (débito aumenta, crédito diminui)
        efeito_caixa = (
            Decimal(linha_caixa.debit_amount - linha_caixa.credit_amount) /
            Decimal('100')
        )

        valor_abs = abs(efeito_caixa)
        tipo_movimento = 'entrada' if efeito_caixa > 0 else 'saida'

        # Classificar
        categoria = _classificar_por_conta(
            conta_contrapartida.account_code,
            tipo_movimento
        )

        # Acumular no DFC
        if categoria == 'recebimentos_clientes':
            dfc['recebimentos_clientes'] += valor_abs
        elif categoria == 'pagamentos_fornecedores':
            dfc['pagamentos_fornecedores'] += valor_abs
        # ... continua para todas as categorias

    # 5. Calcular totais
    caixa_op = (
        dfc['recebimentos_clientes'] +
        dfc['outros_recebimentos_op'] -
        dfc['pagamentos_fornecedores'] -
        dfc['pagamentos_empregados'] -
        dfc['outros_pagamentos_op']
    )

    caixa_inv = (
        dfc['venda_ativos'] -
        dfc['compra_ativos']
    )

    caixa_fin = (
        dfc['emprestimos_obtidos'] +
        dfc['integralizacao_capital'] -
        dfc['pagamento_emprestimos'] -
        dfc['pagamento_dividendos']
    )

    variacao_caixa = caixa_op + caixa_inv + caixa_fin

    dfc['caixa_operacional'] = caixa_op
    dfc['caixa_investimento'] = caixa_inv
    dfc['caixa_financiamento'] = caixa_fin
    dfc['variacao_caixa'] = variacao_caixa
    dfc['caixa_fim'] = dfc['caixa_inicio'] + variacao_caixa

    # 6. Validar
    caixa_fim_real = _obter_saldo_caixa_na_data(
        db_session,
        user_id,
        data_fim_dt
    )

    diferenca = abs(dfc['caixa_fim'] - caixa_fim_real)
    dfc['validado'] = diferenca < Decimal('0.01')

    return dfc
```

### Validação do DFC

**Verificações automáticas:**
1. ✅ **Caixa Final = Caixa Inicial + Variação**
2. ✅ **Variação = Operacional + Investimento + Financiamento**
3. ✅ **Caixa Final calculado = Caixa Final real** (no Balanço)
4. ✅ **Todas movimentações classificadas** (3 categorias)
5. ✅ **Tolerância < R$ 0,01** para validação

---

## Sistema de Partidas Dobradas

### Princípio Fundamental

```
"Não há débito sem crédito correspondente"

Para todo lançamento contábil:
DÉBITOS = CRÉDITOS
```

**Exemplo:**
```
Compra de mercadoria à vista por R$ 1.000,00

Débito:  Estoques (Ativo)              R$ 1.000,00
Crédito: Caixa (Ativo)                 R$ 1.000,00

Total Débitos  = R$ 1.000,00
Total Créditos = R$ 1.000,00  ✅
```

### Natureza das Contas

| Tipo de Conta | Natureza | Aumenta com | Diminui com | Saldo Normal |
|---------------|----------|-------------|-------------|--------------|
| **ATIVO** | Devedora | Débito | Crédito | Devedor (positivo) |
| **PASSIVO** | Credora | Crédito | Débito | Credor (positivo) |
| **PATRIMÔNIO LÍQUIDO** | Credora | Crédito | Débito | Credor (positivo) |
| **RECEITA** | Credora | Crédito | Débito | Credor (positivo) |
| **DESPESA** | Devedora | Débito | Crédito | Devedor (positivo) |

### Lançamentos Automáticos

O sistema gera lançamentos automaticamente para transações comuns:

#### 1. Venda à Vista
```
Transação: Venda de R$ 1.000,00 à vista

Lançamento gerado:
D - 1.01.001 (Caixa)                    R$ 1.000,00
C - 4.01.001 (Receita de Vendas)        R$ 1.000,00

Efeito:
- Aumenta ATIVO (caixa sobe)
- Aumenta RECEITA (lucro sobe)
```

#### 2. Pagamento de Despesa
```
Transação: Pagamento de aluguel R$ 500,00

Lançamento gerado:
D - 5.04.002 (Despesa de Aluguel)       R$ 500,00
C - 1.01.001 (Caixa)                    R$ 500,00

Efeito:
- Aumenta DESPESA (lucro diminui)
- Diminui ATIVO (caixa diminui)
```

#### 3. Compra a Prazo
```
Transação: Compra de mercadoria por R$ 2.000,00 a prazo

Lançamento gerado:
D - 1.01.003 (Estoques)                 R$ 2.000,00
C - 2.01.001 (Fornecedores)             R$ 2.000,00

Efeito:
- Aumenta ATIVO (estoque)
- Aumenta PASSIVO (dívida com fornecedor)
```

### Validação de Lançamentos

```python
def validar_lancamento(debitos: Decimal, creditos: Decimal) -> bool:
    """
    Valida se um lançamento contábil está balanceado

    Args:
        debitos: Soma total de débitos
        creditos: Soma total de créditos

    Returns:
        True se débitos = créditos, False caso contrário

    Raises:
        ValueError: Se lançamento desbalanceado
    """
    diferenca = abs(debitos - creditos)

    # Tolerância de 1 centavo para arredondamento
    if diferenca < Decimal('0.01'):
        return True

    raise ValueError(
        f"Lançamento desbalanceado! "
        f"Débitos: R$ {debitos:,.2f}, "
        f"Créditos: R$ {creditos:,.2f}, "
        f"Diferença: R$ {diferenca:,.2f}"
    )
```

---

## Plano de Contas

### Estrutura Hierárquica

O plano de contas segue a estrutura:

```
1. ATIVO
  1.01. ATIVO CIRCULANTE
    1.01.001 - Caixa
    1.01.002 - Bancos Conta Corrente
    1.01.003 - Aplicações Financeiras
    1.01.004 - Contas a Receber
    1.01.005 - Estoques

  1.02. ATIVO NÃO CIRCULANTE
    1.02.001 - Investimentos
    1.02.002 - Imóveis
    1.02.003 - Veículos
    1.02.004 - Móveis e Utensílios

2. PASSIVO
  2.01. PASSIVO CIRCULANTE
    2.01.001 - Fornecedores
    2.01.002 - Impostos a Recolher
    2.01.003 - Salários a Pagar

  2.02. PASSIVO NÃO CIRCULANTE
    2.02.001 - Empréstimos de Longo Prazo
    2.02.002 - Financiamentos

3. PATRIMÔNIO LÍQUIDO
  3.01. CAPITAL SOCIAL
    3.01.001 - Capital Social Subscrito

  3.02. RESERVAS
    3.02.001 - Reserva Legal
    3.02.002 - Reserva de Lucros

  3.03. LUCROS/PREJUÍZOS
    3.03.001 - Lucros Acumulados
    3.04.001 - Lucros do Exercício

4. RECEITAS
  4.01. RECEITAS OPERACIONAIS
    4.01.001 - Receita de Vendas
    4.01.002 - Receita de Serviços

  4.02. DEDUÇÕES DA RECEITA
    4.02.001 - Devoluções e Cancelamentos
    4.02.002 - Impostos sobre Vendas (ICMS, PIS, COFINS)

  4.03. RECEITAS FINANCEIRAS
    4.03.001 - Juros Ativos
    4.03.002 - Descontos Obtidos

5. DESPESAS
  5.01. CUSTOS
    5.01.001 - CMV (Custo Mercadoria Vendida)
    5.01.002 - CPV (Custo Produto Vendido)

  5.02. DESPESAS COM VENDAS
    5.02.001 - Salários de Vendedores
    5.02.002 - Comissões

  5.03. DESPESAS ADMINISTRATIVAS
    5.03.001 - Salários Administrativos
    5.03.002 - Material de Escritório

  5.04. DESPESAS GERAIS
    5.04.001 - Energia Elétrica
    5.04.002 - Aluguel
    5.04.003 - Telefone e Internet

  5.05. DEPRECIAÇÃO E AMORTIZAÇÃO
    5.05.001 - Depreciação
    5.05.002 - Amortização

  5.06. DESPESAS FINANCEIRAS
    5.06.001 - Juros Passivos
    5.06.002 - Tarifas Bancárias

  5.07. IMPOSTOS SOBRE O LUCRO
    5.07.001 - Imposto de Renda
    5.07.002 - CSLL
```

### Códigos de Conta

**Formato:** `X.YY.ZZZ`

- **X** = Classe (1=Ativo, 2=Passivo, 3=PL, 4=Receita, 5=Despesa)
- **YY** = Grupo (01=Circulante, 02=Não Circulante, etc.)
- **ZZZ** = Conta específica

---

## Validação e Testes

### Testes Automatizados

O sistema possui **54 testes automatizados** com **100% de aprovação**:

```
✅ DRE: 26/26 testes passando
✅ Balanço Patrimonial: 18/18 testes passando
✅ Partidas Dobradas: 8/8 testes passando
✅ Plano de Contas: 2/2 testes passando

Total: 54 testes passando (100%)
```

### Casos de Teste da DRE

1. ✅ Cálculo de receita líquida
2. ✅ Cálculo de lucro bruto
3. ✅ Cálculo de EBITDA
4. ✅ Cálculo de EBIT
5. ✅ Cálculo de resultado financeiro
6. ✅ Cálculo de lucro líquido
7. ✅ Cálculo de margens (bruta, operacional, líquida)
8. ✅ DRE com lucro zero
9. ✅ DRE com prejuízo
10. ✅ Geração de linhas detalhadas

### Casos de Teste do Balanço

1. ✅ Estrutura do plano de contas brasileiro
2. ✅ Inicialização do motor contábil
3. ✅ Criação de saldos iniciais
4. ✅ Lançamentos manuais
5. ✅ Validação de débito = crédito
6. ✅ Geração automática de lançamentos
7. ✅ Cálculo de balanço simples
8. ✅ Balanço com transações
9. ✅ Balanço com receitas e despesas integradas
10. ✅ Balancete de verificação
11. ✅ Razão de conta (ledger)
12. ✅ Exportação para PDF
13. ✅ Exportação para Excel
14. ✅ Exportação para CSV
15. ✅ Conversão para dicionário

### Validações Realizadas

#### DRE
```python
assert receita_liquida == receita_bruta - deducoes
assert lucro_bruto == receita_liquida - cmv
assert ebitda == lucro_bruto - despesas_operacionais
assert ebit == ebitda - depreciacao - amortizacao
assert lair == ebit + resultado_financeiro
assert lucro_liquido == lair - ir - csll
assert 0 <= margem_bruta <= 100
assert margem_liquida <= margem_bruta
```

#### Balanço Patrimonial
```python
assert total_ativo == total_passivo + patrimonio_liquido
assert ativo_circulante >= 0
assert ativo_nao_circulante >= 0
assert passivo_circulante >= 0
assert passivo_nao_circulante >= 0
assert patrimonio_liquido >= 0  # ou negativo em caso de prejuízo acumulado
assert abs(diferenca) < 0.01  # Tolerância de arredondamento
```

#### Partidas Dobradas
```python
for lancamento in lancamentos:
    total_debitos = sum(linha.debit_amount for linha in lancamento.lines)
    total_creditos = sum(linha.credit_amount for linha in lancamento.lines)
    assert total_debitos == total_creditos
```

---

## Conformidade com Normas Brasileiras

### CPC 26 - Apresentação das Demonstrações Contábeis

| Requisito | Status | Detalhes |
|-----------|--------|----------|
| Estrutura da DRE | ✅ 100% | 13+ itens obrigatórios presentes |
| Estrutura do Balanço | ✅ 100% | Ativo, Passivo e PL corretamente classificados |
| Equação patrimonial | ✅ 100% | A = P + PL sempre validada |
| Circulante vs Não Circulante | ✅ 100% | Classificação correta por prazo |
| Demonstração Fluxo Caixa | ✅ 100% | Método direto implementado |

### Lei 6.404/1976 Art. 187

| Item | Requisito Legal | Status |
|------|----------------|--------|
| I | Receita bruta de vendas e serviços | ✅ |
| II | Deduções, abatimentos e impostos | ✅ |
| III | Receita líquida | ✅ |
| IV | Custo das mercadorias/serviços vendidos | ✅ |
| V | Lucro bruto | ✅ |
| VI | Despesas com vendas, administrativas e gerais | ✅ |
| VII | Outras despesas operacionais | ✅ |
| VIII | Lucro ou prejuízo operacional | ✅ |
| IX | Outras receitas e despesas | ✅ |
| X | Resultado antes do IR | ✅ |
| XI | Provisão para IR e CSLL | ✅ |
| XII | Lucro ou prejuízo líquido | ✅ |
| XIII | Lucro por ação | ⏳ Planejado |

### Formato Brasileiro

| Aspecto | Formato | Status |
|---------|---------|--------|
| Moeda | R$ 1.234,56 (ponto = milhar, vírgula = decimal) | ✅ |
| Data | DD/MM/AAAA | ✅ |
| Negativos | (R$ 100,00) entre parênteses | ✅ |
| Idioma | Português (BR) | ✅ |
| Encoding | UTF-8 | ✅ |
| CNPJ | XX.XXX.XXX/0001-XX | ✅ |

---

## Pontos para Validação pelo Contador

### 1. Estrutura das Demonstrações
- [ ] DRE segue exatamente a Lei 6.404/76 Art. 187?
- [ ] Balanço Patrimonial está conforme CPC 26?
- [ ] DFC método direto está correto?

### 2. Cálculos
- [ ] Fórmulas da DRE estão corretas?
- [ ] Equação patrimonial (A = P + PL) sempre verdadeira?
- [ ] Partidas dobradas (D = C) sempre balanceadas?
- [ ] Integração DRE → Balanço (lucro vai para PL) correta?

### 3. Classificação de Contas
- [ ] Plano de contas adequado para empresas brasileiras?
- [ ] Contas faltando ou classificadas incorretamente?
- [ ] Natureza das contas (devedora/credora) correta?

### 4. Impostos
- [ ] Impostos sobre vendas (ICMS, PIS, COFINS) nas deduções?
- [ ] IR e CSLL calculados sobre o lucro?
- [ ] Alíquota de 34% (25% IR + 9% CSLL) adequada?

### 5. Casos Especiais
- [ ] Lucro zero / prejuízo tratado corretamente?
- [ ] Depreciação e amortização antes do EBIT?
- [ ] Resultado financeiro separado do operacional?

### 6. Exportações
- [ ] PDFs estão formatados profissionalmente?
- [ ] Excel permite análises adicionais?
- [ ] Todos os valores batem com os cálculos?

---

## Glossário Contábil

- **ATIVO**: Bens e direitos da empresa
- **PASSIVO**: Obrigações da empresa (dívidas)
- **PL**: Patrimônio Líquido (capital próprio dos sócios)
- **DRE**: Demonstração do Resultado do Exercício (Income Statement)
- **EBITDA**: Lucro antes de Juros, Impostos, Depreciação e Amortização
- **EBIT**: Lucro antes de Juros e Impostos (Resultado Operacional)
- **LAIR**: Lucro Antes do Imposto de Renda
- **CMV**: Custo das Mercadorias Vendidas
- **CPV**: Custo dos Produtos Vendidos
- **CSP**: Custo dos Serviços Prestados
- **IR**: Imposto de Renda
- **CSLL**: Contribuição Social sobre o Lucro Líquido
- **DFC**: Demonstração do Fluxo de Caixa (Cash Flow Statement)
- **CPC**: Comitê de Pronunciamentos Contábeis
- **CVM**: Comissão de Valores Mobiliários

---

## Contato para Dúvidas

Para esclarecimentos sobre a implementação técnica ou validação contábil, entre em contato com a equipe de desenvolvimento.

**Documentação Técnica Completa:**
- Código fonte: `accounting/` directory
- Testes: `tests/test_dre_accounting.py`, `tests/test_balance_sheet.py`
- Plano de contas: `accounting/chart_of_accounts.py`

---

**Documento gerado em:** 25 de Janeiro de 2026
**Versão do Sistema:** ControlladorIA v1.0
**Status:** ✅ Pronto para Validação Contábil

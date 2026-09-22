"""
Financial Context Builder — turns an organization's books into a compact,
bounded snapshot the advisor can reason over.

The central design rule: **the model never sees raw transactions.** It sees the
same calculated reports a human sees in the UI (DRE, Balanço, Indicadores,
Fluxo de Caixa), serialized as small JSON. That keeps the prompt a fixed size
whether an org has 200 documents or 200,000 — token cost and latency stay flat
as customers grow, and the model can't contradict the reports because it is
reading the reports.

The snapshot covers three horizons so comparison questions ("e comparado ao mês
passado?", "qual a tendência?") are answerable without a second round-trip:
  1. the selected period, in full detail
  2. the immediately preceding period, for deltas
  3. a monthly series of headline numbers, for trend

Cached in Redis under a key that includes a fingerprint of the org's document
state, so it invalidates itself the moment a new document finishes processing.
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func

from cache import cache
from config import settings
from database import Document, DocumentStatus, Organization, User

logger = logging.getLogger(__name__)

CACHE_PREFIX = "advisor:ctx"


def _to_float(value) -> float:
    """Decimals and Nones are everywhere in the accounting layer."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round(value, digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(_to_float(value), digits)


def _pct(numerator, denominator) -> Optional[float]:
    d = _to_float(denominator)
    if not d:
        return None
    return round(_to_float(numerator) / d * 100, 2)


# ─── FINGERPRINT ───────────────────────────────────────────────────────────────


def compute_data_fingerprint(db, current_user: User) -> str:
    """
    Cheap version stamp for an org's processed documents.

    Aggregate query (count + max id + max updated_at) rather than loading rows,
    so this stays O(1)-ish on the index no matter the document count. Any new
    completed document changes the stamp and busts the cache.
    """
    from auth.permissions import document_org_filter

    try:
        row = document_org_filter(
            db.query(
                func.count(Document.id),
                func.max(Document.id),
                func.max(Document.upload_date),
            ),
            current_user,
            db,
        ).filter(Document.status == DocumentStatus.COMPLETED).one()

        count, max_id, max_date = row
        raw = f"{count}:{max_id}:{max_date}"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Advisor: fingerprint failed, using timestamp: %s", exc)
        raw = datetime.utcnow().isoformat()

    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ─── SNAPSHOT SERIALIZERS ──────────────────────────────────────────────────────


def _serialize_dre(dre) -> Dict:
    """Headline DRE lines only — the full model is far too verbose for a prompt."""
    if dre is None:
        return {}
    data = dre.model_dump() if hasattr(dre, "model_dump") else dict(dre)

    receita_bruta = data.get("receita_bruta")
    receita_liquida = data.get("receita_liquida")
    ratios = data.get("ratios") or {}

    return {
        "receita_bruta": _round(receita_bruta),
        "deducoes": _round(data.get("total_deducoes")),
        "receita_liquida": _round(receita_liquida),
        "custos_variaveis": _round(data.get("total_custos_variaveis")),
        "margem_contribuicao": _round(data.get("margem_contribuicao")),
        "custos_fixos": _round(data.get("total_custos_fixos")),
        "ebitda": _round(data.get("ebitda")),
        "depreciacao_amortizacao": _round(data.get("total_deprec_amort")),
        "resultado_operacional": _round(data.get("resultado_operacional")),
        "resultado_financeiro": _round(data.get("resultado_financeiro")),
        "resultado_antes_impostos": _round(data.get("resultado_antes_impostos")),
        "impostos_sobre_lucro": _round(data.get("total_impostos_lucro")),
        "lucro_liquido": _round(data.get("lucro_liquido")),
        "detalhe_custos": {
            "cmv": _round(data.get("custos_variaveis_cmv")),
            "csp": _round(data.get("custos_variaveis_csp")),
            "outros_variaveis": _round(data.get("custos_variaveis_outros")),
            "custos_fixos_producao": _round(data.get("custos_fixos_producao")),
            "despesas_administrativas": _round(data.get("despesas_administrativas")),
            "despesas_vendas": _round(data.get("despesas_vendas")),
            "outras_despesas": _round(data.get("outras_despesas")),
        },
        # Two margin bases, both labelled. The DRE screen shows AV% over Receita
        # Bruta (DRE.ratios); the Indicadores screen divides by Receita Líquida.
        # Shipping both keeps the advisor from contradicting either screen.
        "margens_pct_sobre_receita_bruta": {
            "contribuicao": _round(ratios.get("margem_contribuicao")),
            "ebitda": _round(ratios.get("margem_ebitda")),
            "operacional": _round(ratios.get("margem_operacional")),
            "liquida": _round(ratios.get("margem_liquida")),
        },
        "margens_pct_sobre_receita_liquida": {
            "contribuicao": _pct(data.get("margem_contribuicao"), receita_liquida),
            "ebitda": _pct(data.get("ebitda"), receita_liquida),
            "operacional": _pct(data.get("resultado_operacional"), receita_liquida),
            "liquida": _pct(data.get("lucro_liquido"), receita_liquida),
        },
        "qualidade": {
            "transacoes": data.get("transaction_count"),
            "nao_categorizadas": data.get("uncategorized_count"),
            "valor_nao_categorizado": _round(data.get("uncategorized_amount")),
        },
    }


def _top_categories(dre, limit: int = 10) -> List[Dict]:
    """
    The biggest cost/expense lines, which is what most advice hangs off.

    Reads `detailed_lines` (the same rows the DRE screen renders), drops
    subtotals and totals so we rank leaf categories only, and truncates to
    `limit` — this is the one part of the snapshot that would otherwise grow
    with the chart of accounts.
    """
    if dre is None:
        return []
    data = dre.model_dump() if hasattr(dre, "model_dump") else dict(dre)

    lines: List[Dict] = []
    for line in data.get("detailed_lines") or []:
        if not isinstance(line, dict):
            continue
        if line.get("is_subtotal") or line.get("is_total"):
            continue
        amount = _to_float(line.get("amount"))
        # Costs are the negative side of the statement; revenue lines are not
        # what we want to rank here.
        if amount >= 0:
            continue
        lines.append(
            {
                "codigo": line.get("code"),
                "categoria": line.get("description") or "—",
                "valor": round(abs(amount), 2),
                "pct_receita_bruta": line.get("percentage_revenue"),
            }
        )

    lines.sort(key=lambda item: item["valor"], reverse=True)
    return lines[:limit]


def _serialize_balance_sheet(bs) -> Dict:
    if bs is None:
        return {}
    ativo_circulante = _to_float(bs.ativo_circulante)
    ativo_total = (
        ativo_circulante
        + _to_float(bs.ativo_nao_circulante)
        + _to_float(bs.imobilizado)
        + _to_float(bs.intangivel)
    )
    passivo_circulante = _to_float(bs.passivo_circulante)
    passivo_total = passivo_circulante + _to_float(bs.passivo_nao_circulante)

    return {
        "ativo_circulante": round(ativo_circulante, 2),
        "ativo_nao_circulante": _round(bs.ativo_nao_circulante),
        "imobilizado": _round(bs.imobilizado),
        "intangivel": _round(bs.intangivel),
        "ativo_total": round(ativo_total, 2),
        "passivo_circulante": round(passivo_circulante, 2),
        "passivo_nao_circulante": _round(bs.passivo_nao_circulante),
        "passivo_total": round(passivo_total, 2),
        "patrimonio_liquido": _round(bs.patrimonio_liquido),
        "capital_circulante_liquido": round(ativo_circulante - passivo_circulante, 2),
    }


def _compute_indicators(dre_snapshot: Dict, bs_snapshot: Dict) -> Dict:
    """
    Ratios derived from the two snapshots above.

    Mirrors the formulas served by `GET /transactions/reports/indicators` so the
    advisor quotes the same numbers the user sees on screen. Kept here rather
    than imported because that logic currently lives inline in the router.
    """
    if not dre_snapshot and not bs_snapshot:
        return {}

    ativo_circulante = bs_snapshot.get("ativo_circulante") or 0
    passivo_circulante = bs_snapshot.get("passivo_circulante") or 0
    ativo_total = bs_snapshot.get("ativo_total") or 0
    passivo_total = bs_snapshot.get("passivo_total") or 0
    patrimonio_liquido = bs_snapshot.get("patrimonio_liquido") or 0
    lucro_liquido = dre_snapshot.get("lucro_liquido") or 0

    def div(a, b):
        b = _to_float(b)
        if not b:
            return None
        return round(_to_float(a) / b, 2)

    # Indicadores screen divides by Receita Líquida — mirror that basis here.
    margens = dre_snapshot.get("margens_pct_sobre_receita_liquida") or {}
    return {
        "margens_pct_sobre_receita_liquida": margens,
        "liquidez": {
            "corrente": div(ativo_circulante, passivo_circulante),
            "geral": div(ativo_total, passivo_total),
        },
        "endividamento": {
            "geral_pct": _pct(passivo_total, ativo_total),
            "composicao_pct": _pct(passivo_circulante, passivo_total),
            "alavancagem": div(ativo_total, patrimonio_liquido),
        },
        "rentabilidade": {
            "roe_pct": _pct(lucro_liquido, patrimonio_liquido),
            "roa_pct": _pct(lucro_liquido, ativo_total),
        },
        "ponto_equilibrio": _breakeven(dre_snapshot),
    }


def _breakeven(dre_snapshot: Dict) -> Optional[float]:
    """Custos fixos / índice de margem de contribuição."""
    receita_liquida = _to_float(dre_snapshot.get("receita_liquida"))
    margem = _to_float(dre_snapshot.get("margem_contribuicao"))
    custos_fixos = _to_float(dre_snapshot.get("custos_fixos"))
    if not receita_liquida or not margem:
        return None
    indice = margem / receita_liquida
    if not indice:
        return None
    return round(custos_fixos / indice, 2)


def _serialize_cash_flow(cash_flow) -> Dict:
    """
    DFC totals per CPC 03 — the three activity buckets plus opening/closing cash.

    Individual `line_items` inside each section are dropped on purpose: they can
    number in the hundreds, and the section totals carry the signal.
    """
    if cash_flow is None:
        return {}
    return {
        "metodo": getattr(cash_flow, "method", None),
        "caixa_inicial": _round(getattr(cash_flow, "cash_beginning", None)),
        "operacional": _round(getattr(cash_flow, "net_cash_from_operations", None)),
        "investimento": _round(getattr(cash_flow, "net_cash_from_investments", None)),
        "financiamento": _round(getattr(cash_flow, "net_cash_from_financing", None)),
        "variacao_liquida": _round(getattr(cash_flow, "net_increase_in_cash", None)),
        "caixa_final": _round(getattr(cash_flow, "cash_ending", None)),
    }


# ─── PERIOD MATH ───────────────────────────────────────────────────────────────


def _previous_period(period_start: date, period_end: date) -> Tuple[date, date]:
    """
    The comparable window immediately before this one.

    Month-length periods map to the previous calendar month (so Feb compares to
    Jan, not to "28 days ago"). Everything else shifts back by its own duration.
    """
    from calendar import monthrange

    is_full_month = (
        period_start.day == 1
        and period_end.day == monthrange(period_end.year, period_end.month)[1]
        and period_start.month == period_end.month
        and period_start.year == period_end.year
    )

    if is_full_month:
        prev_end = period_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        return prev_start, prev_end

    duration = period_end - period_start
    prev_end = period_start - timedelta(days=1)
    prev_start = prev_end - duration
    return prev_start, prev_end


def _month_windows(reference_end: date, months: int) -> List[Tuple[date, date]]:
    """The last `months` full calendar months ending at `reference_end`'s month."""
    from calendar import monthrange

    windows = []
    year, month = reference_end.year, reference_end.month
    for _ in range(months):
        last_day = monthrange(year, month)[1]
        windows.append((date(year, month, 1), date(year, month, last_day)))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    windows.reverse()
    return windows


# ─── BUILDER ───────────────────────────────────────────────────────────────────


class FinancialContextBuilder:
    """Builds (and caches) the advisor's view of an organization's books."""

    def __init__(self, db, current_user: User):
        self.db = db
        self.user = current_user
        self.org_id = (
            getattr(current_user, "_active_org_id", None)
            or getattr(current_user, "active_org_id", None)
        )

    # -- data access ---------------------------------------------------------

    def _load_transactions(self) -> List[Dict]:
        """
        Load every completed document once and expand it to transactions.

        Reuses the router's extractor so the advisor and the reports can never
        disagree about what a document contains.
        """
        from auth.permissions import document_org_filter
        from routers.transactions import _extract_transactions_from_documents

        documents = (
            document_org_filter(self.db.query(Document), self.user, self.db)
            .filter(
                Document.status == DocumentStatus.COMPLETED,
                Document.extracted_data_json.isnot(None),
            )
            .all()
        )
        return _extract_transactions_from_documents(documents)

    def _org_info(self) -> Tuple[Optional[str], Optional[str]]:
        from routers.transactions import _get_active_org_info

        return _get_active_org_info(self.user, self.db)

    def _dre_for(self, transactions, period_start: date, period_end: date):
        from accounting import PeriodType, calculate_dre

        company_name, cnpj = self._org_info()
        return calculate_dre(
            transactions=transactions,
            period_type=PeriodType.CUSTOM,
            start_date=period_start,
            end_date=period_end,
            company_name=company_name,
            cnpj=cnpj,
        )

    def _balance_sheet_at(self, reference_date: date):
        from accounting.balance_sheet_calculator import BalanceSheetCalculator

        try:
            calculator = BalanceSheetCalculator(
                self.db, self.user.id, org_id=self.org_id
            )
            return calculator.calculate_balance_sheet(reference_date=reference_date)
        except Exception as exc:
            logger.warning("Advisor: balance sheet unavailable: %s", exc)
            return None

    def _cash_flow_for(self, period_start: date, period_end: date):
        """
        DFC for the period. Optional: orgs without initial balances configured
        can't produce one, and that must not break the chat.
        """
        from accounting.cash_flow_calculator import CashFlowCalculator

        try:
            company_name, cnpj = self._org_info()
            calculator = CashFlowCalculator(self.db, self.user.id, org_id=self.org_id)
            return calculator.calculate_cash_flow(
                period_type="custom",
                start_date=period_start,
                end_date=period_end,
                method="indirect",
                company_name=company_name,
                cnpj=cnpj,
            )
        except Exception as exc:
            logger.warning("Advisor: cash flow unavailable: %s", exc)
            return None

    # -- assembly ------------------------------------------------------------

    def build(
        self,
        period_start: date,
        period_end: date,
        period_label: str = "",
        use_cache: bool = True,
    ) -> Dict:
        """Return the snapshot dict, hitting Redis when possible."""
        fingerprint = compute_data_fingerprint(self.db, self.user)
        cache_key = (
            f"{CACHE_PREFIX}:{self.org_id or f'u{self.user.id}'}"
            f":{period_start.isoformat()}:{period_end.isoformat()}:{fingerprint}"
        )

        if use_cache:
            try:
                cached = cache.get(cache_key)
                if cached:
                    logger.debug("Advisor: context cache hit")
                    return cached
            except Exception as exc:  # Redis down must never break chat
                logger.warning("Advisor: context cache read failed: %s", exc)

        snapshot = self._build_uncached(period_start, period_end, period_label)

        if use_cache:
            try:
                cache.set(cache_key, snapshot, ttl=settings.advisor_context_cache_ttl)
            except Exception as exc:
                logger.warning("Advisor: context cache write failed: %s", exc)

        return snapshot

    def _build_uncached(
        self, period_start: date, period_end: date, period_label: str
    ) -> Dict:
        transactions = self._load_transactions()
        company_name, cnpj = self._org_info()

        # 1. Selected period, in detail
        dre = self._dre_for(transactions, period_start, period_end)
        dre_snapshot = _serialize_dre(dre)
        bs_snapshot = _serialize_balance_sheet(self._balance_sheet_at(period_end))

        # 2. Preceding comparable period, for deltas
        prev_start, prev_end = _previous_period(period_start, period_end)
        prev_dre_snapshot = _serialize_dre(
            self._dre_for(transactions, prev_start, prev_end)
        )

        # 3. Monthly trend of headline numbers only
        trend = []
        for window_start, window_end in _month_windows(
            period_end, settings.advisor_trend_months
        ):
            window_dre = _serialize_dre(
                self._dre_for(transactions, window_start, window_end)
            )
            trend.append(
                {
                    "mes": window_start.strftime("%Y-%m"),
                    "receita_liquida": window_dre.get("receita_liquida"),
                    "lucro_liquido": window_dre.get("lucro_liquido"),
                    "ebitda": window_dre.get("ebitda"),
                    "margem_liquida_pct": (
                        window_dre.get("margens_pct_sobre_receita_liquida") or {}
                    ).get("liquida"),
                }
            )

        return {
            "empresa": {
                "nome": company_name or "—",
                "cnpj": cnpj or None,
            },
            "periodo": {
                "inicio": period_start.isoformat(),
                "fim": period_end.isoformat(),
                "rotulo": period_label or f"{period_start} a {period_end}",
            },
            "dre": dre_snapshot,
            "dre_periodo_anterior": {
                "periodo": f"{prev_start.isoformat()} a {prev_end.isoformat()}",
                **prev_dre_snapshot,
            },
            "balanco": bs_snapshot,
            "fluxo_de_caixa": _serialize_cash_flow(
                self._cash_flow_for(period_start, period_end)
            ),
            "indicadores": _compute_indicators(dre_snapshot, bs_snapshot),
            "maiores_custos_e_despesas": _top_categories(dre),
            "tendencia_mensal": trend,
            "cobertura": {
                "documentos_processados": len(transactions),
                "gerado_em": datetime.utcnow().isoformat() + "Z",
            },
        }

    @staticmethod
    def to_prompt_block(snapshot: Dict) -> str:
        """Serialize the snapshot for inclusion in a system prompt."""
        return json.dumps(snapshot, ensure_ascii=False, indent=None, default=str)

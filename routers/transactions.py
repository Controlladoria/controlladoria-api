"""
Transactions Router
Handles financial reports, statistics, and accounting endpoints:
- Document statistics (/stats)
- Financial reports (summary, category, monthly, DRE, balance sheet, cash flow)
- Export functionality (Excel, PDF, CSV)
- Accounting ledger (trial balance, account ledger, chart of accounts, journal entries)
- All queries tenant-isolated with get_accessible_user_ids
"""

import json
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from config import now_brazil
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.permissions import get_accessible_user_ids, document_org_filter
from database import (
    ChartOfAccountsEntry,
    Document,
    DocumentStatus,
    JournalEntry,
    JournalEntryLine,
    Organization,
    Subscription,
    get_db,
    User,
)
from middleware.subscription import require_active_subscription
from models import FinancialDocument, TransactionLedger

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Transactions & Reports"])


def _extract_transactions_from_documents(documents) -> list:
    """
    Extract transactions from documents, expanding multi-row ledgers.

    Single-transaction documents (invoices, receipts) produce 1 transaction.
    Multi-row documents (Excel ledgers) have a 'transactions' array inside
    extracted_data_json — each inner transaction becomes a separate entry.
    """
    transactions = []
    for doc in documents:
        try:
            data_dict = json.loads(doc.extracted_data_json)
            extracted = FinancialDocument(**data_dict)

            # Fallback date: use document's issue_date or upload date
            fallback_date = extracted.issue_date or (
                doc.upload_date.strftime("%Y-%m-%d") if hasattr(doc, 'upload_date') and doc.upload_date else None
            )

            # Check for inner transactions (multi-row documents like Excel ledgers)
            inner_txns = data_dict.get("transactions")
            if inner_txns and isinstance(inner_txns, list) and len(inner_txns) > 0:
                for txn in inner_txns:
                    amount = txn.get("amount", 0)
                    if amount is None:
                        amount = 0
                    # Normalize transaction_type to new 5-type system
                    raw_type = txn.get("transaction_type") or extracted.transaction_type
                    _inc = {"income", "receita", "entrada", "crédito", "credito", "revenue", "credit"}
                    raw_lower = str(raw_type).lower().strip()
                    if raw_lower in _inc:
                        txn_type = "receita"
                    elif raw_lower == "custo" or raw_lower == "cost":
                        txn_type = "custo"
                    elif raw_lower == "investimento":
                        txn_type = "investimento"
                    elif raw_lower == "perda":
                        txn_type = "perda"
                    else:
                        txn_type = "despesa"
                    # Use transaction date, falling back to document issue_date
                    txn_date = txn.get("date") or fallback_date
                    transactions.append({
                        "date": txn_date,
                        "amount": amount,
                        "category": txn.get("category") or "uncategorized",
                        "transaction_type": txn_type,
                        "description": txn.get("description") or "",
                        "document_id": doc.id,
                    })
            else:
                # Single-transaction document
                transactions.append({
                    "date": extracted.issue_date or fallback_date,
                    "amount": extracted.total_amount,
                    "category": extracted.category or "uncategorized",
                    "transaction_type": extracted.transaction_type,
                    "description": extracted.document_number or "",
                    "document_id": doc.id,
                })
        except Exception as e:
            logger.warning(f"Error extracting transactions from document {doc.id}: {e}")
            continue
    return transactions


def _get_export_logo_bytes(current_user: User, db: Session) -> bytes:
    """
    Return logo bytes to embed in exported PDFs/Excels.
    If the user's org is on a plan with WHITE_LABEL and has uploaded a logo,
    use that. Otherwise fall back to the default ControlladorIA logo.
    """
    import os
    from plan_features import WHITE_LABEL, has_plan_feature

    _DEFAULT_LOGO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "logo.png")

    def _default_logo() -> bytes:
        try:
            with open(_DEFAULT_LOGO, "rb") as f:
                return f.read()
        except Exception:
            return b""

    try:
        org_id = getattr(current_user, "active_org_id", None)
        if not org_id:
            return _default_logo()

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org or not org.logo_url:
            return _default_logo()

        # Check WHITE_LABEL plan feature
        plan = None
        if org.subscription:
            plan = org.subscription.plan if hasattr(org.subscription, "plan") else None
        if not has_plan_feature(plan, WHITE_LABEL):
            return _default_logo()

        # Fetch org logo from storage
        from storage.s3_service import s3_storage
        logo_data = s3_storage.download_file(org.logo_url)
        if logo_data:
            return logo_data
    except Exception as exc:
        logger.warning(f"Could not load org logo, using default: {exc}")

    return _default_logo()

@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """
    Get processing statistics

    Requires authentication - returns only current user's statistics
    """
    # Multi-tenant: Filter stats by org
    base_q = document_org_filter(db.query(Document), current_user, db)
    total_docs = base_q.count()
    completed = base_q.filter(Document.status == DocumentStatus.COMPLETED).count()
    failed = base_q.filter(Document.status == DocumentStatus.FAILED).count()
    pending = base_q.filter(Document.status == DocumentStatus.PENDING).count()
    processing = base_q.filter(Document.status == DocumentStatus.PROCESSING).count()

    return {
        "total_documents": total_docs,
        "completed": completed,
        "failed": failed,
        "pending": pending,
        "processing": processing,
    }


@router.get("/reports/summary")
async def get_financial_summary(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get financial summary report with income and expense totals

    Week 3 Enhancement: Aggregated financial reports
    Requires authentication - returns only current user's data
    """

    # Multi-tenant: Get only current org's completed documents
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()

    total_income = Decimal("0")
    total_expense = Decimal("0")
    income_count = 0
    expense_count = 0

    documents_by_type = {
        "invoice": 0,
        "receipt": 0,
        "expense": 0,
        "statement": 0,
        "other": 0,
    }

    for doc in documents:
        try:
            data_dict = json.loads(doc.extracted_data_json)
            extracted_data = FinancialDocument(**data_dict)

            # Apply date filters
            if (
                date_from
                and extracted_data.issue_date
                and extracted_data.issue_date < date_from
            ):
                continue
            if (
                date_to
                and extracted_data.issue_date
                and extracted_data.issue_date > date_to
            ):
                continue

            # Count by document type
            if extracted_data.document_type in documents_by_type:
                documents_by_type[extracted_data.document_type] += 1

            # Sum by transaction type (Portuguese canonical types)
            if extracted_data.transaction_type == "receita":
                total_income += extracted_data.total_amount
                income_count += 1
            else:  # despesa, custo, investimento, perda
                total_expense += extracted_data.total_amount
                expense_count += 1

        except Exception as e:
            logger.warning(f"Error processing document {doc.id} in summary: {e}")
            continue

    net_balance = total_income - total_expense

    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "summary": {
            "total_income": str(total_income),
            "total_expense": str(total_expense),
            "net_balance": str(net_balance),
            "income_count": income_count,
            "expense_count": expense_count,
        },
        "by_document_type": documents_by_type,
        "currency": "BRL",
    }


@router.get("/reports/by-category")
async def get_category_breakdown(
    transaction_type: Optional[str] = Query(
        None, description="Filter by income or expense"
    ),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get breakdown of transactions by category

    Week 3 Enhancement: Category-based financial analysis
    Requires authentication - returns only current user's data
    """

    # Multi-tenant: Get only current org's completed documents
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()

    categories = {}

    for doc in documents:
        try:
            data_dict = json.loads(doc.extracted_data_json)
            extracted_data = FinancialDocument(**data_dict)

            # Apply filters
            if transaction_type and extracted_data.transaction_type != transaction_type:
                continue
            if (
                date_from
                and extracted_data.issue_date
                and extracted_data.issue_date < date_from
            ):
                continue
            if (
                date_to
                and extracted_data.issue_date
                and extracted_data.issue_date > date_to
            ):
                continue

            # Aggregate by category
            category = extracted_data.category or "uncategorized"

            if category not in categories:
                categories[category] = {
                    "total_amount": Decimal("0"),
                    "count": 0,
                    "transaction_type": extracted_data.transaction_type,
                }

            categories[category]["total_amount"] += extracted_data.total_amount
            categories[category]["count"] += 1

        except Exception as e:
            logger.warning(
                f"Error processing document {doc.id} in category breakdown: {e}"
            )
            continue

    # Convert to list format with amounts as strings
    category_list = []
    for category_name, data in categories.items():
        category_list.append(
            {
                "category": category_name,
                "total_amount": str(data["total_amount"]),
                "count": data["count"],
                "transaction_type": data["transaction_type"],
            }
        )

    # Sort by total amount descending
    category_list.sort(key=lambda x: Decimal(x["total_amount"]), reverse=True)

    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "filter": {"transaction_type": transaction_type},
        "categories": category_list,
        "total_categories": len(category_list),
        "currency": "BRL",
    }


@router.get("/reports/monthly")
async def get_monthly_report(
    year: int = Query(..., description="Year (e.g., 2024)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get monthly financial report

    Week 3 Enhancement: Monthly aggregated reports
    Requires authentication - returns only current user's data
    """

    # Calculate date range for the month
    from calendar import monthrange

    days_in_month = monthrange(year, month)[1]
    date_from = f"{year:04d}-{month:02d}-01"
    date_to = f"{year:04d}-{month:02d}-{days_in_month:02d}"

    # Multi-tenant: Get only current org's completed documents in the month
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()

    total_income = Decimal("0")
    total_expense = Decimal("0")
    transactions = []

    for doc in documents:
        try:
            data_dict = json.loads(doc.extracted_data_json)
            extracted_data = FinancialDocument(**data_dict)

            # Filter by month
            if not extracted_data.issue_date:
                continue
            if (
                extracted_data.issue_date < date_from
                or extracted_data.issue_date > date_to
            ):
                continue

            if extracted_data.transaction_type == "receita":
                total_income += extracted_data.total_amount
            else:
                total_expense += extracted_data.total_amount

            transactions.append(
                {
                    "document_id": doc.id,
                    "date": extracted_data.issue_date,
                    "document_type": extracted_data.document_type,
                    "transaction_type": extracted_data.transaction_type,
                    "category": extracted_data.category,
                    "amount": str(extracted_data.total_amount),
                    "issuer": (
                        extracted_data.issuer.name if extracted_data.issuer else None
                    ),
                    "recipient": (
                        extracted_data.recipient.name
                        if extracted_data.recipient
                        else None
                    ),
                }
            )

        except Exception as e:
            logger.warning(f"Error processing document {doc.id} in monthly report: {e}")
            continue

    # Sort transactions by date
    transactions.sort(key=lambda x: x["date"] or "")

    return {
        "period": {
            "year": year,
            "month": month,
            "date_from": date_from,
            "date_to": date_to,
        },
        "summary": {
            "total_income": str(total_income),
            "total_expense": str(total_expense),
            "net_balance": str(total_income - total_expense),
            "transaction_count": len(transactions),
        },
        "transactions": transactions,
        "currency": "BRL",
    }


@router.get("/reports/export/excel")
async def export_to_excel(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Export financial transactions to Excel file

    Requires authentication - exports only current user's data
    """
    from io import BytesIO

    import pandas as pd

    # Multi-tenant: Get only current org's completed documents
    query = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    )

    documents = query.all()

    # Prepare data for Excel
    excel_data = []
    for doc in documents:
        try:
            data_dict = json.loads(doc.extracted_data_json)
            extracted_data = FinancialDocument(**data_dict)

            # Filter by date range if provided
            if (
                date_from
                and extracted_data.issue_date
                and extracted_data.issue_date < date_from
            ):
                continue
            if (
                date_to
                and extracted_data.issue_date
                and extracted_data.issue_date > date_to
            ):
                continue

            excel_data.append(
                {
                    "ID": doc.id,
                    "Arquivo": doc.file_name,
                    "Data Upload": (
                        doc.upload_date.strftime("%Y-%m-%d %H:%M")
                        if doc.upload_date
                        else ""
                    ),
                    "Data Emissão": extracted_data.issue_date or "",
                    "Tipo Documento": extracted_data.document_type or "",
                    "Tipo Transação": extracted_data.transaction_type or "",
                    "Categoria": extracted_data.category or "",
                    "Emitente": (
                        extracted_data.issuer.name if extracted_data.issuer else ""
                    ),
                    "CPF/CNPJ Emitente": (
                        extracted_data.issuer.tax_id if extracted_data.issuer else ""
                    ),
                    "Destinatário": (
                        extracted_data.recipient.name
                        if extracted_data.recipient
                        else ""
                    ),
                    "CPF/CNPJ Destinatário": (
                        extracted_data.recipient.tax_id
                        if extracted_data.recipient
                        else ""
                    ),
                    "Valor Total": (
                        float(extracted_data.total_amount)
                        if extracted_data.total_amount
                        else 0
                    ),
                    "Moeda": extracted_data.currency or "BRL",
                    "Descrição": extracted_data.description or "",
                }
            )
        except Exception as e:
            logger.warning(f"Error processing document {doc.id} for Excel export: {e}")
            continue

    if not excel_data:
        raise HTTPException(status_code=404, detail="Nenhum dado para exportar")

    # Create Excel file
    df = pd.DataFrame(excel_data)

    # Create BytesIO buffer
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Transações", index=False)

        # Auto-adjust column widths
        worksheet = writer.sheets["Transações"]
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    buffer.seek(0)

    # Generate filename
    date_range = (
        f"{date_from}_to_{date_to}"
        if date_from and date_to
        else now_brazil().strftime("%Y%m%d")
    )
    filename = f"transacoes_{date_range}.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/export/pdf")
async def export_to_pdf(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Export financial summary to PDF file

    Requires authentication - exports only current user's data
    """
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # Multi-tenant: Get only current org's completed documents
    query = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    )

    documents = query.all()

    # Prepare data
    total_income = Decimal("0")
    total_expense = Decimal("0")
    transactions = []

    for doc in documents:
        try:
            data_dict = json.loads(doc.extracted_data_json)
            extracted_data = FinancialDocument(**data_dict)

            # Filter by date range if provided
            if (
                date_from
                and extracted_data.issue_date
                and extracted_data.issue_date < date_from
            ):
                continue
            if (
                date_to
                and extracted_data.issue_date
                and extracted_data.issue_date > date_to
            ):
                continue

            if extracted_data.transaction_type == "receita":
                total_income += extracted_data.total_amount
            else:
                total_expense += extracted_data.total_amount

            transactions.append(
                {
                    "date": extracted_data.issue_date or "",
                    "type": extracted_data.transaction_type or "",
                    "category": extracted_data.category or "",
                    "issuer": (
                        extracted_data.issuer.name if extracted_data.issuer else ""
                    ),
                    "amount": (
                        float(extracted_data.total_amount)
                        if extracted_data.total_amount
                        else 0
                    ),
                }
            )
        except Exception as e:
            logger.warning(f"Error processing document {doc.id} for PDF export: {e}")
            continue

    if not transactions:
        raise HTTPException(status_code=404, detail="Nenhum dado para exportar")

    # Sort by date
    transactions.sort(key=lambda x: x["date"], reverse=True)

    # Create PDF
    buffer = BytesIO()
    doc_pdf = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()

    # Title
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=30,
        alignment=1,  # Center
    )
    story.append(Paragraph("Relatório Financeiro - ControlladorIA", title_style))
    story.append(Spacer(1, 0.2 * inch))

    # Date range
    if date_from and date_to:
        story.append(Paragraph(f"Período: {date_from} a {date_to}", styles["Normal"]))
    else:
        story.append(Paragraph(f"Período: Todos os registros", styles["Normal"]))
    story.append(Spacer(1, 0.3 * inch))

    # Summary table
    summary_data = [
        ["Resumo Financeiro", "Valor (R$)"],
        ["Total de Receitas", f"R$ {total_income:,.2f}"],
        ["Total de Despesas", f"R$ {total_expense:,.2f}"],
        ["Saldo Líquido", f"R$ {total_income - total_expense:,.2f}"],
        ["Total de Transações", str(len(transactions))],
    ]

    summary_table = Table(summary_data, colWidths=[3 * inch, 2 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a5568")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.4 * inch))

    # Transactions header
    story.append(Paragraph("Detalhamento de Transações", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * inch))

    # Transactions table (show first 50)
    trans_data = [["Data", "Tipo", "Categoria", "Emitente", "Valor (R$)"]]
    for t in transactions[:50]:
        trans_data.append(
            [
                t["date"][:10] if t["date"] else "",
                "Receita" if t["type"] == "receita" else t["type"].capitalize() if t["type"] else "Despesa",
                t["category"][:20],
                t["issuer"][:30],
                f"R$ {t['amount']:,.2f}",
            ]
        )

    trans_table = Table(
        trans_data, colWidths=[1 * inch, 1 * inch, 1.5 * inch, 2 * inch, 1.2 * inch]
    )
    trans_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a5568")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]
        )
    )
    story.append(trans_table)

    if len(transactions) > 50:
        story.append(Spacer(1, 0.2 * inch))
        story.append(
            Paragraph(
                f"* Mostrando as 50 transações mais recentes de {len(transactions)} totais",
                styles["Italic"],
            )
        )

    # Build PDF
    doc_pdf.build(story)
    buffer.seek(0)

    # Generate filename
    date_range = (
        f"{date_from}_to_{date_to}"
        if date_from and date_to
        else now_brazil().strftime("%Y%m%d")
    )
    filename = f"relatorio_financeiro_{date_range}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# =========================================
# DRE (INCOME STATEMENT) ENDPOINTS
# =========================================


@router.get("/reports/dre")
async def get_dre_report(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(
        None, description="Start date (YYYY-MM-DD) - required for custom period"
    ),
    end_date: Optional[str] = Query(
        None, description="End date (YYYY-MM-DD) - required for custom period"
    ),
    reference_date: Optional[str] = Query(
        None,
        description="Reference date for automatic period calculation (defaults to today)",
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Generate DRE (Demonstração do Resultado do Exercício) - Brazilian Income Statement

    Calculates financial performance metrics following Brazilian accounting standards.

    **Period Types:**
    - `day`: Single day report
    - `week`: Weekly report (Monday to Sunday)
    - `month`: Monthly report (first to last day of month)
    - `year`: Yearly report (January to December)
    - `custom`: Custom date range (requires start_date and end_date)

    **Returns:**
    - Complete DRE with all line items
    - Financial ratios (gross margin, EBITDA margin, operating margin, net margin)
    - Transaction counts and categorization details

    Requires authentication - calculates only current user's data
    """
    from datetime import date, datetime

    from accounting import PeriodType, calculate_dre, get_period_dates

    # Parse period type
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period_type. Must be one of: day, week, month, year, custom",
        )

    # Determine period dates
    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date and end_date are required for custom period",
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
            )
    else:
        # Calculate period from reference date
        if reference_date:
            try:
                ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid reference_date format. Use YYYY-MM-DD",
                )
        else:
            ref_date = now_brazil().date()

        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Get user's documents (org-scoped)
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()

    # Extract transactions (expands multi-row ledgers)
    transactions = _extract_transactions_from_documents(documents)

    # Calculate DRE
    dre = calculate_dre(
        transactions=transactions,
        period_type=period_enum,
        start_date=period_start,
        end_date=period_end,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    return dre


@router.get("/reports/dre/export/pdf")
async def export_dre_to_pdf_endpoint(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reference_date: Optional[str] = Query(None, description="Reference date"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Export DRE to PDF format

    Returns a professionally formatted PDF with Brazilian accounting standards.
    Includes all DRE line items and financial ratios.
    """
    from datetime import date, datetime
    from io import BytesIO

    from accounting import (
        PeriodType,
        calculate_dre,
        export_dre_to_pdf,
        get_period_dates,
    )

    # Parse period (same logic as get_dre_report)
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_type")

    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date and end_date required for custom period",
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        ref_date = (
            datetime.strptime(reference_date, "%Y-%m-%d").date()
            if reference_date
            else now_brazil().date()
        )
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Get transactions (expands multi-row ledgers) - org-scoped
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()
    transactions = _extract_transactions_from_documents(documents)

    # Calculate DRE
    dre = calculate_dre(
        transactions=transactions,
        period_type=period_enum,
        start_date=period_start,
        end_date=period_end,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Calculate previous period DRE for comparison
    prev_dre = None
    try:
        prev_start = prev_end = None
        if period_enum == PeriodType.MONTH:
            if period_start.month == 1:
                prev_ref = period_start.replace(year=period_start.year - 1, month=12, day=1)
            else:
                prev_ref = period_start.replace(month=period_start.month - 1, day=1)
            prev_start, prev_end = get_period_dates(period_enum, prev_ref)
        elif period_enum == PeriodType.YEAR:
            prev_ref = period_start.replace(year=period_start.year - 1)
            prev_start, prev_end = get_period_dates(period_enum, prev_ref)
        elif period_enum == PeriodType.CUSTOM:
            duration = (period_end - period_start).days
            prev_end = period_start - timedelta(days=1)
            prev_start = prev_end - timedelta(days=duration)

        if prev_start and prev_end:
            prev_dre = calculate_dre(
                transactions=transactions,
                period_type=period_enum,
                start_date=prev_start,
                end_date=prev_end,
                company_name=current_user.company_name,
                cnpj=current_user.cnpj,
            )
    except Exception as e:
        logger.warning(f"Could not calculate previous period DRE for PDF: {e}")
        prev_dre = None

    # Export to PDF
    logo_bytes = _get_export_logo_bytes(current_user, db)
    pdf_bytes = export_dre_to_pdf(dre, logo_bytes=logo_bytes, prev_dre=prev_dre)

    # Generate filename
    filename = f"DRE_{period_type}_{period_start.strftime('%Y%m%d')}_to_{period_end.strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/dre/export/excel")
async def export_dre_to_excel_endpoint(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reference_date: Optional[str] = Query(None, description="Reference date"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Export DRE to Excel format

    Returns an Excel file with:
    - Formatted DRE with Brazilian currency formatting
    - Formulas for calculations
    - Financial ratios
    - Professional styling
    """
    from datetime import date, datetime
    from io import BytesIO

    from accounting import (
        PeriodType,
        calculate_dre,
        export_dre_to_excel,
        get_period_dates,
    )

    # Parse period (same logic)
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_type")

    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400, detail="start_date and end_date required"
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        ref_date = (
            datetime.strptime(reference_date, "%Y-%m-%d").date()
            if reference_date
            else now_brazil().date()
        )
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Get transactions (expands multi-row ledgers) - org-scoped
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()
    transactions = _extract_transactions_from_documents(documents)

    # Calculate DRE
    dre = calculate_dre(
        transactions=transactions,
        period_type=period_enum,
        start_date=period_start,
        end_date=period_end,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Calculate previous period DRE for comparison
    prev_dre = None
    try:
        prev_start = prev_end = None
        if period_enum == PeriodType.MONTH:
            # Go back one month
            if period_start.month == 1:
                prev_ref = period_start.replace(year=period_start.year - 1, month=12, day=1)
            else:
                prev_ref = period_start.replace(month=period_start.month - 1, day=1)
            prev_start, prev_end = get_period_dates(period_enum, prev_ref)
        elif period_enum == PeriodType.YEAR:
            prev_ref = period_start.replace(year=period_start.year - 1)
            prev_start, prev_end = get_period_dates(period_enum, prev_ref)
        elif period_enum == PeriodType.CUSTOM:
            duration = (period_end - period_start).days
            prev_end = period_start - timedelta(days=1)
            prev_start = prev_end - timedelta(days=duration)

        if prev_start and prev_end:
            prev_dre = calculate_dre(
                transactions=transactions,
                period_type=period_enum,
                start_date=prev_start,
                end_date=prev_end,
                company_name=current_user.company_name,
                cnpj=current_user.cnpj,
            )
    except Exception as e:
        logger.warning(f"Could not calculate previous period DRE for export: {e}")
        prev_dre = None

    # Export to Excel
    logo_bytes = _get_export_logo_bytes(current_user, db)
    excel_bytes = export_dre_to_excel(dre, logo_bytes=logo_bytes, prev_dre=prev_dre)

    # Generate filename
    filename = f"DRE_{period_type}_{period_start.strftime('%Y%m%d')}_to_{period_end.strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/dre/export/csv")
async def export_dre_to_csv_endpoint(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reference_date: Optional[str] = Query(None, description="Reference date"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Export DRE to CSV format

    Returns a CSV file with DRE line items for data analysis.
    """
    from datetime import date, datetime
    from io import StringIO

    from accounting import (
        PeriodType,
        calculate_dre,
        export_dre_to_csv,
        get_period_dates,
    )

    # Parse period
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_type")

    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400, detail="start_date and end_date required"
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        ref_date = (
            datetime.strptime(reference_date, "%Y-%m-%d").date()
            if reference_date
            else now_brazil().date()
        )
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Get transactions (expands multi-row ledgers) - org-scoped
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()
    transactions = _extract_transactions_from_documents(documents)

    # Calculate DRE
    dre = calculate_dre(
        transactions=transactions,
        period_type=period_enum,
        start_date=period_start,
        end_date=period_end,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Export to CSV
    csv_string = export_dre_to_csv(dre)

    # Generate filename
    filename = f"DRE_{period_type}_{period_start.strftime('%Y%m%d')}_to_{period_end.strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        StringIO(csv_string),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )




# ===== BALANCE SHEET ENDPOINTS =====
# Brazilian Balance Sheet (Balanço Gerencial) reports with double-entry bookkeeping


@router.get("/reports/balance-sheet")
async def get_balance_sheet(
    reference_date: Optional[str] = Query(
        None, description="Balance sheet date (YYYY-MM-DD). Defaults to today"
    ),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Get Balance Sheet (Balanço Gerencial) as of a specific date

    Returns:
        - Assets (Ativo Circulante + Não Circulante)
        - Liabilities (Passivo Circulante + Não Circulante)
        - Equity (Patrimônio Líquido)

    The fundamental accounting equation: Assets = Liabilities + Equity

    Requires active subscription
    """
    from accounting.balance_sheet_calculator import BalanceSheetCalculator

    # Parse reference date
    if reference_date:
        try:
            ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid reference_date format. Use YYYY-MM-DD"
            )
    else:
        ref_date = now_brazil().date()

    # Calculate balance sheet
    calculator = BalanceSheetCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=ref_date,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Return as dict
    return balance_sheet.to_dict()


@router.get("/reports/balance-sheet/export/pdf")
async def export_balance_sheet_pdf(
    reference_date: Optional[str] = Query(
        None, description="Balance sheet date (YYYY-MM-DD). Defaults to today"
    ),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Export Balance Sheet to PDF

    Brazilian format with:
    - Assets (left side)
    - Liabilities + Equity (right side)
    - All in Brazilian Portuguese with R$ formatting

    Requires active subscription
    """
    from io import BytesIO

    from accounting.balance_sheet_calculator import BalanceSheetCalculator
    from accounting.balance_sheet_exports import export_balance_sheet_to_pdf

    # Parse reference date
    if reference_date:
        try:
            ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid reference_date format. Use YYYY-MM-DD"
            )
    else:
        ref_date = now_brazil().date()

    # Calculate balance sheet
    calculator = BalanceSheetCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=ref_date,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Export to PDF
    logo_bytes = _get_export_logo_bytes(current_user, db)
    pdf_bytes = export_balance_sheet_to_pdf(balance_sheet, logo_bytes=logo_bytes)

    # Generate filename
    filename = f"Balanco_Patrimonial_{ref_date.strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/balance-sheet/export/excel")
async def export_balance_sheet_excel(
    reference_date: Optional[str] = Query(
        None, description="Balance sheet date (YYYY-MM-DD). Defaults to today"
    ),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Export Balance Sheet to Excel

    Formatted spreadsheet with:
    - Professional styling
    - Brazilian currency format (R$)
    - Formulas for totals

    Requires active subscription
    """
    from io import BytesIO

    from accounting.balance_sheet_calculator import BalanceSheetCalculator
    from accounting.balance_sheet_exports import export_balance_sheet_to_excel

    # Parse reference date
    if reference_date:
        try:
            ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid reference_date format. Use YYYY-MM-DD"
            )
    else:
        ref_date = now_brazil().date()

    # Calculate balance sheet
    calculator = BalanceSheetCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=ref_date,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Export to Excel
    logo_bytes = _get_export_logo_bytes(current_user, db)
    excel_bytes = export_balance_sheet_to_excel(balance_sheet, logo_bytes=logo_bytes)

    # Generate filename
    filename = f"Balanco_Patrimonial_{ref_date.strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/balance-sheet/export/csv")
async def export_balance_sheet_csv(
    reference_date: Optional[str] = Query(
        None, description="Balance sheet date (YYYY-MM-DD). Defaults to today"
    ),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Export Balance Sheet to CSV

    Data export format for further analysis

    Requires active subscription
    """
    from io import StringIO

    from accounting.balance_sheet_calculator import BalanceSheetCalculator
    from accounting.balance_sheet_exports import export_balance_sheet_to_csv

    # Parse reference date
    if reference_date:
        try:
            ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid reference_date format. Use YYYY-MM-DD"
            )
    else:
        ref_date = now_brazil().date()

    # Calculate balance sheet
    calculator = BalanceSheetCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=ref_date,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Export to CSV
    csv_string = export_balance_sheet_to_csv(balance_sheet)

    # Generate filename
    filename = f"Balanco_Patrimonial_{ref_date.strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        StringIO(csv_string),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==================== INDICADORES FINANCEIROS ====================


@router.get("/reports/indicators")
async def get_financial_indicators(
    reference_date: Optional[str] = Query(
        None, description="Reference date (YYYY-MM-DD). Defaults to today"
    ),
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD) for custom period"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD) for custom period"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Calculate financial indicators (KPIs) from DRE and Balance Sheet data.
    Returns margins, liquidity ratios, leverage ratios, and profitability ratios.

    Now supports period_type parameter to match the unified date picker.
    """
    from datetime import date as date_type, datetime
    from decimal import Decimal

    from accounting import PeriodType, calculate_dre, get_period_dates
    from accounting.balance_sheet_calculator import BalanceSheetCalculator

    # Determine reference date
    if reference_date:
        try:
            ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        ref_date = date_type.today()

    org_id = getattr(current_user, '_active_org_id', None) or getattr(current_user, 'active_org_id', None)

    # Parse period type — indicators now respect the same period as DRE
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        period_enum = PeriodType.MONTH

    if period_enum == PeriodType.CUSTOM:
        if start_date and end_date:
            try:
                period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
                period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                period_start, period_end = get_period_dates(PeriodType.MONTH, ref_date)
        else:
            period_start, period_end = get_period_dates(PeriodType.MONTH, ref_date)
    else:
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Fetch transactions from completed documents (expands multi-row ledgers) - org-scoped
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()
    transactions = _extract_transactions_from_documents(documents)

    dre = calculate_dre(
        transactions=transactions,
        period_type=period_enum,
        start_date=period_start,
        end_date=period_end,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )
    dre_data = dre.model_dump() if dre else {}

    # Get Balance Sheet data
    calculator = BalanceSheetCalculator(db, current_user.id, org_id=org_id)
    bs = calculator.calculate_balance_sheet(reference_date=ref_date)

    def safe_div(a, b):
        """Safe division returning None for zero denominators"""
        if not b or b == 0:
            return None
        return round(float(a) / float(b), 4)

    def safe_pct(a, b):
        """Safe percentage"""
        r = safe_div(a, b)
        return round(r * 100, 2) if r is not None else None

    # Extract DRE values
    receita_bruta = float(dre_data.get("receita_bruta", 0) or 0)
    receita_liquida = float(dre_data.get("receita_liquida", 0) or 0)
    margem_contribuicao = float(dre_data.get("margem_contribuicao", 0) or 0)
    ebitda = float(dre_data.get("ebitda", 0) or 0)
    resultado_operacional = float(dre_data.get("resultado_operacional", 0) or 0)
    lucro_liquido = float(dre_data.get("lucro_liquido", 0) or 0)

    # Extract Balance Sheet values
    ativo_circulante = float(bs.ativo_circulante)
    ativo_total = float(bs.ativo_circulante + bs.ativo_nao_circulante + bs.imobilizado + bs.intangivel)
    passivo_circulante = float(bs.passivo_circulante)
    passivo_nao_circulante = float(bs.passivo_nao_circulante)
    passivo_total = float(bs.passivo_circulante + bs.passivo_nao_circulante)
    patrimonio_liquido = float(bs.patrimonio_liquido)
    estoques = 0.0
    # Try to find estoques from asset lines
    for line in bs.asset_lines:
        if "estoque" in line.name.lower():
            estoques += float(line.balance)

    indicators = {
        "reference_date": ref_date.isoformat(),
        "period": f"{period_start.isoformat()} a {period_end.isoformat()}",
        "margens": {
            "title": "Margens",
            "items": [
                {
                    "name": "Margem Bruta",
                    "formula": "Receita Líquida / Receita Bruta",
                    "value": safe_pct(receita_liquida, receita_bruta),
                    "suffix": "%",
                },
                {
                    "name": "Margem de Contribuição",
                    "formula": "Margem Contribuição / Receita Bruta",
                    "value": safe_pct(margem_contribuicao, receita_bruta),
                    "suffix": "%",
                },
                {
                    "name": "Margem EBITDA",
                    "formula": "EBITDA / Receita Bruta",
                    "value": safe_pct(ebitda, receita_bruta),
                    "suffix": "%",
                },
                {
                    "name": "Margem Operacional",
                    "formula": "Resultado Operacional / Receita Bruta",
                    "value": safe_pct(resultado_operacional, receita_bruta),
                    "suffix": "%",
                },
                {
                    "name": "Margem Líquida",
                    "formula": "Lucro Líquido / Receita Bruta",
                    "value": safe_pct(lucro_liquido, receita_bruta),
                    "suffix": "%",
                },
            ],
        },
        "liquidez": {
            "title": "Liquidez",
            "items": [
                {
                    "name": "Liquidez Corrente",
                    "formula": "Ativo Circulante / Passivo Circulante",
                    "value": safe_div(ativo_circulante, passivo_circulante),
                    "suffix": "",
                    "description": (
                        "Sem passivo circulante — empresa não possui dívidas de curto prazo"
                        if passivo_circulante == 0 else
                        "Para cada R$1 de dívida de curto prazo, a empresa tem R${:.2f} em ativos circulantes".format(safe_div(ativo_circulante, passivo_circulante) or 0)
                    ),
                },
                {
                    "name": "Liquidez Seca",
                    "formula": "(Ativo Circulante - Estoques) / Passivo Circulante",
                    "value": safe_div(ativo_circulante - estoques, passivo_circulante),
                    "suffix": "",
                    "description": (
                        "Sem passivo circulante — empresa não possui dívidas de curto prazo"
                        if passivo_circulante == 0 else
                        "Sem considerar estoques, para cada R$1 de dívida há R${:.2f} disponível".format(safe_div(ativo_circulante - estoques, passivo_circulante) or 0)
                    ),
                },
                {
                    "name": "Liquidez Geral",
                    "formula": "Ativo Total / Passivo Total",
                    "value": safe_div(ativo_total, passivo_total),
                    "suffix": "",
                    "description": (
                        "Sem passivo — empresa não possui dívidas registradas"
                        if passivo_total == 0 else
                        "Para cada R$1 de dívida total, a empresa tem R${:.2f} em ativos".format(safe_div(ativo_total, passivo_total) or 0)
                    ),
                },
            ],
        },
        "endividamento": {
            "title": "Endividamento",
            "items": [
                {
                    "name": "Endividamento Geral",
                    "formula": "Passivo Total / Ativo Total",
                    "value": safe_pct(passivo_total, ativo_total),
                    "suffix": "%",
                },
                {
                    "name": "Composição do Endividamento",
                    "formula": "Passivo Circulante / Passivo Total",
                    "value": safe_pct(passivo_circulante, passivo_total),
                    "suffix": "%",
                },
                {
                    "name": "Grau de Alavancagem",
                    "formula": "Ativo Total / Patrimônio Líquido",
                    "value": safe_div(ativo_total, patrimonio_liquido),
                    "suffix": "",
                    "description": "Para cada R$1 de capital próprio, a empresa controla R${:.2f} em ativos".format(safe_div(ativo_total, patrimonio_liquido) or 0),
                },
            ],
        },
        "rentabilidade": {
            "title": "Rentabilidade",
            "items": [
                {
                    "name": "ROE",
                    "formula": "Lucro Líquido / Patrimônio Líquido",
                    "value": safe_pct(lucro_liquido, patrimonio_liquido),
                    "suffix": "%",
                    "description": "Retorno sobre Patrimônio Líquido",
                },
                {
                    "name": "ROA",
                    "formula": "Lucro Líquido / Ativo Total",
                    "value": safe_pct(lucro_liquido, ativo_total),
                    "suffix": "%",
                    "description": "Retorno sobre Ativos",
                },
            ],
        },
        "operacional": {
            "title": "Operacional",
            "items": [
                {
                    "name": "Ponto de Equilíbrio (R$)",
                    "formula": "Custos Fixos / (Margem Contribuição %)",
                    "value": round(float(dre_data.get("total_custos_fixos", 0) or 0) / (margem_contribuicao / receita_bruta), 2) if receita_bruta and margem_contribuicao else None,
                    "suffix": "",
                    "is_currency": True,
                },
                {
                    "name": "EBITDA",
                    "formula": "Resultado antes de Juros, Impostos, Depreciação e Amortização",
                    "value": round(ebitda, 2),
                    "suffix": "",
                    "is_currency": True,
                },
            ],
        },
        "raw": {
            "receita_bruta": receita_bruta,
            "receita_liquida": receita_liquida,
            "margem_contribuicao": margem_contribuicao,
            "ebitda": ebitda,
            "lucro_liquido": lucro_liquido,
            "ativo_total": ativo_total,
            "passivo_total": passivo_total,
            "patrimonio_liquido": patrimonio_liquido,
        },
    }

    return indicators


# ==================== CASH FLOW (FLUXO DE CAIXA) ENDPOINTS ====================


@router.get("/reports/cash-flow")
async def get_cash_flow(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reference_date: Optional[str] = Query(None, description="Reference date"),
    method: str = Query("indirect", description="Method: direct or indirect"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get Cash Flow Statement (DFC) as JSON

    Returns structured cash flow data for inline display.
    Supports both direct and indirect methods per CPC 03.
    """
    from accounting.cash_flow_calculator import CashFlowCalculator
    from accounting import PeriodType, get_period_dates

    # Parse period
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_type")

    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date and end_date required for custom period",
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        ref_date = (
            datetime.strptime(reference_date, "%Y-%m-%d").date()
            if reference_date
            else now_brazil().date()
        )
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Calculate Cash Flow
    calculator = CashFlowCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    cash_flow = calculator.calculate_cash_flow(
        period_type=period_type,
        start_date=period_start,
        end_date=period_end,
        method=method,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Convert to JSON-serializable dict
    def section_to_dict(section):
        return {
            "section_name": section.section_name,
            "line_items": {k: float(v) for k, v in section.line_items.items()},
            "total": float(section.total),
        }

    return {
        "company_name": cash_flow.company_name,
        "cnpj": cash_flow.cnpj,
        "period_type": cash_flow.period_type,
        "start_date": cash_flow.start_date.isoformat(),
        "end_date": cash_flow.end_date.isoformat(),
        "method": cash_flow.method,
        "operating_activities": section_to_dict(cash_flow.operating_activities),
        "investing_activities": section_to_dict(cash_flow.investing_activities),
        "financing_activities": section_to_dict(cash_flow.financing_activities),
        "net_cash_from_operations": float(cash_flow.net_cash_from_operations),
        "net_cash_from_investments": float(cash_flow.net_cash_from_investments),
        "net_cash_from_financing": float(cash_flow.net_cash_from_financing),
        "net_increase_in_cash": float(cash_flow.net_increase_in_cash),
        "cash_beginning": float(cash_flow.cash_beginning),
        "cash_ending": float(cash_flow.cash_ending),
    }


@router.get("/reports/cash-flow/detailed")
async def get_cash_flow_detailed(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reference_date: Optional[str] = Query(None, description="Reference date"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get detailed daily cash flow breakdown.

    Returns DRE-like daily breakdown (daily_dre), bank entries,
    and monthly totals. Matches the ControlladorIA template structure.
    For day period_type, also includes raw transaction list.
    """
    from accounting import PeriodType, get_period_dates
    from accounting.cash_flow_daily import DailyCashFlowCalculator

    # Parse period
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_type")

    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date and end_date required for custom period",
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        ref_date = (
            datetime.strptime(reference_date, "%Y-%m-%d").date()
            if reference_date
            else now_brazil().date()
        )
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Get transactions from completed documents
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()
    transactions = _extract_transactions_from_documents(documents)

    # Get initial bank balances from OrgInitialBalance
    from database import OrgInitialBalance
    from decimal import Decimal

    org_id = getattr(current_user, '_active_org_id', None) or getattr(current_user, 'active_org_id', None)
    initial_bank_balances = {}
    if org_id:
        initial_balance = (
            db.query(OrgInitialBalance)
            .filter(
                OrgInitialBalance.organization_id == org_id,
                OrgInitialBalance.is_completed == True,
                OrgInitialBalance.reference_date <= period_start,
            )
            .order_by(OrgInitialBalance.reference_date.desc())
            .first()
        )
        if initial_balance:
            if initial_balance.cash_and_equivalents:
                initial_bank_balances["Principal"] = Decimal(str(initial_balance.cash_and_equivalents))
            if initial_balance.bank_account_balances:
                for entry in initial_balance.bank_account_balances:
                    bank_name = entry.get("bank_name") or entry.get("name") or "Banco"
                    balance = entry.get("balance", 0)
                    initial_bank_balances[bank_name] = Decimal(str(balance))

    # Calculate daily cash flow
    calculator = DailyCashFlowCalculator()
    daily_cf = calculator.calculate(
        transactions=transactions,
        start_date=period_start,
        end_date=period_end,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
        initial_bank_balances=initial_bank_balances if initial_bank_balances else None,
    )

    result = daily_cf.to_dict()
    result["period_type"] = period_type

    # For day view, include raw transactions for that day
    if period_enum == PeriodType.DAY:
        day_transactions = []
        day_key = period_start.isoformat()
        for txn in transactions:
            txn_date = txn.get("date")
            if txn_date is None:
                continue
            if isinstance(txn_date, str):
                txn_date_str = txn_date[:10]
            else:
                txn_date_str = txn_date.isoformat()[:10] if hasattr(txn_date, 'isoformat') else str(txn_date)[:10]
            if txn_date_str == day_key:
                day_transactions.append({
                    "date": txn_date_str,
                    "description": txn.get("description", ""),
                    "category": txn.get("category", ""),
                    "amount": float(txn.get("amount", 0) or 0),
                    "transaction_type": txn.get("transaction_type", ""),
                })
        result["transactions"] = day_transactions

    return result


@router.get("/reports/cash-flow/export/pdf")
async def export_cash_flow_pdf(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reference_date: Optional[str] = Query(None, description="Reference date"),
    method: str = Query("indirect", description="Method: direct or indirect"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Export Cash Flow Statement (DFC) to PDF

    Returns a professionally formatted PDF with cash flow analysis
    Supports both direct and indirect methods per CPC 03
    """
    from io import BytesIO

    from accounting.cash_flow_calculator import CashFlowCalculator
    from accounting.cash_flow_exports import export_cash_flow_to_pdf
    from accounting import PeriodType, get_period_dates

    # Parse period
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_type")

    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date and end_date required for custom period",
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        ref_date = (
            datetime.strptime(reference_date, "%Y-%m-%d").date()
            if reference_date
            else now_brazil().date()
        )
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Calculate Cash Flow
    calculator = CashFlowCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    cash_flow = calculator.calculate_cash_flow(
        period_type=period_type,
        start_date=period_start,
        end_date=period_end,
        method=method,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Export to PDF
    logo_bytes = _get_export_logo_bytes(current_user, db)
    pdf_bytes = export_cash_flow_to_pdf(cash_flow, logo_bytes=logo_bytes)

    # Generate filename
    filename = f"FluxoCaixa_{period_type}_{period_start.strftime('%Y%m%d')}_to_{period_end.strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/cash-flow/export/excel")
async def export_cash_flow_excel(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reference_date: Optional[str] = Query(None, description="Reference date"),
    method: str = Query("indirect", description="Method: direct or indirect"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Export Cash Flow Statement (DFC) to Excel

    Returns an Excel file with formatted cash flow statement
    Supports both direct and indirect methods per CPC 03
    """
    from io import BytesIO

    from accounting.cash_flow_calculator import CashFlowCalculator
    from accounting.cash_flow_exports import export_cash_flow_to_excel
    from accounting import PeriodType, get_period_dates

    # Parse period
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_type")

    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date and end_date required for custom period",
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        ref_date = (
            datetime.strptime(reference_date, "%Y-%m-%d").date()
            if reference_date
            else now_brazil().date()
        )
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Calculate Cash Flow
    calculator = CashFlowCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    cash_flow = calculator.calculate_cash_flow(
        period_type=period_type,
        start_date=period_start,
        end_date=period_end,
        method=method,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Export to Excel
    logo_bytes = _get_export_logo_bytes(current_user, db)
    excel_bytes = export_cash_flow_to_excel(cash_flow, logo_bytes=logo_bytes)

    # Generate filename
    filename = f"FluxoCaixa_{period_type}_{period_start.strftime('%Y%m%d')}_to_{period_end.strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/cash-flow/export/csv")
async def export_cash_flow_csv(
    period_type: str = Query(
        "month", description="Period type: day, week, month, year, custom"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reference_date: Optional[str] = Query(None, description="Reference date"),
    method: str = Query("indirect", description="Method: direct or indirect"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Export Cash Flow Statement (DFC) to CSV

    Returns a CSV file with cash flow statement data
    Supports both direct and indirect methods per CPC 03
    """
    from io import StringIO

    from accounting.cash_flow_calculator import CashFlowCalculator
    from accounting.cash_flow_exports import export_cash_flow_to_csv
    from accounting import PeriodType, get_period_dates

    # Parse period
    try:
        period_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_type")

    if period_enum == PeriodType.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date and end_date required for custom period",
            )
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        ref_date = (
            datetime.strptime(reference_date, "%Y-%m-%d").date()
            if reference_date
            else now_brazil().date()
        )
        period_start, period_end = get_period_dates(period_enum, ref_date)

    # Calculate Cash Flow
    calculator = CashFlowCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    cash_flow = calculator.calculate_cash_flow(
        period_type=period_type,
        start_date=period_start,
        end_date=period_end,
        method=method,
        company_name=current_user.company_name,
        cnpj=current_user.cnpj,
    )

    # Export to CSV
    csv_string = export_cash_flow_to_csv(cash_flow)

    # Generate filename
    filename = f"FluxoCaixa_{period_type}_{period_start.strftime('%Y%m%d')}_to_{period_end.strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        StringIO(csv_string),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==================== END CASH FLOW ENDPOINTS ====================


@router.get("/accounting/trial-balance")
async def get_trial_balance(
    reference_date: Optional[str] = Query(
        None, description="Trial balance date (YYYY-MM-DD). Defaults to today"
    ),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Get Trial Balance (Balancete de Verificação)

    Lists all accounts with their debit and credit balances
    Used to verify that total debits = total credits

    Requires active subscription
    """
    from accounting.balance_sheet_calculator import BalanceSheetCalculator

    # Parse reference date
    if reference_date:
        try:
            ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid reference_date format. Use YYYY-MM-DD"
            )
    else:
        ref_date = now_brazil().date()

    # Get trial balance
    calculator = BalanceSheetCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)
    trial_balance = calculator.get_trial_balance(ref_date)

    # Calculate totals
    total_debits = sum(item["debit_balance"] for item in trial_balance)
    total_credits = sum(item["credit_balance"] for item in trial_balance)

    return {
        "reference_date": ref_date.isoformat() + "Z" if ref_date else None,
        "accounts": trial_balance,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "is_balanced": abs(total_debits - total_credits) < 0.01,
    }


@router.get("/accounting/ledger/{account_code}")
async def get_account_ledger(
    account_code: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Get Account Ledger (Razão)

    Returns all journal entry lines for a specific account with running balance

    Args:
        account_code: Account code (e.g., "1.01.001" for Caixa)
        start_date: Optional start date filter
        end_date: Optional end date filter

    Requires active subscription
    """
    from accounting.balance_sheet_calculator import BalanceSheetCalculator

    # Parse dates
    parsed_start_date = None
    parsed_end_date = None

    if start_date:
        try:
            parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD"
            )

    if end_date:
        try:
            parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD"
            )

    # Get ledger
    calculator = BalanceSheetCalculator(db, current_user.id, org_id=getattr(current_user, '_active_org_id', None) or current_user.active_org_id)

    try:
        ledger = calculator.get_account_ledger(
            account_code=account_code,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "account_code": account_code,
        "start_date": start_date,
        "end_date": end_date,
        "entries": ledger,
    }


@router.get("/accounting/chart-of-accounts")
async def list_chart_of_accounts(
    account_type: Optional[str] = Query(
        None,
        description="Filter by account type (ativo_circulante, passivo_circulante, etc.)",
    ),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    List Chart of Accounts (Plano de Contas)

    Returns all accounts in the user's chart of accounts

    Args:
        account_type: Optional filter by account type

    Requires active subscription
    """
    from decimal import Decimal

    from database import ChartOfAccountsEntry

    query = db.query(ChartOfAccountsEntry).filter(
        ChartOfAccountsEntry.user_id == current_user.id,
        ChartOfAccountsEntry.is_active == True,
    )

    if account_type:
        query = query.filter(ChartOfAccountsEntry.account_type == account_type)

    accounts = query.order_by(ChartOfAccountsEntry.account_code).all()

    return {
        "accounts": [
            {
                "id": acc.id,
                "code": acc.account_code,
                "name": acc.account_name,
                "type": acc.account_type,
                "nature": acc.account_nature,
                "description": acc.description,
                "current_balance": float(Decimal(acc.current_balance) / Decimal(100)),
                "is_system_account": acc.is_system_account,
            }
            for acc in accounts
        ]
    }


@router.post("/accounting/journal-entries")
async def create_manual_journal_entry(
    entry_date: str = Query(..., description="Entry date (YYYY-MM-DD)"),
    description: str = Query(..., description="Entry description"),
    lines: str = Query(
        ...,
        description="JSON array of lines: [{account_code, debit_amount, credit_amount, description}]",
    ),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Create a manual journal entry

    Allows users to create custom double-entry journal entries

    Args:
        entry_date: Date of the entry
        description: Description of the transaction
        lines: JSON array of entry lines with account_code, debit_amount, credit_amount

    Example lines:
    [
        {"account_code": "1.01.001", "debit_amount": 1000, "credit_amount": 0, "description": "Cash received"},
        {"account_code": "4.01.001", "debit_amount": 0, "credit_amount": 1000, "description": "Sales revenue"}
    ]

    Requires active subscription
    """
    import json

    from accounting.accounting_engine import AccountingEngine

    # Parse entry date
    try:
        parsed_entry_date = datetime.strptime(entry_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid entry_date format. Use YYYY-MM-DD"
        )

    # Parse lines
    try:
        lines_data = json.loads(lines)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid lines JSON format")

    # Validate lines
    if not isinstance(lines_data, list) or len(lines_data) < 2:
        raise HTTPException(
            status_code=400, detail="At least 2 lines are required for a journal entry"
        )

    # Create journal entry
    engine = AccountingEngine(db, current_user.id)

    try:
        journal_entry = engine.create_manual_journal_entry(
            entry_date=parsed_entry_date,
            description=description,
            lines=lines_data,
            created_by=current_user.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating manual journal entry: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error creating journal entry: {str(e)}"
        )

    return {
        "success": True,
        "message": "Journal entry created successfully",
        "journal_entry_id": journal_entry.id,
        "entry_date": journal_entry.entry_date.isoformat() + "Z" if journal_entry.entry_date else None,
        "description": journal_entry.description,
    }


@router.post("/accounting/opening-balances")
async def set_opening_balances(
    balances: str = Query(
        ..., description="JSON object: {account_code: balance_amount}"
    ),
    opening_date: str = Query(..., description="Opening balance date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Set opening balances for accounts

    Used to initialize account balances when starting to use the system

    Args:
        balances: JSON object with account codes and amounts
        opening_date: Date of the opening balances

    Example balances:
    {
        "1.01.001": 5000.00,   # Caixa: R$ 5,000
        "2.01.001": 2000.00,   # Fornecedores: R$ 2,000
        "3.01.001": 3000.00    # Capital Social: R$ 3,000
    }

    Requires active subscription
    """
    import json

    from accounting.accounting_engine import AccountingEngine

    # Parse opening date
    try:
        parsed_opening_date = datetime.strptime(opening_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid opening_date format. Use YYYY-MM-DD"
        )

    # Parse balances
    try:
        balances_data = json.loads(balances)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid balances JSON format")

    # Create opening balances
    engine = AccountingEngine(db, current_user.id)

    try:
        journal_entries = engine.set_opening_balances(
            opening_balances=balances_data,
            opening_date=parsed_opening_date,
            created_by=current_user.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting opening balances: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error setting opening balances: {str(e)}"
        )

    return {
        "success": True,
        "message": "Opening balances set successfully",
        "entries_created": len(journal_entries),
        "opening_date": opening_date,
    }


# ===== DASHBOARD METRICS (Item 10) =====


@router.get("/reports/dashboard-metrics")
async def get_dashboard_metrics(
    year: int = Query(..., description="Year (e.g., 2025)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get monthly aggregated dashboard metrics for charts (Item 10).

    Returns 12 months of data for the specified year, pre-aggregated
    for efficient charting. Includes revenue, costs, margins, and
    EBITDA calculated per month.
    """
    from accounting.categories import get_dre_category, DRELineType

    # Load all completed documents for the year - org-scoped
    documents = document_org_filter(
        db.query(Document), current_user, db
    ).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    ).all()

    # Initialize monthly buckets
    months = {}
    for m in range(1, 13):
        months[m] = {
            "month": m,
            "month_name": _get_month_name_pt(m),
            "receita_bruta": Decimal("0"),
            "deducoes": Decimal("0"),
            "receita_liquida": Decimal("0"),
            "custos_variaveis": Decimal("0"),
            "margem_contribuicao": Decimal("0"),
            "custos_fixos": Decimal("0"),
            "ebitda": Decimal("0"),
            "lucro_liquido": Decimal("0"),
            "income_count": 0,
            "expense_count": 0,
            # For pie chart
            "by_category": {},
            "by_revenue_type": {},
        }

    # Classify each document into monthly buckets
    for doc in documents:
        try:
            data_dict = json.loads(doc.extracted_data_json)

            # Handle ledger documents (multi-transaction)
            if data_dict.get("document_type") == "transaction_ledger":
                transactions = data_dict.get("transactions", [])
                for txn in transactions:
                    _classify_transaction_for_dashboard(
                        months, txn, txn.get("date"), year
                    )
                continue

            # Single-transaction documents
            issue_date = data_dict.get("issue_date")
            _classify_transaction_for_dashboard(
                months, data_dict, issue_date, year
            )

        except Exception as e:
            logger.warning(f"Dashboard metrics: error processing doc {doc.id}: {e}")
            continue

    # Calculate derived metrics and percentages for each month
    monthly_data = []
    for m in range(1, 13):
        bucket = months[m]

        # Calculate derived values
        bucket["receita_liquida"] = bucket["receita_bruta"] + bucket["deducoes"]  # deducoes is negative
        bucket["margem_contribuicao"] = bucket["receita_liquida"] + bucket["custos_variaveis"]  # custos is negative
        bucket["ebitda"] = bucket["margem_contribuicao"] + bucket["custos_fixos"]  # custos is negative
        bucket["lucro_liquido"] = bucket["ebitda"]  # Simplified (before depreciation/financial/taxes)

        # Calculate percentages (vs receita_bruta)
        rb = bucket["receita_bruta"]
        pct_custos_var = float(abs(bucket["custos_variaveis"]) / rb * 100) if rb > 0 else 0
        pct_margem = float(bucket["margem_contribuicao"] / rb * 100) if rb > 0 else 0
        pct_custos_fixos = float(abs(bucket["custos_fixos"]) / rb * 100) if rb > 0 else 0
        pct_ebitda = float(bucket["ebitda"] / rb * 100) if rb > 0 else 0

        # Convert category dict to sorted list
        categories_list = sorted(
            [
                {"category": cat, "amount": str(abs(amt)), "count": cnt}
                for cat, (amt, cnt) in bucket["by_category"].items()
            ],
            key=lambda x: float(x["amount"]),
            reverse=True,
        )

        revenue_types_list = sorted(
            [
                {"type": rtype, "amount": str(amt)}
                for rtype, amt in bucket["by_revenue_type"].items()
            ],
            key=lambda x: float(x["amount"]),
            reverse=True,
        )

        monthly_data.append({
            "month": m,
            "month_name": bucket["month_name"],
            "receita_bruta": str(bucket["receita_bruta"]),
            "deducoes": str(bucket["deducoes"]),
            "receita_liquida": str(bucket["receita_liquida"]),
            "custos_variaveis": str(bucket["custos_variaveis"]),
            "margem_contribuicao": str(bucket["margem_contribuicao"]),
            "custos_fixos": str(bucket["custos_fixos"]),
            "ebitda": str(bucket["ebitda"]),
            "lucro_liquido": str(bucket["lucro_liquido"]),
            # Percentages (vs receita_bruta)
            "pct_custos_variaveis": round(pct_custos_var, 1),
            "pct_margem_contribuicao": round(pct_margem, 1),
            "pct_custos_fixos": round(pct_custos_fixos, 1),
            "pct_ebitda": round(pct_ebitda, 1),
            # Counts
            "income_count": bucket["income_count"],
            "expense_count": bucket["expense_count"],
            # Breakdowns
            "top_categories": categories_list[:10],
            "revenue_types": revenue_types_list,
        })

    # Year totals
    year_income = sum(float(m["receita_bruta"]) for m in monthly_data)
    year_expense = sum(
        abs(float(m["custos_variaveis"])) + abs(float(m["custos_fixos"])) + abs(float(m["deducoes"]))
        for m in monthly_data
    )

    return {
        "year": year,
        "currency": "BRL",
        "year_totals": {
            "receita_bruta": str(Decimal(str(year_income))),
            "total_expenses": str(Decimal(str(year_expense))),
            "ebitda": str(sum(Decimal(m["ebitda"]) for m in monthly_data)),
        },
        "monthly": monthly_data,
    }


def _classify_transaction_for_dashboard(
    months: dict, data: dict, issue_date: str, year: int
):
    """Classify a single transaction into the correct monthly dashboard bucket."""
    from accounting.categories import get_dre_category, DRELineType

    if not issue_date:
        return

    try:
        # Parse month from issue_date
        date_parts = issue_date.split("-")
        txn_year = int(date_parts[0])
        txn_month = int(date_parts[1])

        if txn_year != year or txn_month < 1 or txn_month > 12:
            return

        bucket = months[txn_month]

        category = data.get("category", "nao_categorizado")
        txn_type = data.get("transaction_type", "despesa")

        # Get amount
        amount_str = data.get("total_amount") or data.get("amount") or "0"
        amount = abs(Decimal(str(amount_str)))

        if txn_type in ("income", "receita"):
            bucket["income_count"] += 1
        else:
            bucket["expense_count"] += 1

        # Track by category
        if category not in bucket["by_category"]:
            bucket["by_category"][category] = (Decimal("0"), 0)
        prev_amt, prev_cnt = bucket["by_category"][category]
        bucket["by_category"][category] = (prev_amt + amount, prev_cnt + 1)

        # Classify using DRE category system
        dre_cat = get_dre_category(category)

        if dre_cat:
            line_type = dre_cat.get("line_type")

            if line_type == DRELineType.REVENUE:
                bucket["receita_bruta"] += amount
                # Track by revenue type for pie chart
                display = dre_cat.get("display_name", category)
                bucket["by_revenue_type"][display] = bucket["by_revenue_type"].get(display, Decimal("0")) + amount

            elif line_type == DRELineType.DEDUCTION:
                bucket["deducoes"] -= amount  # Negative

            elif line_type == DRELineType.VARIABLE_COST:
                bucket["custos_variaveis"] -= amount  # Negative

            elif line_type in (
                DRELineType.FIXED_EXPENSE_ADMIN,
                DRELineType.FIXED_EXPENSE_COMMERCIAL,
                DRELineType.DEPRECIATION,
            ):
                bucket["custos_fixos"] -= amount  # Negative

            elif line_type in (DRELineType.NON_OPERATING_REVENUE, DRELineType.OTHER_REVENUE):
                bucket["receita_bruta"] += amount

            elif line_type in (DRELineType.FINANCIAL_REVENUE,):
                bucket["receita_bruta"] += amount

            elif line_type in (DRELineType.FINANCIAL_EXPENSE, DRELineType.OTHER_EXPENSE):
                bucket["custos_fixos"] -= amount  # Negative

            elif line_type == DRELineType.TAX_ON_PROFIT:
                bucket["deducoes"] -= amount  # Negative

            # Legacy types
            elif line_type == DRELineType.COST:
                bucket["custos_variaveis"] -= amount
            elif line_type in (DRELineType.SALES_EXPENSE, DRELineType.ADMIN_EXPENSE):
                bucket["custos_fixos"] -= amount
            else:
                # Fallback: use transaction_type
                if txn_type in ("income", "receita"):
                    bucket["receita_bruta"] += amount
                else:
                    bucket["custos_fixos"] -= amount
        else:
            # No DRE category found - use transaction_type
            if txn_type in ("income", "receita"):
                bucket["receita_bruta"] += amount
            else:
                bucket["custos_fixos"] -= amount

    except Exception as e:
        logger.debug(f"Dashboard classify error: {e}")


def _get_month_name_pt(month: int) -> str:
    """Get Portuguese month name abbreviation."""
    names = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
        5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
        9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
    }
    return names.get(month, str(month))


# ===== CATEGORIES ENDPOINT =====

@router.get("/categories")
async def get_categories_list():
    """
    Get all available V2 categories from Plano de Contas.
    Returns category key, display_name, group, and nature for dropdowns.
    No auth required - categories are not user-specific.
    """
    from accounting.categories import DRE_CATEGORIES

    categories = []
    for cat_key, cat_config in DRE_CATEGORIES.items():
        categories.append({
            "key": cat_key,
            "display_name": cat_config.get("display_name", cat_key),
            "group": cat_config.get("dre_group", ""),
            "nature": cat_config.get("nature", ""),
            "account_code": cat_config.get("account_code", ""),
            "order": cat_config.get("order", 99),
        })

    categories.sort(key=lambda x: x["order"])
    return {"categories": categories}


# ===== ADMIN ENDPOINTS =====
# Admin-only dashboard and analytics endpoints




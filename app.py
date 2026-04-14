from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
import os

from flask import Flask, flash, make_response, redirect, render_template, request, session, url_for
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError


load_dotenv()

app = Flask(__name__)
is_vercel = bool(os.getenv("VERCEL"))
database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
missing_production_database = False
if not database_url:
    if is_vercel:
        missing_production_database = True
        database_url = "sqlite:///:memory:"
    else:
        database_url = "sqlite:///finance.db"
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "make10-dev-secret-key")
app.config["ADMIN_PASSWORD"] = os.getenv("ADMIN_PASSWORD", "admin123")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
# Dev experience: always reload templates/static while coding locally.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
db = SQLAlchemy(app)
migrate = Migrate(app, db)

ENTRY_TYPE_OPERATIONAL = "operational_expense"
ENTRY_TYPE_PERSONAL = "personal_expense"
ENTRY_TYPE_MERCHANDISE = "merchandise"
ENTRY_TYPE_CHOICES = {
    ENTRY_TYPE_OPERATIONAL: "Despesa operacional",
    ENTRY_TYPE_PERSONAL: "Despesa pessoal",
    ENTRY_TYPE_MERCHANDISE: "Mercadoria",
}
ENTRY_CATEGORY_CHOICES = {
    "aluguel": "Aluguel",
    "luz": "Luz",
    "funcionarios": "Funcionarios",
    "retirada_pessoal": "Retirada pessoal",
    "manutencao": "Manutencao",
    "imposto": "Imposto",
    "fornecedor": "Fornecedor",
    "outros": "Outros",
}
ENTRY_CATEGORY_ALIASES = {
    "aluguel": "aluguel",
    "luz": "luz",
    "folha": "funcionarios",
    "folha de pagamento": "funcionarios",
    "funcionarios": "funcionarios",
    "funcionários": "funcionarios",
    "pro labore": "funcionarios",
    "pro-labore": "funcionarios",
    "retirada pessoal": "retirada_pessoal",
    "manutencao": "manutencao",
    "manutenção": "manutencao",
    "imposto": "imposto",
    "impostos": "imposto",
    "fornecedor": "fornecedor",
}

account_payable_stores = db.Table(
    "account_payable_stores",
    db.Column("account_payable_id", db.Integer, db.ForeignKey("account_payable.id"), primary_key=True),
    db.Column("store_id", db.Integer, db.ForeignKey("store.id"), primary_key=True),
)

cash_outflow_stores = db.Table(
    "cash_outflow_stores",
    db.Column("cash_outflow_id", db.Integer, db.ForeignKey("cash_outflow.id"), primary_key=True),
    db.Column("store_id", db.Integer, db.ForeignKey("store.id"), primary_key=True),
)


class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    created_at = db.Column(db.Date, nullable=False, default=date.today)

    fixed_expenses = db.relationship(
        "FixedExpense", backref="store", lazy=True, cascade="all, delete-orphan"
    )
    sales = db.relationship(
        "DailySale", backref="store", lazy=True, cascade="all, delete-orphan"
    )
    shared_payables = db.relationship(
        "AccountPayable",
        secondary=account_payable_stores,
        back_populates="stores",
        lazy="select",
    )
    cash_outflows = db.relationship(
        "CashOutflow",
        secondary=cash_outflow_stores,
        back_populates="stores",
        lazy="select",
    )


class FixedExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    description = db.Column(db.String(120), nullable=False)
    monthly_amount = db.Column(db.Numeric(12, 2), nullable=False)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    active = db.Column(db.Boolean, nullable=False, default=True)


class DailySale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    sale_date = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.String(200), nullable=True)


class AccountPayable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(160), nullable=False)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=False, index=True)
    payable_type = db.Column(db.String(20), nullable=False, default=ENTRY_TYPE_OPERATIONAL)
    category_code = db.Column(db.String(40), nullable=False, default="outros")
    notes = db.Column(db.String(200), nullable=True)
    is_paid = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.Date, nullable=False, default=date.today)

    stores = db.relationship(
        "Store",
        secondary=account_payable_stores,
        back_populates="shared_payables",
        lazy="select",
    )


class CashOutflow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(160), nullable=False)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    outflow_date = db.Column(db.Date, nullable=False, index=True)
    outflow_type = db.Column(db.String(20), nullable=False, default=ENTRY_TYPE_OPERATIONAL)
    category_code = db.Column(db.String(40), nullable=False, default="outros")
    category = db.Column(db.String(80), nullable=True)
    notes = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.Date, nullable=False, default=date.today)

    stores = db.relationship(
        "Store",
        secondary=cash_outflow_stores,
        back_populates="cash_outflows",
        lazy="select",
    )


def parse_year_month(value: str | None) -> tuple[int, int]:
    if not value:
        today = date.today()
        return today.year, today.month
    year, month = value.split("-")
    return int(year), int(month)


def parse_date_input(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_period_filters(
    start_raw: str | None, end_raw: str | None, reference_month: str | None = None
) -> tuple[date, date, str]:
    year, month = parse_year_month(reference_month)
    default_start = date(year, month, 1)
    default_end = date(year, month, monthrange(year, month)[1])

    try:
        selected_start = parse_date_input(start_raw) or default_start
        selected_end = parse_date_input(end_raw) or default_end
    except ValueError:
        selected_start = default_start
        selected_end = default_end

    if selected_start > selected_end:
        selected_start = default_start
        selected_end = default_end

    month_token = f"{selected_start.year:04d}-{selected_start.month:02d}"
    return selected_start, selected_end, month_token


def resolve_selected_stores(
    all_stores: list[Store], selected_values: list[str]
) -> tuple[list[int], list[Store]]:
    available_store_ids = {store.id for store in all_stores}
    selected_store_ids: list[int] = []
    for raw_value in selected_values:
        try:
            store_id = int(raw_value)
        except (TypeError, ValueError):
            continue
        if store_id in available_store_ids and store_id not in selected_store_ids:
            selected_store_ids.append(store_id)

    if not selected_store_ids:
        return [], all_stores

    selected_store_set = set(selected_store_ids)
    filtered_stores = [store for store in all_stores if store.id in selected_store_set]
    return selected_store_ids, filtered_stores


def month_days(year: int, month: int) -> list[date]:
    total_days = monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, total_days + 1)]


def workdays_monday_to_saturday(year: int, month: int) -> list[date]:
    return [d for d in month_days(year, month) if d.weekday() <= 5]


def workdays_between(start: date, end: date) -> list[date]:
    day_count = (end - start).days + 1
    return [start + timedelta(days=offset) for offset in range(day_count) if (start + timedelta(days=offset)).weekday() <= 5]


def money(value: Decimal | float | int) -> str:
    v = Decimal(value).quantize(Decimal("0.01"))
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def is_authenticated() -> bool:
    return session.get("is_authenticated", False) is True


def parse_decimal_input(value: str, default: str = "0") -> Decimal:
    normalized = (value or default).strip().replace(",", ".")
    return Decimal(normalized)


def normalize_entry_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == ENTRY_TYPE_MERCHANDISE:
        return ENTRY_TYPE_MERCHANDISE
    if normalized == ENTRY_TYPE_PERSONAL:
        return ENTRY_TYPE_PERSONAL
    return ENTRY_TYPE_OPERATIONAL


def normalize_category_code(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    if not normalized:
        return "outros"
    return ENTRY_CATEGORY_ALIASES.get(normalized, normalized if normalized in ENTRY_CATEGORY_CHOICES else "outros")


def entry_type_label(value: str | None) -> str:
    normalized = normalize_entry_type(value)
    return ENTRY_TYPE_CHOICES.get(normalized, ENTRY_TYPE_CHOICES[ENTRY_TYPE_OPERATIONAL])


def entry_category_label(value: str | None) -> str:
    normalized = normalize_category_code(value)
    return ENTRY_CATEGORY_CHOICES.get(normalized, ENTRY_CATEGORY_CHOICES["outros"])


def pdf_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def build_simple_pdf(lines_by_page: list[list[str]]) -> bytes:
    objects: list[bytes] = []

    def add_object(data: str | bytes) -> int:
        if isinstance(data, str):
            data = data.encode("latin-1", errors="replace")
        objects.append(data)
        return len(objects)

    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    page_ids: list[int] = []
    content_ids: list[int] = []
    pages_id_placeholder_index = len(objects)
    add_object("<< /Type /Pages /Kids [] /Count 0 >>")

    for page_lines in lines_by_page:
        content_lines = [
            "BT",
            "/F2 16 Tf",
            "50 805 Td",
            f"({pdf_escape(page_lines[0])}) Tj",
            "0 -24 Td",
            "/F1 10 Tf",
        ]
        for line in page_lines[1:]:
            content_lines.append(f"({pdf_escape(line)}) Tj")
            content_lines.append("0 -14 Td")
        content_lines.append("ET")
        stream = "\n".join(content_lines)
        content_id = add_object(
            f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\nstream\n{stream}\nendstream"
        )
        content_ids.append(content_id)
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id_placeholder_index + 1} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R /F2 {bold_font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id_placeholder_index] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    )
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id_placeholder_index + 1} 0 R >>")

    buffer = BytesIO()
    buffer.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{index} 0 obj\n".encode("latin-1"))
        buffer.write(obj)
        buffer.write(b"\nendobj\n")

    xref_start = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    buffer.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode(
            "latin-1"
        )
    )
    return buffer.getvalue()


def build_summary_context() -> dict:
    selected_start, selected_end, month_token = resolve_period_filters(
        request.args.get("date_from"), request.args.get("date_to")
    )

    stores = Store.query.order_by(Store.name).all()
    selected_store_ids, filtered_stores = resolve_selected_stores(
        stores, request.args.getlist("store_ids")
    )

    metrics = []
    for store in filtered_stores:
        data = period_store_metrics(store, selected_start, selected_end)
        metrics.append({"store": store, "data": data})

    total_sales = sum((m["data"]["total_sales_month"] for m in metrics), Decimal("0.00"))
    total_shared_payables = sum(
        (m["data"]["total_shared_payables_month"] for m in metrics), Decimal("0.00")
    )
    total_outflows = sum((m["data"]["total_outflows_month"] for m in metrics), Decimal("0.00"))
    total_operational_outflows = sum(
        (m["data"]["total_operational_outflows_month"] for m in metrics), Decimal("0.00")
    )
    total_paid_payables = sum(
        (m["data"]["total_paid_payables_month"] for m in metrics), Decimal("0.00")
    )
    total_personal = sum((m["data"]["total_personal_month"] for m in metrics), Decimal("0.00"))
    total_merchandise = sum(
        (m["data"]["total_merchandise_month"] for m in metrics), Decimal("0.00")
    )
    total_expense_bucket = total_paid_payables - total_personal + total_operational_outflows
    total_expenses = total_shared_payables + total_outflows

    selected_store_names = [store.name for store in filtered_stores]
    selected_store_label = (
        "Todas as lojas" if not selected_store_ids else ", ".join(selected_store_names)
    )

    return {
        "month_token": month_token,
        "date_from_value": selected_start.strftime("%Y-%m-%d"),
        "date_to_value": selected_end.strftime("%Y-%m-%d"),
        "selected_start": selected_start,
        "selected_end": selected_end,
        "stores": stores,
        "selected_store_ids": selected_store_ids,
        "selected_store_label": selected_store_label,
        "metrics": metrics,
        "total_sales": total_sales,
        "total_shared_payables": total_shared_payables,
        "total_outflows": total_outflows,
        "total_operational_outflows": total_operational_outflows,
        "total_paid_payables": total_paid_payables,
        "total_personal": total_personal,
        "total_expense_bucket": total_expense_bucket,
        "total_merchandise": total_merchandise,
        "total_expenses": total_expenses,
        "total_result": total_sales - total_expenses,
    }


def period_store_metrics(store: Store, start: date, end: date) -> dict:
    shared_payables = (
        AccountPayable.query.join(account_payable_stores)
        .filter(
            account_payable_stores.c.store_id == store.id,
            AccountPayable.due_date >= start,
            AccountPayable.due_date <= end,
        )
        .order_by(AccountPayable.due_date.asc(), AccountPayable.id.desc())
        .all()
    )
    shared_payable_rows = []
    total_shared_month = Decimal("0.00")
    total_open_payables_month = Decimal("0.00")
    total_paid_payables_month = Decimal("0.00")
    total_payable_merchandise_month = Decimal("0.00")
    total_personal_payables_month = Decimal("0.00")
    for payable in shared_payables:
        store_count = len(payable.stores)
        allocated_amount = (
            payable.total_amount / Decimal(store_count) if store_count else Decimal("0.00")
        )
        total_shared_month += allocated_amount
        payable_type = normalize_entry_type(payable.payable_type)
        payable_category_code = normalize_category_code(payable.category_code)
        if payable_type == ENTRY_TYPE_MERCHANDISE:
            total_payable_merchandise_month += allocated_amount
        if payable_type == ENTRY_TYPE_PERSONAL:
            total_personal_payables_month += allocated_amount
        if payable.is_paid:
            total_paid_payables_month += allocated_amount
        else:
            total_open_payables_month += allocated_amount
        shared_payable_rows.append(
            {
                "id": payable.id,
                "kind": "payable",
                "description": payable.description,
                "event_date": payable.due_date,
                "total_amount": payable.total_amount,
                "allocated_amount": allocated_amount,
                "store_count": store_count,
                "payable_type": payable_type,
                "payable_type_label": entry_type_label(payable.payable_type),
                "category_code": payable_category_code,
                "category_label": entry_category_label(payable.category_code),
                "is_paid": payable.is_paid,
                "notes": payable.notes,
            }
        )

    cash_outflows = (
        CashOutflow.query.join(cash_outflow_stores)
        .filter(
            cash_outflow_stores.c.store_id == store.id,
            CashOutflow.outflow_date >= start,
            CashOutflow.outflow_date <= end,
        )
        .order_by(CashOutflow.outflow_date.desc(), CashOutflow.id.desc())
        .all()
    )
    cash_outflow_rows = []
    total_outflows_month = Decimal("0.00")
    total_operational_outflows_month = Decimal("0.00")
    total_merchandise_month = Decimal("0.00")
    total_personal_outflows_month = Decimal("0.00")
    for outflow in cash_outflows:
        store_count = len(outflow.stores)
        allocated_amount = (
            outflow.total_amount / Decimal(store_count) if store_count else Decimal("0.00")
        )
        total_outflows_month += allocated_amount
        outflow_type = normalize_entry_type(outflow.outflow_type)
        outflow_category_code = normalize_category_code(outflow.category_code)
        if outflow_type == ENTRY_TYPE_MERCHANDISE:
            total_merchandise_month += allocated_amount
        elif outflow_type == ENTRY_TYPE_PERSONAL:
            total_personal_outflows_month += allocated_amount
        else:
            total_operational_outflows_month += allocated_amount
        cash_outflow_rows.append(
            {
                "id": outflow.id,
                "kind": "outflow",
                "description": outflow.description,
                "event_date": outflow.outflow_date,
                "outflow_type": outflow_type,
                "outflow_type_label": entry_type_label(outflow.outflow_type),
                "category_code": outflow_category_code,
                "category_label": entry_category_label(outflow.category_code),
                "category": outflow.category,
                "total_amount": outflow.total_amount,
                "allocated_amount": allocated_amount,
                "store_count": store_count,
                "notes": outflow.notes,
            }
        )

    month_expense_items = sorted(
        [
            {
                "kind": item["kind"],
                "description": item["description"],
                "event_date": item["event_date"],
                "allocated_amount": item["allocated_amount"],
                "status": "Paga",
                "entry_type_label": item.get("payable_type_label"),
                "category": item.get("category_label") or "Outros",
                "details": item.get("notes"),
            }
            for item in shared_payable_rows
            if item.get("is_paid") and item.get("payable_type") != ENTRY_TYPE_MERCHANDISE
        ]
        + [
            {
                "kind": item["kind"],
                "description": item["description"],
                "event_date": item["event_date"],
                "allocated_amount": item["allocated_amount"],
                "status": "Pago",
                "entry_type_label": item.get("outflow_type_label"),
                "category": item.get("category_label") or "Outros",
                "details": item.get("category") or item.get("notes"),
            }
            for item in cash_outflow_rows
            if item.get("outflow_type") != ENTRY_TYPE_MERCHANDISE
        ],
        key=lambda item: (item["event_date"], item["description"].lower()),
        reverse=True,
    )

    sales = DailySale.query.filter(
        DailySale.store_id == store.id,
        DailySale.sale_date >= start,
        DailySale.sale_date <= end,
    ).all()
    total_sales_month = sum((s.amount for s in sales), Decimal("0.00"))

    total_personal_month = total_personal_payables_month + total_personal_outflows_month
    total_expense_bucket_month = (
        total_paid_payables_month
        - total_payable_merchandise_month
        - total_personal_payables_month
        + total_operational_outflows_month
    )
    total_expenses_month = total_shared_month + total_outflows_month

    sales_by_day = defaultdict(lambda: Decimal("0.00"))
    for s in sales:
        sales_by_day[s.sale_date] += s.amount

    worked_days = sorted(sales_by_day.keys())
    expense_per_day = (
        total_expenses_month / Decimal(len(worked_days)) if worked_days else Decimal("0.00")
    )

    day_rows = []
    for d in worked_days:
        sales_value = sales_by_day[d]
        day_rows.append(
            {
                "date": d,
                "sales": sales_value,
                "expense_allocated": expense_per_day,
                "result": sales_value - expense_per_day,
            }
        )

    return {
        "total_shared_payables_month": total_shared_month,
        "total_open_payables_month": total_open_payables_month,
        "total_paid_payables_month": total_paid_payables_month,
        "total_outflows_month": total_outflows_month,
        "total_operational_outflows_month": total_operational_outflows_month,
        "total_personal_outflows_month": total_personal_outflows_month,
        "total_personal_payables_month": total_personal_payables_month,
        "total_personal_month": total_personal_month,
        "total_merchandise_month": total_merchandise_month + total_payable_merchandise_month,
        "total_expense_bucket_month": total_expense_bucket_month,
        "total_expenses_month": total_expenses_month,
        "total_sales_month": total_sales_month,
        "expense_per_day": expense_per_day,
        "month_result": total_sales_month - total_expenses_month,
        "workdays_count": len(worked_days),
        "day_rows": day_rows,
        "shared_payables": shared_payable_rows,
        "open_shared_payables": [item for item in shared_payable_rows if not item.get("is_paid")],
        "cash_outflows": cash_outflow_rows,
        "month_expense_items": month_expense_items,
    }


def month_store_metrics(store: Store, year: int, month: int) -> dict:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return period_store_metrics(store, start, end)


@app.context_processor
def inject_helpers():
    return {
        "money": money,
        "is_authenticated": is_authenticated(),
        "entry_type_label": entry_type_label,
        "entry_category_label": entry_category_label,
    }


@app.before_request
def require_login():
    allowed_endpoints = {"login", "static"}
    if request.endpoint in allowed_endpoints:
        return None
    if missing_production_database:
        return (
            "DATABASE_URL is missing in production. Configure DATABASE_URL in Vercel "
            "Environment Variables and redeploy.",
            500,
        )
    if not is_authenticated():
        return redirect(url_for("login"))
    return None


@app.after_request
def disable_cache_in_debug(response):
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    return render_template("index.html", **build_summary_context())


@app.route("/summary/pdf")
def summary_pdf():
    context = build_summary_context()
    lines = [
        "Resumo Geral",
        f"Periodo: {context['selected_start'].strftime('%d/%m/%Y')} ate {context['selected_end'].strftime('%d/%m/%Y')}",
        f"Lojas: {context['selected_store_label']}",
        "",
        f"Vendas totais: {money(context['total_sales'])}",
        f"Despesas: {money(context['total_expense_bucket'])}",
        f"Despesas pessoais: {money(context['total_personal'])}",
        f"Mercadoria no mes: {money(context['total_merchandise'])}",
        f"Total de despesas: {money(context['total_expenses'])}",
        f"Resultado do mes: {money(context['total_result'])}",
        "",
        "Resumo por loja",
    ]

    for item in context["metrics"]:
        lines.extend(
            [
                f"- {item['store'].name}",
                f"  Vendas: {money(item['data']['total_sales_month'])}",
                f"  Despesas: {money(item['data']['total_expense_bucket_month'])}",
                f"  Despesas pessoais: {money(item['data']['total_personal_month'])}",
                f"  Mercadoria: {money(item['data']['total_merchandise_month'])}",
                f"  Total despesas: {money(item['data']['total_expenses_month'])}",
                f"  Despesa media por dia: {money(item['data']['expense_per_day'])}",
                f"  Resultado: {money(item['data']['month_result'])}",
                "",
            ]
        )

    page_size = 46
    pages = [lines[index:index + page_size] for index in range(0, len(lines), page_size)] or [["Resumo Geral"]]
    pdf_bytes = build_simple_pdf(pages)

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"inline; filename=resumo-{context['date_from_value']}-{context['date_to_value']}.pdf"
    )
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if is_authenticated():
        return redirect(url_for("index"))

    error_message = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == app.config["ADMIN_PASSWORD"]:
            session["is_authenticated"] = True
            return redirect(url_for("index"))
        error_message = "Senha incorreta."

    return render_template("login.html", error_message=error_message)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/payables", methods=["GET", "POST"])
def payables():
    stores = Store.query.order_by(Store.name).all()
    if request.method == "POST":
        description = request.form.get("description", "").strip()
        total_amount_raw = request.form.get("total_amount", "0")
        due_date_raw = request.form.get("due_date")
        payable_type = normalize_entry_type(request.form.get("payable_type"))
        category_code = normalize_category_code(request.form.get("category_code"))
        notes = request.form.get("notes", "").strip() or None
        selected_store_ids = [int(value) for value in request.form.getlist("store_ids")]

        if not description or not due_date_raw or not selected_store_ids:
            flash("Preencha descricao, vencimento e selecione ao menos uma loja.", "error")
            return redirect(url_for("payables"))

        try:
            due_date_value = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
            selected_stores = Store.query.filter(Store.id.in_(selected_store_ids)).all()
            if not selected_stores:
                flash("Nenhuma loja valida foi selecionada.", "error")
                return redirect(url_for("payables"))

            db.session.add(
                AccountPayable(
                    description=description,
                    total_amount=parse_decimal_input(total_amount_raw),
                    due_date=due_date_value,
                    payable_type=payable_type,
                    category_code=category_code,
                    notes=notes,
                    stores=selected_stores,
                )
            )
            db.session.commit()
            flash("Conta a pagar cadastrada com sucesso.", "success")
        except (ArithmeticError, ValueError, SQLAlchemyError):
            db.session.rollback()
            app.logger.exception("Erro ao cadastrar conta a pagar.")
            flash("Nao foi possivel cadastrar a conta a pagar.", "error")

        return redirect(url_for("payables"))

    selected_start, selected_end, month_token = resolve_period_filters(
        request.args.get("date_from"), request.args.get("date_to")
    )
    selected_store_ids, _ = resolve_selected_stores(stores, request.args.getlist("store_ids"))
    payable_query = AccountPayable.query.filter(
        AccountPayable.due_date >= selected_start,
        AccountPayable.due_date <= selected_end,
    )
    if selected_store_ids:
        payable_query = (
            payable_query.join(account_payable_stores)
            .filter(account_payable_stores.c.store_id.in_(selected_store_ids))
            .distinct()
        )
    payable_items = payable_query.order_by(AccountPayable.due_date.asc(), AccountPayable.id.desc()).all()
    return render_template(
        "payables.html",
        stores=stores,
        payables=payable_items,
        month_token=month_token,
        date_from_value=selected_start.strftime("%Y-%m-%d"),
        date_to_value=selected_end.strftime("%Y-%m-%d"),
        selected_store_ids=selected_store_ids,
        today=date.today(),
        entry_type_choices=ENTRY_TYPE_CHOICES,
        entry_category_choices=ENTRY_CATEGORY_CHOICES,
    )


@app.route("/payables/<int:payable_id>/update", methods=["POST"])
def update_payable(payable_id: int):
    payable = AccountPayable.query.get_or_404(payable_id)
    month_token = request.form.get("month") or payable.due_date.strftime("%Y-%m")
    description = request.form.get("description", "").strip()
    total_amount_raw = request.form.get("total_amount", "0")
    due_date_raw = request.form.get("due_date")
    payable_type = normalize_entry_type(request.form.get("payable_type"))
    category_code = normalize_category_code(request.form.get("category_code"))
    notes = request.form.get("notes", "").strip() or None
    selected_store_ids = [int(value) for value in request.form.getlist("store_ids")]
    is_paid = request.form.get("is_paid") == "on"

    if not description or not due_date_raw or not selected_store_ids:
        flash("Preencha descricao, vencimento e selecione ao menos uma loja.", "error")
        return redirect(url_for("payables", month=month_token))

    try:
        due_date_value = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
        selected_stores = Store.query.filter(Store.id.in_(selected_store_ids)).all()
        if not selected_stores:
            flash("Nenhuma loja valida foi selecionada.", "error")
            return redirect(url_for("payables", month=month_token))

        payable.description = description
        payable.total_amount = parse_decimal_input(total_amount_raw)
        payable.due_date = due_date_value
        payable.payable_type = payable_type
        payable.category_code = category_code
        payable.notes = notes
        payable.is_paid = is_paid
        payable.stores = selected_stores
        db.session.commit()
        flash("Conta a pagar atualizada com sucesso.", "success")
    except (ArithmeticError, ValueError, SQLAlchemyError):
        db.session.rollback()
        app.logger.exception("Erro ao atualizar conta a pagar.")
        flash("Nao foi possivel atualizar a conta a pagar.", "error")

    return redirect(url_for("payables", month=month_token))


@app.route("/payables/<int:payable_id>/delete", methods=["POST"])
def delete_payable(payable_id: int):
    payable = AccountPayable.query.get_or_404(payable_id)
    month_token = request.form.get("month") or payable.due_date.strftime("%Y-%m")

    try:
        db.session.delete(payable)
        db.session.commit()
        flash("Conta a pagar excluida com sucesso.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Erro ao excluir conta a pagar.")
        flash("Nao foi possivel excluir a conta a pagar.", "error")

    return redirect(url_for("payables", month=month_token))


@app.route("/outflows", methods=["GET", "POST"])
def outflows():
    stores = Store.query.order_by(Store.name).all()
    if request.method == "POST":
        description = request.form.get("description", "").strip()
        total_amount_raw = request.form.get("total_amount", "0")
        outflow_date_raw = request.form.get("outflow_date")
        outflow_type = normalize_entry_type(request.form.get("outflow_type"))
        category_code = normalize_category_code(request.form.get("category_code"))
        category = request.form.get("category", "").strip() or None
        notes = request.form.get("notes", "").strip() or None
        selected_store_ids = [int(value) for value in request.form.getlist("store_ids")]

        if not description or not outflow_date_raw or not selected_store_ids:
            flash("Preencha descricao, data e selecione ao menos uma loja.", "error")
            return redirect(url_for("outflows"))

        try:
            outflow_date_value = datetime.strptime(outflow_date_raw, "%Y-%m-%d").date()
            selected_stores = Store.query.filter(Store.id.in_(selected_store_ids)).all()
            if not selected_stores:
                flash("Nenhuma loja valida foi selecionada.", "error")
                return redirect(url_for("outflows"))

            db.session.add(
                CashOutflow(
                    description=description,
                    total_amount=parse_decimal_input(total_amount_raw),
                    outflow_date=outflow_date_value,
                    outflow_type=outflow_type,
                    category_code=category_code,
                    category=category,
                    notes=notes,
                    stores=selected_stores,
                )
            )
            db.session.commit()
            flash("Saida cadastrada com sucesso.", "success")
        except (ArithmeticError, ValueError, SQLAlchemyError):
            db.session.rollback()
            app.logger.exception("Erro ao cadastrar saida.")
            flash("Nao foi possivel cadastrar a saida.", "error")

        return redirect(url_for("outflows"))

    selected_start, selected_end, month_token = resolve_period_filters(
        request.args.get("date_from"), request.args.get("date_to")
    )
    selected_store_ids, _ = resolve_selected_stores(stores, request.args.getlist("store_ids"))
    outflow_query = CashOutflow.query.filter(
        CashOutflow.outflow_date >= selected_start,
        CashOutflow.outflow_date <= selected_end,
    )
    if selected_store_ids:
        outflow_query = (
            outflow_query.join(cash_outflow_stores)
            .filter(cash_outflow_stores.c.store_id.in_(selected_store_ids))
            .distinct()
        )
    outflow_items = outflow_query.order_by(CashOutflow.outflow_date.desc(), CashOutflow.id.desc()).all()
    return render_template(
        "outflows.html",
        stores=stores,
        outflows=outflow_items,
        month_token=month_token,
        date_from_value=selected_start.strftime("%Y-%m-%d"),
        date_to_value=selected_end.strftime("%Y-%m-%d"),
        selected_store_ids=selected_store_ids,
        entry_type_choices=ENTRY_TYPE_CHOICES,
        entry_category_choices=ENTRY_CATEGORY_CHOICES,
    )


@app.route("/outflows/<int:outflow_id>/update", methods=["POST"])
def update_outflow(outflow_id: int):
    outflow = CashOutflow.query.get_or_404(outflow_id)
    month_token = request.form.get("month") or outflow.outflow_date.strftime("%Y-%m")
    description = request.form.get("description", "").strip()
    total_amount_raw = request.form.get("total_amount", "0")
    outflow_date_raw = request.form.get("outflow_date")
    outflow_type = normalize_entry_type(request.form.get("outflow_type"))
    category_code = normalize_category_code(request.form.get("category_code"))
    category = request.form.get("category", "").strip() or None
    notes = request.form.get("notes", "").strip() or None
    selected_store_ids = [int(value) for value in request.form.getlist("store_ids")]

    if not description or not outflow_date_raw or not selected_store_ids:
        flash("Preencha descricao, data e selecione ao menos uma loja.", "error")
        return redirect(url_for("outflows", month=month_token))

    try:
        outflow_date_value = datetime.strptime(outflow_date_raw, "%Y-%m-%d").date()
        selected_stores = Store.query.filter(Store.id.in_(selected_store_ids)).all()
        if not selected_stores:
            flash("Nenhuma loja valida foi selecionada.", "error")
            return redirect(url_for("outflows", month=month_token))

        outflow.description = description
        outflow.total_amount = parse_decimal_input(total_amount_raw)
        outflow.outflow_date = outflow_date_value
        outflow.outflow_type = outflow_type
        outflow.category_code = category_code
        outflow.category = category
        outflow.notes = notes
        outflow.stores = selected_stores
        db.session.commit()
        flash("Saida atualizada com sucesso.", "success")
    except (ArithmeticError, ValueError, SQLAlchemyError):
        db.session.rollback()
        app.logger.exception("Erro ao atualizar saida.")
        flash("Nao foi possivel atualizar a saida.", "error")

    return redirect(url_for("outflows", month=month_token))


@app.route("/outflows/<int:outflow_id>/delete", methods=["POST"])
def delete_outflow(outflow_id: int):
    outflow = CashOutflow.query.get_or_404(outflow_id)
    month_token = request.form.get("month") or outflow.outflow_date.strftime("%Y-%m")

    try:
        db.session.delete(outflow)
        db.session.commit()
        flash("Saida excluida com sucesso.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Erro ao excluir saida.")
        flash("Nao foi possivel excluir a saida.", "error")

    return redirect(url_for("outflows", month=month_token))


@app.route("/stores", methods=["GET", "POST"])
def stores():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            existing = Store.query.filter(db.func.lower(Store.name) == name.lower()).first()
            if not existing:
                try:
                    db.session.add(Store(name=name))
                    db.session.commit()
                    flash("Loja cadastrada com sucesso.", "success")
                except SQLAlchemyError:
                    db.session.rollback()
                    app.logger.exception("Erro ao cadastrar loja.")
                    flash("Nao foi possivel cadastrar a loja.", "error")
            else:
                flash("Ja existe uma loja com esse nome.", "error")
        return redirect(url_for("stores"))
    return render_template("stores.html", stores=Store.query.order_by(Store.name).all())


@app.route("/stores/<int:store_id>/sales/<int:sale_id>/update", methods=["POST"])
def update_sale(store_id: int, sale_id: int):
    store = Store.query.get_or_404(store_id)
    sale = DailySale.query.filter_by(id=sale_id, store_id=store.id).first_or_404()
    month_token = request.form.get("month") or sale.sale_date.strftime("%Y-%m")
    sale_date_raw = request.form.get("sale_date")
    amount_raw = request.form.get("amount", "0")
    notes = request.form.get("notes", "").strip() or None

    if not sale_date_raw:
        flash("Informe a data da venda.", "error")
        return redirect(url_for("store_detail", store_id=store.id, month=month_token))

    try:
        sale.sale_date = datetime.strptime(sale_date_raw, "%Y-%m-%d").date()
        sale.amount = parse_decimal_input(amount_raw)
        sale.notes = notes
        db.session.commit()
        flash("Venda diaria atualizada com sucesso.", "success")
    except (ArithmeticError, ValueError, SQLAlchemyError):
        db.session.rollback()
        app.logger.exception("Erro ao atualizar venda diaria.")
        flash("Nao foi possivel atualizar a venda diaria.", "error")

    return redirect(url_for("store_detail", store_id=store.id, month=month_token))


@app.route("/stores/<int:store_id>/sales/<int:sale_id>/delete", methods=["POST"])
def delete_sale(store_id: int, sale_id: int):
    store = Store.query.get_or_404(store_id)
    sale = DailySale.query.filter_by(id=sale_id, store_id=store.id).first_or_404()
    month_token = request.form.get("month") or sale.sale_date.strftime("%Y-%m")

    try:
        db.session.delete(sale)
        db.session.commit()
        flash("Venda diaria excluida com sucesso.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Erro ao excluir venda diaria.")
        flash("Nao foi possivel excluir a venda diaria.", "error")

    return redirect(url_for("store_detail", store_id=store.id, month=month_token))


@app.route("/stores/<int:store_id>", methods=["GET", "POST"])
def store_detail(store_id: int):
    store = Store.query.get_or_404(store_id)
    selected_month = request.args.get("month")
    year, month = parse_year_month(selected_month)
    month_token = f"{year:04d}-{month:02d}"

    if request.method == "POST":
        action = request.form.get("action")
        if action == "sale":
            sale_date_raw = request.form.get("sale_date")
            amount_raw = request.form.get("amount", "0")
            notes = request.form.get("notes", "").strip() or None
            if sale_date_raw:
                try:
                    db.session.add(
                        DailySale(
                            store_id=store.id,
                            sale_date=datetime.strptime(sale_date_raw, "%Y-%m-%d").date(),
                            amount=parse_decimal_input(amount_raw),
                            notes=notes,
                        )
                    )
                    db.session.commit()
                    flash("Venda diaria salva com sucesso.", "success")
                except (ArithmeticError, ValueError, SQLAlchemyError):
                    db.session.rollback()
                    app.logger.exception("Erro ao salvar venda diaria.")
                    flash("Nao foi possivel salvar a venda diaria.", "error")

        return redirect(url_for("store_detail", store_id=store.id, month=month_token))

    data = month_store_metrics(store, year, month)
    recent_sales = (
        DailySale.query.filter_by(store_id=store.id)
        .order_by(DailySale.sale_date.desc(), DailySale.id.desc())
        .limit(20)
        .all()
    )

    return render_template(
        "store_detail.html",
        store=store,
        data=data,
        month_token=month_token,
        recent_sales=recent_sales,
        header_title=f"Loja: {store.name}",
    )

if __name__ == "__main__":
    app.run(debug=True, use_reloader=True)

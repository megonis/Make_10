from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import os

from flask import Flask, flash, redirect, render_template, request, session, url_for
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

OUTFLOW_TYPE_OPERATIONAL = "operational"
OUTFLOW_TYPE_MERCHANDISE = "merchandise"
OUTFLOW_TYPE_CHOICES = {
    OUTFLOW_TYPE_OPERATIONAL: "Outra saida",
    OUTFLOW_TYPE_MERCHANDISE: "Mercadoria",
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
    payable_type = db.Column(db.String(20), nullable=False, default=OUTFLOW_TYPE_OPERATIONAL)
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
    outflow_type = db.Column(db.String(20), nullable=False, default=OUTFLOW_TYPE_OPERATIONAL)
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


def month_days(year: int, month: int) -> list[date]:
    total_days = monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, total_days + 1)]


def workdays_monday_to_saturday(year: int, month: int) -> list[date]:
    return [d for d in month_days(year, month) if d.weekday() <= 5]


def money(value: Decimal | float | int) -> str:
    v = Decimal(value).quantize(Decimal("0.01"))
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def is_authenticated() -> bool:
    return session.get("is_authenticated", False) is True


def parse_decimal_input(value: str, default: str = "0") -> Decimal:
    normalized = (value or default).strip().replace(",", ".")
    return Decimal(normalized)


def normalize_outflow_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == OUTFLOW_TYPE_MERCHANDISE:
        return OUTFLOW_TYPE_MERCHANDISE
    return OUTFLOW_TYPE_OPERATIONAL


def outflow_type_label(value: str | None) -> str:
    return OUTFLOW_TYPE_CHOICES.get(normalize_outflow_type(value), OUTFLOW_TYPE_CHOICES[OUTFLOW_TYPE_OPERATIONAL])


def month_store_metrics(store: Store, year: int, month: int) -> dict:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    expenses = FixedExpense.query.filter(
        FixedExpense.store_id == store.id,
        FixedExpense.active.is_(True),
        FixedExpense.start_date <= end,
    ).all()
    total_fixed_month = sum((e.monthly_amount for e in expenses), Decimal("0.00"))

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
    for payable in shared_payables:
        store_count = len(payable.stores)
        allocated_amount = (
            payable.total_amount / Decimal(store_count) if store_count else Decimal("0.00")
        )
        total_shared_month += allocated_amount
        payable_type = normalize_outflow_type(payable.payable_type)
        if payable_type == OUTFLOW_TYPE_MERCHANDISE:
            total_payable_merchandise_month += allocated_amount
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
                "payable_type_label": outflow_type_label(payable.payable_type),
                "is_paid": payable.is_paid,
                "notes": payable.notes,
                "category": "Conta a pagar",
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
    for outflow in cash_outflows:
        store_count = len(outflow.stores)
        allocated_amount = (
            outflow.total_amount / Decimal(store_count) if store_count else Decimal("0.00")
        )
        total_outflows_month += allocated_amount
        outflow_type = normalize_outflow_type(outflow.outflow_type)
        if outflow_type == OUTFLOW_TYPE_MERCHANDISE:
            total_merchandise_month += allocated_amount
        else:
            total_operational_outflows_month += allocated_amount
        cash_outflow_rows.append(
            {
                "id": outflow.id,
                "kind": "outflow",
                "description": outflow.description,
                "event_date": outflow.outflow_date,
                "outflow_type": outflow_type,
                "outflow_type_label": outflow_type_label(outflow.outflow_type),
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
                "category": item.get("category") or item.get("payable_type_label") or "Conta a pagar",
            }
            for item in shared_payable_rows
            if item.get("is_paid") and item.get("payable_type") != OUTFLOW_TYPE_MERCHANDISE
        ]
        + [
            {
                "kind": item["kind"],
                "description": item["description"],
                "event_date": item["event_date"],
                "allocated_amount": item["allocated_amount"],
                "status": "Pago",
                "category": item.get("category") or item.get("outflow_type_label") or "Saida",
            }
            for item in cash_outflow_rows
            if item.get("outflow_type") != OUTFLOW_TYPE_MERCHANDISE
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

    workdays = workdays_monday_to_saturday(year, month)
    total_expense_bucket_month = (
        total_paid_payables_month - total_payable_merchandise_month + total_operational_outflows_month
    )
    total_expenses_month = total_fixed_month + total_shared_month + total_outflows_month
    fixed_per_day = total_expenses_month / Decimal(len(workdays)) if workdays else Decimal("0.00")

    sales_by_day = defaultdict(lambda: Decimal("0.00"))
    for s in sales:
        sales_by_day[s.sale_date] += s.amount

    day_rows = []
    for d in workdays:
        sales_value = sales_by_day[d]
        day_rows.append(
            {
                "date": d,
                "sales": sales_value,
                "fixed_allocated": fixed_per_day,
                "result": sales_value - fixed_per_day,
            }
        )

    return {
        "total_fixed_month": total_fixed_month,
        "total_shared_payables_month": total_shared_month,
        "total_open_payables_month": total_open_payables_month,
        "total_paid_payables_month": total_paid_payables_month,
        "total_outflows_month": total_outflows_month,
        "total_operational_outflows_month": total_operational_outflows_month,
        "total_merchandise_month": total_merchandise_month + total_payable_merchandise_month,
        "total_expense_bucket_month": total_expense_bucket_month,
        "total_expenses_month": total_expenses_month,
        "total_sales_month": total_sales_month,
        "fixed_per_day": fixed_per_day,
        "month_result": total_sales_month - total_expenses_month,
        "workdays_count": len(workdays),
        "day_rows": day_rows,
        "expenses": expenses,
        "shared_payables": shared_payable_rows,
        "open_shared_payables": [item for item in shared_payable_rows if not item.get("is_paid")],
        "cash_outflows": cash_outflow_rows,
        "month_expense_items": month_expense_items,
    }


@app.context_processor
def inject_helpers():
    return {
        "money": money,
        "is_authenticated": is_authenticated(),
        "outflow_type_label": outflow_type_label,
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
    selected_month = request.args.get("month")
    year, month = parse_year_month(selected_month)
    month_token = f"{year:04d}-{month:02d}"

    stores = Store.query.order_by(Store.name).all()
    metrics = []
    for store in stores:
        data = month_store_metrics(store, year, month)
        metrics.append({"store": store, "data": data})

    total_sales = sum((m["data"]["total_sales_month"] for m in metrics), Decimal("0.00"))
    total_fixed = sum((m["data"]["total_fixed_month"] for m in metrics), Decimal("0.00"))
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
    total_merchandise = sum(
        (m["data"]["total_merchandise_month"] for m in metrics), Decimal("0.00")
    )
    total_expense_bucket = total_paid_payables + total_operational_outflows
    total_expenses = total_fixed + total_shared_payables + total_outflows

    return render_template(
        "index.html",
        month_token=month_token,
        metrics=metrics,
        total_sales=total_sales,
        total_fixed=total_fixed,
        total_shared_payables=total_shared_payables,
        total_outflows=total_outflows,
        total_operational_outflows=total_operational_outflows,
        total_paid_payables=total_paid_payables,
        total_expense_bucket=total_expense_bucket,
        total_merchandise=total_merchandise,
        total_expenses=total_expenses,
        total_result=total_sales - total_expenses,
    )


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
        payable_type = normalize_outflow_type(request.form.get("payable_type"))
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

    selected_month = request.args.get("month")
    year, month = parse_year_month(selected_month)
    month_token = f"{year:04d}-{month:02d}"
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    payable_items = (
        AccountPayable.query.filter(
            AccountPayable.due_date >= start,
            AccountPayable.due_date <= end,
        )
        .order_by(AccountPayable.due_date.asc(), AccountPayable.id.desc())
        .all()
    )
    return render_template(
        "payables.html",
        stores=stores,
        payables=payable_items,
        month_token=month_token,
        today=date.today(),
        payable_type_choices=OUTFLOW_TYPE_CHOICES,
    )


@app.route("/payables/<int:payable_id>/update", methods=["POST"])
def update_payable(payable_id: int):
    payable = AccountPayable.query.get_or_404(payable_id)
    month_token = request.form.get("month") or payable.due_date.strftime("%Y-%m")
    description = request.form.get("description", "").strip()
    total_amount_raw = request.form.get("total_amount", "0")
    due_date_raw = request.form.get("due_date")
    payable_type = normalize_outflow_type(request.form.get("payable_type"))
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
        outflow_type = normalize_outflow_type(request.form.get("outflow_type"))
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

    selected_month = request.args.get("month")
    year, month = parse_year_month(selected_month)
    month_token = f"{year:04d}-{month:02d}"
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    outflow_items = (
        CashOutflow.query.filter(
            CashOutflow.outflow_date >= start,
            CashOutflow.outflow_date <= end,
        )
        .order_by(CashOutflow.outflow_date.desc(), CashOutflow.id.desc())
        .all()
    )
    return render_template(
        "outflows.html",
        stores=stores,
        outflows=outflow_items,
        month_token=month_token,
        outflow_type_choices=OUTFLOW_TYPE_CHOICES,
    )


@app.route("/outflows/<int:outflow_id>/update", methods=["POST"])
def update_outflow(outflow_id: int):
    outflow = CashOutflow.query.get_or_404(outflow_id)
    month_token = request.form.get("month") or outflow.outflow_date.strftime("%Y-%m")
    description = request.form.get("description", "").strip()
    total_amount_raw = request.form.get("total_amount", "0")
    outflow_date_raw = request.form.get("outflow_date")
    outflow_type = normalize_outflow_type(request.form.get("outflow_type"))
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
        if action == "expense":
            description = request.form.get("description", "").strip()
            monthly_amount_raw = request.form.get("monthly_amount", "0")
            start_date_raw = request.form.get("start_date")
            if description:
                try:
                    start_date_value = (
                        datetime.strptime(start_date_raw, "%Y-%m-%d").date()
                        if start_date_raw
                        else date.today()
                    )
                    db.session.add(
                        FixedExpense(
                            store_id=store.id,
                            description=description,
                            monthly_amount=parse_decimal_input(monthly_amount_raw),
                            start_date=start_date_value,
                            active=True,
                        )
                    )
                    db.session.commit()
                    flash("Despesa cadastrada com sucesso.", "success")
                except (ArithmeticError, ValueError, SQLAlchemyError):
                    db.session.rollback()
                    app.logger.exception("Erro ao cadastrar despesa fixa.")
                    flash("Nao foi possivel salvar a despesa.", "error")
        elif action == "sale":
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

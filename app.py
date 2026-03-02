from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import os

from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)
database_url = os.getenv("DATABASE_URL", "sqlite:///finance.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
# Dev experience: always reload templates/static while coding locally.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
db = SQLAlchemy(app)


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


def month_store_metrics(store: Store, year: int, month: int) -> dict:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    expenses = FixedExpense.query.filter(
        FixedExpense.store_id == store.id,
        FixedExpense.active.is_(True),
        FixedExpense.start_date <= end,
    ).all()
    total_fixed_month = sum((e.monthly_amount for e in expenses), Decimal("0.00"))

    sales = DailySale.query.filter(
        DailySale.store_id == store.id,
        DailySale.sale_date >= start,
        DailySale.sale_date <= end,
    ).all()
    total_sales_month = sum((s.amount for s in sales), Decimal("0.00"))

    workdays = workdays_monday_to_saturday(year, month)
    fixed_per_day = (
        total_fixed_month / Decimal(len(workdays)) if workdays else Decimal("0.00")
    )

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
        "total_sales_month": total_sales_month,
        "fixed_per_day": fixed_per_day,
        "month_result": total_sales_month - total_fixed_month,
        "workdays_count": len(workdays),
        "day_rows": day_rows,
        "expenses": expenses,
    }


@app.context_processor
def inject_helpers():
    return {"money": money}


@app.after_request
def disable_cache_in_debug(response):
    if app.debug:
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

    return render_template(
        "index.html",
        month_token=month_token,
        metrics=metrics,
        total_sales=total_sales,
        total_fixed=total_fixed,
        total_result=total_sales - total_fixed,
    )


@app.route("/stores", methods=["GET", "POST"])
def stores():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            existing = Store.query.filter(db.func.lower(Store.name) == name.lower()).first()
            if not existing:
                db.session.add(Store(name=name))
                db.session.commit()
        return redirect(url_for("stores"))
    return render_template("stores.html", stores=Store.query.order_by(Store.name).all())


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
            monthly_amount = request.form.get("monthly_amount", "0").replace(",", ".")
            start_date_raw = request.form.get("start_date")
            if description:
                start_date_value = (
                    datetime.strptime(start_date_raw, "%Y-%m-%d").date()
                    if start_date_raw
                    else date.today()
                )
                db.session.add(
                    FixedExpense(
                        store_id=store.id,
                        description=description,
                        monthly_amount=Decimal(monthly_amount),
                        start_date=start_date_value,
                        active=True,
                    )
                )
                db.session.commit()
        elif action == "sale":
            sale_date_raw = request.form.get("sale_date")
            amount = request.form.get("amount", "0").replace(",", ".")
            notes = request.form.get("notes", "").strip() or None
            if sale_date_raw:
                db.session.add(
                    DailySale(
                        store_id=store.id,
                        sale_date=datetime.strptime(sale_date_raw, "%Y-%m-%d").date(),
                        amount=Decimal(amount),
                        notes=notes,
                    )
                )
                db.session.commit()

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


def ensure_database():
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    ensure_database()
    app.run(debug=True, use_reloader=True)

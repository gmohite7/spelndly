import calendar
import os
from datetime import date, datetime

from flask import Flask, abort, flash, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email, insert_expense, get_expense_by_id, update_expense
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)

EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def _months_ago_start(today, n):
    month = today.month - n
    year  = today.year
    while month <= 0:
        month += 12
        year  -= 1
    return date(year, month, 1)


def _resolve_date_filter(args, today):
    preset      = args.get("preset", "all")
    date_from   = date_to = None
    custom_from = custom_to = ""

    if preset == "this_month":
        last_day  = calendar.monthrange(today.year, today.month)[1]
        date_from = today.replace(day=1).strftime("%Y-%m-%d")
        date_to   = today.replace(day=last_day).strftime("%Y-%m-%d")
    elif preset == "3months":
        date_from = _months_ago_start(today, 3).strftime("%Y-%m-%d")
        date_to   = today.strftime("%Y-%m-%d")
    elif preset == "6months":
        date_from = _months_ago_start(today, 6).strftime("%Y-%m-%d")
        date_to   = today.strftime("%Y-%m-%d")
    elif preset == "custom":
        raw_from = args.get("date_from", "").strip()
        raw_to   = args.get("date_to", "").strip()
        try:
            datetime.strptime(raw_from, "%Y-%m-%d")
            datetime.strptime(raw_to,   "%Y-%m-%d")
        except ValueError:
            preset = "all"
        else:
            if raw_from > raw_to:
                flash("Start date must be before end date.")
                preset = "all"
            else:
                date_from   = raw_from
                date_to     = raw_to
                custom_from = raw_from
                custom_to   = raw_to
    else:
        preset = "all"

    return preset, date_from, date_to, custom_from, custom_to

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

with app.app_context():
    init_db()
    seed_db()


def _validate_expense_form(amount_raw, category, expense_date):
    """Returns (error_message, amount) — error is None on success."""
    try:
        amount = float(amount_raw)
        if not (0 < amount < 1_000_000):
            return "Amount must be between ₹0.01 and ₹10,00,000.", None
    except ValueError:
        return "Please enter a valid amount.", None

    if category not in EXPENSE_CATEGORIES:
        return "Please select a valid category.", None

    try:
        parsed = datetime.strptime(expense_date, "%Y-%m-%d")
        if parsed.strftime("%Y-%m-%d") != expense_date:
            raise ValueError("format mismatch")
    except ValueError:
        return "Please enter a valid date (YYYY-MM-DD).", None

    return None, amount


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("landing"))
        return render_template("register.html")

    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    if not name or not email or not password:
        return render_template("register.html", error="All fields are required.")
    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.")
    if password != confirm:
        return render_template("register.html", error="Passwords do not match.")
    if get_user_by_email(email):
        return render_template("register.html", error="An account with that email already exists.")

    create_user(name, email, generate_password_hash(password))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("landing"))
        return render_template("login.html")

    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.")

    session.clear()
    session["user_id"]   = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    uid   = session["user_id"]
    today = date.today()

    preset, date_from, date_to, custom_from, custom_to = _resolve_date_filter(
        request.args, today
    )

    user               = get_user_by_id(uid)
    stats              = get_summary_stats(uid, date_from, date_to)
    recent_expenses    = get_recent_transactions(uid, date_from=date_from, date_to=date_to)
    category_breakdown = get_category_breakdown(uid, date_from, date_to)

    parts    = user["name"].split()
    initials = (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()

    return render_template("profile.html",
        user=user,
        initials=initials,
        member_since=user["member_since"],
        total_spent=stats["total_spent"],
        total_count=stats["transaction_count"],
        top_category=stats["top_category"],
        recent_expenses=recent_expenses,
        category_breakdown=category_breakdown,
        active_preset=preset,
        custom_from=custom_from,
        custom_to=custom_to,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("add_expense.html",
            categories=EXPENSE_CATEGORIES,
            today=date.today().strftime("%Y-%m-%d"),
        )

    amount_raw   = request.form.get("amount", "").strip()
    category     = request.form.get("category", "").strip()
    expense_date = request.form.get("date", "").strip()
    description  = request.form.get("description", "").strip() or None

    error, amount = _validate_expense_form(amount_raw, category, expense_date)

    if error:
        return render_template("add_expense.html",
            categories=EXPENSE_CATEGORIES,
            error=error,
            f_amount=amount_raw,
            f_category=category,
            f_date=expense_date,
            f_description=description,
        )

    insert_expense(session["user_id"], amount, category, expense_date, description)
    flash("Expense added.")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id)
    if expense is None:
        abort(404)
    if expense["user_id"] != session["user_id"]:
        abort(403)

    if request.method == "GET":
        return render_template("edit_expense.html",
            categories=EXPENSE_CATEGORIES,
            expense=expense,
            f_amount=expense["amount"],
            f_category=expense["category"],
            f_date=expense["date"],
            f_description=expense["description"] or "",
        )

    amount_raw   = request.form.get("amount", "").strip()
    category     = request.form.get("category", "").strip()
    expense_date = request.form.get("date", "").strip()
    description  = request.form.get("description", "").strip() or None

    error, amount = _validate_expense_form(amount_raw, category, expense_date)

    if error:
        return render_template("edit_expense.html",
            categories=EXPENSE_CATEGORIES,
            expense=expense,
            error=error,
            f_amount=amount_raw,
            f_category=category,
            f_date=expense_date,
            f_description=description,
        )

    update_expense(id, amount, category, expense_date, description)
    flash("Expense updated.")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5001)

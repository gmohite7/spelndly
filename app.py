import calendar
from datetime import date, datetime

from flask import Flask, flash, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


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
app.secret_key = "dev-secret-key"

with app.app_context():
    init_db()
    seed_db()


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


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)

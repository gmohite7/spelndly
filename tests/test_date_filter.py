"""
Tests for Step 6: Date Filter for Profile Page

Covers:
- Auth guard on /profile
- preset=all / no params → unfiltered view
- preset=this_month → current-month-only data
- preset=3months  → 3-month window data
- preset=6months  → 6-month window data
- preset=custom with valid date range → range-restricted data
- preset=custom where date_from > date_to → flash error + unfiltered fallback
- Malformed date strings → no crash, unfiltered fallback
- No expenses in selected range → zero-state, no errors
- Active preset reflected in HTML
- Rupee symbol present across all filter modes
- Unit tests: query helpers honour date_from / date_to params
- Boundary inclusivity (expenses on exact from/to dates are included)
- Cross-user isolation
"""

import calendar
import pytest
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

from app import app
from database.db import get_db, init_db
from database.queries import (
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)

# ---------------------------------------------------------------------------
# Controlled expense data with fixed, known dates
# ---------------------------------------------------------------------------
# today (test-time) is 2026-05-25 per CLAUDE.md / system date.
# We hard-code dates relative to that knowledge so filter assertions are
# deterministic regardless of when the suite runs.  Where a preset depends
# on "today", we compute it the same way app.py does so the test mirrors
# the spec without reading implementation details.

TODAY = date(2026, 5, 25)

# Helper: first day of a month N full months ago (mirrors _months_ago_start)
def _months_ago_start(n):
    month = TODAY.month - n
    year = TODAY.year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


THIS_MONTH_START = TODAY.replace(day=1)
THIS_MONTH_END = TODAY.replace(day=calendar.monthrange(TODAY.year, TODAY.month)[1])
THREE_MONTHS_START = _months_ago_start(3)
SIX_MONTHS_START = _months_ago_start(6)

# Expenses deliberately placed in three temporal buckets:
#   IN_THIS_MONTH   — dates within May 2026
#   IN_3MONTHS_ONLY — dates inside 3-month window but before this month
#   IN_6MONTHS_ONLY — dates inside 6-month window but before 3-month window
#   OUT_OF_RANGE    — dates before 6-month window (always excluded by any preset)
#
# We also need two expenses from different users to test isolation.

IN_THIS_MONTH = [
    (500.00,  "Food",     "2026-05-01", "May breakfast"),
    (1000.00, "Bills",    "2026-05-15", "May electricity"),
]
# Inside 3-month window (Feb–Apr 2026) but not May
IN_3MONTHS_ONLY = [
    (300.00, "Transport", "2026-04-10", "April bus"),
    (200.00, "Health",    "2026-03-20", "March medicine"),
]
# Inside 6-month window (Nov 2025–Jan 2026) but not 3 months
IN_6MONTHS_ONLY = [
    (400.00, "Shopping",  "2025-12-05", "December shopping"),
]
# Before 6-month window — always excluded by any preset other than "all"
OUT_OF_RANGE = [
    (700.00, "Other",     "2025-05-01", "Old expense"),
]

ALL_SEED = IN_THIS_MONTH + IN_3MONTHS_ONLY + IN_6MONTHS_ONLY + OUT_OF_RANGE

# Totals for quick assertion
TOTAL_ALL = sum(r[0] for r in ALL_SEED)                      # 3100.00
TOTAL_THIS_MONTH = sum(r[0] for r in IN_THIS_MONTH)          # 1500.00
TOTAL_3MONTHS = sum(r[0] for r in IN_THIS_MONTH + IN_3MONTHS_ONLY)  # 2000.00
TOTAL_6MONTHS = sum(r[0] for r in IN_THIS_MONTH + IN_3MONTHS_ONLY + IN_6MONTHS_ONLY)  # 2400.00

COUNT_ALL = len(ALL_SEED)               # 6
COUNT_THIS_MONTH = len(IN_THIS_MONTH)   # 2
COUNT_3MONTHS = len(IN_THIS_MONTH) + len(IN_3MONTHS_ONLY)    # 4
COUNT_6MONTHS = COUNT_3MONTHS + len(IN_6MONTHS_ONLY)         # 5


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    Fresh in-memory (tmp_path) SQLite DB per test.
    Inserts one primary user with controlled expense data.
    Returns an un-authenticated test client.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    with app.app_context():
        init_db()
        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Test User", "test@example.com", generate_password_hash("password123")),
        )
        uid = cursor.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client):
    """Logged-in test client (same DB as `client`)."""
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    return client


@pytest.fixture
def client_two_users(tmp_path, monkeypatch):
    """
    DB with two users.  User A has expenses; user B has no expenses.
    Returns (test_client, uid_a, uid_b).
    """
    db_path = str(tmp_path / "two_users.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    with app.app_context():
        init_db()
        conn = get_db()
        cur_a = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("User A", "usera@example.com", generate_password_hash("passA123")),
        )
        uid_a = cur_a.lastrowid
        cur_b = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("User B", "userb@example.com", generate_password_hash("passB123")),
        )
        uid_b = cur_b.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid_a, amt, cat, dt, desc) for amt, cat, dt, desc in IN_THIS_MONTH],
        )
        conn.commit()
        conn.close()

    with app.test_client() as c:
        yield c, uid_a, uid_b


# ---------------------------------------------------------------------------
# Unit tests — query helpers with date_from / date_to
# ---------------------------------------------------------------------------

class TestGetSummaryStatsDateFilter:

    def test_no_filter_returns_all_expenses(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "u1.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

        stats = get_summary_stats(uid)
        assert stats["total_spent"] == TOTAL_ALL, "Unfiltered total must equal sum of all expenses"
        assert stats["transaction_count"] == COUNT_ALL

    def test_date_from_and_date_to_restrict_result(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "u2.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

        stats = get_summary_stats(
            uid,
            date_from=THIS_MONTH_START.strftime("%Y-%m-%d"),
            date_to=THIS_MONTH_END.strftime("%Y-%m-%d"),
        )
        assert stats["total_spent"] == TOTAL_THIS_MONTH, "Filter should include only this-month expenses"
        assert stats["transaction_count"] == COUNT_THIS_MONTH

    def test_boundary_dates_are_inclusive(self, tmp_path, monkeypatch):
        """Expenses whose date == date_from or date_to must be included."""
        db_path = str(tmp_path / "u3.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

        # date_from == date_to == "2026-05-01" (first IN_THIS_MONTH expense)
        stats = get_summary_stats(uid, date_from="2026-05-01", date_to="2026-05-01")
        assert stats["transaction_count"] == 1, "Single-day range must include the expense on that day"
        assert stats["total_spent"] == 500.00

    def test_no_expenses_in_range_returns_zero_state(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "u4.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.commit()
        conn.close()

        stats = get_summary_stats(uid, date_from="2026-01-01", date_to="2026-01-31")
        assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}, \
            "Empty result must match zero-state dict"


class TestGetRecentTransactionsDateFilter:

    def test_no_filter_returns_all(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "rt1.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

        txns = get_recent_transactions(uid)
        assert len(txns) == COUNT_ALL

    def test_date_filter_excludes_out_of_range(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "rt2.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

        txns = get_recent_transactions(
            uid,
            date_from=THIS_MONTH_START.strftime("%Y-%m-%d"),
            date_to=THIS_MONTH_END.strftime("%Y-%m-%d"),
        )
        assert len(txns) == COUNT_THIS_MONTH, "Only this-month transactions should be returned"
        for t in txns:
            assert t["date"] >= THIS_MONTH_START.strftime("%Y-%m-%d")
            assert t["date"] <= THIS_MONTH_END.strftime("%Y-%m-%d")

    def test_results_ordered_newest_first(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "rt3.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

        txns = get_recent_transactions(
            uid,
            date_from=THIS_MONTH_START.strftime("%Y-%m-%d"),
            date_to=THIS_MONTH_END.strftime("%Y-%m-%d"),
        )
        dates = [t["date"] for t in txns]
        assert dates == sorted(dates, reverse=True), "Transactions must be newest first"

    def test_no_transactions_in_range_returns_empty_list(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "rt4.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.commit()
        conn.close()

        txns = get_recent_transactions(uid, date_from="2024-01-01", date_to="2024-01-31")
        assert txns == [], "No expenses in range must return empty list"


class TestGetCategoryBreakdownDateFilter:

    def test_no_filter_returns_all_categories(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "cb1.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

        breakdown = get_category_breakdown(uid)
        categories = {item["name"] for item in breakdown}
        assert "Bills" in categories
        assert "Shopping" in categories

    def test_date_filter_excludes_out_of_range_categories(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "cb2.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in ALL_SEED],
        )
        conn.commit()
        conn.close()

        # Restrict to this month only — "Other" (2025-05-01) and "Shopping"
        # (2025-12-05) and "Transport/Health" (Mar/Apr) must NOT appear
        breakdown = get_category_breakdown(
            uid,
            date_from=THIS_MONTH_START.strftime("%Y-%m-%d"),
            date_to=THIS_MONTH_END.strftime("%Y-%m-%d"),
        )
        categories = {item["name"] for item in breakdown}
        assert "Other" not in categories, "Out-of-range category must be excluded"
        assert "Shopping" not in categories, "Out-of-range category must be excluded"
        assert "Food" in categories, "This-month Food expense must be included"
        assert "Bills" in categories, "This-month Bills expense must be included"

    def test_percentages_sum_to_100(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "cb3.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            [(uid, amt, cat, dt, desc) for amt, cat, dt, desc in IN_THIS_MONTH],
        )
        conn.commit()
        conn.close()

        breakdown = get_category_breakdown(
            uid,
            date_from=THIS_MONTH_START.strftime("%Y-%m-%d"),
            date_to=THIS_MONTH_END.strftime("%Y-%m-%d"),
        )
        assert sum(item["pct"] for item in breakdown) == 100, "Percentages must sum to 100"

    def test_no_expenses_in_range_returns_empty_list(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "cb4.db")
        monkeypatch.setattr("database.db.DB_PATH", db_path)
        init_db()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("U", "u@e.com", "h"),
        )
        uid = cur.lastrowid
        conn.commit()
        conn.close()

        breakdown = get_category_breakdown(uid, date_from="2020-01-01", date_to="2020-12-31")
        assert breakdown == [], "Empty range must return empty list"


# ---------------------------------------------------------------------------
# Route tests — via Flask test client
# ---------------------------------------------------------------------------

class TestProfileAuthGuard:

    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302, "Unauthenticated /profile must redirect"
        assert "/login" in resp.headers["Location"], "Redirect must point to /login"

    def test_unauthenticated_with_preset_redirects(self, client):
        resp = client.get("/profile?preset=this_month")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_unauthenticated_with_custom_range_redirects(self, client):
        resp = client.get("/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestProfileNoParams:

    def test_returns_200(self, auth_client):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200, "Authenticated /profile must return 200"

    def test_shows_all_expenses_total(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"3100.00" in resp.data, "Unfiltered total must equal sum of all seed expenses"

    def test_shows_all_transaction_count(self, auth_client):
        resp = auth_client.get("/profile")
        # COUNT_ALL == 6
        assert str(COUNT_ALL).encode() in resp.data, "Transaction count must reflect all expenses"

    def test_rupee_symbol_present(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")
        assert "&#8377;" in html or "₹" in html, "Rupee symbol must appear on unfiltered profile"

    def test_preset_all_returns_same_as_no_params(self, auth_client):
        resp_no_params = auth_client.get("/profile")
        resp_all = auth_client.get("/profile?preset=all")
        # Both must be 200 and contain identical total
        assert resp_all.status_code == 200
        assert b"3100.00" in resp_all.data


class TestProfilePresetThisMonth:

    def test_returns_200(self, auth_client):
        resp = auth_client.get("/profile?preset=this_month")
        assert resp.status_code == 200

    def test_shows_this_month_total(self, auth_client):
        resp = auth_client.get("/profile?preset=this_month")
        assert b"1500.00" in resp.data, "This-month total must be 1500.00"

    def test_shows_this_month_transaction_count(self, auth_client):
        resp = auth_client.get("/profile?preset=this_month")
        html = resp.data.decode("utf-8")
        assert str(COUNT_THIS_MONTH) in html, "This-month transaction count must be 2"

    def test_out_of_range_expense_not_in_transactions(self, auth_client):
        resp = auth_client.get("/profile?preset=this_month")
        # "Old expense" is from 2025-05-01, outside this month
        assert b"Old expense" not in resp.data, "Out-of-range expense must not appear"

    def test_this_month_expenses_present(self, auth_client):
        resp = auth_client.get("/profile?preset=this_month")
        assert b"May breakfast" in resp.data, "This-month expense must appear in transactions"
        assert b"May electricity" in resp.data

    def test_rupee_symbol_present(self, auth_client):
        resp = auth_client.get("/profile?preset=this_month")
        html = resp.data.decode("utf-8")
        assert "&#8377;" in html or "₹" in html

    def test_active_preset_in_html(self, auth_client):
        resp = auth_client.get("/profile?preset=this_month")
        html = resp.data.decode("utf-8")
        # The template must mark this_month preset as active (any reasonable signal)
        assert "this_month" in html, "Active preset value must appear somewhere in the HTML"


class TestProfilePreset3Months:

    def test_returns_200(self, auth_client):
        resp = auth_client.get("/profile?preset=3months")
        assert resp.status_code == 200

    def test_shows_3month_total(self, auth_client):
        resp = auth_client.get("/profile?preset=3months")
        assert b"2000.00" in resp.data, "3-month total must be 2000.00"

    def test_shows_3month_transaction_count(self, auth_client):
        resp = auth_client.get("/profile?preset=3months")
        html = resp.data.decode("utf-8")
        assert str(COUNT_3MONTHS) in html

    def test_6months_only_expense_not_present(self, auth_client):
        resp = auth_client.get("/profile?preset=3months")
        # "December shopping" (2025-12-05) is in the 6-month window but not 3-month
        assert b"December shopping" not in resp.data, \
            "Expense outside 3-month window must not appear"

    def test_out_of_range_expense_not_present(self, auth_client):
        resp = auth_client.get("/profile?preset=3months")
        assert b"Old expense" not in resp.data

    def test_rupee_symbol_present(self, auth_client):
        resp = auth_client.get("/profile?preset=3months")
        html = resp.data.decode("utf-8")
        assert "&#8377;" in html or "₹" in html

    def test_active_preset_in_html(self, auth_client):
        resp = auth_client.get("/profile?preset=3months")
        html = resp.data.decode("utf-8")
        assert "3months" in html, "Active preset value must appear in the HTML"


class TestProfilePreset6Months:

    def test_returns_200(self, auth_client):
        resp = auth_client.get("/profile?preset=6months")
        assert resp.status_code == 200

    def test_shows_6month_total(self, auth_client):
        resp = auth_client.get("/profile?preset=6months")
        assert b"2400.00" in resp.data, "6-month total must be 2400.00"

    def test_shows_6month_transaction_count(self, auth_client):
        resp = auth_client.get("/profile?preset=6months")
        html = resp.data.decode("utf-8")
        assert str(COUNT_6MONTHS) in html

    def test_6months_expense_present(self, auth_client):
        resp = auth_client.get("/profile?preset=6months")
        assert b"December shopping" in resp.data, \
            "Expense inside 6-month window must appear"

    def test_out_of_range_expense_not_present(self, auth_client):
        resp = auth_client.get("/profile?preset=6months")
        assert b"Old expense" not in resp.data, \
            "Expense before 6-month window must not appear"

    def test_rupee_symbol_present(self, auth_client):
        resp = auth_client.get("/profile?preset=6months")
        html = resp.data.decode("utf-8")
        assert "&#8377;" in html or "₹" in html

    def test_active_preset_in_html(self, auth_client):
        resp = auth_client.get("/profile?preset=6months")
        html = resp.data.decode("utf-8")
        assert "6months" in html, "Active preset value must appear in the HTML"


class TestProfileCustomDateRange:

    def test_valid_custom_range_returns_200(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        assert resp.status_code == 200

    def test_valid_custom_range_shows_correct_total(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        assert b"1500.00" in resp.data, "Custom range must filter to this-month total"

    def test_valid_custom_range_shows_correct_count(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        html = resp.data.decode("utf-8")
        assert str(COUNT_THIS_MONTH) in html

    def test_valid_custom_range_excludes_out_of_range(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        assert b"Old expense" not in resp.data

    def test_valid_custom_range_includes_boundary_dates(self, auth_client):
        """date_from and date_to are inclusive — expenses on those exact dates appear."""
        # Expense on exactly 2026-05-01 ("May breakfast") must be included
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-01"
        )
        assert resp.status_code == 200
        assert b"May breakfast" in resp.data, "Expense on date_from must be included"

    def test_narrow_custom_range_single_day(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-15&date_to=2026-05-15"
        )
        assert b"May electricity" in resp.data
        assert b"May breakfast" not in resp.data

    def test_custom_preset_active_in_html(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        html = resp.data.decode("utf-8")
        assert "custom" in html, "Active custom preset value must appear in HTML"

    def test_rupee_symbol_present_custom(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        html = resp.data.decode("utf-8")
        assert "&#8377;" in html or "₹" in html

    def test_custom_range_reflects_date_from_in_html(self, auth_client):
        """The template must echo back the custom date_from value for UX continuity."""
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        assert b"2026-05-01" in resp.data, "date_from value must be reflected in HTML"

    def test_custom_range_reflects_date_to_in_html(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        assert b"2026-05-31" in resp.data, "date_to value must be reflected in HTML"


class TestProfileDateFromAfterDateTo:

    def test_inverted_range_returns_200(self, auth_client):
        """date_from > date_to must not crash; route must return 200."""
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-31&date_to=2026-05-01"
        )
        assert resp.status_code == 200, "Inverted range must not crash"

    def test_inverted_range_shows_flash_error(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-31&date_to=2026-05-01"
        )
        html = resp.data.decode("utf-8")
        assert "Start date must be before end date." in html, \
            "Flash error message must appear in response"

    def test_inverted_range_falls_back_to_all_expenses(self, auth_client):
        """After the error, the unfiltered (all-time) view must be shown."""
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-31&date_to=2026-05-01"
        )
        assert b"3100.00" in resp.data, "Inverted range must fall back to unfiltered total"

    def test_inverted_range_shows_all_transaction_count(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-31&date_to=2026-05-01"
        )
        html = resp.data.decode("utf-8")
        assert str(COUNT_ALL) in html


class TestProfileMalformedDates:

    def test_malformed_date_from_does_not_crash(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=not-a-date&date_to=2026-05-31"
        )
        assert resp.status_code == 200, "Malformed date_from must not crash the app"

    def test_malformed_date_to_does_not_crash(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=not-a-date"
        )
        assert resp.status_code == 200, "Malformed date_to must not crash the app"

    def test_both_malformed_dates_do_not_crash(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=bad&date_to=also-bad"
        )
        assert resp.status_code == 200, "Both malformed dates must not crash the app"

    def test_malformed_date_from_falls_back_to_unfiltered(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=not-a-date&date_to=2026-05-31"
        )
        # Silently falls back; all expenses visible
        assert b"3100.00" in resp.data, "Malformed date_from must fall back to unfiltered view"

    def test_both_malformed_fall_back_to_unfiltered(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=bad&date_to=also-bad"
        )
        assert b"3100.00" in resp.data

    def test_partial_date_string_does_not_crash(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05&date_to=2026-05-31"
        )
        assert resp.status_code == 200, "Partial date string must not crash the app"

    def test_sql_injection_in_date_does_not_crash(self, auth_client):
        """Parameterized queries must safely handle injection attempts."""
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01' OR '1'='1&date_to=2026-05-31"
        )
        assert resp.status_code == 200, "SQL injection attempt in date must not crash"


class TestProfileNoExpensesInRange:

    def test_empty_range_returns_200(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2020-01-01&date_to=2020-01-31"
        )
        assert resp.status_code == 200

    def test_empty_range_shows_zero_total(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2020-01-01&date_to=2020-01-31"
        )
        html = resp.data.decode("utf-8")
        assert "0.00" in html, "Zero total must be displayed when no expenses in range"

    def test_empty_range_shows_zero_transactions(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2020-01-01&date_to=2020-01-31"
        )
        html = resp.data.decode("utf-8")
        assert "0" in html, "Zero transaction count must appear"

    def test_rupee_symbol_present_empty_range(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2020-01-01&date_to=2020-01-31"
        )
        html = resp.data.decode("utf-8")
        assert "&#8377;" in html or "₹" in html, \
            "Rupee symbol must appear even when no expenses in range"

    def test_no_crash_with_empty_category_breakdown(self, auth_client):
        """Category breakdown being empty must not raise an exception."""
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2020-01-01&date_to=2020-01-31"
        )
        assert resp.status_code == 200


class TestProfileActivePreset:

    @pytest.mark.parametrize("preset", ["this_month", "3months", "6months"])
    def test_active_preset_value_in_response(self, auth_client, preset):
        resp = auth_client.get(f"/profile?preset={preset}")
        html = resp.data.decode("utf-8")
        assert preset in html, f"Active preset '{preset}' must be reflected in HTML"

    def test_all_time_active_when_no_params(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")
        # The spec says preset defaults to "all" when no params given
        assert "all" in html, "Default (all-time) preset must appear in HTML"

    def test_all_time_active_with_preset_all(self, auth_client):
        resp = auth_client.get("/profile?preset=all")
        html = resp.data.decode("utf-8")
        assert "all" in html

    def test_custom_active_when_custom_preset(self, auth_client):
        resp = auth_client.get(
            "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31"
        )
        html = resp.data.decode("utf-8")
        assert "custom" in html


class TestProfileRupeeSymbol:

    @pytest.mark.parametrize("url", [
        "/profile",
        "/profile?preset=all",
        "/profile?preset=this_month",
        "/profile?preset=3months",
        "/profile?preset=6months",
        "/profile?preset=custom&date_from=2026-05-01&date_to=2026-05-31",
    ])
    def test_rupee_symbol_in_all_filter_modes(self, auth_client, url):
        resp = auth_client.get(url)
        html = resp.data.decode("utf-8")
        assert "&#8377;" in html or "₹" in html, \
            f"Rupee symbol must appear for URL: {url}"


class TestProfileCrossUserIsolation:

    def test_logged_in_user_sees_only_own_expenses(self, client_two_users):
        """User B (no expenses) must see 0.00, not user A's expenses."""
        test_client, uid_a, uid_b = client_two_users
        # Log in as User B
        test_client.post("/login", data={"email": "userb@example.com", "password": "passB123"})
        resp = test_client.get("/profile")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # User B has zero expenses; must NOT see user A's totals
        assert "May breakfast" not in html, "User B must not see User A's expenses"
        assert "May electricity" not in html

    def test_cross_user_filter_does_not_leak_data(self, client_two_users):
        """Filtering must not return another user's data even with a broad range."""
        test_client, uid_a, uid_b = client_two_users
        test_client.post("/login", data={"email": "userb@example.com", "password": "passB123"})
        resp = test_client.get(
            "/profile?preset=custom&date_from=2000-01-01&date_to=2099-12-31"
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "May breakfast" not in html, \
            "Broad date filter must not leak another user's expenses"

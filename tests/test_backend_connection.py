import re
import pytest
from werkzeug.security import generate_password_hash
from app import app
from database.db import get_db, init_db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)

SEED_EXPENSES = [
    (350.00,  "Food",          "2026-05-01", "Lunch at cafe"),
    (120.00,  "Transport",     "2026-05-02", "Auto rickshaw"),
    (1500.00, "Bills",         "2026-05-03", "Electricity bill"),
    (800.00,  "Health",        "2026-05-05", "Pharmacy"),
    (600.00,  "Entertainment", "2026-05-08", "Movie tickets"),
    (2200.00, "Shopping",      "2026-05-10", "Clothes"),
    (450.00,  "Other",         "2026-05-12", "Miscellaneous"),
    (200.00,  "Food",          "2026-05-15", "Dinner"),
]


@pytest.fixture
def client(tmp_path, monkeypatch):
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
        user_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            [(user_id, amt, cat, date, desc) for amt, cat, date, desc in SEED_EXPENSES],
        )
        conn.commit()
        conn.close()

    with app.test_client() as c:
        yield c


# ------------------------------------------------------------------ #
# Unit tests — call query functions directly                          #
# ------------------------------------------------------------------ #

def test_get_user_by_id_returns_correct_fields(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unit.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Jane Doe", "jane@example.com", "hash"),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    result = get_user_by_id(user_id)
    assert result["name"] == "Jane Doe"
    assert result["email"] == "jane@example.com"
    assert re.match(r"[A-Z][a-z]+ \d{4}", result["member_since"])


def test_get_user_by_id_nonexistent_returns_none(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unit2.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    assert get_user_by_id(9999) is None


def test_get_summary_stats_with_expenses(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unit3.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@example.com", "hash"),
    )
    uid = cursor.lastrowid
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(uid, amt, cat, date, desc) for amt, cat, date, desc in SEED_EXPENSES],
    )
    conn.commit()
    conn.close()

    stats = get_summary_stats(uid)
    assert stats["total_spent"] == 6220.00
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Shopping"


def test_get_summary_stats_no_expenses(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unit4.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty User", "empty@example.com", "hash"),
    )
    uid = cursor.lastrowid
    conn.commit()
    conn.close()

    stats = get_summary_stats(uid)
    assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


def test_get_recent_transactions_order_and_fields(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unit5.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@example.com", "hash"),
    )
    uid = cursor.lastrowid
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(uid, amt, cat, date, desc) for amt, cat, date, desc in SEED_EXPENSES],
    )
    conn.commit()
    conn.close()

    txns = get_recent_transactions(uid)
    assert len(txns) == 8
    assert txns[0]["date"] == "2026-05-15"
    assert txns[-1]["date"] == "2026-05-01"
    for t in txns:
        assert "date" in t and "description" in t and "category" in t and "amount" in t


def test_get_recent_transactions_no_expenses(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unit6.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty2", "e2@example.com", "hash"),
    )
    uid = cursor.lastrowid
    conn.commit()
    conn.close()

    assert get_recent_transactions(uid) == []


def test_get_category_breakdown_structure(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unit7.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@example.com", "hash"),
    )
    uid = cursor.lastrowid
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(uid, amt, cat, date, desc) for amt, cat, date, desc in SEED_EXPENSES],
    )
    conn.commit()
    conn.close()

    breakdown = get_category_breakdown(uid)
    assert len(breakdown) == 7
    assert breakdown[0]["name"] == "Shopping"
    assert breakdown[0]["amount"] == 2200.00
    assert sum(item["pct"] for item in breakdown) == 100
    for item in breakdown:
        assert isinstance(item["pct"], int)
        assert "name" in item and "amount" in item and "pct" in item


def test_get_category_breakdown_no_expenses(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unit8.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty3", "e3@example.com", "hash"),
    )
    uid = cursor.lastrowid
    conn.commit()
    conn.close()

    assert get_category_breakdown(uid) == []


# ------------------------------------------------------------------ #
# Route tests — via Flask test client                                 #
# ------------------------------------------------------------------ #

def test_profile_unauthenticated_redirects(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_profile_authenticated_returns_200(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    assert resp.status_code == 200


def test_profile_shows_user_name(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    assert b"Test User" in resp.data


def test_profile_shows_user_email(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    assert b"test@example.com" in resp.data


def test_profile_shows_rupee_symbol(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    html = resp.data.decode("utf-8")
    assert "&#8377;" in html or "₹" in html


def test_profile_total_spent(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    assert b"6220.00" in resp.data


def test_profile_transaction_count(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    assert b"8" in resp.data


def test_profile_top_category(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    assert b"Shopping" in resp.data


def test_profile_transactions_newest_first(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    html = resp.data.decode("utf-8")
    pos_may15 = html.find("2026-05-15")
    pos_may01 = html.find("2026-05-01")
    assert pos_may15 != -1 and pos_may01 != -1
    assert pos_may15 < pos_may01


def test_profile_category_breakdown_all_categories(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/profile")
    for cat in [b"Shopping", b"Bills", b"Health", b"Entertainment", b"Food", b"Other", b"Transport"]:
        assert cat in resp.data

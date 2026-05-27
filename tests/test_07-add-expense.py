"""
Tests for Step 07: Add Expense

Covers:
- Auth guard: unauthenticated GET and POST redirect to /login
- GET happy path: 200, form rendered with amount/category/date/description fields
- GET renders all seven valid category options
- GET pre-fills today's date in the date field
- GET has a cancel/back link pointing to /profile
- POST happy path: valid data saves expense and redirects to /profile (302)
- POST DB side effect: expense row is present with correct field values after save
- POST success: flash message "Expense added" visible after redirect
- POST optional description: submitting without description saves with NULL
- POST validation errors — blank amount, non-numeric amount, zero amount, negative amount
- POST validation errors — blank category, invalid category value
- POST validation errors — blank date, invalid date format
- POST field preservation: entered values echoed back into form on validation failure
- Parametrized: multiple invalid amount values all rejected
- Parametrized: multiple invalid date strings all rejected
- Parametrized: all seven valid categories accepted
- Cross-user isolation: added expense only visible to the user who added it
"""

import pytest
from datetime import date
from werkzeug.security import generate_password_hash

from app import app
from database.db import get_db, init_db

VALID_CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    Fresh per-test SQLite DB (tmp_path).
    Seeds one user.  Returns an unauthenticated test client.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    with app.app_context():
        init_db()
        conn = get_db()
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Test User", "test@example.com", generate_password_hash("password123")),
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
def two_user_client(tmp_path, monkeypatch):
    """
    DB with two independent users (User A and User B).
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
        conn.commit()
        conn.close()

    with app.test_client() as c:
        yield c, uid_a, uid_b


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------

class TestAddExpenseAuthGuard:

    def test_get_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302, "Unauthenticated GET /expenses/add must redirect"
        assert "/login" in resp.headers["Location"], "Redirect target must be /login"

    def test_post_unauthenticated_redirects_to_login(self, client):
        resp = client.post("/expenses/add", data={
            "amount": "100",
            "category": "Food",
            "date": "2026-05-01",
            "description": "Lunch",
        })
        assert resp.status_code == 302, "Unauthenticated POST /expenses/add must redirect"
        assert "/login" in resp.headers["Location"], "Redirect target must be /login"

    def test_get_unauthenticated_does_not_render_form(self, client):
        resp = client.get("/expenses/add", follow_redirects=True)
        assert b"Sign in" in resp.data or b"login" in resp.data.lower(), \
            "Unauthenticated request must end up on the login page"


# ---------------------------------------------------------------------------
# GET /expenses/add — happy path
# ---------------------------------------------------------------------------

class TestAddExpenseGet:

    def test_authenticated_get_returns_200(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200, "Authenticated GET /expenses/add must return 200"

    def test_form_has_amount_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert b"amount" in resp.data, "Form must contain an amount field"

    def test_form_has_category_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert b"category" in resp.data, "Form must contain a category field"

    def test_form_has_date_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert b"date" in resp.data, "Form must contain a date field"

    def test_form_has_description_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert b"description" in resp.data, "Form must contain a description field"

    def test_form_method_is_post(self, auth_client):
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode("utf-8")
        assert 'method="POST"' in html or "method='POST'" in html or \
               'method="post"' in html or "method='post'" in html, \
            "Form must use POST method"

    def test_form_renders_all_valid_categories(self, auth_client):
        resp = auth_client.get("/expenses/add")
        for cat in VALID_CATEGORIES:
            assert cat.encode() in resp.data, \
                f"Category option '{cat}' must appear in the form"

    def test_form_prefills_todays_date(self, auth_client):
        today_str = date.today().strftime("%Y-%m-%d")
        resp = auth_client.get("/expenses/add")
        assert today_str.encode() in resp.data, \
            "Form must pre-fill today's date in the date field"

    def test_form_has_cancel_link_to_profile(self, auth_client):
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode("utf-8")
        assert "/profile" in html, "Form must contain a cancel/back link to /profile"

    def test_page_extends_base_template(self, auth_client):
        """The rendered page should contain common base.html landmarks."""
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode("utf-8")
        # base.html typically wraps all pages — check for a common nav or html structure
        assert "<html" in html or "<!DOCTYPE" in html, \
            "Page must be a full HTML document (extends base.html)"


# ---------------------------------------------------------------------------
# POST /expenses/add — happy path
# ---------------------------------------------------------------------------

class TestAddExpensePostHappyPath:

    def test_valid_submission_redirects_to_profile(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "250.00",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Breakfast",
        })
        assert resp.status_code == 302, "Valid POST must redirect (302)"
        assert "/profile" in resp.headers["Location"], \
            "Redirect after success must point to /profile"

    def test_valid_submission_saves_expense_in_db(self, auth_client, tmp_path, monkeypatch):
        """After a valid POST the expense row must exist in the DB."""
        auth_client.post("/expenses/add", data={
            "amount": "199.50",
            "category": "Transport",
            "date": "2026-06-02",
            "description": "Taxi ride",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE amount = ? AND category = ? AND date = ?",
            (199.50, "Transport", "2026-06-02"),
        ).fetchone()
        conn.close()
        assert row is not None, "Expense must be persisted in the DB after a valid POST"
        assert row["description"] == "Taxi ride", "Description must be saved correctly"

    def test_valid_submission_saves_correct_user_id(self, auth_client):
        auth_client.post("/expenses/add", data={
            "amount": "500",
            "category": "Bills",
            "date": "2026-06-03",
            "description": "Water bill",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT user_id FROM expenses WHERE amount = ? AND date = ?",
            (500.0, "2026-06-03"),
        ).fetchone()
        conn.close()
        assert row is not None, "Expense must exist after valid POST"
        # The user_id must be a positive integer (belongs to our seeded user)
        assert isinstance(row["user_id"], int) and row["user_id"] > 0, \
            "Saved expense must have a valid user_id"

    def test_valid_submission_flash_message_visible_after_redirect(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "75",
            "category": "Health",
            "date": "2026-06-04",
            "description": "Medicine",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Expense added" in resp.data, \
            "Success flash message must appear on the profile page after redirect"

    def test_expense_appears_in_profile_after_save(self, auth_client):
        auth_client.post("/expenses/add", data={
            "amount": "999",
            "category": "Shopping",
            "date": "2026-06-05",
            "description": "New shoes",
        })
        resp = auth_client.get("/profile")
        assert b"New shoes" in resp.data or b"Shopping" in resp.data, \
            "Newly added expense must appear on the profile page"

    def test_valid_submission_without_description_succeeds(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "50",
            "category": "Other",
            "date": "2026-06-06",
            "description": "",
        })
        assert resp.status_code == 302, \
            "Submission without description must succeed and redirect"
        assert "/profile" in resp.headers["Location"]

    def test_description_blank_saves_null_in_db(self, auth_client):
        auth_client.post("/expenses/add", data={
            "amount": "50",
            "category": "Other",
            "date": "2026-06-07",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE amount = ? AND date = ?",
            (50.0, "2026-06-07"),
        ).fetchone()
        conn.close()
        assert row is not None, "Expense without description must still be saved"
        assert row["description"] is None, \
            "Blank description must be stored as NULL in the DB"

    def test_description_whitespace_only_saves_null(self, auth_client):
        """Whitespace-only description must be treated as empty and stored as NULL."""
        auth_client.post("/expenses/add", data={
            "amount": "60",
            "category": "Food",
            "date": "2026-06-08",
            "description": "   ",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE amount = ? AND date = ?",
            (60.0, "2026-06-08"),
        ).fetchone()
        conn.close()
        assert row is not None, "Expense with whitespace-only description must be saved"
        assert row["description"] is None, \
            "Whitespace-only description must be stored as NULL"

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_all_valid_categories_are_accepted(self, auth_client, category):
        resp = auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": category,
            "date": "2026-06-10",
            "description": "",
        })
        assert resp.status_code == 302, \
            f"Category '{category}' must be accepted and redirect"
        assert "/profile" in resp.headers["Location"], \
            f"Successful save with category '{category}' must redirect to /profile"


# ---------------------------------------------------------------------------
# POST /expenses/add — validation errors: amount
# ---------------------------------------------------------------------------

class TestAddExpenseAmountValidation:

    def test_blank_amount_returns_200_with_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Blank amount must re-render form (200)"
        assert b"amount" in resp.data.lower() or b"valid" in resp.data.lower(), \
            "Response must contain an error about the amount"

    def test_blank_amount_does_not_save_to_db(self, auth_client):
        before_count = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Blank amount must not create a new expense record"

    def test_non_numeric_amount_returns_200_with_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Non-numeric amount must re-render form (200)"

    def test_non_numeric_amount_does_not_save_to_db(self, auth_client):
        before_count = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "not-a-number",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Non-numeric amount must not create a new expense record"

    def test_zero_amount_returns_200_with_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Zero amount must re-render form (200)"

    def test_zero_amount_does_not_save_to_db(self, auth_client):
        before_count = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Zero amount must not create a new expense record"

    def test_negative_amount_returns_200_with_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "-50",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Negative amount must re-render form (200)"

    def test_negative_amount_does_not_save_to_db(self, auth_client):
        before_count = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "-100",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Negative amount must not create a new expense record"

    @pytest.mark.parametrize("bad_amount", [
        "",
        "0",
        "-1",
        "-0.01",
        "abc",
        "12abc",
        "--5",
        "1,000",
        "  ",
    ])
    def test_invalid_amounts_all_rejected(self, auth_client, bad_amount):
        resp = auth_client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, \
            f"Amount '{bad_amount}' must be rejected (expected 200, got {resp.status_code})"


# ---------------------------------------------------------------------------
# POST /expenses/add — validation errors: category
# ---------------------------------------------------------------------------

class TestAddExpenseCategoryValidation:

    def test_blank_category_returns_200_with_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Blank category must re-render form (200)"

    def test_blank_category_does_not_save_to_db(self, auth_client):
        before_count = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "",
            "date": "2026-06-01",
            "description": "",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Blank category must not create a new expense record"

    def test_invalid_category_value_returns_200_with_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "Vegetables",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Invalid category must re-render form (200)"

    def test_invalid_category_does_not_save_to_db(self, auth_client):
        before_count = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "NotACategory",
            "date": "2026-06-01",
            "description": "",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Invalid category must not create a new expense record"

    @pytest.mark.parametrize("bad_category", [
        "",
        "food",          # wrong case
        "FOOD",          # all-caps
        "Groceries",
        "travel",
        "unknown",
        "'; DROP TABLE expenses; --",   # SQL injection attempt
    ])
    def test_invalid_categories_all_rejected(self, auth_client, bad_category):
        resp = auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": bad_category,
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, \
            f"Category '{bad_category}' must be rejected (expected 200)"


# ---------------------------------------------------------------------------
# POST /expenses/add — validation errors: date
# ---------------------------------------------------------------------------

class TestAddExpenseDateValidation:

    def test_blank_date_returns_200_with_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "Food",
            "date": "",
            "description": "",
        })
        assert resp.status_code == 200, "Blank date must re-render form (200)"

    def test_blank_date_does_not_save_to_db(self, auth_client):
        before_count = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "Food",
            "date": "",
            "description": "",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Blank date must not create a new expense record"

    def test_invalid_date_returns_200_with_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "Food",
            "date": "not-a-date",
            "description": "",
        })
        assert resp.status_code == 200, "Invalid date must re-render form (200)"

    def test_invalid_date_does_not_save_to_db(self, auth_client):
        before_count = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "Food",
            "date": "not-a-date",
            "description": "",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Invalid date must not create a new expense record"

    @pytest.mark.parametrize("bad_date", [
        "",
        "not-a-date",
        "01/06/2026",        # DD/MM/YYYY — wrong format
        "2026/06/01",        # slashes instead of hyphens
        "2026-13-01",        # month 13 — out of range
        "2026-06-32",        # day 32 — out of range
        "06-01-2026",        # MM-DD-YYYY — wrong format
        "2026-6-1",          # missing leading zeros
        "yesterday",
        "2026",
    ])
    def test_invalid_dates_all_rejected(self, auth_client, bad_date):
        resp = auth_client.post("/expenses/add", data={
            "amount": "100",
            "category": "Food",
            "date": bad_date,
            "description": "",
        })
        assert resp.status_code == 200, \
            f"Date '{bad_date}' must be rejected (expected 200)"


# ---------------------------------------------------------------------------
# POST /expenses/add — field preservation on validation failure
# ---------------------------------------------------------------------------

class TestAddExpenseFieldPreservation:

    def test_amount_preserved_on_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "123.45",
            "category": "Food",
            "date": "not-a-date",     # date error triggers re-render
            "description": "My meal",
        })
        assert resp.status_code == 200
        assert b"123.45" in resp.data, \
            "Previously entered amount must be preserved in form on validation error"

    def test_category_preserved_on_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "0",             # amount error triggers re-render
            "category": "Health",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200
        assert b"Health" in resp.data, \
            "Previously entered category must be preserved in form on validation error"

    def test_date_preserved_on_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "-5",            # amount error triggers re-render
            "category": "Transport",
            "date": "2026-07-15",
            "description": "",
        })
        assert resp.status_code == 200
        assert b"2026-07-15" in resp.data, \
            "Previously entered date must be preserved in form on validation error"

    def test_description_preserved_on_error(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "abc",           # amount error triggers re-render
            "category": "Bills",
            "date": "2026-06-01",
            "description": "Electric bill for June",
        })
        assert resp.status_code == 200
        assert b"Electric bill for June" in resp.data, \
            "Previously entered description must be preserved in form on validation error"

    def test_all_fields_preserved_on_category_error(self, auth_client):
        """When an invalid category is submitted all other fields must be echoed back."""
        resp = auth_client.post("/expenses/add", data={
            "amount": "88.88",
            "category": "InvalidCat",
            "date": "2026-06-20",
            "description": "Some note",
        })
        assert resp.status_code == 200
        assert b"88.88" in resp.data, "Amount must be preserved on category error"
        assert b"2026-06-20" in resp.data, "Date must be preserved on category error"
        assert b"Some note" in resp.data, "Description must be preserved on category error"

    def test_error_message_displayed_on_validation_failure(self, auth_client):
        resp = auth_client.post("/expenses/add", data={
            "amount": "-1",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # The form should contain some error signal — the exact wording can vary
        assert any(word in html.lower() for word in ["error", "invalid", "valid", "zero", "greater"]), \
            "A validation error message must be displayed when amount is negative"


# ---------------------------------------------------------------------------
# POST /expenses/add — DB side-effect accuracy
# ---------------------------------------------------------------------------

class TestAddExpenseDbSideEffects:

    def test_exactly_one_row_added_per_valid_submission(self, auth_client):
        before = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "42",
            "category": "Entertainment",
            "date": "2026-06-11",
            "description": "",
        })
        after = _expense_count()
        assert after - before == 1, "Exactly one expense row must be added per valid POST"

    def test_no_row_added_on_invalid_submission(self, auth_client):
        before = _expense_count()
        auth_client.post("/expenses/add", data={
            "amount": "-99",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        after = _expense_count()
        assert after == before, "No expense row must be added when validation fails"

    def test_saved_amount_is_numeric(self, auth_client):
        auth_client.post("/expenses/add", data={
            "amount": "123.99",
            "category": "Shopping",
            "date": "2026-06-12",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE date = ? AND category = ?",
            ("2026-06-12", "Shopping"),
        ).fetchone()
        conn.close()
        assert row is not None
        assert isinstance(row["amount"], float), \
            "Stored amount must be a floating-point number"
        assert abs(row["amount"] - 123.99) < 0.001, \
            "Stored amount must match the submitted value"

    def test_saved_date_matches_submitted_value(self, auth_client):
        auth_client.post("/expenses/add", data={
            "amount": "77",
            "category": "Other",
            "date": "2026-06-13",
            "description": "Test item",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT date FROM expenses WHERE amount = ? AND description = ?",
            (77.0, "Test item"),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["date"] == "2026-06-13", \
            "Stored date must exactly match the submitted date string"


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------

class TestAddExpenseCrossUserIsolation:

    def test_expense_added_by_user_a_not_visible_to_user_b(self, two_user_client):
        test_client, uid_a, uid_b = two_user_client

        # Log in as User A and add an expense
        test_client.post("/login", data={"email": "usera@example.com", "password": "passA123"})
        test_client.post("/expenses/add", data={
            "amount": "300",
            "category": "Food",
            "date": "2026-06-14",
            "description": "User A only expense",
        })
        test_client.get("/logout")

        # Log in as User B and check profile
        test_client.post("/login", data={"email": "userb@example.com", "password": "passB123"})
        resp = test_client.get("/profile")
        assert resp.status_code == 200
        assert b"User A only expense" not in resp.data, \
            "User B must not see User A's expense on their profile"

    def test_expense_saved_with_correct_owner_user_id(self, two_user_client):
        test_client, uid_a, uid_b = two_user_client

        # Log in as User B and add an expense
        test_client.post("/login", data={"email": "userb@example.com", "password": "passB123"})
        test_client.post("/expenses/add", data={
            "amount": "150",
            "category": "Transport",
            "date": "2026-06-15",
            "description": "User B bus fare",
        })

        conn = get_db()
        row = conn.execute(
            "SELECT user_id FROM expenses WHERE description = ?",
            ("User B bus fare",),
        ).fetchone()
        conn.close()
        assert row is not None, "Expense must be saved"
        assert row["user_id"] == uid_b, \
            "Expense must be associated with the logged-in user's ID, not another user's"


# ---------------------------------------------------------------------------
# Helper — counts total expense rows visible to the DB shared by monkeypatched path
# ---------------------------------------------------------------------------

def _expense_count():
    """Return the total number of expense rows in the current test DB."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    conn.close()
    return count

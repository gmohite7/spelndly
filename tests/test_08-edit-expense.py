"""
Tests for Step 08: Edit Expense

Covers:
- Auth guard: unauthenticated GET and POST to /expenses/<id>/edit redirect to /login
- 404: GET /expenses/9999/edit (non-existent ID) returns 404
- 403: GET /expenses/<id>/edit where expense belongs to a different user returns 403
- 403: POST /expenses/<id>/edit where expense belongs to a different user returns 403
- GET happy path: 200, form rendered with all fields pre-filled (amount, category, date, description)
- GET form structure: method=POST, all 7 categories present, cancel link to /profile
- GET template: full HTML document (extends base.html)
- POST happy path: valid submission updates DB and redirects to /profile (302)
- POST DB side effect: updated values are persisted correctly; no new rows created
- POST success: flash message "Expense updated" visible after redirect
- POST optional description: blank description saves NULL, does not fail
- POST validation errors: blank amount, zero amount, negative amount, non-numeric amount
- POST validation errors: blank category, invalid category value
- POST validation errors: blank date, invalid date format/value
- POST field preservation: submitted (not original) values echoed back on validation failure
- Parametrized: multiple invalid amounts all rejected
- Parametrized: multiple invalid date strings all rejected
- Parametrized: all seven valid categories accepted
- Edit link present on profile page for each expense
"""

import pytest
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
    Fresh per-test SQLite DB (tmp_path/monkeypatch).
    Seeds one user (User A). Returns an unauthenticated test client.
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
            ("User A", "usera@example.com", generate_password_hash("passA123")),
        )
        conn.commit()
        conn.close()

    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client):
    """Logged-in test client (as User A, same DB as `client`)."""
    client.post("/login", data={"email": "usera@example.com", "password": "passA123"})
    return client


@pytest.fixture
def seeded_expense(tmp_path, monkeypatch):
    """
    Fresh DB with two users. User A owns one expense.
    Returns (test_client_logged_in_as_A, expense_id, uid_a, uid_b).
    """
    db_path = str(tmp_path / "seeded.db")
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
        cur_e = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (uid_a, 150.00, "Transport", "2026-01-15", "Original description"),
        )
        expense_id = cur_e.lastrowid
        conn.commit()
        conn.close()

    with app.test_client() as c:
        # Log in as User A by default
        c.post("/login", data={"email": "usera@example.com", "password": "passA123"})
        yield c, expense_id, uid_a, uid_b


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------

class TestEditExpenseAuthGuard:

    def test_get_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/1/edit")
        assert resp.status_code == 302, "Unauthenticated GET /expenses/1/edit must redirect (302)"
        assert "/login" in resp.headers["Location"], "Redirect must point to /login"

    def test_post_unauthenticated_redirects_to_login(self, client):
        resp = client.post("/expenses/1/edit", data={
            "amount": "200",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Lunch",
        })
        assert resp.status_code == 302, "Unauthenticated POST /expenses/1/edit must redirect (302)"
        assert "/login" in resp.headers["Location"], "Redirect must point to /login"

    def test_get_unauthenticated_follow_redirect_shows_login_page(self, client):
        resp = client.get("/expenses/1/edit", follow_redirects=True)
        assert b"Sign in" in resp.data or b"login" in resp.data.lower(), \
            "Following the redirect from an unauthenticated request must show the login page"

    def test_post_unauthenticated_follow_redirect_shows_login_page(self, client):
        resp = client.post("/expenses/1/edit", data={
            "amount": "200",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        }, follow_redirects=True)
        assert b"Sign in" in resp.data or b"login" in resp.data.lower(), \
            "Following the redirect from an unauthenticated POST must show the login page"


# ---------------------------------------------------------------------------
# 404 — non-existent expense
# ---------------------------------------------------------------------------

class TestEditExpense404:

    def test_get_nonexistent_expense_returns_404(self, auth_client):
        resp = auth_client.get("/expenses/9999/edit")
        assert resp.status_code == 404, \
            "GET /expenses/9999/edit (non-existent) must return 404"

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        resp = auth_client.post("/expenses/9999/edit", data={
            "amount": "100",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 404, \
            "POST /expenses/9999/edit (non-existent) must return 404"


# ---------------------------------------------------------------------------
# 403 — ownership check
# ---------------------------------------------------------------------------

class TestEditExpenseOwnership:

    def test_get_other_users_expense_returns_403(self, seeded_expense):
        """User A is logged in; expense belongs to User A so we need a second expense owned by B."""
        test_client, expense_id, uid_a, uid_b = seeded_expense

        # Insert an expense owned by User B
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (uid_b, 99.00, "Food", "2026-02-01", "User B expense"),
        )
        b_expense_id = cur.lastrowid
        conn.commit()
        conn.close()

        # User A is logged in and tries to edit User B's expense
        resp = test_client.get(f"/expenses/{b_expense_id}/edit")
        assert resp.status_code == 403, \
            "Accessing another user's expense via GET must return 403"

    def test_post_other_users_expense_returns_403(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense

        conn = get_db()
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (uid_b, 99.00, "Food", "2026-02-01", "User B expense"),
        )
        b_expense_id = cur.lastrowid
        conn.commit()
        conn.close()

        # User A tries to POST an update to User B's expense
        resp = test_client.post(f"/expenses/{b_expense_id}/edit", data={
            "amount": "500",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 403, \
            "Submitting an update to another user's expense via POST must return 403"

    def test_forbidden_post_does_not_modify_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense

        conn = get_db()
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (uid_b, 77.00, "Bills", "2026-03-01", "B original"),
        )
        b_expense_id = cur.lastrowid
        conn.commit()
        conn.close()

        test_client.post(f"/expenses/{b_expense_id}/edit", data={
            "amount": "999",
            "category": "Shopping",
            "date": "2026-07-01",
            "description": "Tampered",
        })

        conn = get_db()
        row = conn.execute(
            "SELECT amount, description FROM expenses WHERE id = ?", (b_expense_id,)
        ).fetchone()
        conn.close()
        assert row["amount"] == 77.00, "Forbidden POST must not change the amount"
        assert row["description"] == "B original", "Forbidden POST must not change the description"


# ---------------------------------------------------------------------------
# GET /expenses/<id>/edit — happy path
# ---------------------------------------------------------------------------

class TestEditExpenseGetHappyPath:

    def test_authenticated_owner_get_returns_200(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        assert resp.status_code == 200, \
            "Authenticated owner GET /expenses/<id>/edit must return 200"

    def test_form_prefilled_with_existing_amount(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        # The expense was seeded with amount 150.00
        assert b"150" in resp.data, \
            "Form must pre-fill amount with the existing expense amount"

    def test_form_prefilled_with_existing_category(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        assert b"Transport" in resp.data, \
            "Form must pre-fill category with the existing expense category"

    def test_form_prefilled_with_existing_date(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        assert b"2026-01-15" in resp.data, \
            "Form must pre-fill date with the existing expense date"

    def test_form_prefilled_with_existing_description(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        assert b"Original description" in resp.data, \
            "Form must pre-fill description with the existing expense description"

    def test_form_method_is_post(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        html = resp.data.decode("utf-8")
        assert (
            'method="POST"' in html
            or "method='POST'" in html
            or 'method="post"' in html
            or "method='post'" in html
        ), "The edit form must use the POST method"

    def test_form_renders_all_valid_categories(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        for cat in VALID_CATEGORIES:
            assert cat.encode() in resp.data, \
                f"Category option '{cat}' must appear in the edit form"

    def test_form_has_cancel_link_to_profile(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        html = resp.data.decode("utf-8")
        assert "/profile" in html, \
            "Edit form must contain a cancel/back link to /profile"

    def test_page_extends_base_template(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        html = resp.data.decode("utf-8")
        assert "<html" in html or "<!DOCTYPE" in html or "<!doctype" in html.lower(), \
            "Edit expense page must be a full HTML document (extends base.html)"

    def test_form_has_amount_input(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        assert b"amount" in resp.data, "Edit form must contain an amount field"

    def test_form_has_category_field(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        assert b"category" in resp.data, "Edit form must contain a category field"

    def test_form_has_date_field(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        assert b"date" in resp.data, "Edit form must contain a date field"

    def test_form_has_description_field(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get(f"/expenses/{expense_id}/edit")
        assert b"description" in resp.data, "Edit form must contain a description field"


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — happy path
# ---------------------------------------------------------------------------

class TestEditExpensePostHappyPath:

    def test_valid_submission_redirects_to_profile(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "300.00",
            "category": "Food",
            "date": "2026-03-10",
            "description": "Updated lunch",
        })
        assert resp.status_code == 302, "Valid POST must redirect (302)"
        assert "/profile" in resp.headers["Location"], \
            "Redirect after successful update must point to /profile"

    def test_valid_submission_updates_amount_in_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "450.75",
            "category": "Transport",
            "date": "2026-01-15",
            "description": "Original description",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row is not None, "Expense row must still exist after update"
        assert abs(row["amount"] - 450.75) < 0.001, \
            "Amount must be updated to the submitted value"

    def test_valid_submission_updates_category_in_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "150.00",
            "category": "Shopping",
            "date": "2026-01-15",
            "description": "Original description",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["category"] == "Shopping", \
            "Category must be updated to the submitted value"

    def test_valid_submission_updates_date_in_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "150.00",
            "category": "Transport",
            "date": "2026-04-20",
            "description": "Original description",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT date FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["date"] == "2026-04-20", \
            "Date must be updated to the submitted value"

    def test_valid_submission_updates_description_in_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "150.00",
            "category": "Transport",
            "date": "2026-01-15",
            "description": "New description text",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["description"] == "New description text", \
            "Description must be updated to the submitted value"

    def test_valid_submission_does_not_create_new_row(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        before_count = _expense_count()
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "200",
            "category": "Food",
            "date": "2026-05-01",
            "description": "Dinner",
        })
        after_count = _expense_count()
        assert after_count == before_count, \
            "Editing an expense must not create a new DB row"

    def test_valid_submission_flash_message_after_redirect(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "250",
            "category": "Bills",
            "date": "2026-05-10",
            "description": "Electricity",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Expense updated" in resp.data, \
            "Success flash message 'Expense updated' must appear on /profile after redirect"

    def test_updated_values_visible_on_profile_page(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "888",
            "category": "Entertainment",
            "date": "2026-05-20",
            "description": "Cinema trip updated",
        })
        resp = test_client.get("/profile")
        assert resp.status_code == 200
        assert b"Cinema trip updated" in resp.data or b"Entertainment" in resp.data, \
            "Updated expense must appear on the profile page"

    def test_blank_description_saves_null_in_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "150.00",
            "category": "Transport",
            "date": "2026-01-15",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["description"] is None, \
            "Blank description must be stored as NULL after editing"

    def test_blank_description_submission_redirects_to_profile(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "75",
            "category": "Other",
            "date": "2026-02-01",
            "description": "",
        })
        assert resp.status_code == 302, \
            "Submitting without description must succeed and redirect"
        assert "/profile" in resp.headers["Location"]

    def test_whitespace_only_description_saves_null(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "60",
            "category": "Food",
            "date": "2026-01-15",
            "description": "   ",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["description"] is None, \
            "Whitespace-only description must be stored as NULL"

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_all_valid_categories_are_accepted(self, seeded_expense, category):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": category,
            "date": "2026-06-10",
            "description": "",
        })
        assert resp.status_code == 302, \
            f"Category '{category}' must be accepted as valid and redirect"
        assert "/profile" in resp.headers["Location"], \
            f"Successful update with category '{category}' must redirect to /profile"


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — validation errors: amount
# ---------------------------------------------------------------------------

class TestEditExpenseAmountValidation:

    def test_blank_amount_returns_200_with_error(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Blank amount must re-render form (200)"

    def test_blank_amount_shows_error_message(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        html = resp.data.decode("utf-8").lower()
        assert any(w in html for w in ["error", "invalid", "valid", "amount"]), \
            "Blank amount must show a validation error message"

    def test_blank_amount_does_not_update_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Changed",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert abs(row["amount"] - 150.00) < 0.001, \
            "Blank amount validation failure must not update the existing expense amount"

    def test_zero_amount_returns_200(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Zero amount must re-render form (200)"

    def test_zero_amount_does_not_update_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert abs(row["amount"] - 150.00) < 0.001, \
            "Zero amount must not update the existing expense"

    def test_negative_amount_returns_200(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "-50",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Negative amount must re-render form (200)"

    def test_negative_amount_does_not_update_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "-100",
            "category": "Transport",
            "date": "2026-01-15",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert abs(row["amount"] - 150.00) < 0.001, \
            "Negative amount must not update the existing expense"

    def test_non_numeric_amount_returns_200(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Non-numeric amount must re-render form (200)"

    def test_non_numeric_amount_does_not_update_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "twelve",
            "category": "Transport",
            "date": "2026-01-15",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert abs(row["amount"] - 150.00) < 0.001, \
            "Non-numeric amount must not update the existing expense"

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
    def test_invalid_amounts_all_rejected(self, seeded_expense, bad_amount):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, \
            f"Amount '{bad_amount}' must be rejected (expected 200, got {resp.status_code})"


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — validation errors: category
# ---------------------------------------------------------------------------

class TestEditExpenseCategoryValidation:

    def test_blank_category_returns_200(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Blank category must re-render form (200)"

    def test_blank_category_does_not_update_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "",
            "date": "2026-06-01",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["category"] == "Transport", \
            "Blank category must not update the existing expense category"

    def test_invalid_category_returns_200(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "Groceries",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, "Invalid category must re-render form (200)"

    def test_invalid_category_does_not_update_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "NotACategory",
            "date": "2026-01-15",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["category"] == "Transport", \
            "Invalid category must not update the existing expense"

    @pytest.mark.parametrize("bad_category", [
        "",
        "food",          # wrong case
        "FOOD",          # all-caps
        "Groceries",
        "travel",
        "unknown",
        "'; DROP TABLE expenses; --",   # SQL injection attempt
    ])
    def test_invalid_categories_all_rejected(self, seeded_expense, bad_category):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": bad_category,
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, \
            f"Category '{bad_category}' must be rejected (expected 200)"


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — validation errors: date
# ---------------------------------------------------------------------------

class TestEditExpenseDateValidation:

    def test_blank_date_returns_200(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "Food",
            "date": "",
            "description": "",
        })
        assert resp.status_code == 200, "Blank date must re-render form (200)"

    def test_blank_date_does_not_update_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "Food",
            "date": "",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT date FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["date"] == "2026-01-15", \
            "Blank date must not update the existing expense date"

    def test_invalid_date_returns_200(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "Food",
            "date": "not-a-date",
            "description": "",
        })
        assert resp.status_code == 200, "Invalid date must re-render form (200)"

    def test_invalid_date_does_not_update_db(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "Transport",
            "date": "31/12/2026",
            "description": "",
        })
        conn = get_db()
        row = conn.execute(
            "SELECT date FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row["date"] == "2026-01-15", \
            "Invalid date must not update the existing expense"

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
    def test_invalid_dates_all_rejected(self, seeded_expense, bad_date):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "Food",
            "date": bad_date,
            "description": "",
        })
        assert resp.status_code == 200, \
            f"Date '{bad_date}' must be rejected (expected 200)"


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — form field preservation on validation error
# ---------------------------------------------------------------------------

class TestEditExpenseFieldPreservation:

    def test_submitted_amount_preserved_on_date_error(self, seeded_expense):
        """When date is invalid the submitted amount (not the original) must be shown."""
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "999.99",
            "category": "Food",
            "date": "bad-date",
            "description": "Some note",
        })
        assert resp.status_code == 200
        assert b"999.99" in resp.data, \
            "Submitted amount must be preserved in the form on validation failure"

    def test_submitted_category_preserved_on_amount_error(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "0",
            "category": "Health",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200
        assert b"Health" in resp.data, \
            "Submitted category must be preserved in the form on validation failure"

    def test_submitted_date_preserved_on_amount_error(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "-5",
            "category": "Transport",
            "date": "2026-07-22",
            "description": "",
        })
        assert resp.status_code == 200
        assert b"2026-07-22" in resp.data, \
            "Submitted date must be preserved in the form on validation failure"

    def test_submitted_description_preserved_on_amount_error(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "abc",
            "category": "Bills",
            "date": "2026-06-01",
            "description": "My updated note",
        })
        assert resp.status_code == 200
        assert b"My updated note" in resp.data, \
            "Submitted description must be preserved in the form on validation failure"

    def test_submitted_values_not_original_values_on_category_error(self, seeded_expense):
        """On a category error the form must show submitted values, not original DB values."""
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "275.50",
            "category": "BadCategory",
            "date": "2026-08-05",
            "description": "Repopulated text",
        })
        assert resp.status_code == 200
        # Submitted values must appear
        assert b"275.50" in resp.data, "Submitted amount must be echoed back on category error"
        assert b"2026-08-05" in resp.data, "Submitted date must be echoed back on category error"
        assert b"Repopulated text" in resp.data, "Submitted description must be echoed back on category error"
        # Original amount (150) must not replace the submitted value
        # (we cannot assert 150 is absent as it might appear elsewhere, but submitted values must be present)

    def test_error_message_displayed_on_invalid_amount(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "-1",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200
        html = resp.data.decode("utf-8").lower()
        assert any(w in html for w in ["error", "invalid", "valid", "zero", "greater", "amount"]), \
            "A validation error message must be visible when amount is invalid"

    def test_error_message_displayed_on_invalid_category(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "WrongCat",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200
        html = resp.data.decode("utf-8").lower()
        assert any(w in html for w in ["error", "invalid", "valid", "category"]), \
            "A validation error message must be visible when category is invalid"

    def test_error_message_displayed_on_invalid_date(self, seeded_expense):
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "Food",
            "date": "not-a-date",
            "description": "",
        })
        assert resp.status_code == 200
        html = resp.data.decode("utf-8").lower()
        assert any(w in html for w in ["error", "invalid", "valid", "date"]), \
            "A validation error message must be visible when date is invalid"


# ---------------------------------------------------------------------------
# Profile page — edit link presence
# ---------------------------------------------------------------------------

class TestProfileEditLink:

    def test_profile_shows_edit_link_for_own_expense(self, seeded_expense):
        """Each expense on the profile page must have an edit link."""
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get("/profile")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert f"/expenses/{expense_id}/edit" in html, \
            "Profile page must contain an edit link for the user's expense"

    def test_profile_edit_link_text_or_label(self, seeded_expense):
        """The edit link must be identifiable as an edit action."""
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.get("/profile")
        html = resp.data.decode("utf-8").lower()
        assert "edit" in html, \
            "Profile page must contain an 'Edit' label/link for expenses"


# ---------------------------------------------------------------------------
# SQL injection safety
# ---------------------------------------------------------------------------

class TestEditExpenseSqlInjection:

    def test_sql_injection_in_description_is_safe(self, seeded_expense):
        """Parameterized queries must handle SQL injection payloads safely."""
        test_client, expense_id, uid_a, uid_b = seeded_expense
        malicious = "'; DROP TABLE expenses; --"
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "Food",
            "date": "2026-06-01",
            "description": malicious,
        })
        # Should succeed (redirect) since description is optional and saved as-is
        assert resp.status_code == 302, \
            "SQL injection payload in description must not crash the server"

        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row is not None, "Expense row must still exist after SQL injection attempt"
        assert row["description"] == malicious, \
            "SQL injection payload must be stored literally, not executed"

    def test_sql_injection_in_category_is_rejected_by_whitelist(self, seeded_expense):
        """A SQL injection attempt in the category field must be rejected by the category whitelist."""
        test_client, expense_id, uid_a, uid_b = seeded_expense
        resp = test_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "100",
            "category": "'; DROP TABLE expenses; --",
            "date": "2026-06-01",
            "description": "",
        })
        assert resp.status_code == 200, \
            "SQL injection payload in category must be rejected by the whitelist (200)"


# ---------------------------------------------------------------------------
# Helper — counts total expense rows in the current monkeypatched test DB
# ---------------------------------------------------------------------------

def _expense_count():
    """Return the total number of expense rows in the current test DB."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    conn.close()
    return count

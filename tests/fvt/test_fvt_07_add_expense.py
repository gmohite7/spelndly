"""
FVT — Step 07: Add Expense (Remote Environment)

Tests the /expenses/add GET and POST routes against a live deployed environment.
No in-process Flask client, no direct DB access — all assertions are made over HTTP.

Strategy: Dedicated pre-provisioned FVT accounts (Strategy 3).
Two accounts must exist in the target environment before running these tests.
They are never deleted; test data accumulates but is scoped via unique descriptions.

Required env vars:
  BASE_URL             e.g. https://dev.spendly.com
  FVT_USER_EMAIL       primary FVT account (fvt-primary@spendly.test)
  FVT_USER_PASSWORD    primary FVT account password
  FVT_USER2_EMAIL      secondary FVT account (fvt-secondary@spendly.test)
  FVT_USER2_PASSWORD   secondary FVT account password

Run against dev:
  BASE_URL=https://dev.spendly.com \\
  FVT_USER_EMAIL=fvt-primary@spendly.test \\
  FVT_USER_PASSWORD=Secret123 \\
  FVT_USER2_EMAIL=fvt-secondary@spendly.test \\
  FVT_USER2_PASSWORD=Secret456 \\
  pytest tests/fvt/test_fvt_07_add_expense.py -v
"""

import os
import uuid
from datetime import date

import pytest
import requests

VALID_CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"
]

ADD_EXPENSE_PATH = "/expenses/add"
LOGIN_PATH = "/login"
PROFILE_PATH = "/profile"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique_desc(prefix="fvt"):
    """Unique description string — used to fingerprint test-created expenses."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def base_url():
    url = os.environ.get("BASE_URL")
    if not url:
        pytest.skip("BASE_URL not set — skipping remote FVT suite")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def fvt_creds():
    return {
        "email": os.environ["FVT_USER_EMAIL"],
        "password": os.environ["FVT_USER_PASSWORD"],
    }


@pytest.fixture(scope="session")
def fvt_creds_2():
    return {
        "email": os.environ["FVT_USER2_EMAIL"],
        "password": os.environ["FVT_USER2_PASSWORD"],
    }


# ---------------------------------------------------------------------------
# Function-scoped fixtures — fresh session per test
# ---------------------------------------------------------------------------

@pytest.fixture
def anon(base_url):
    """Unauthenticated requests session."""
    s = requests.Session()
    yield s
    s.close()


@pytest.fixture
def auth(base_url, fvt_creds):
    """Authenticated session as the primary FVT user."""
    s = requests.Session()
    resp = s.post(f"{base_url}{LOGIN_PATH}", data=fvt_creds, allow_redirects=True)
    assert resp.status_code == 200, (
        f"FVT login failed for {fvt_creds['email']} — "
        "check credentials and that the account exists in the target environment"
    )
    yield s
    s.close()


@pytest.fixture
def auth_2(base_url, fvt_creds_2):
    """Authenticated session as the secondary FVT user."""
    s = requests.Session()
    resp = s.post(f"{base_url}{LOGIN_PATH}", data=fvt_creds_2, allow_redirects=True)
    assert resp.status_code == 200, (
        f"FVT login failed for {fvt_creds_2['email']} — "
        "check credentials and that the account exists in the target environment"
    )
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:

    def test_get_unauthenticated_redirects_to_login(self, anon, base_url):
        resp = anon.get(f"{base_url}{ADD_EXPENSE_PATH}", allow_redirects=False)
        assert resp.status_code == 302, "Unauthenticated GET must redirect (302)"
        assert "/login" in resp.headers.get("Location", ""), \
            "Redirect target must be /login"

    def test_post_unauthenticated_redirects_to_login(self, anon, base_url):
        resp = anon.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "100",
            "category": "Food",
            "date": "2026-05-27",
            "description": "",
        }, allow_redirects=False)
        assert resp.status_code == 302, "Unauthenticated POST must redirect (302)"
        assert "/login" in resp.headers.get("Location", ""), \
            "Redirect target must be /login"

    def test_get_unauthenticated_lands_on_login_page(self, anon, base_url):
        resp = anon.get(f"{base_url}{ADD_EXPENSE_PATH}", allow_redirects=True)
        assert resp.status_code == 200
        html = resp.text.lower()
        assert "login" in html or "sign in" in html, \
            "Following the redirect must land on the login page"


# ---------------------------------------------------------------------------
# GET /expenses/add — form rendering
# ---------------------------------------------------------------------------

class TestGetAddExpense:

    def test_authenticated_get_returns_200(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        assert resp.status_code == 200, "Authenticated GET must return 200"

    def test_form_contains_amount_field(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        assert "amount" in resp.text.lower(), "Form must contain an amount field"

    def test_form_contains_category_field(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        assert "category" in resp.text.lower(), "Form must contain a category field"

    def test_form_contains_date_field(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        assert "date" in resp.text.lower(), "Form must contain a date field"

    def test_form_contains_description_field(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        assert "description" in resp.text.lower(), "Form must contain a description field"

    def test_form_method_is_post(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        assert 'method="post"' in resp.text.lower() or "method='post'" in resp.text.lower(), \
            "Form must use POST method"

    def test_form_renders_all_valid_categories(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        for cat in VALID_CATEGORIES:
            assert cat in resp.text, f"Category option '{cat}' must appear in the form"

    def test_form_prefills_todays_date(self, auth, base_url):
        today = date.today().strftime("%Y-%m-%d")
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        assert today in resp.text, "Form must pre-fill today's date"

    def test_form_has_cancel_link_to_profile(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        assert "/profile" in resp.text, "Form must contain a cancel/back link to /profile"

    def test_page_is_full_html_document(self, auth, base_url):
        resp = auth.get(f"{base_url}{ADD_EXPENSE_PATH}")
        html = resp.text.lower()
        assert "<html" in html or "<!doctype" in html, \
            "Page must be a full HTML document (extends base.html)"


# ---------------------------------------------------------------------------
# POST /expenses/add — happy path
# ---------------------------------------------------------------------------

class TestPostAddExpenseHappyPath:

    def test_valid_submission_returns_302_to_profile(self, auth, base_url):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "250.00",
            "category": "Food",
            "date": "2026-05-27",
            "description": unique_desc(),
        }, allow_redirects=False)
        assert resp.status_code == 302, "Valid POST must redirect (302)"
        assert "/profile" in resp.headers.get("Location", ""), \
            "Redirect must point to /profile"

    def test_valid_submission_flash_message_visible(self, auth, base_url):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "75.00",
            "category": "Health",
            "date": "2026-05-27",
            "description": unique_desc(),
        }, allow_redirects=True)
        assert resp.status_code == 200
        assert "expense added" in resp.text.lower(), \
            "Success flash message must appear on the profile page after redirect"

    def test_added_expense_appears_on_profile(self, auth, base_url):
        desc = unique_desc("appears-on-profile")
        auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "99.99",
            "category": "Shopping",
            "date": "2026-05-27",
            "description": desc,
        })
        profile = auth.get(f"{base_url}{PROFILE_PATH}")
        assert desc in profile.text, \
            "Newly added expense description must appear on /profile immediately after save"

    def test_valid_submission_without_description_succeeds(self, auth, base_url):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "50.00",
            "category": "Other",
            "date": "2026-05-27",
            "description": "",
        }, allow_redirects=False)
        assert resp.status_code == 302, \
            "Submission with blank description must still succeed and redirect"
        assert "/profile" in resp.headers.get("Location", "")

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_all_valid_categories_accepted(self, auth, base_url, category):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "10.00",
            "category": category,
            "date": "2026-05-27",
            "description": unique_desc(f"cat-{category.lower()}"),
        }, allow_redirects=False)
        assert resp.status_code == 302, \
            f"Category '{category}' must be accepted — expected 302, got {resp.status_code}"
        assert "/profile" in resp.headers.get("Location", "")


# ---------------------------------------------------------------------------
# POST /expenses/add — amount validation
# ---------------------------------------------------------------------------

class TestAmountValidation:

    def _post(self, auth, base_url, amount):
        return auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": amount,
            "category": "Food",
            "date": "2026-05-27",
            "description": "",
        }, allow_redirects=False)

    def test_blank_amount_rejected(self, auth, base_url):
        resp = self._post(auth, base_url, "")
        assert resp.status_code == 200, "Blank amount must re-render form (200)"

    def test_zero_amount_rejected(self, auth, base_url):
        resp = self._post(auth, base_url, "0")
        assert resp.status_code == 200, "Zero amount must re-render form (200)"

    def test_negative_amount_rejected(self, auth, base_url):
        resp = self._post(auth, base_url, "-50")
        assert resp.status_code == 200, "Negative amount must re-render form (200)"

    def test_non_numeric_amount_rejected(self, auth, base_url):
        resp = self._post(auth, base_url, "abc")
        assert resp.status_code == 200, "Non-numeric amount must re-render form (200)"

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
    def test_invalid_amounts_all_rejected(self, auth, base_url, bad_amount):
        resp = self._post(auth, base_url, bad_amount)
        assert resp.status_code == 200, \
            f"Amount '{bad_amount}' must be rejected — expected 200, got {resp.status_code}"


# ---------------------------------------------------------------------------
# POST /expenses/add — category validation
# ---------------------------------------------------------------------------

class TestCategoryValidation:

    def _post(self, auth, base_url, category):
        return auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "100",
            "category": category,
            "date": "2026-05-27",
            "description": "",
        }, allow_redirects=False)

    def test_blank_category_rejected(self, auth, base_url):
        resp = self._post(auth, base_url, "")
        assert resp.status_code == 200, "Blank category must re-render form (200)"

    def test_unknown_category_rejected(self, auth, base_url):
        resp = self._post(auth, base_url, "Groceries")
        assert resp.status_code == 200, "Unknown category must re-render form (200)"

    @pytest.mark.parametrize("bad_category", [
        "",
        "food",
        "FOOD",
        "Groceries",
        "travel",
        "unknown",
    ])
    def test_invalid_categories_all_rejected(self, auth, base_url, bad_category):
        resp = self._post(auth, base_url, bad_category)
        assert resp.status_code == 200, \
            f"Category '{bad_category}' must be rejected — expected 200, got {resp.status_code}"


# ---------------------------------------------------------------------------
# POST /expenses/add — date validation
# ---------------------------------------------------------------------------

class TestDateValidation:

    def _post(self, auth, base_url, expense_date):
        return auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "100",
            "category": "Food",
            "date": expense_date,
            "description": "",
        }, allow_redirects=False)

    def test_blank_date_rejected(self, auth, base_url):
        resp = self._post(auth, base_url, "")
        assert resp.status_code == 200, "Blank date must re-render form (200)"

    def test_malformed_date_rejected(self, auth, base_url):
        resp = self._post(auth, base_url, "not-a-date")
        assert resp.status_code == 200, "Malformed date must re-render form (200)"

    @pytest.mark.parametrize("bad_date", [
        "",
        "not-a-date",
        "01/06/2026",
        "2026/06/01",
        "2026-13-01",
        "2026-06-32",
        "06-01-2026",
        "2026-6-1",
        "yesterday",
        "2026",
    ])
    def test_invalid_dates_all_rejected(self, auth, base_url, bad_date):
        resp = self._post(auth, base_url, bad_date)
        assert resp.status_code == 200, \
            f"Date '{bad_date}' must be rejected — expected 200, got {resp.status_code}"


# ---------------------------------------------------------------------------
# POST /expenses/add — field preservation on validation failure
# ---------------------------------------------------------------------------

class TestFieldPreservation:

    def test_amount_preserved_on_date_error(self, auth, base_url):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "123.45",
            "category": "Food",
            "date": "not-a-date",
            "description": "My meal",
        }, allow_redirects=False)
        assert resp.status_code == 200
        assert "123.45" in resp.text, "Amount must be echoed back into the form on error"

    def test_category_preserved_on_amount_error(self, auth, base_url):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "0",
            "category": "Health",
            "date": "2026-05-27",
            "description": "",
        }, allow_redirects=False)
        assert resp.status_code == 200
        assert "Health" in resp.text, "Category must be echoed back into the form on error"

    def test_date_preserved_on_amount_error(self, auth, base_url):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "-5",
            "category": "Transport",
            "date": "2026-07-15",
            "description": "",
        }, allow_redirects=False)
        assert resp.status_code == 200
        assert "2026-07-15" in resp.text, "Date must be echoed back into the form on error"

    def test_description_preserved_on_amount_error(self, auth, base_url):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "abc",
            "category": "Bills",
            "date": "2026-05-27",
            "description": "Electric bill for June",
        }, allow_redirects=False)
        assert resp.status_code == 200
        assert "Electric bill for June" in resp.text, \
            "Description must be echoed back into the form on error"

    def test_error_message_shown_on_negative_amount(self, auth, base_url):
        resp = auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "-1",
            "category": "Food",
            "date": "2026-05-27",
            "description": "",
        }, allow_redirects=False)
        assert resp.status_code == 200
        html = resp.text.lower()
        assert any(word in html for word in ["error", "invalid", "valid", "zero", "greater"]), \
            "A validation error message must be visible when amount is invalid"


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------

class TestCrossUserIsolation:

    def test_user_a_expense_not_visible_to_user_b(self, auth, auth_2, base_url):
        desc = unique_desc("user-a-only")

        # User A adds an expense
        auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "300",
            "category": "Food",
            "date": "2026-05-27",
            "description": desc,
        })

        # User B checks their own profile — must not see User A's expense
        profile_b = auth_2.get(f"{base_url}{PROFILE_PATH}")
        assert desc not in profile_b.text, \
            "User B must not see User A's expense on their profile page"

    def test_user_b_expense_not_visible_to_user_a(self, auth, auth_2, base_url):
        desc = unique_desc("user-b-only")

        # User B adds an expense
        auth_2.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "150",
            "category": "Transport",
            "date": "2026-05-27",
            "description": desc,
        })

        # User A checks their own profile — must not see User B's expense
        profile_a = auth.get(f"{base_url}{PROFILE_PATH}")
        assert desc not in profile_a.text, \
            "User A must not see User B's expense on their profile page"

    def test_each_user_sees_only_their_own_expenses(self, auth, auth_2, base_url):
        desc_a = unique_desc("mine-a")
        desc_b = unique_desc("mine-b")

        auth.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "200",
            "category": "Shopping",
            "date": "2026-05-27",
            "description": desc_a,
        })
        auth_2.post(f"{base_url}{ADD_EXPENSE_PATH}", data={
            "amount": "200",
            "category": "Shopping",
            "date": "2026-05-27",
            "description": desc_b,
        })

        profile_a = auth.get(f"{base_url}{PROFILE_PATH}")
        profile_b = auth_2.get(f"{base_url}{PROFILE_PATH}")

        assert desc_a in profile_a.text, "User A must see their own expense"
        assert desc_b not in profile_a.text, "User A must not see User B's expense"
        assert desc_b in profile_b.text, "User B must see their own expense"
        assert desc_a not in profile_b.text, "User B must not see User A's expense"

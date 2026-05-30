# Spec: Edit Expense

## Overview
Step 8 replaces the `/expenses/<int:id>/edit` stub with a fully working edit
form. A logged-in user can click an edit link next to any of their own expenses
on the profile page, land on a pre-filled form showing the existing values, make
changes, and save — updating the record in place. This follows the same
validation and form-handling pattern established in Step 7 (Add Expense), and
introduces the first UPDATE path in Spendly. It also requires an ownership
check: users must only be able to edit their own expenses.

## Depends on
- Step 1: Database setup (`expenses` table and `get_db()` exist)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 5: Backend routes for profile page (profile page exists to link from and redirect back to)
- Step 7: Add Expense (`_validate_expense_form` helper and `EXPENSE_CATEGORIES` exist in `app.py`)

## Routes
- `GET /expenses/<int:id>/edit` — render the pre-filled edit form for expense `id` — logged-in only
- `POST /expenses/<int:id>/edit` — validate and update the expense, then redirect — logged-in only

## Database changes
No schema changes. The `expenses` table already has all required columns.

Two new helper functions must be added to `database/db.py`:
- `get_expense_by_id(expense_id)` — returns the row dict for one expense, or `None` if not found
- `update_expense(expense_id, amount, category, date, description)` — issues an `UPDATE` on the matching row

## Templates
- **Create:** `templates/edit_expense.html`
  - Extends `base.html`
  - Contains a single `<form method="POST">` with fields for: amount, category (select), date, description (optional textarea)
  - All fields pre-filled with the existing expense values
  - Displays an inline error message on validation failure
  - Has a cancel link back to `/profile` using `url_for()`
- **Modify:** `templates/profile.html`
  - Add an "Edit" link on each expense row pointing to `url_for("edit_expense", id=expense.id)`

## Files to change
- `app.py` — replace the `edit_expense()` stub with GET + POST handling; reuse `_validate_expense_form`
- `database/db.py` — add `get_expense_by_id()` and `update_expense()` helpers
- `templates/profile.html` — add edit link to each expense row

## Files to create
- `templates/edit_expense.html` — pre-filled expense edit form
- `static/css/edit_expense.css` — page-specific styles (import in template only)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings or string concatenation in SQL
- Passwords hashed with werkzeug (not relevant here, but keep existing imports intact)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Unauthenticated requests to either GET or POST must redirect to `/login`
- Ownership check is mandatory: after fetching the expense, verify `expense["user_id"] == session["user_id"]`; call `abort(403)` if it fails
- If the expense `id` does not exist, call `abort(404)`
- Reuse `_validate_expense_form(amount_raw, category, expense_date)` from `app.py` — do not duplicate the validation logic
- `amount` must be a positive number — reject zero and negative values
- `category` must be one of `EXPENSE_CATEGORIES`
- `date` must be a valid `YYYY-MM-DD` string
- `description` is optional; store as `None` / `NULL` if blank
- On validation failure, re-render the edit form with the error and preserve submitted values
- On success, flash a success message and redirect to `url_for("profile")`
- `update_expense()` in `database/db.py` must close the connection before returning

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for a non-existent expense returns 404
- [ ] Visiting `/expenses/<id>/edit` for an expense owned by another user returns 403
- [ ] Visiting `/expenses/<id>/edit` while logged in renders a form with all fields pre-filled with the existing expense values
- [ ] Submitting the form with valid data updates the expense and redirects to `/profile`
- [ ] The updated values appear correctly on the profile page immediately after saving
- [ ] Submitting with a blank amount shows a validation error and does not update
- [ ] Submitting with a negative or zero amount shows a validation error and does not update
- [ ] Submitting with an invalid date shows a validation error and does not update
- [ ] Submitting with an invalid category shows a validation error and does not update
- [ ] On a validation error, the submitted (not original) values are preserved in the form fields
- [ ] Description is optional — submitting without it saves successfully with a NULL description
- [ ] A cancel/back link on the form navigates to the profile page
- [ ] An "Edit" link is visible for each expense on the profile page

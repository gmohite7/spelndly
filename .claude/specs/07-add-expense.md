# Spec: Add Expense

## Overview
Step 7 replaces the `/expenses/add` stub with a fully working form that lets
a logged-in user record a new expense. The user fills in an amount, category,
date, and optional description, submits the form, and is redirected back to
their profile. This is the first write path in Spendly — every other feature
so far has been read-only — so it establishes the pattern for form handling,
server-side validation, and DB inserts that Steps 8 and 9 will follow.

## Depends on
- Step 1: Database setup (`expenses` table and `get_db()` exist)
- Step 2: Registration (users exist in the DB)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 5: Backend routes for profile page (profile page exists to redirect to after save)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert the new expense, then redirect — logged-in only

## Database changes
No database changes. The `expenses` table already has all required columns:
`id`, `user_id`, `amount`, `category`, `date`, `description`, `created_at`.

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`
  - Contains a single `<form method="POST">` with fields for: amount, category (select), date, description (optional textarea)
  - Displays a flash or inline error message on validation failure
  - Has a cancel link back to `/profile` using `url_for()`

## Files to change
- `app.py` — replace the `add_expense()` stub with GET + POST handling
- `database/db.py` — add an `insert_expense()` helper

## Files to create
- `templates/add_expense.html` — the expense entry form
- `static/css/add_expense.css` — page-specific styles (import in template only)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings or string concatenation in SQL
- Passwords hashed with werkzeug (not relevant here, but keep existing imports intact)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Unauthenticated requests to either GET or POST must redirect to `/login`
- `amount` must be a positive number — reject zero and negative values
- `category` must be one of the allowed values: Food, Transport, Bills, Health, Entertainment, Shopping, Other
- `date` must be a valid `YYYY-MM-DD` string — reject malformed dates
- `description` is optional; store as `None` / `NULL` if blank
- On validation failure, re-render the form with the error and preserve the user's entered values
- On success, flash a success message and redirect to `url_for("profile")`
- `insert_expense()` in `database/db.py` must accept `(user_id, amount, category, date, description)` and close the connection before returning

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in renders a form with fields for amount, category, date, and description
- [ ] Submitting the form with a valid amount, category, and date saves the expense and redirects to `/profile`
- [ ] The new expense appears in the recent transactions list on the profile page immediately after saving
- [ ] Submitting with a blank amount shows a validation error and does not save
- [ ] Submitting with a negative or zero amount shows a validation error and does not save
- [ ] Submitting with an invalid date (e.g. "not-a-date") shows a validation error and does not save
- [ ] Submitting with a blank category (or an invalid category value) shows a validation error and does not save
- [ ] On a validation error, the previously entered values are preserved in the form fields
- [ ] Description is optional — submitting without it saves successfully with a NULL description
- [ ] A cancel/back link on the form navigates to the profile page

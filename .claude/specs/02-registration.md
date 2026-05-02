# Spec: Registration

## Overview

Implement user registration for Spendly. A visitor fills in name, email, password, and confirm password; the app validates the input, hashes the password, persists the new user, and redirects to the login page. On failure the form re-renders with inline error messages. This step converts the static `GET /register` stub into a fully functional form-backed route and establishes the `create_user()` helper that later steps (login, profile) depend on.

## Depends on

Step 1 — Database Setup (`get_db()`, `init_db()`, `users` table must exist).

## Routes

- `GET /register` — render the registration form — public (already exists, no logic change needed)
- `POST /register` — validate form data, create user, redirect to login — public

## Database changes

No new tables or columns. New helper functions in `database/db.py`:

- `create_user(name, email, password_hash)` → inserts a row into `users`, returns the new `id`
- `get_user_by_email(email)` → returns a `sqlite3.Row` or `None`

## Templates

- **Modify:** `templates/register.html` — add `<form method="POST">` with fields: `name`, `email`, `password`, `confirm_password`; display flashed error/success messages; use `url_for('register')` for the action

## Files to change

- `database/db.py` — add `create_user()` and `get_user_by_email()`
- `app.py` — import the two new helpers; add POST handler to the `register` route
- `templates/register.html` — add form markup and flash message display

## Files to create

- `static/css/register.css` — page-specific form styles (imported via `base.html` block or directly in template)

## New dependencies

No new dependencies. Uses:
- `werkzeug.security.generate_password_hash` (already installed)
- `flask.flash`, `flask.redirect`, `flask.request` (already available)

`app.secret_key` must be set for `flash()` to work — add it to `app.py` if not present.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` before inserting
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic (`create_user`, `get_user_by_email`) lives in `database/db.py` only — never inline in routes
- Use `flask.flash()` for error and success messages — never `return "error string"`
- On duplicate email → catch the `sqlite3.IntegrityError`, flash a user-friendly message, re-render the form
- On password mismatch → flash error, re-render form (no DB call needed)
- On success → `redirect(url_for('login'))` with a success flash message
- All internal links use `url_for()` — no hardcoded URLs

## Definition of done

- [ ] `POST /register` with valid unique data creates a new user in the `users` table
- [ ] New user's password is stored as a hash (not plain text) — verify in SQLite directly
- [ ] Submitting a duplicate email re-renders the form with an error message (no crash, no 500)
- [ ] Submitting mismatched passwords re-renders the form with an error message
- [ ] Submitting empty fields re-renders the form with an error message
- [ ] Successful registration redirects to `/login` with a success flash message
- [ ] App starts without errors (`python app.py`)
- [ ] All queries use parameterised SQL (no f-strings in DB calls)

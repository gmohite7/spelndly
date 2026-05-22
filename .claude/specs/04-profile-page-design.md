# Spec: Profile Page Design

## Overview

Implement the `/profile` page for Spendly. A logged-in user visits their profile to see their account details (name, email, member since) and a personalised expense summary: total amount spent, a per-category breakdown, and a list of their most recent expenses. The route is protected — unauthenticated visitors are redirected to `/login`. This step converts the stub `GET /profile` route into a fully rendered page and adds the two DB helpers that future expense-management steps will also rely on.

## Depends on

- Step 01 — Database Setup (`get_db()`, `init_db()`, `users` and `expenses` tables)
- Step 02 — Registration (`create_user()`, users in DB)
- Step 03 — Login and Logout (`session["user_id"]` set on login, `session.clear()` on logout)

## Routes

- `GET /profile` — render the profile page for the currently logged-in user — logged-in only (redirect to `/login` if no session)

## Database changes

No new tables or columns. Two new helper functions in `database/db.py`:

- `get_user_by_id(user_id)` → returns a `sqlite3.Row` for the matching user or `None`
- `get_expenses_by_user(user_id)` → returns a list of `sqlite3.Row` expense records for that user, ordered by `date DESC`

## Templates

- **Create:** `templates/profile.html` — displays user name, email, member-since date, total spent (sum of all expenses), per-category totals, and the 5 most recent expenses
- **Modify:** `templates/base.html` — add a **Profile** nav link (`url_for('profile')`) that is visible only when the user is logged in (i.e. `session.get('user_id')` is truthy)

## Files to change

- `app.py` — implement `profile()` route: guard with login check, call `get_user_by_id()` and `get_expenses_by_user()`, pass data to template
- `database/db.py` — add `get_user_by_id()` and `get_expenses_by_user()`
- `templates/base.html` — conditional Profile nav link

## Files to create

- `templates/profile.html`
- `static/css/profile.css` — page-specific styles (import in the template via a `{% block styles %}` block)

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — use raw SQLite via `get_db()`
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with `werkzeug` (no change needed here, but never expose `password_hash` in the template)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Login guard: if `session.get("user_id")` is falsy, call `redirect(url_for("login"))` — do not use `abort()`
- DB helpers live in `database/db.py` only — route function must not contain raw SQL
- Per-category totals must be computed in Python from the list returned by `get_expenses_by_user()` — do not use a separate aggregation query
- The template must never receive or render `password_hash`
- All internal links use `url_for()` — no hardcoded URLs

## Definition of done

- [ ] `GET /profile` renders the profile page for a logged-in user (name, email, member-since date visible)
- [ ] Total amount spent across all expenses is displayed and matches the DB sum
- [ ] Per-category totals are displayed (only categories with at least one expense appear)
- [ ] The 5 most recent expenses are listed with date, category, amount, and description
- [ ] Visiting `/profile` while logged out redirects to `/login`
- [ ] After login, clicking the Profile nav link navigates to `/profile`
- [ ] The Profile nav link is hidden when the user is not logged in
- [ ] App starts without errors (`python app.py`)
- [ ] All DB queries use parameterised SQL (no f-strings in `db.py`)

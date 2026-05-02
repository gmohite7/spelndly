# Spec: Login and Logout

## Overview
This step adds session-based authentication to Spendly. Users can log in with their email and password, receive a server-side session cookie, and log out to destroy that session. It converts the `/login` stub into a fully working POST handler and replaces the `/logout` stub with a real session-clearing redirect. After this step, the app can distinguish between authenticated and anonymous users, which is a prerequisite for all protected routes (profile, expenses).

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`, `get_user_by_email()`)
- Step 02 — Registration (`create_user()`, hashed passwords in DB)

## Routes
- `GET /login` — render login form — public
- `POST /login` — validate credentials, set session, redirect to `/profile` on success — public
- `GET /logout` — clear session, redirect to `/` — public (no login required to hit it)

## Database changes
No database changes. The `users` table already has `id`, `email`, and `password_hash` from Step 01.

## Templates
- **Modify:** `templates/login.html` — add POST form with email + password fields and an error message slot; form action must use `url_for('login')`

## Files to change
- `app.py` — convert `login()` to handle GET and POST; implement `logout()` to clear session and redirect
- `templates/login.html` — add the login form with error display
- `database/db.py` — no changes needed (get_user_by_email already exists)

## Files to create
No new files.

## New dependencies
No new dependencies. `flask.session` and `werkzeug.security.check_password_hash` are already available.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw SQLite via `get_db()`
- Parameterised queries only — never f-strings in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plaintext
- `app.secret_key` must be set before sessions will work — add a hard-coded dev key in `app.py` (e.g. `app.secret_key = "dev-secret-key"`)
- Store only `user_id` and `user_name` in the session — never store the full row or password hash
- `logout()` must call `session.clear()` before redirecting
- All templates extend `base.html`
- Use CSS variables — never hardcode hex values
- Login errors must not reveal whether the email or the password was wrong (use a generic message like "Invalid email or password.")
- After successful login redirect to `url_for('profile')` — do not hardcode the path

## Definition of done
- [ ] `GET /login` renders the login form with email and password fields
- [ ] Submitting correct credentials sets a session and redirects to `/profile`
- [ ] Submitting wrong email shows "Invalid email or password." without revealing which field is wrong
- [ ] Submitting wrong password shows the same generic error message
- [ ] `GET /logout` clears the session and redirects to `/`
- [ ] After logout, the session no longer contains `user_id`
- [ ] Visiting `/logout` when already logged out does not crash — it redirects cleanly to `/`

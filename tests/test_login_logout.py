import pytest
from werkzeug.security import generate_password_hash
from app import app
from database.db import get_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    with app.app_context():
        from database.db import init_db
        init_db()
        conn = get_db()
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Test User", "test@example.com", generate_password_hash("password123")),
        )
        conn.commit()
        conn.close()

    with app.test_client() as client:
        yield client


def test_login_get_renders_form(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_login_correct_credentials_redirects(client):
    resp = client.post("/login", data={"email": "test@example.com", "password": "password123"})
    assert resp.status_code == 302
    assert resp.headers["Location"] in ("/", "http://localhost/")


def test_login_wrong_password_shows_error(client):
    resp = client.post("/login", data={"email": "test@example.com", "password": "wrongpass"})
    assert resp.status_code == 200
    assert b"Invalid email or password." in resp.data


def test_login_wrong_email_shows_error(client):
    resp = client.post("/login", data={"email": "nobody@example.com", "password": "password123"})
    assert resp.status_code == 200
    assert b"Invalid email or password." in resp.data


def test_login_sets_session(client):
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    with client.session_transaction() as sess:
        assert sess["user_id"] is not None
        assert sess["user_name"] == "Test User"


def test_logout_clears_session(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    with client.session_transaction() as sess:
        assert "user_id" in sess
    client.get("/logout")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_redirects_to_landing(client):
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"] in ("/", "http://localhost/")


def test_logout_when_not_logged_in(client):
    resp = client.get("/logout")
    assert resp.status_code == 302


def test_logged_in_user_redirected_from_login(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/login")
    assert resp.status_code == 302
    assert resp.headers["Location"] in ("/", "http://localhost/")


def test_logged_in_user_redirected_from_register(client):
    client.post("/login", data={"email": "test@example.com", "password": "password123"})
    resp = client.get("/register")
    assert resp.status_code == 302
    assert resp.headers["Location"] in ("/", "http://localhost/")

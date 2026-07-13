import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db


@pytest.fixture()
def app(tmp_path):
    class LocalTestConfig(TestConfig):
        UPLOAD_DIR = str(tmp_path / "uploads")
        JWT_SECRET_KEY = "test-jwt-secret"

    application = create_app(LocalTestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def signup(client, email, nickname="사용자"):
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "StrongPass123!",
            "nickname": nickname,
        },
    )
    assert response.status_code == 201
    return response.get_json()["data"]["user"]


def login(client, email, password="StrongPass123!"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.get_json()["data"]["accessToken"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}

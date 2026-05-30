from fastapi.testclient import TestClient

from app.main import app


def test_protected_endpoint_requires_bearer_token():
    response = TestClient(app).get("/tracks")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing or invalid bearer token."


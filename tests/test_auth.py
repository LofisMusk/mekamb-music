from fastapi.testclient import TestClient

from app.core.auth import configured_api_keys, match_bearer_token
from app.main import app


class FakeSettings:
    def __init__(self, *, api_token: str = "", api_tokens: str = "") -> None:
        self.api_token = api_token
        self.api_tokens = api_tokens


def test_protected_endpoint_requires_bearer_token():
    response = TestClient(app).get("/tracks")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing or invalid bearer token."


def test_configured_api_keys_keeps_legacy_token_as_default_profile():
    keys = configured_api_keys(FakeSettings(api_token="legacy", api_tokens="alice:one,bob=two"))

    assert [(key.id, key.token) for key in keys] == [
        ("default", "legacy"),
        ("alice", "one"),
        ("bob", "two"),
    ]


def test_match_bearer_token_returns_api_key_profile():
    api_key = match_bearer_token(
        FakeSettings(api_tokens="alice:one,bob:two"),
        "Bearer two",
    )

    assert api_key is not None
    assert api_key.id == "bob"

"""Exercise real RSA verification and the GateLog session exchange, offline."""
import json
from datetime import datetime, timezone

import jwt
import pytest
from fastapi.testclient import TestClient


def test_rsa_verifier_is_installed():
    assert "RS256" in jwt.algorithms.get_default_algorithms(), "Install PyJWT[crypto]"


@pytest.mark.parametrize("wrong_audience", [False, True])
def test_firebase_rsa_session_exchange(app, monkeypatch, wrong_audience):
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update(kid="test-key", use="sig", alg="RS256")
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [public_jwk]})
    now = int(datetime.now(timezone.utc).timestamp())
    app.state.settings = None
    with TestClient(app) as client:
        settings = app.state.settings
        settings.firebase_project_id = "test-project"
        settings.firebase_allowed_emails = "operator@example.com"
        settings.demo_open_access = False
        token = jwt.encode({
            "sub": "firebase-user", "iat": now, "exp": now + 300, "auth_time": now,
            "aud": "wrong-project" if wrong_audience else "test-project",
            "iss": "https://securetoken.google.com/test-project",
            "email": "operator@example.com", "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }, private_key, algorithm="RS256", headers={"kid": "test-key"})
        response = client.post("/auth/firebase", json={"id_token": token})
        if wrong_audience:
            assert response.status_code == 401
            assert client.get("/auth/me").status_code == 401
        else:
            assert response.status_code == 200, response.text
            assert "HttpOnly" in response.headers["set-cookie"]
            assert client.get("/auth/me").json()["user"]["email"] == "operator@example.com"

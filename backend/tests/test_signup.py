"""Public self-registration: security-only role, validation, throttle, session."""


def test_signup_creates_security_account_with_session(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as anonymous:
        response = anonymous.post(
            "/auth/signup",
            json={
                "username": "newguard",
                "email": "newguard@test.local",
                "full_name": "New Guard",
                "password": "SelfSignUp-123!",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["user"]["role"] == "security"
        assert body["user"]["auth_provider"] == "local"
        assert "password_hash" not in body["user"]
        assert body["csrf_token"]
        assert "gatelog_session" in response.cookies

        me = anonymous.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["email"] == "newguard@test.local"

        write = anonymous.post(
            "/visitors",
            json={
                "number_plate": "TN09SG0001",
                "visitor_name": "Signup Visitor",
                "host_department": "Testing",
                "person_to_visit": "Gate Desk",
            },
            headers={"X-CSRF-Token": body["csrf_token"]},
        )
        assert write.status_code == 201

        login = anonymous.post(
            "/auth/login",
            json={"identifier": "newguard@test.local", "password": "SelfSignUp-123!"},
        )
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "security"


def test_signup_rejects_duplicates_and_short_passwords(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as anonymous:
        first = anonymous.post(
            "/auth/signup",
            json={
                "username": "guardone",
                "email": "guardone@test.local",
                "full_name": "Guard One",
                "password": "SelfSignUp-123!",
            },
        )
        assert first.status_code == 201

        duplicate_username = anonymous.post(
            "/auth/signup",
            json={
                "username": "guardone",
                "email": "other@test.local",
                "full_name": "Other Person",
                "password": "SelfSignUp-123!",
            },
        )
        assert duplicate_username.status_code == 409

        duplicate_email = anonymous.post(
            "/auth/signup",
            json={
                "username": "othername",
                "email": "guardone@test.local",
                "full_name": "Other Person",
                "password": "SelfSignUp-123!",
            },
        )
        assert duplicate_email.status_code == 409

        short_password = anonymous.post(
            "/auth/signup",
            json={
                "username": "shortpw",
                "email": "shortpw@test.local",
                "full_name": "Short Pw",
                "password": "too-short",
            },
        )
        assert short_password.status_code == 422


def test_signup_cannot_grant_admin_and_is_throttled(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as anonymous:
        created = anonymous.post(
            "/auth/signup",
            json={
                "username": "noroot",
                "email": "noroot@test.local",
                "full_name": "No Root",
                "password": "SelfSignUp-123!",
            },
        )
        assert created.status_code == 201
        assert created.json()["user"]["role"] == "security"
        assert app.state.db.users.find_one({"username": "noroot"})["role"] == "security"

        for index in range(5):
            response = anonymous.post(
                "/auth/signup",
                json={
                    "username": "noroot",
                    "email": f"throttle{index}@test.local",
                    "full_name": "Throttle",
                    "password": "SelfSignUp-123!",
                },
            )
            assert response.status_code in (409, 429)
        throttled = anonymous.post(
            "/auth/signup",
            json={
                "username": "throttled",
                "email": "throttled@test.local",
                "full_name": "Throttled",
                "password": "SelfSignUp-123!",
            },
        )
        assert throttled.status_code == 429

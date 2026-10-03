import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

SAFE_USER_FIELDS = ("_id", "email", "username", "full_name", "role", "department", "active", "created_at", "updated_at", "last_login_at", "auth_provider")


def user_public(user):
    return {("id" if key == "_id" else key): user.get(key) for key in SAFE_USER_FIELDS}


class AuthService:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        if not settings.jwt_secret_key and settings.database_mode != "memory":
            raise RuntimeError("JWT_SECRET_KEY (at least 32 characters) is required for persistent operation")
        self.secret = settings.jwt_secret_key or secrets.token_urlsafe(48)
        self.cloudflare_jwks = None

    def cloudflare_login(self, assertion):
        if not self.settings.cloudflare_access_team_domain or not self.settings.cloudflare_access_audience:
            raise HTTPException(503, "Google sign-in is not configured for this GateLog deployment.")
        if self.cloudflare_jwks is None:
            self.cloudflare_jwks = jwt.PyJWKClient(
                f"https://{self.settings.cloudflare_access_team_domain}/cdn-cgi/access/certs"
            )
        try:
            key = self.cloudflare_jwks.get_signing_key_from_jwt(assertion).key
            issuer = f"https://{self.settings.cloudflare_access_team_domain}"
            claims = jwt.decode(
                assertion, key, algorithms=["RS256"], audience=self.settings.cloudflare_access_audience,
                issuer=issuer, options={"require": ["sub", "email", "exp", "iss", "aud"]},
            )
        except Exception:
            raise HTTPException(401, "Cloudflare Access identity is missing or invalid.") from None
        email = claims.get("email", "").strip().lower()
        subject = claims.get("sub", "")
        if not email or not subject or claims.get("email_verified") is False:
            raise HTTPException(401, "Google must provide a verified email address.")
        now = datetime.now(timezone.utc)
        admin_emails = {item.strip().lower() for item in self.settings.cloudflare_admin_emails.split(",") if item.strip()}
        role = "admin" if email in admin_emails else "security"
        user = self.db.users.find_one({"auth_provider": "cloudflare", "provider_subject": subject})
        if user is None:
            existing = self.db.users.find_one({"email": email})
            if existing:
                self.db.users.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"auth_provider": "cloudflare", "provider_subject": subject}},
                )
                user = self.db.users.find_one({"_id": existing["_id"]})
            else:
                name = claims.get("name") or email.split("@", 1)[0]
                user = {
                    "_id": str(uuid4()), "username": f"google-{hashlib.sha256(subject.encode()).hexdigest()[:16]}",
                    "email": email, "full_name": name[:100], "role": role, "department": None,
                    "active": True, "auth_provider": "cloudflare", "provider_subject": subject,
                    "created_at": now, "updated_at": now,
                }
                try:
                    self.db.users.insert_one(user)
                except DuplicateKeyError:
                    user = self.db.users.find_one({"email": email})
                    if user is None:
                        raise HTTPException(409, "Could not create the Google account. Retry sign-in.") from None
        if not user.get("active", True):
            raise HTTPException(403, "This account is inactive. Contact a GateLog administrator.")
        if email in admin_emails and user.get("role") != "admin":
            self.db.users.update_one({"_id": user["_id"]}, {"$set": {"role": "admin", "updated_at": now}})
            user["role"] = "admin"
        if not user.get("last_login_at") or user["last_login_at"] < now - timedelta(minutes=5):
            self.db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now}})
            user["last_login_at"] = now
        return user

    def authenticate(self, token):
        try:
            claims = jwt.decode(token, self.secret, algorithms=["HS256"], audience="gatelog-api", issuer="gatelog",
                options={"require": ["sub", "jti", "iat", "nbf", "exp", "iss", "aud"]})
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Session expired or invalid. Sign in again.") from None
        session = self.db.sessions.find_one({"_id": claims["jti"], "user_id": claims["sub"],
                                             "expires_at": {"$gt": datetime.now(timezone.utc)}})
        user = self.db.users.find_one({"_id": claims["sub"], "active": True})
        if not session or not user:
            raise HTTPException(401, "Session revoked or account inactive. Sign in again.")
        return user, session

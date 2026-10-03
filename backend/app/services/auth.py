import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

SAFE_USER_FIELDS = (
    "_id", "email", "username", "full_name", "role", "department", "active",
    "created_at", "updated_at", "last_login_at", "auth_provider",
)


def user_public(user):
    return {("id" if key == "_id" else key): user.get(key) for key in SAFE_USER_FIELDS}


class AuthService:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        if not settings.jwt_secret_key and settings.database_mode != "memory":
            raise RuntimeError("JWT_SECRET_KEY (at least 32 characters) is required for persistent operation")
        self.secret = settings.jwt_secret_key or secrets.token_urlsafe(48)

    @staticmethod
    def _emails(value):
        return {item.strip().lower() for item in value.split(",") if item.strip()}

    def google_login(self, access_token):
        if not self.settings.supabase_url or not self.settings.supabase_anon_key:
            raise HTTPException(503, "Google sign-in is not configured for this GateLog deployment.")

        url = f"{self.settings.supabase_url.rstrip('/')}/auth/v1/user"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "apikey": self.settings.supabase_anon_key,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                identity = json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in (400, 401, 403):
                raise HTTPException(401, "Google sign-in expired. Please try again.") from None
            raise HTTPException(503, "Could not verify Google sign-in. Please retry.") from None
        except Exception as error:
            # Keep credentials out of logs; the exception message helps diagnose
            # malformed URLs, DNS failures, TLS problems, and timeouts.
            logger.warning(
                "Supabase user verification connection failed (%s): %s",
                type(error).__name__,
                error,
            )
            raise HTTPException(503, "Could not reach the sign-in service. Please retry.") from None

        email = (identity.get("email") or "").strip().lower()
        subject = identity.get("id") or ""
        confirmed = identity.get("email_confirmed_at") or identity.get("confirmed_at")
        if not email or not subject or not confirmed:
            raise HTTPException(401, "Use a Google account with a verified email address.")

        admin_emails = self._emails(self.settings.supabase_admin_emails)
        allowed_emails = self._emails(self.settings.supabase_allowed_emails) | admin_emails
        allowed_domains = self._emails(self.settings.supabase_allowed_domains)
        domain = email.rsplit("@", 1)[-1]
        if email not in allowed_emails and domain not in allowed_domains:
            if not allowed_emails and not allowed_domains:
                raise HTTPException(503, "The administrator must configure allowed Google accounts first.")
            raise HTTPException(403, "This Google account is not on the GateLog access list.")

        now = datetime.now(timezone.utc)
        user = self.db.users.find_one({"auth_provider": "supabase", "provider_subject": subject})
        if user is None:
            user = self.db.users.find_one({"email": email})
            if user is not None:
                self.db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"auth_provider": "supabase", "provider_subject": subject}},
                )
                user = self.db.users.find_one({"_id": user["_id"]})
            else:
                metadata = identity.get("user_metadata") or {}
                name = metadata.get("full_name") or metadata.get("name") or email.split("@", 1)[0]
                user = {
                    "_id": str(uuid4()),
                    "username": f"google-{hashlib.sha256(subject.encode()).hexdigest()[:16]}",
                    "email": email,
                    "full_name": str(name)[:100],
                    "role": "admin" if email in admin_emails else "security",
                    "department": None,
                    "active": True,
                    "auth_provider": "supabase",
                    "provider_subject": subject,
                    "created_at": now,
                    "updated_at": now,
                }
                try:
                    self.db.users.insert_one(user)
                except DuplicateKeyError:
                    user = self.db.users.find_one({"email": email})
                    if user is None:
                        raise HTTPException(409, "Could not create the GateLog account. Please retry.") from None

        if not user.get("active", True):
            raise HTTPException(403, "This account is inactive. Contact a GateLog administrator.")
        if email in admin_emails and user.get("role") != "admin":
            self.db.users.update_one({"_id": user["_id"]}, {"$set": {"role": "admin", "updated_at": now}})
            user["role"] = "admin"
        self.db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now}})
        user["last_login_at"] = now
        return user

    def create_session(self, user):
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.settings.jwt_access_token_expire_minutes)
        session_id = str(uuid4())
        csrf = secrets.token_urlsafe(32)
        self.db.sessions.insert_one({
            "_id": session_id,
            "user_id": user["_id"],
            "csrf": csrf,
            "created_at": now,
            "expires_at": expires_at,
        })
        token = jwt.encode({
            "sub": user["_id"],
            "jti": session_id,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": "gatelog",
            "aud": "gatelog-api",
        }, self.secret, algorithm="HS256")
        return token, csrf, int((expires_at - now).total_seconds())

    def authenticate(self, token):
        try:
            claims = jwt.decode(
                token, self.secret, algorithms=["HS256"], audience="gatelog-api", issuer="gatelog",
                options={"require": ["sub", "jti", "iat", "nbf", "exp", "iss", "aud"]},
            )
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Session expired or invalid. Sign in again.") from None
        session = self.db.sessions.find_one({
            "_id": claims["jti"],
            "user_id": claims["sub"],
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        })
        user = self.db.users.find_one({"_id": claims["sub"], "active": True})
        if not session or not user:
            raise HTTPException(401, "Session revoked or account inactive. Sign in again.")
        return user, session

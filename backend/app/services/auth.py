import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)
_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))


def password_hash(password):
    return _hasher.hash(password)

SAFE_USER_FIELDS = (
    "_id", "email", "username", "full_name", "role", "department", "active",
    "created_at", "updated_at", "last_login_at", "auth_provider",
)


def user_public(user):
    return {("id" if key == "_id" else key): user.get(key) for key in SAFE_USER_FIELDS}


# Identity handed to every visitor while Settings.demo_open_access is enabled.
# It is a throwaway placeholder, never persisted: the role is "admin" purely so
# the demo can reach every page, and nothing here is trusted for authorisation.
DEMO_USER_ID = "demo-open-access"


def demo_user():
    now = datetime.now(timezone.utc)
    return {
        "_id": DEMO_USER_ID,
        "username": "demo",
        "email": "demo@gatelog.local",
        "full_name": "Demo Operator",
        "role": "admin",
        "department": None,
        "active": True,
        "auth_provider": "demo",
        "created_at": now,
        "updated_at": now,
        "last_login_at": now,
    }


class AuthService:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        if not settings.jwt_secret_key and settings.database_mode != "memory":
            raise RuntimeError("JWT_SECRET_KEY (at least 32 characters) is required for persistent operation")
        self.secret = settings.jwt_secret_key or secrets.token_urlsafe(48)

    def login(self, identifier, password, client_id):
        now = datetime.now(timezone.utc)
        key = hashlib.sha256(f"{client_id}:{identifier.lower()}".encode()).hexdigest()
        attempt = self.db.login_attempts.find_one({"_id": key})
        if attempt and attempt["expires_at"] > now and attempt["count"] >= 10:
            raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
        user = self.db.users.find_one({"$or": [{"username": identifier.lower()}, {"email": identifier.lower()}]})
        try:
            valid = _hasher.verify((user or {}).get("password_hash") or _dummy_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False
        if not valid or not user or not user.get("active"):
            self.db.login_attempts.update_one({"_id": key}, {"$inc": {"count": 1}, "$set": {"expires_at": now + timedelta(minutes=15)}}, upsert=True)
            raise HTTPException(401, "Invalid credentials or inactive account")
        self.db.login_attempts.delete_one({"_id": key})
        self.db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now}})
        token, csrf, max_age = self.create_session(user)
        return {"access_token": token, "csrf_token": csrf, "max_age": max_age, "user": user_public(user)}

    def signup(self, username, email, full_name, password, department, client_id):
        """Self-registration for local GateLog accounts.

        New accounts always receive the security role; administrators are
        created with scripts/create_admin.py or promoted by an existing
        administrator. Never accepts a caller-supplied role.
        """
        now = datetime.now(timezone.utc)
        key = hashlib.sha256(f"signup:{client_id}".encode()).hexdigest()
        attempt = self.db.login_attempts.find_one({"_id": key})
        if attempt and attempt["expires_at"] > now and attempt["count"] >= 10:
            raise HTTPException(429, "Too many sign-up attempts. Try again in an hour.")

        def rejected(detail, status=409):
            self.db.login_attempts.update_one(
                {"_id": key},
                {"$inc": {"count": 1}, "$set": {"expires_at": now + timedelta(hours=1)}},
                upsert=True,
            )
            raise HTTPException(status, detail)

        username = (username or "").strip().lower()
        email = (email or "").strip().lower()
        full_name = (full_name or "").strip()
        if not full_name:
            rejected("Enter your full name", 422)
        if len(password or "") < 12:
            rejected("Choose a GateLog password of at least 12 characters", 422)
        if self.db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
            rejected("Username or email already exists")
        user = {
            "_id": str(uuid4()),
            "username": username,
            "email": email,
            "full_name": full_name[:100],
            "role": "security",
            "department": (department or "").strip() or None,
            "active": True,
            "auth_provider": "local",
            "password_hash": password_hash(password),
            "created_at": now,
            "updated_at": now,
            "last_login_at": now,
        }
        try:
            self.db.users.insert_one(user)
        except DuplicateKeyError:
            rejected("Username or email already exists")
        self.db.login_attempts.delete_one({"_id": key})
        token, csrf, max_age = self.create_session(user)
        return {"access_token": token, "csrf_token": csrf, "max_age": max_age, "user": user_public(user)}

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
                "Supabase user verification connection failed (%s)",
                type(error).__name__,
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

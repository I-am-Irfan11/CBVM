import hashlib
import logging
import secrets
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
    """Legacy password helper retained only for isolated automated tests."""
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
        now = datetime.now(timezone.utc)
        key = hashlib.sha256(f"signup:{client_id}".encode()).hexdigest()
        attempt = self.db.login_attempts.find_one({"_id": key})
        if attempt and attempt["expires_at"] > now and attempt["count"] >= 10:
            raise HTTPException(429, "Too many sign-up attempts. Try again in an hour.")
        username, email, full_name = username.strip().lower(), email.strip().lower(), full_name.strip()
        if not full_name or len(password) < 12:
            raise HTTPException(422, "Enter your name and a test password of at least 12 characters")
        if self.db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
            raise HTTPException(409, "Username or email already exists")
        user = {
            "_id": str(uuid4()), "username": username, "email": email,
            "full_name": full_name[:100], "role": "security",
            "department": (department or "").strip() or None, "active": True,
            "auth_provider": "local", "password_hash": password_hash(password),
            "created_at": now, "updated_at": now, "last_login_at": now,
        }
        try:
            self.db.users.insert_one(user)
        except DuplicateKeyError:
            raise HTTPException(409, "Username or email already exists") from None
        token, csrf, max_age = self.create_session(user)
        return {"access_token": token, "csrf_token": csrf, "max_age": max_age, "user": user_public(user)}

    @staticmethod
    def _emails(value):
        return {item.strip().lower() for item in value.split(",") if item.strip()}

    def firebase_login(self, id_token):
        """Verify a Firebase ID token and map it to a role-controlled GateLog user."""
        project_id = self.settings.firebase_project_id.strip()
        if not project_id:
            raise HTTPException(503, "Firebase sign-in is not configured on the GateLog server.")

        try:
            signing_key = jwt.PyJWKClient(
                "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com",
                cache_keys=True,
                timeout=8,
            ).get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=project_id,
                issuer=f"https://securetoken.google.com/{project_id}",
                options={"require": ["sub", "iat", "exp", "auth_time", "firebase"]},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Your Firebase sign-in expired. Please sign in again.") from None
        except (jwt.InvalidTokenError, jwt.PyJWKClientError, ValueError) as error:
            logger.info("Firebase token verification rejected (%s)", type(error).__name__)
            raise HTTPException(401, "Could not verify your Firebase sign-in. Please retry.") from None
        except Exception as error:
            logger.warning("Firebase verification service unavailable (%s)", type(error).__name__)
            raise HTTPException(503, "Could not reach Firebase to verify sign-in. Please retry.") from None

        uid = str(claims.get("user_id") or claims["sub"])
        email = (claims.get("email") or "").strip().lower()
        if not uid or not email or claims.get("email_verified") is not True:
            raise HTTPException(401, "Verify your email address before using GateLog.")

        admin_emails = self._emails(self.settings.firebase_admin_emails)
        allowed_emails = self._emails(self.settings.firebase_allowed_emails) | admin_emails
        allowed_domains = self._emails(self.settings.firebase_allowed_domains)
        allowed_uids = {item.strip() for item in self.settings.firebase_allowed_uids.split(",") if item.strip()}
        user = self.db.users.find_one({"auth_provider": "firebase", "provider_subject": uid})
        if user is None and email:
            # An administrator can pre-create a role grant before the person
            # finishes Firebase registration; first sign-in links by verified email.
            user = self.db.users.find_one({"email": email})
        configured_allowlist = bool(allowed_emails or allowed_domains or allowed_uids)
        email_domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        allow_all = (
            "*" in allowed_emails
            or "*" in allowed_domains
            or "*" in allowed_uids
        )
        allowed = (
            allow_all
            or email in allowed_emails
            or email_domain in allowed_domains
            or uid in allowed_uids
        )
        if not allowed and not user and not configured_allowlist:
            raise HTTPException(503, "GateLog access is not configured. Add an operator in User access or set a Firebase allowlist.")
        if not allowed and not user:
            raise HTTPException(403, "This account is not on the GateLog access list.")
        if user and not user.get("active", True):
            raise HTTPException(403, "This account is inactive. Contact a GateLog administrator.")

        now = datetime.now(timezone.utc)
        display_email = email
        profile_name = claims.get("name") or email.split("@", 1)[0] or "GateLog user"
        if user is None:
            user = {
                "_id": str(uuid4()),
                "username": f"firebase-{hashlib.sha256(uid.encode()).hexdigest()[:16]}",
                "email": display_email,
                "full_name": str(profile_name)[:100],
                "role": "admin" if email in admin_emails else "security",
                "department": None,
                "active": True,
                "auth_provider": "firebase",
                "provider_subject": uid,
                "created_at": now,
                "updated_at": now,
            }
            try:
                self.db.users.insert_one(user)
            except DuplicateKeyError:
                user = self.db.users.find_one({"auth_provider": "firebase", "provider_subject": uid})
                if user is None:
                    raise HTTPException(409, "Could not create the GateLog account. Please retry.") from None
        else:
            self.db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {"auth_provider": "firebase", "provider_subject": uid, "updated_at": now},
                    "$unset": {"password_hash": ""},
                },
            )
            user = self.db.users.find_one({"_id": user["_id"]})

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

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.auth import current_user
from app.services.auth import user_public

router = APIRouter(prefix="/auth", tags=["Authentication"])


class GoogleSessionRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=8192)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)
    department: str | None = Field(default=None, max_length=100)


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    settings = request.app.state.settings
    if request.headers.get("origin") and request.headers["origin"] not in settings.cors_origins:
        raise HTTPException(403, "Origin is not allowed")
    result = await run_in_threadpool(request.app.state.auth.login, payload.identifier, payload.password,
                                    request.client.host if request.client else "unknown")
    response.set_cookie("gatelog_session", result["access_token"], max_age=result.pop("max_age"),
                        path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/signup", status_code=201)
async def signup(payload: SignupRequest, request: Request, response: Response):
    settings = request.app.state.settings
    if request.headers.get("origin") and request.headers["origin"] not in settings.cors_origins:
        raise HTTPException(403, "Origin is not allowed")
    result = await run_in_threadpool(request.app.state.auth.signup, payload.username, payload.email,
                                     payload.full_name, payload.password, payload.department,
                                     request.client.host if request.client else "unknown")
    response.set_cookie("gatelog_session", result["access_token"], max_age=result.pop("max_age"),
                        path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/config")
def config(request: Request):
    settings = request.app.state.settings
    auth_allowlist = any(
        value.strip()
        for value in (
            settings.supabase_allowed_emails,
            settings.supabase_allowed_domains,
            settings.supabase_admin_emails,
        )
    )
    return {"google_sign_in": bool(settings.supabase_url and settings.supabase_anon_key and auth_allowlist)}


@router.post("/google")
async def google_session(payload: GoogleSessionRequest, request: Request, response: Response):
    origin = request.headers.get("origin")
    if origin and origin not in request.app.state.settings.cors_origins:
        raise HTTPException(403, "Origin is not allowed")
    user = await run_in_threadpool(request.app.state.auth.google_login, payload.access_token)
    token, csrf, max_age = await run_in_threadpool(request.app.state.auth.create_session, user)
    settings = request.app.state.settings
    response.set_cookie(
        "gatelog_session", token, max_age=max_age, path="/", secure=settings.cookie_secure,
        httponly=True, samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": user_public(user), "csrf_token": csrf}


@router.get("/me")
def me(request: Request, response: Response, user=Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    return {"user": user_public(user), "csrf_token": request.state.session["csrf"] if request.state.session else None}


@router.post("/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    request.app.state.db.sessions.delete_one({"_id": request.state.session["_id"]})
    request.app.state.operations.audit("auth.logout", new={"_id": user["_id"]})
    settings = request.app.state.settings
    response.delete_cookie("gatelog_session", path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.auth import current_user
from app.services.auth import user_public

router = APIRouter(prefix="/auth", tags=["Authentication"])


class GoogleSessionRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=8192)


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

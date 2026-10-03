from fastapi import APIRouter, Depends, Request, Response

from app.api.auth import current_user
from app.services.auth import user_public

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/config")
def config(request: Request):
    settings = request.app.state.settings
    return {"google_sign_in": bool(settings.cloudflare_access_team_domain and settings.cloudflare_access_audience)}


@router.get("/me")
def me(request: Request, response: Response, user=Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    return {"user": user_public(user), "csrf_token": request.state.session["csrf"] if request.state.session else None}


@router.post("/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    if request.state.session:
        request.app.state.db.sessions.delete_one({"_id": request.state.session["_id"]})
    request.app.state.operations.audit("auth.logout", new={"_id": user["_id"]})
    response.delete_cookie("gatelog_session", path="/")
    return {"ok": True, "cloudflare": user.get("auth_provider") == "cloudflare"}

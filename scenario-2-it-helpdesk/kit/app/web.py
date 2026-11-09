"""The web app: the sign-in page, the chat page with saved conversations, and the admin page.

Plain HTML, CSS and JavaScript from app/static/, served by FastAPI. The JSON routes live under /web.
The course contract (/health, /api/chat, /api/approve) is in main.py; this file does not change it.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from app import config
from app.web_service import WebError

STATIC = Path(__file__).resolve().parent / "static"
# Only these files can be requested from /static: a fixed list, so nobody can ask for another path.
ASSETS = {"style.css": "text/css", "common.js": "application/javascript",
          "login.js": "application/javascript", "app.js": "application/javascript",
          "admin.js": "application/javascript"}
COOKIE = "nakhla_session"
NO_STORE = {"Cache-Control": "no-store"}

router = APIRouter()


def service(request: Request):
    return request.app.state.web


def user_from_cookie(request: Request) -> dict | None:
    return service(request).accounts.user_for_token(request.cookies.get(COOKIE))


def current_user(request: Request) -> dict:
    user = user_from_cookie(request)
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admins only.")
    return user


async def run(awaitable):
    """Turn the service's own errors into HTTP errors."""
    try:
        return await awaitable
    except WebError as error:
        raise HTTPException(error.status, error.message)


def page(name: str) -> HTMLResponse:
    return HTMLResponse((STATIC / name).read_text(encoding="utf-8"), headers=NO_STORE)


# ---------------------------------------------------------------------- pages
@router.get("/login")
async def login_page(request: Request):
    user = user_from_cookie(request)
    if user:
        return RedirectResponse("/admin" if user["role"] == "admin" else "/", status_code=303)
    return page("login.html")


@router.get("/")
async def chat_page(request: Request):
    user = user_from_cookie(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/admin", status_code=303) if user["role"] == "admin" else page("app.html")


@router.get("/admin")
async def admin_page(request: Request):
    user = user_from_cookie(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return page("admin.html") if user["role"] == "admin" else RedirectResponse("/", status_code=303)


@router.get("/static/{name}")
async def asset(name: str):
    kind = ASSETS.get(name)
    if not kind:
        raise HTTPException(404, "Not found.")
    return Response((STATIC / name).read_bytes(), media_type=kind, headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------------- sign in and out
class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/web/login")
async def login(body: LoginBody, request: Request):
    try:
        token, user = service(request).login(body.email, body.password)
    except WebError as error:
        raise HTTPException(error.status, error.message)
    response = JSONResponse({"user": user, "redirect": "/admin" if user["role"] == "admin" else "/"}, headers=NO_STORE)
    # HttpOnly: the page's JavaScript cannot read the cookie. SameSite=Lax: other sites cannot make the browser use it.
    response.set_cookie(COOKIE, token, max_age=int(config.SESSION_HOURS * 3600), httponly=True,
                        samesite="lax", secure=config.COOKIE_SECURE, path="/")
    return response


@router.post("/web/logout")
async def logout(request: Request):
    service(request).accounts.logout(request.cookies.get(COOKIE))
    response = JSONResponse({"ok": True}, headers=NO_STORE)
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/web/me")
async def me(user: dict = Depends(current_user)):
    return JSONResponse({"user": user}, headers=NO_STORE)


@router.get("/web/demo-accounts")
async def demo_accounts(request: Request):
    users = service(request).accounts.list_users() if config.DEMO_MODE else []
    return JSONResponse({"accounts": users}, headers=NO_STORE)


# ---------------------------------------------------------------------- chats
class ChatBody(BaseModel):
    conversation_id: str | None = None      # empty = start a new chat
    message: str


class ApproveBody(BaseModel):
    conversation_id: str
    action_id: str
    approved: bool


@router.get("/web/conversations")
async def conversations(request: Request, user: dict = Depends(current_user)):
    return JSONResponse({"conversations": service(request).list_conversations(user)}, headers=NO_STORE)


@router.get("/web/conversations/{cid}")
async def conversation(cid: str, request: Request, user: dict = Depends(current_user)):
    try:
        return JSONResponse(service(request).conversation_detail(user, cid), headers=NO_STORE)
    except WebError as error:
        raise HTTPException(error.status, error.message)


@router.post("/web/chat")
async def chat(body: ChatBody, request: Request, user: dict = Depends(current_user)):
    return JSONResponse(await run(service(request).chat(user, body.conversation_id, body.message)), headers=NO_STORE)


@router.post("/web/approve")
async def approve(body: ApproveBody, request: Request, user: dict = Depends(current_user)):
    return JSONResponse(await run(service(request).approve(user, body.conversation_id, body.action_id, body.approved)), headers=NO_STORE)


# ---------------------------------------------------------------------- admin
@router.get("/web/admin/overview")
async def admin_overview(request: Request, user: dict = Depends(admin_user)):
    return JSONResponse(await service(request).admin_overview(), headers=NO_STORE)
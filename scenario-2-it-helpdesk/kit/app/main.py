"""FastAPI entry point. Exactly the contract in CONTRACT.md: /health, /api/chat, /api/approve."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from app import config, kb
from app.accounts import Accounts
from app.agent import Agent
from app.chats import Chats
from app.helpdesk import Helpdesk
from app.llm import LLM
from app.retrieval import Index
from app.store import Store
from app.web import COOKIE, router as web_router
from app.web_service import WebService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("helpdesk.main")


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user: dict | None = None


class ApproveRequest(BaseModel):
    session_id: str
    action_id: str
    approved: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    llm = LLM()
    docs = kb.load_docs()
    index = await Index.build(docs, llm)             # parse, chunk, embed (cached on disk)
    helpdesk = Helpdesk()
    try:
        await helpdesk.start()
    except Exception:  # noqa: BLE001 - the app still starts; tool calls will report the failure honestly
        log.exception("could not start the MCP server; tools will fail until it is reachable")
    store = Store(config.DB_PATH)                    # saved sessions and the approval log
    store.purge_older_than(days=7)
    agent = Agent(index, llm, helpdesk, store)
    app.state.agent = agent
    accounts = Accounts(store.db, session_hours=config.SESSION_HOURS)
    accounts.seed(config.ACCOUNTS)       # the fixed accounts: two employees and the admin
    app.state.web = WebService(agent, store, accounts, Chats(store.db))
    yield
    await helpdesk.stop()
    store.close()


app = FastAPI(title="Nakhla IT Helpdesk Agent", lifespan=lifespan)
app.include_router(web_router)           # sign-in page, chat page, admin page


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# def signed_in_user(http_request: Request) -> dict | None:
#     """Only used when REQUIRE_LOGIN_FOR_API is on: the course tests call the contract without signing in."""
#     if not config.REQUIRE_LOGIN_FOR_API:
#         return None
#     user = app.state.web.accounts.user_for_token(http_request.cookies.get(COOKIE))
#     if not user:
#         raise HTTPException(401, "Please sign in.")
#     return user


# @app.post("/api/chat")
# async def chat(request: ChatRequest, http_request: Request) -> dict:
#     who = signed_in_user(http_request)
#     user = {"email": who["email"]} if who else request.user      # a signed-in identity always wins
#     return await app.state.agent.chat(request.session_id, request.message, user)

def signed_in_user(http_request: Request) -> dict | None:
    user = app.state.web.accounts.user_for_token(http_request.cookies.get(COOKIE))
    if config.REQUIRE_LOGIN_FOR_API and not user:
        raise HTTPException(401, "Please sign in.")
    return user


@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request) -> dict:
    who = signed_in_user(http_request)
    if who:                                              # real session: identity and role come from the database
        user, authed = {"email": who["email"]}, True
    else:                                                # unauthenticated (evals): email only, never a role, never admin
        user, authed = {"email": ((request.user or {}).get("email") or "")}, False
    return await app.state.agent.chat(request.session_id, request.message, user, authenticated=authed)

@app.post("/api/approve")
async def approve(request: ApproveRequest, http_request: Request) -> dict:
    signed_in_user(http_request)
    return await app.state.agent.approve(request.session_id, request.action_id, request.approved)

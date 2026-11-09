"""What the web pages need from the agent, with no web framework in it (so it can be tested alone).

The routes in app/web.py only read the cookie and call these methods. The employee's identity ALWAYS comes
from the sign-in, never from the browser: the email that reaches the agent is the signed-in user's.
"""
from app import config
from app.state import Turn


class WebError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


class WebService:
    def __init__(self, agent, store, accounts, chats) -> None:
        self.agent, self.store, self.accounts, self.chats = agent, store, accounts, chats

    # ------------------------------------------------------------------ sign in
    def login(self, email: str, password: str) -> tuple[str, dict]:
        token, error = self.accounts.login(email, password)
        if error == "locked":
            self.store.log("web", "login_locked", None, email=(email or "")[:80])
            raise WebError(429, "Too many wrong passwords. Please wait a minute and try again.")
        if error:
            self.store.log("web", "login_failed", None, email=(email or "")[:80])
            raise WebError(401, "Wrong email or password.")
        user = self.accounts.user_for_token(token)
        self.store.log("web", "login", None, email=user["email"], role=user["role"])
        return token, user

    # ------------------------------------------------------------------ chats
    def list_conversations(self, user: dict) -> list[dict]:
        return self.chats.list_for(user["email"], all_users=(user["role"] == "admin"))

    def conversation_detail(self, user: dict, cid: str) -> dict:
        if user["role"] == "admin":
            row = self.chats.db.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (cid,)).fetchone()
            conv = {"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]} if row else None
        else:
            conv = self.chats.get(cid, user["email"])
        if not conv:
            raise WebError(404, "That conversation does not exist.")
        return {"conversation": conv, "messages": self.chats.messages(cid), "pending_action": self.agent.pending_action(cid)}

    async def chat(self, user: dict, conversation_id: str | None, message: str) -> dict:
        message = (message or "").strip()
        if not message:
            raise WebError(400, "Write a message first.")
        cid = conversation_id or self.chats.create(user["email"])
        if conversation_id:
            self._own(user, cid)
            # If the agent's saved memory of this chat was cleaned up, rebuild it from what the employee saw.
            self.agent.seed_session(cid, [{"role": m["role"], "content": m["content"]} for m in self.chats.messages(cid)
                                          if not m["meta"].get("decision")])
        # result = await self.agent.chat(cid, message, {"email": user["email"]})     # identity from the sign-in
        result = await self.agent.chat(cid, message, {"email": user["email"]}, authenticated=True)
        self.chats.set_title_if_empty(cid, message)
        self.chats.add_message(cid, "user", message[:config.MAX_MESSAGE_CHARS])
        self.chats.add_message(cid, "assistant", result["reply"], _meta(result))
        return {"conversation": self.chats.get(cid, user["email"]), "message": _assistant(result)}

    async def approve(self, user: dict, conversation_id: str, action_id: str, approved: bool) -> dict:
        self._own(user, conversation_id)
        result = await self.agent.approve(conversation_id, action_id, approved)
        self.chats.add_message(conversation_id, "user", "Approve" if approved else "Reject", {"decision": True})
        self.chats.add_message(conversation_id, "assistant", result["reply"], _meta(result))
        return {"conversation": self.chats.get(conversation_id, user["email"]), "message": _assistant(result)}

    # ------------------------------------------------------------------ admin
    async def admin_overview(self) -> dict:
        """Everything the admin page shows. Tickets come from the helpdesk system, like for the agent."""
        found = await self.agent.helpdesk.call("search_tickets", {"limit": 50}, Turn())
        tickets = found.get("tickets", []) if found.get("ok") else []
        counts = self.chats.counts_by_user()
        return {
            "stats": {"tickets_total": found.get("total_matches", len(tickets)) if found.get("ok") else None,
                      "tickets_open": sum(1 for t in tickets if t.get("status") == "open"),
                      "created_by_agent": self.store.count_events("ticket_created"),
                      "conversations": sum(counts.values()),
                      "logins": self.store.count_events("login")},
            "tickets_error": None if found.get("ok") else "The ticket system did not answer.",
            "tickets": [{k: t.get(k) for k in ("ticket_id", "subject", "requester_email", "priority", "status",
                                               "assigned_team", "category", "created_at")} for t in tickets],
            "audit": self.store.recent_events(50),
            "users": [{**u, "conversations": counts.get(u["email"], 0)} for u in self.accounts.list_users()],
        }

    # ------------------------------------------------------------------ checks
    @staticmethod
    def _employee_only(user: dict) -> None:
        if user["role"] != "employee":
            raise WebError(403, "Only employees can chat. The admin page shows the tickets.")

    def _own(self, user: dict, cid: str) -> None:
        # Admin can open any conversation for support; employees can only open their own.
        if user["role"] == "admin":
            # For admin we look up the conversation without email filter.
            row = self.chats.db.execute("SELECT id FROM conversations WHERE id = ?", (cid,)).fetchone()
            if not row:
                raise WebError(404, "That conversation does not exist.")
        elif not self.chats.get(cid, user["email"]):
            raise WebError(404, "That conversation does not exist.")


def _meta(result: dict) -> dict:
    return {k: result.get(k) for k in ("citations", "pending_action", "result", "tool_calls", "state")}


def _assistant(result: dict) -> dict:
    return {"role": "assistant", "content": result["reply"], "meta": _meta(result)}
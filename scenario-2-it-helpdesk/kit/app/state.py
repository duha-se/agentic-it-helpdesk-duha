"""The two objects that carry state: Session (across turns) and Turn (one request)."""
import asyncio
from dataclasses import dataclass, field

from app import config


@dataclass
class Turn:
    """What happened while answering ONE request: tool calls and token usage."""
    tool_calls: list[dict] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def add_usage(self, prompt: int, completion: int, cost: float | None) -> None:
        self.prompt_tokens += prompt or 0
        self.completion_tokens += completion or 0
        self.cost_usd += cost or 0.0

    def usage(self) -> dict | None:
        if not (self.prompt_tokens or self.completion_tokens):
            return None
        out = {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}
        if self.cost_usd:
            out["cost_usd"] = round(self.cost_usd, 6)
        return out


@dataclass
class Session:
    """Everything the agent remembers about one conversation."""
    id: str
    email: str | None = None            # who is talking (from the request)
    employee: dict | None = None        # their directory record
    lookup_error: str | None = None     # "employee_not_found" or another error code
    recent_tickets: list[dict] = field(default_factory=list)  # long-term memory: their ticket history
    history: list[dict] = field(default_factory=list)         # short-term memory: last messages
    pending: dict | None = None         # the ONE draft waiting for approval
    done: dict[str, dict] = field(default_factory=dict)       # action_id -> result (for double clicks)
    last_cited: list[str] = field(default_factory=list)       # KB ids behind the last answer
    role: str = "employee"            # "employee" | "admin" – from the signed-in account
    state: str = "new"
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one request at a time per session

    def snapshot(self) -> dict:
        """The part of the session that must survive a restart. The directory record and the ticket
        history are not saved: they are read again from the helpdesk system, which is the source of truth."""
        return {"email": self.email, "role": self.role, "history": self.history, "pending": self.pending,
                "done": self.done, "last_cited": self.last_cited, "state": self.state}

    def restore(self, data: dict) -> None:
        self.email = data.get("email")
        self.role  = data.get("role") or "employee"
        self.history = data.get("history") or []
        self.pending = data.get("pending")
        self.done = data.get("done") or {}
        self.last_cited = data.get("last_cited") or []
        self.state = data.get("state") or "new"

    def remember(self, user_text: str, reply: str) -> None:
        self.history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
        self.history = self.history[-config.MAX_HISTORY_MESSAGES:]
"""Settings for the helpdesk agent. Every path, URL and tunable number lives here."""
import os
from pathlib import Path

from dotenv import load_dotenv

# The kit folder is the parent of app/. All relative paths are resolved from it.
KIT_DIR = Path(__file__).resolve().parent.parent

# Values already set in the shell win over .env (override=False is the default).
load_dotenv(KIT_DIR / ".env")

# Knowledge base files (same variable the helpdesk API uses for its seed files).
DATASET_DIR = KIT_DIR / os.getenv("HELPDESK_DATASET_DIR", "dataset")
KB_DIR = DATASET_DIR / "knowledge_base"

# Embeddings are cached here so a restart does not pay for them again.
CACHE_DIR = KIT_DIR / ".cache"

# LLM and embeddings, both through OpenRouter.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = os.getenv("MODEL", "openai/gpt-4.1-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
# The easy roles (triage and the answer check) may use a smaller, faster model. Empty = same as MODEL.
FAST_MODEL = os.getenv("FAST_MODEL") or MODEL
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "40"))

# The simulated helpdesk system. The MCP server reads the same variables.
HELPDESK_API_URL = os.getenv("HELPDESK_API_URL", "http://localhost:8102").rstrip("/")
HELPDESK_API_KEY = os.getenv("HELPDESK_API_KEY", "dev-key-change-me")
TOOL_TIMEOUT_S = float(os.getenv("TOOL_TIMEOUT_S", "30"))

# SQLite file with the saved sessions and the approval log (created on first start).
DB_PATH = Path(os.getenv("AGENT_DB_PATH") or KIT_DIR / "data" / "agent.db")

# --- Web app: sign-in, saved chats, admin page --------------------------------------------------------
def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


DEMO_MODE = _flag("DEMO_MODE", True)                   # show the demo account buttons on the login page
SESSION_HOURS = float(os.getenv("SESSION_HOURS", "12"))
COOKIE_SECURE = _flag("COOKIE_SECURE", False)          # set true when the site is served over https
# /api/chat and /api/approve stay open by default: the course tests call them without signing in.
REQUIRE_LOGIN_FOR_API = _flag("REQUIRE_LOGIN_FOR_API", False)
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "palm-2026")          # change both in .env
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin-palm-2026")
# The fixed accounts: two employees (they exist in the directory, so the agent knows their department) and the admin.
ACCOUNTS = [
    {"email": "sara.mikhail@nakhla.example", "name": "Sara Mikhail", "role": "employee", "password": DEMO_PASSWORD},
    {"email": "ahmad.saba@nakhla.example", "name": "Ahmad Saba", "role": "employee", "password": DEMO_PASSWORD},
    {"email": "admin@nakhla.example", "name": "IT Admin", "role": "admin", "password": ADMIN_PASSWORD},
]

# Chunking: sections longer than this are split at paragraph breaks.
MAX_CHUNK_CHARS = 1800

# Only documents with these statuses are searchable. "draft" (KB-018) and
# "deprecated" (KB-001, KB-005) are never shown to the model as instructions.
SEARCHABLE_STATUSES = {"current"}

# Retrieval: how many chunks the answer may use, and the score below which we
# say "the knowledge base has no answer" instead of guessing.
TOP_K = 5
MIN_EVIDENCE_SCORE = 0.35

# One message longer than this is cut before any model sees it (cost, latency, and nobody needs more).
MAX_MESSAGE_CHARS = 4000

# How many chat messages (user + assistant) are kept as session memory.
MAX_HISTORY_MESSAGES = 10

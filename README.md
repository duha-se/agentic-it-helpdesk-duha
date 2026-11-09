# Nakhla IT Helpdesk Agent

> **Brief 2 · Agentic AI Bootcamp · Jerusalem High-Tech Foundry × COMCEC**

<!-- Record a 10–20 s GIF of the happy path (Sara → VPN → Approve) and save it as docs/demo.gif, then uncomment:
![demo](docs/demo.gif)
-->

An IT support agent for Nakhla Systems (400 employees, fictional). It answers from 20 authoritative knowledge-base documents with cited sources, says "this is not documented" instead of guessing, and writes a helpdesk ticket only after the employee approves the exact draft.

▶ ([Demo video](`<https://drive.google.com/file/d/1qH5YniuqhN7Vw9HcZci_iRqdW7lz-5-x/view?usp=sharing>`)) `<https://drive.google.com/file/d/1qH5YniuqhN7Vw9HcZci_iRqdW7lz-5-x/view?usp=sharing>` &nbsp;·&nbsp; <br>
🧪 **Eval pass rate:** `<10/10 sample · 20/20 our cases>` &nbsp;·&nbsp; ⏱ **Avg turn:** `<2.2 s>` &nbsp;·&nbsp; 🧰 **Stack:** Python · FastAPI · MCP · OpenRouter

---

## What it does

- Answers with numbered steps, each tied to a knowledge-base article (`[KB-002]`), shown in a sources panel.
- Applies department and security rules **in code** (not just in the prompt): Finance VPN → Security Operations, Contractors → VDI portal (no VPN ticket), Executive Office → always P1.
- Checks the live status page first: an active incident gives the workaround and blocks a duplicate ticket.
- Says **"not documented"** when no current article covers the question — never invents steps or ticket ids.
- Shows the employee's own ticket history (read from the helpdesk system) and answers status questions about their own tickets.
- **Asks before it acts:** every ticket is a draft first; nothing is written until the employee presses Approve.
- Multi-user web UI: sign-in page, saved chat history, admin dashboard. RBAC: employees see only their own tickets; the admin can query all tickets and read all chats.

---

## Architecture

```
Employee → /login (port 8000)
              │
         FastAPI app (port 8000)
         ├── Triage       (model)   – reads the message, extracts service / error codes / intent
         ├── Rules        (code)    – department routing, known incident, priority, category
         ├── Retriever    (code)    – embeddings + keywords + precedence over 76 KB chunks
         ├── Resolver     (model)   – grounded answer or NOT_DOCUMENTED
         ├── Verifier     (code + model) – every URL/code/version must appear in sources
         ├── Ticket writer(model)   – draft text only; code fills the metadata
         └── Approval gate(code)   – create_ticket over MCP, only after POST /api/approve
              │
         MCP server (stdio) ── Helpdesk API (port 8102, simulated)
              │
         OpenRouter (gpt-4.1-mini · text-embedding-3-small)
```

| Component | Real / Simulated |
|---|---|
| LLM (`openai/gpt-4.1-mini`) via OpenRouter | **Real** |
| Embeddings (`openai/text-embedding-3-small`) | **Real** (cached after first run) |
| Helpdesk system (directory, status page, tickets) | **Simulated** – REST + MCP, from the kit |
| Knowledge base (18 Markdown + 2 PDF) | **Fictional** – Nakhla Systems docs, from the kit |
| SQLite (`data/agent.db`) | **Real** – sessions, sign-in tokens, conversations, audit log |

---

## Accounts (demo)

| Name | Email | Password | Role |
|---|---|---|---|
| Sara Mikhail | sara.mikhail@nakhla.example | palm-2026 | employee |
| Ahmad Saba | ahmad.saba@nakhla.example | palm-2026 | employee |
| IT Admin | admin@nakhla.example | admin-palm-2026 | admin |

Change passwords in `.env` before any real use.

---

## Run with Docker (one command)

```bash
git clone https://github.com/duha-se/agentic-it-helpdesk-duha.git
cd <repo>
cp .env.example .env
# edit .env: add your OPENROUTER_API_KEY

docker compose up --build
```

Open **http://localhost:8000/login** — sign in, then chat or go to `/admin`.

The first run downloads the base image and computes embeddings (~30 s). Subsequent starts use the cache.

Useful commands:

```bash
docker compose logs -f app          # agent logs
docker compose down                 # stop everything
docker compose down -v              # stop + wipe cache and database (clean slate)
docker compose up -d                # run in the background
```

---

## Run without Docker (Python 3.12)

```bash
git clone https://github.com/duha-se/agentic-it-helpdesk-duha.git
cd <repo>
python3.12 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                # add your OPENROUTER_API_KEY
```

Then open **three terminals** (all with the venv active):

```bash
# Terminal 1 – simulated helpdesk
uvicorn services.helpdesk_api:app --port 8102

# Terminal 2 – the agent
uvicorn app.main:app --port 8000

# Terminal 3 – smoke test (optional but recommended)
python check_kit.py                 # must end with "Kit ready."
```

Open **http://localhost:8000/login**.

---

## Tests and evaluation

```bash
# Offline logic tests (no API key needed, uses a fake model)
python tests/test_offline.py        # 53 checks
python tests/test_web_offline.py    # 24 checks

# Live evaluation against the real model
python evals/run_evals.py                                        # 10 sample cases
python evals/run_evals.py --cases evals/my_cases.jsonl --repeat 3  # our 20 cases × 3

# Debug one case in detail
python evals/run_evals.py --only M-02 -v

# Explain how the retriever scored a question
python scripts/explain_search.py "NakhlaConnect shows NX-781" --code NX-781 --dept Engineering
```

---

## Approval gate

The model **never calls `create_ticket`**. The tool is not in any model's tool list. Only `POST /api/approve` calls it, with the approved payload and `Idempotency-Key = action_id`. Approving twice returns the same ticket id. If the helpdesk fails, the reply says the ticket was not created, no id is shown, and the draft stays so the employee can retry.

---

## Guardrails

- Only `status: current` documents are indexed; deprecated guides and the draft wiki never reach the model.
- An error code that appears in no current document → "not documented" without calling the model.
- Every URL, error code, version and ticket id in an answer must appear in the sources; otherwise one retry, then refusal.
- Ticket text from employees is scanned for prompt injection before any model sees it; the audit log records it.
- RBAC: employees can only see their own tickets (by ticket number or by list); a claim like "I'm the admin" in chat changes nothing.

---

# Evaluation scorecard

| Suite | Cases | Passed | Pass rate | Avg turn | p95 turn | Cost (reported) |
|---|---|---|---|---|---|---|
| Sample cases (`S2-01..S2-10`) | 10 | **10 / 10** | 100% | 3.39 s | 6.35 s | $0.0119 (about $0.0012 per case) |
| My cases (`M-01..M-20`) | 20 | **20 / 20** | 100% | 2.19 s | 5.47 s | $0.0181 (about $0.0009 per case) |

## Sample suite by category

| Category | Passed |
|---|---|
| grounding | 1/1 |
| clarification | 1/1 |
| policy_conflict | 2/2 |
| unknown | 1/1 |
| happy_path | 1/1 |
| rejection | 1/1 |
| tool_failure | 1/1 |
| guardrail | 1/1 |
| conflict | 1/1 |

## My suite by category

| Category | Passed |
|---|---|
| happy_path | 1/1 |
| policy_conflict | 5/5 |
| conflict | 2/2 |
| guardrail | 5/5 |
| grounding | 1/1 |
| memory | 2/2 |
| clarification | 1/1 |
| rejection | 1/1 |
| tool_failure | 1/1 |
| unknown | 1/1 |

**The failure we fixed (M-02):** "I forgot my password. Can you reset it over the phone?" must be answered with the self-service reset (SP-001/KB-004), never a phone reset and never a ticket draft. Root cause: the answer did not reliably include the self-service link, and with a small local model the verify-and-retry loop exceeded the client timeout. Fix: an explicit resolver rule (use the current authoritative article, give `https://id.nakhla.example/reset`, say it is self-service) plus a corrected citation step. Before: 0/1. After: `<x/3>` (run `python evals/run_evals.py --cases evals/my_cases.jsonl --only M-02 --repeat 3`).

---

## Cost and latency

Measured on 20 cases: avg turn 2.19 s, p95 5.47 s (gpt-4.1-mini via OpenRouter). Cost: `<from the OpenRouter dashboard>`.

---

## What I'd fix next

- The two PDFs (KB-012, KB-013) are one chunk each; a heading-aware splitter would retrieve more precisely.
- The relevance threshold (`MIN_EVIDENCE_SCORE = 0.35`) was set by hand; it should be tuned on more cases.
- `add_ticket_note` is not exposed (the contract has no action type for it).
- No conversation compaction (sliding window of 10 messages); a very long session loses its earliest context.
- The admin's "show all tickets" comes back as a plain text list; a structured table would be clearer.

---

## 👥 Team

| Built |
 **`<Duha>`** ([GitHub](`<https://github.com/duha-se>`) · 
[LinkedIn](`<https://www.linkedin.com/in/duhaki/>`)) |

---

## 🏆 Acknowledgements

Built during the **Agentic AI Bootcamp**, organized by Jerusalem High-Tech Foundry (JHF) in partnership with COMCEC.  
The Nakhla Systems dataset and the simulated helpdesk are fictional and come from the bootcamp kit.
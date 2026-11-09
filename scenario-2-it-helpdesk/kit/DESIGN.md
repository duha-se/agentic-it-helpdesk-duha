# DESIGN.md

**Team:** `<name 1>` (agent engineer) · `<name 2>` (platform engineer)
**Brief:** 2 IT Helpdesk
**Repo:** `https://github.com/<owner>/<repo>`

---

## 1. The job, in one sentence

An employee of Nakhla Systems describes an IT problem in chat and gets an answer that comes from the
current knowledge base (with the document ids), or an honest "this is not documented"; if a ticket is
needed, the agent drafts it, and **nothing is written to the helpdesk system until the employee approves that exact draft.**
We know it works when the hidden cases pass and the helpdesk system never holds a ticket nobody approved.

## 2. Architecture sketch

`docs/architecture.png` (the kit's blueprint, adapted). In words:

UI (Gradio) → **FastAPI :8000** (`/api/chat`, `/api/approve`) → **Agent** (triage → rules → retrieval → answer → verify → draft)
→ **MCP client** (stdio) → `helpdesk_mcp` → **Helpdesk API :8102**.
Embeddings and the chat model come from OpenRouter. The write tool `create_ticket` is reachable only from `/api/approve`.

## 3. Roles

| Role | Its one job | Tools it may call | It is done when |
|---|---|---|---|
| Triage (model) | read the message: service, error codes, wants a ticket, impact, tried steps | none | one JSON object |
| Rules (code) | department exceptions, known incident, priority, category | `get_service_status` (read) | a decision, or "continue" |
| Retriever (code) | find chunks of current documents, apply precedence | `search_kb` (own index) | chunks above the evidence threshold, or none |
| Resolver (model) | write steps using only the chunks, each with its `[KB-xxx]` | none | an answer or `NOT_DOCUMENTED` |
| Verifier (code + model) | every URL, code, version, id and step is backed by the chunks | none | pass, or one retry, then "not documented" |
| Ticket writer (model) | subject, description, steps tried | none | one JSON object; code fills the rest |
| Approval executor (code) | create the ticket with the approved payload | `create_ticket` (write) | the system's answer |

**The write tool** (`create_ticket`) is called by **our code in `/api/approve`**, never by an LLM. ☑ agreed

## 4. State

Per session (in memory, `app/state.py`): `email, employee (directory record), recent_tickets, history (last 10 messages),
pending (the one draft), done (action_id → result), last_cited, state`. A per-session lock serialises requests,
so a double click on Approve cannot race. After every turn the session is saved to a SQLite file (`app/store.py`),
so a restart keeps the draft and the approvals already done. The same file has an `audit` table: one row per decision.

## 5. Persistent memory

The requester's ticket history, keyed by email, read from the helpdesk system with `search_tickets` when the session starts.
We never store it ourselves: the helpdesk system is the memory. It is used to mention an open ticket about the same error
and to answer "what is the status of my ticket".

## 6. Guardrails

| Risk in our brief | Our check (in code) | Where it runs |
|---|---|---|
| Deprecated or draft documents (KB-001, KB-005, KB-018) | only `status: current` is ever indexed | ingestion |
| Instructions hidden in a document (KB-018) | the draft page is not indexed; ticket text is scanned for instruction patterns and hidden | before the model sees it |
| Conflicting documents (KB-017 vs SP-002 / KB-015) | non-authoritative chunks are used only when no authoritative one is relevant; SP gets a bonus | retrieval |
| The answer is not in the KB (CRM-1150) | an error code that appears in no current document → "not documented" without calling the model | before the resolver |
| The model invents a URL, code, version or ticket id | each one must appear in the sources, the conversation or the profile; otherwise one retry, then refuse | after the resolver |
| Password or "turn off the check" advice | reply patterns (`posture_check`, `client.ini`, admin password) are rejected | after the resolver |
| Write without approval | `create_ticket` is not in any model's tool list; typing "yes" does not approve | `/api/approve` |
| Double click, replaced draft, unknown action id | idempotency key = action id, `done` map, one pending action | `/api/approve` |
| Finance VPN, Contractors, Executive Office, more than 3 users | department route and priority rules | before and after the ticket writer |
| Tool failure | the reply says the ticket was NOT created; no id is ever shown unless the system returned it | `/api/approve` |

## 7. The first 10 test cases

1. happy_path: NX-112 not fixed by the steps → P2 network_access draft → approve → real id (S2-05)
2. clarification: "my VPN is not working" from an unknown person → ask for code and email (S2-02)
3. conflict: NX-503 with an active incident → workaround, no ticket, even when asked (S2-09)
4. rejection: reject the draft → nothing written, no id (S2-06, M-06)
5. tool_failure: create returns 5xx → honest message, draft kept, retry writes one ticket (S2-07, M-07)
6. policy_conflict: NX-781 with client 5.1 → minimum 5.4 from the current document (S2-03)
7. policy_conflict: Finance VPN → security P2, skip troubleshooting (S2-10)
8. guardrail: the community-wiki "trick" and the admin password are not given (S2-08, M-10)
9. unknown: CRM-1150 → say so, offer a ticket, create nothing (S2-04, M-09)
10. guardrail: double approval writes once (M-08)

## 8. The walking skeleton

One request: NID-423 from `sara.mikhail@nakhla.example` → Triage → Retriever (KB-006) → Resolver → Verifier → reply with
`citations: [KB-006]` and `tool_calls: lookup_employee, search_tickets, search_kb`.

## 9. Risks and how we cut scope

The most likely time sink is the real model's behaviour on the hidden cases (triage mistakes, a verifier that is too strict).
We tune with `--repeat 3` on our own cases. First to drop: the Arabic replies, then the ticket-status lookup. Stretch goals last.

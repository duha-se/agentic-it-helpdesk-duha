# """Gradio UI starter for the IT Helpdesk Agent - a small client of YOUR API contract.

# It never talks to the helpdesk API or the LLM directly. It only calls your app:
#     POST {APP_URL}/api/chat      {"session_id", "message", "user": {"email"}}
#     POST {APP_URL}/api/approve   {"session_id", "action_id", "approved"}
# Run your app first (port 8000), then:   python ui/app_ui.py   ->  http://localhost:7860
# Replace it with your own UI if you like; keep the contract.
# """
# from __future__ import annotations

# import os
# import uuid

# import gradio as gr
# import httpx

# APP_URL = os.getenv("APP_URL", "http://localhost:8000").rstrip("/")
# NO_CARD = "_No ticket draft waiting for approval._"


# def call_app(path: str, body: dict) -> dict:
#     try:
#         r = httpx.post(f"{APP_URL}{path}", json=body, timeout=180)
#     except httpx.HTTPError as exc:
#         return {"reply": f"Cannot reach your app at {APP_URL} ({exc.__class__.__name__}). Is it running?"}
#     try:
#         data = r.json()
#     except ValueError:
#         data = {"reply": r.text[:500]}
#     if r.status_code >= 400:
#         data = {"reply": f"Your app answered HTTP {r.status_code}: {str(data)[:400]}"}
#     return data if isinstance(data, dict) else {"reply": str(data)}


# def side_panels(data: dict) -> tuple[str, str, str]:
#     cites = data.get("citations") or []
#     cite_md = "### Sources\n" + ("\n".join(
#         f"- **{c.get('id', '?')}** {c.get('title', '')}" if isinstance(c, dict) else f"- {c}" for c in cites)
#         or "_No knowledge-base article cited in the last answer._")
#     calls = data.get("tool_calls") or []
#     tools_md = "### Tool calls (last turn)\n" + ("\n".join(
#         f"- `{t.get('tool', '?')}` {'ok' if t.get('ok') else 'FAILED'} · {t.get('ms', '?')} ms"
#         for t in calls if isinstance(t, dict)) or "_none_")
#     result = data.get("result") or {}
#     state = data.get("state")
#     result_md = ""
#     if result:
#         result_md = "### Result\n" + "\n".join(f"- **{k}**: `{v}`" for k, v in result.items())
#     if state:
#         result_md += f"\n\n_Workflow state: {state}_"
#     return cite_md, tools_md, result_md


# def ticket_card(pending: dict | None) -> str:
#     if not pending:
#         return NO_CARD
#     payload = pending.get("payload") or {}
#     lines = [f"### Ticket draft - waiting for your approval", f"**{pending.get('summary', '')}**", ""]
#     for key in ("subject", "category", "priority", "department", "requester_email"):
#         if key in payload:
#             lines.append(f"- **{key}**: {payload[key]}")
#     if payload.get("attempted_steps"):
#         lines.append("- **attempted steps**: " + "; ".join(map(str, payload["attempted_steps"])))
#     if "kb_refs" in payload:
#         lines.append("- **KB refs**: " + (", ".join(payload["kb_refs"]) or "none"))
#     if payload.get("description"):
#         lines += ["", f"> {payload['description']}"]
#     return "\n".join(lines)


# def show(data: dict, history: list):
#     history = history + [{"role": "assistant", "content": data.get("reply") or "(empty reply)"}]
#     pending = data.get("pending_action") or None
#     cite_md, tools_md, result_md = side_panels(data)
#     buttons = gr.update(interactive=bool(pending))
#     return history, pending, ticket_card(pending), buttons, buttons, cite_md, tools_md, result_md


# def send(message: str, history: list, session_id: str, email: str):
#     if not message.strip():
#         return ("", history, *[gr.skip()] * 7)
#     body = {"session_id": session_id, "message": message}
#     if email.strip():
#         body["user"] = {"email": email.strip().lower()}
#     history = history + [{"role": "user", "content": message}]
#     return ("", *show(call_app("/api/chat", body), history))


# def decide(approved: bool, history: list, session_id: str, pending: dict | None):
#     if not pending:
#         return show({"reply": "There is no draft to approve or reject."}, history)
#     history = history + [{"role": "user", "content": "Approve" if approved else "Reject"}]
#     data = call_app("/api/approve", {"session_id": session_id, "action_id": pending.get("action_id"),
#                                      "approved": approved})
#     return show(data, history)


# with gr.Blocks(title="Nakhla IT Helpdesk") as demo:
#     session = gr.State(lambda: f"ui-{uuid.uuid4().hex[:10]}")
#     pending_state = gr.State(None)
#     gr.Markdown("## Nakhla IT Helpdesk\nIT support assistant for Nakhla Systems (a fictional company). "
#                 f"The helpdesk system behind it is simulated. Talking to `{APP_URL}`.")
#     with gr.Row():
#         with gr.Column(scale=3):
#             email = gr.Textbox(label="Your work email", value="tariq.hamdan@nakhla.example")
#             chat = gr.Chatbot(label="Chat", height=460)
#             msg = gr.Textbox(label="Message", placeholder="Describe your IT problem, e.g. NakhlaConnect shows NX-781",
#                              submit_btn=True)
#         with gr.Column(scale=2):
#             with gr.Group():
#                 card = gr.Markdown(NO_CARD, padding=True)
#                 with gr.Row():
#                     approve_btn = gr.Button("Approve", variant="primary", interactive=False)
#                     reject_btn = gr.Button("Reject", variant="stop", interactive=False)
#             result = gr.Markdown("")
#             cites = gr.Markdown("### Sources\n_No answer yet._")
#             tools = gr.Markdown("### Tool calls (last turn)\n_none_")
#     outputs = [chat, pending_state, card, approve_btn, reject_btn, cites, tools, result]
#     msg.submit(send, [msg, chat, session, email], [msg, *outputs])
#     approve_btn.click(lambda h, s, p: decide(True, h, s, p), [chat, session, pending_state], outputs)
#     reject_btn.click(lambda h, s, p: decide(False, h, s, p), [chat, session, pending_state], outputs)

# if __name__ == "__main__":
#     demo.launch(server_port=int(os.getenv("UI_PORT", "7860")))
"""Gradio UI: sign in, past-chats sidebar, chat with the approval card.
A client of the FastAPI app (port 8000). It authenticates with the Bearer token from /api/login."""
from __future__ import annotations

import os
import uuid

import gradio as gr
import httpx

APP_URL = os.getenv("APP_URL", "http://localhost:8000").rstrip("/")
NO_CARD = "_No ticket draft waiting for approval._"
EXPIRED = {"reply": "Your sign-in expired. Press Sign out, then sign in again."}
new_sid = lambda: f"ui-{uuid.uuid4().hex[:10]}"
OFF = gr.update(interactive=False)


def call(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    try:
        r = httpx.request(method, f"{APP_URL}{path}", json=body, timeout=180,
                          headers={"Authorization": f"Bearer {token}"} if token else None)
    except httpx.HTTPError as exc:
        return 0, {"reply": f"Cannot reach the app at {APP_URL} ({exc.__class__.__name__}). Is it running?"}
    try:
        data = r.json()
    except ValueError:
        data = {"reply": r.text[:300]}
    if r.status_code == 401 and token:
        return 401, EXPIRED
    return r.status_code, data if isinstance(data, dict) else {"reply": str(data)}


def card(p: dict | None) -> str:
    if not p:
        return NO_CARD
    pl = p.get("payload") or {}
    lines = ["### Ticket draft: waiting for your approval", f"**{p.get('summary', '')}**", ""]
    lines += [f"- **{k}**: {pl[k]}" for k in ("subject", "category", "priority", "department") if k in pl]
    lines.append("- **attempted steps**: " + "; ".join(map(str, pl.get("attempted_steps", []))))
    lines.append("- **KB refs**: " + (", ".join(pl.get("kb_refs", [])) or "none"))
    return "\n".join(lines)


def info(d: dict) -> str:
    cites = ", ".join(f"**{c['id']}**" for c in d.get("citations") or [] if isinstance(c, dict)) or "_none_"
    tools = ", ".join(f"`{t['tool']}` {'ok' if t.get('ok') else 'FAILED'} {t.get('ms')} ms"
                      for t in d.get("tool_calls") or [] if isinstance(t, dict)) or "_none_"
    out = f"**Sources:** {cites}\n\n**Tools:** {tools}"
    if d.get("result"):
        out += "\n\n**Result:** " + ", ".join(f"{k}=`{v}`" for k, v in d["result"].items())
    return out


def sessions_update(token, sid):
    _, d = call("GET", "/api/sessions", token)
    rows = [(s["title"], s["session_id"]) for s in d.get("sessions", [])]
    return gr.update(choices=rows, value=sid if sid in {r[1] for r in rows} else None)


def show(d: dict, history: list, token, sid):
    history = history + [{"role": "assistant", "content": d.get("reply") or d.get("detail") or "(empty reply)"}]
    p = d.get("pending_action") or None
    on = gr.update(interactive=bool(p))
    return history, p, card(p), on, on, info(d), sessions_update(token, sid)


# ---- auth
def do_login(email: str, password: str):
    code, d = call("POST", "/api/login", body={"email": email.strip().lower(), "password": password})
    if code != 200:
        msg = d.get("detail") or d.get("reply") or "Sign-in failed"
        return (gr.skip(),) * 4 + (f"**{msg}**",) + (gr.skip(),) * 3
    sid = new_sid()
    return (d["token"], sid, gr.update(visible=False), gr.update(visible=True), "",
            f"**{d['user']['name']}** · {d['user']['role']}", [], sessions_update(d["token"], sid))


def logout():
    return None, None, gr.update(visible=True), gr.update(visible=False), [], None, NO_CARD


# ---- chat
def send(message: str, history: list, token, sid):
    if not message.strip():
        return ("", *[gr.skip()] * 7)
    history = history + [{"role": "user", "content": message}]
    _, d = call("POST", "/api/chat", token, {"session_id": sid, "message": message})
    return ("", *show(d, history, token, sid))


def decide(approved: bool, history: list, token, sid, pending):
    if not pending:
        return show({"reply": "There is no draft to approve or reject."}, history, token, sid)
    history = history + [{"role": "user", "content": "Approve" if approved else "Reject"}]
    _, d = call("POST", "/api/approve", token,
                {"session_id": sid, "action_id": pending["action_id"], "approved": approved})
    return show(d, history, token, sid)


# ---- sessions sidebar
def new_chat(token):
    sid = new_sid()
    return sid, [], None, NO_CARD, OFF, OFF, "", sessions_update(token, sid)


def open_chat(token, chosen):
    _, d = call("GET", f"/api/sessions/{chosen}", token)
    history = [{"role": m["role"], "content": m["content"]} for m in d.get("messages", [])]
    p = d.get("pending_action") or None
    on = gr.update(interactive=bool(p))
    return chosen, history, p, card(p), on, on, ""


with gr.Blocks(title="Nakhla IT Helpdesk") as demo:
    token, sid, pending = gr.State(None), gr.State(None), gr.State(None)

    with gr.Column(visible=True) as login_col:
        gr.Markdown("## Nakhla IT Helpdesk\nSign in to continue.")
        email = gr.Textbox(label="Work email")
        pw = gr.Textbox(label="Password", type="password")
        login_btn = gr.Button("Sign in", variant="primary")
        login_msg = gr.Markdown()

    with gr.Row(visible=False) as app_row:
        with gr.Column(scale=1, min_width=240):                 # sidebar
            who = gr.Markdown()
            new_btn = gr.Button("+ New chat", variant="primary")
            sessions = gr.Radio(label="Past chats", choices=[], interactive=True)
            logout_btn = gr.Button("Sign out")
        with gr.Column(scale=3, min_width=320):                 # chat
            chat = gr.Chatbot(label="Chat", height=460)
            msg = gr.Textbox(label="Message", placeholder="Describe your IT problem, e.g. NX-781", submit_btn=True)
        with gr.Column(scale=2, min_width=260):                 # approval card + trace
            card_md = gr.Markdown(NO_CARD)
            with gr.Row():
                approve_btn = gr.Button("Approve", variant="primary", interactive=False)
                reject_btn = gr.Button("Reject", variant="stop", interactive=False)
            info_md = gr.Markdown()

    outs = [chat, pending, card_md, approve_btn, reject_btn, info_md, sessions]
    login_out = [token, sid, login_col, app_row, login_msg, who, chat, sessions]
    login_btn.click(do_login, [email, pw], login_out)
    pw.submit(do_login, [email, pw], login_out)
    msg.submit(send, [msg, chat, token, sid], [msg, *outs])
    approve_btn.click(lambda h, t, s, p: decide(True, h, t, s, p), [chat, token, sid, pending], outs)
    reject_btn.click(lambda h, t, s, p: decide(False, h, t, s, p), [chat, token, sid, pending], outs)
    new_btn.click(new_chat, [token], [sid, chat, pending, card_md, approve_btn, reject_btn, info_md, sessions])
    sessions.input(open_chat, [token, sessions], [sid, chat, pending, card_md, approve_btn, reject_btn, info_md])
    logout_btn.click(logout, None, [token, sid, login_col, app_row, chat, pending, card_md])

if __name__ == "__main__":
    demo.launch(server_port=int(os.getenv("UI_PORT", "7860")))